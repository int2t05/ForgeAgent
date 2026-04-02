"""单计划步内的 ReAct：模型轮次输出工具调用或终答；已发生过工具调用时，终答须经独立审核与步骤及观测对齐。

供 Actor 按步调用；与 ``tool_runner`` 事件语义一致。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.modules.execution.tool_runner import run_single_tool_with_retry
from app.modules.prompts.step_react import build_step_react_system_prompt
from app.modules.prompts.step_react_verify import (
    STEP_REACT_FINAL_ANSWER_VERIFY_SYSTEM,
    build_step_react_final_answer_verify_user_content,
)
from app.schemas.tools import ToolItem
from app.shared.llm_json_parse import collect_json_candidates, try_parse_single_candidate
from app.shared.react_llm_output import (
    parse_react_round_json,
    pick_action_input,
    pick_final_answer,
    pick_react_tool_name,
)

logger = logging.getLogger(__name__)

_PRIOR_TAIL = 4


def _tail_prior(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """截取步前工具轨迹尾部，控制首轮上下文长度。"""
    if len(trace) <= _PRIOR_TAIL:
        return trace
    return trace[-_PRIOR_TAIL:]


def _msg_text(msg: Any) -> str:
    """从 Chat 消息对象取出纯文本 ``content``。"""
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    return str(content or "")


def _observation_block(tool_name: str, last_exec: dict[str, Any]) -> str:
    """将单次工具执行结果序列化为 Observation 载荷字符串。"""
    payload = {
        "tool": tool_name,
        "ok": last_exec.get("ok"),
        "data": last_exec.get("data"),
        "error": last_exec.get("error"),
    }
    return json.dumps(payload, ensure_ascii=False)


async def _verify_final_answer_against_step(
    chat: Any,
    settings: Settings,
    *,
    step: dict[str, Any],
    user_message: str,
    call_results: list[dict[str, Any]],
    proposed_final: str,
) -> tuple[bool, str]:
    """调用辅助模型判断候选终答与工具结果、步骤目标是否一致，返回 (是否通过, 简述理由)。"""
    sys = SystemMessage(content=STEP_REACT_FINAL_ANSWER_VERIFY_SYSTEM)
    human = HumanMessage(
        content=build_step_react_final_answer_verify_user_content(
            user_message=user_message,
            step=step,
            call_results=call_results,
            proposed_final=proposed_final,
        ),
    )
    try:
        msg = await ainvoke_with_retry(chat, [sys, human], settings)
    except Exception:
        logger.exception("verify final_answer alignment failed")
        return False, "审核调用失败"
    text = _msg_text(msg)
    for cand in collect_json_candidates(text):
        d = try_parse_single_candidate(cand)
        if not d or not isinstance(d, dict):
            continue
        aligned = d.get("aligned")
        ok_align: bool | None = None
        if isinstance(aligned, bool):
            ok_align = aligned
        elif isinstance(aligned, str) and aligned.strip():
            ok_align = aligned.strip().lower() in ("true", "1", "yes")
        if ok_align is not None:
            reason = d.get("brief_reason")
            br = str(reason).strip() if reason is not None else ""
            return ok_align, br
    return False, "无法解析审核结果"


async def run_step_react_loop(
    task_id: str,
    step_id: Any,
    step: dict[str, Any],
    *,
    user_message: str,
    prior_tool_trace: list[dict[str, Any]],
    tools: list[ToolItem],
    settings: Settings | None = None,
    max_tool_tries: int,
    max_rounds: int,
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """在单步上限内运行 ReAct；无工具调用时可直接收终答，有工具时终答需审核通过。"""
    s = settings or get_settings()
    # 1. 无可执行工具或模型未配置
    if not tools or not is_llm_configured(s):
        return False, [], None

    # 2. 首轮消息（系统提示 + 用户任务 / 步骤 / 历史轨迹摘要）
    chat = build_chat_model(s)
    sys_text = build_step_react_system_prompt(tools)
    initial = (
        f"用户任务：{user_message}\n"
        f"当前步骤（仅目标）：{json.dumps(step, ensure_ascii=False)}\n"
        f"此前步骤轨迹摘要：{json.dumps(_tail_prior(prior_tool_trace), ensure_ascii=False)}\n"
        "输出本轮 JSON（thought + action/action_input 或 final_answer）。"
    )
    messages: list[BaseMessage] = [
        SystemMessage(content=sys_text),
        HumanMessage(content=initial),
    ]

    call_results: list[dict[str, Any]] = []
    step_final: str | None = None
    rounds = max(1, int(max_rounds))
    round_num = 0

    # 3. 步内循环：模型轮次 → 终答（或核准）或工具 → Observation
    while True:
        if round_num >= rounds:
            break
        round_num += 1
        # 3.1 本步单轮：调用模型并解析 ReAct JSON
        try:
            msg = await ainvoke_with_retry(chat, messages, s)
        except Exception:
            logger.exception("step react LLM invoke failed task=%s step=%s", task_id, step_id)
            break

        text = _msg_text(msg)
        messages.append(AIMessage(content=text))
        data = parse_react_round_json(text)
        if not data:
            logger.warning("step react parse failed task=%s step=%s", task_id, step_id)
            break

        fa = pick_final_answer(data)
        # 3.2 终答分支：无前置工具则直接采纳；否则走核准
        if fa:
            if not call_results:
                step_final = fa
                break
            ok_align, reason = await _verify_final_answer_against_step(
                chat,
                s,
                step=step,
                user_message=user_message,
                call_results=call_results,
                proposed_final=fa,
            )
            if ok_align:
                step_final = fa
                break
            feedback = reason or "与步骤目标或工具观测不一致"
            messages.append(
                HumanMessage(
                    content=(
                        "审核未通过：候选 final_answer 未通过校验。"
                        f"{feedback}。\n"
                        "请结合已有 Observation，继续调用工具或修订推理，再输出 JSON（action 或 final_answer）。"
                    )
                )
            )
            continue

        # 3.3 工具分支：解析可执行工具名；缺失则中止本步循环
        tn = pick_react_tool_name(data)
        if not tn:
            break

        # 3.4 执行单次工具（含重试）并将 Observation 追加到对话
        args = pick_action_input(data)
        final_ok, last_exec, attempt_rows = await run_single_tool_with_retry(
            task_id,
            step_id,
            tn,
            args,
            max_tool_tries,
        )
        call_results.append(
            {
                "tool": tn,
                "args": args,
                "ok": final_ok,
                "data": last_exec.get("data"),
                "error": last_exec.get("error"),
                "attempts": attempt_rows,
            }
        )
        messages.append(
            HumanMessage(
                content="Observation:\n" + _observation_block(tn, last_exec),
            )
        )

    # 4. 本步整体成功与否：存在终答且历次工具均成功（无调用则视为真）
    all_tool_ok = all(c.get("ok") for c in call_results) if call_results else True
    overall = bool(step_final) and all_tool_ok
    return overall, call_results, step_final
