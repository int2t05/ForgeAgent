"""执行域：ReAct（推理-行动-观察）路径下的图节点实现。

与 plan_execute 分支并列；工具调用经统一注册表，事件形态与既有 execution/tool 事件对齐。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.modules.memory.session_context import SessionLLMContextManager
from app.modules.execution.nodes import _StreamDeltaBatcher, _TK_C, _TK_O
from app.modules.planning.llm import _tools_catalog_for_prompt, parse_llm_json_object
from app.modules.tools.registry import tool_registry
from app.modules.workflow.state import AgentState
from app.repositories import event_repository

logger = logging.getLogger(__name__)

_REACT_SHAPE_NUDGE = (
    "系统提示：你上一段输出不符合约定。请只输出一个 JSON 对象（不要 markdown 围栏），"
    "且在以下两种形态中【严格二选一】：\n"
    '1) 还要调工具：{"thought":"…","action":"工具name","action_input":{…}}\n'
    '2) 已可答用户：{"thought":"…","final_answer":"…"}\n'
    "注意：final_answer / action 至少其一为非空；勿用空字符串凑字段；"
    "若可作答请直接给出 final_answer。"
)


def _coerce_final_answer(value: Any) -> str | None:
    """确保 final_answer 为非空字符串。"""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (dict, list)):
        try:
            s = json.dumps(value, ensure_ascii=False).strip()
            return s if s else None
        except (TypeError, ValueError):
            return None
    s = str(value).strip()
    return s if s else None


def _pick_final_answer(data: dict[str, Any]) -> str | None:
    """兼容模型常用别名：answer、response、text/message 等；tool 误写为 action 由 _pick_action 处理。"""
    for key in (
        "final_answer",
        "answer",
        "response",
        "reply",
        "output",
        "content",
        "text",
        "message",
        "echoed"
    ):
        s = _coerce_final_answer(data.get(key))
        if s:
            return s
    return None


def _pick_action(data: dict[str, Any]) -> str | None:
    """兼容模型常用别名：action、tool 误写为 tool_name、function_name 等由 _normalize_steps 处理。"""
    for key in ("action", "tool", "tool_name", "function_name", "function"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _pick_thought(data: dict[str, Any]) -> str | None:
    """解析推理文本；兼容模型常用别名字段（与 final_answer / action 的别名策略一致）。"""
    for key in (
        "thought",
        "reasoning",
        "thinking",
        "think",
        "analysis",
        "rationale",
        "reflection",
        "反思",
    ):
        v = data.get(key)
        if isinstance(v, str):
            s = v.strip()
            if s:
                return s
    return None


def _pick_action_input(data: dict[str, Any]) -> dict[str, Any]:
    """从模型输出中解析工具入参，兼容 action_input、arguments 等别名。"""
    for key in (
        "action_input",
        "tool_input",
        "arguments",
        "args",
        "parameters",
        "params",
    ):
        v = data.get(key)
        if isinstance(v, dict):
            return dict(v)
        if isinstance(v, str) and v.strip():
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return dict(parsed)
    inp = data.get("input")
    if isinstance(inp, dict):
        return dict(inp)
    if isinstance(inp, str) and inp.strip():
        try:
            parsed = json.loads(inp)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(parsed, dict):
                return dict(parsed)
    return {}


def _react_system_prompt(catalog_block: str) -> str:
    """拼装 ReAct 轮次的系统提示（JSON 输出契约与工具目录块）。"""
    return (
        "你是 ReAct 智能体（Reason + Act）：每一步只输出一个 JSON 对象，不要 markdown、不要注释。\n\n"
        "【两种合法输出】恰含其一：\n"
        '1) 需调用工具：{"thought":"简要中文推理","action":"工具 name","action_input":{...}}\n'
        '2) 可回答用户：{"thought":"简要中文推理","final_answer":"给用户的完整中文答复"}\n\n'
        "action 必须是【工具目录】中某一工具的 name（区分大小写）；"
        "action_input 的键须符合该工具的 parameters（JSON Schema）。\n"
        "（等价别名：thought 可用 reasoning/thinking 等；final_answer 可用 answer、text、message；"
        "action 可用 tool；action_input 可用 args。）\n\n"
        "【工具目录】\n"
        f"{catalog_block}"
    )


def _append_observation(
    messages: list[BaseMessage], observation: dict[str, Any]
) -> None:
    """向消息列表追加一条 HumanMessage 形式的 Observation。"""
    text = json.dumps(observation, ensure_ascii=False)
    messages.append(HumanMessage(content=f"Observation:\n{text}"))


async def react_executor_node(state: AgentState) -> dict:
    """LangGraph 节点：在 ReAct 路径下执行多轮推理与工具调用直至终态。"""
    # 1. 读取任务标识、会话与用户输入、迭代上限
    task_id = state["task_id"]  # type: ignore
    session_id = state.get("session_id") or ""
    user_message = state.get("user_message") or ""
    settings = get_settings()
    max_iter = max(1, int(getattr(settings, "max_react_iterations", 8) or 8))
    # 2. 加载会话最近消息窗口
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    async with AsyncSessionLocal() as db:
        chat_messages = await mgr.load_chat_messages(
            db,
            session_id=session_id,
            fallback_user_content=user_message,
        )

    # 3. 拉取工具目录与允许的 tool 名称集合
    tools = tool_registry.list_tools_public().tools
    catalog = _tools_catalog_for_prompt(tools)
    tool_names = frozenset(t.name for t in tools)

    # 4. 未配置 LLM 时的确定性回退
    if not is_llm_configured(settings):
        summary = "任务已完成（LangGraph 最小闭环）。配置 API Key 后可使用 ReAct 与工具循环。\n"
        return {"outcome": "success", "summary": summary, "replan_requested": False}

    # 5. 初始化模型消息链与客户端
    sys = _react_system_prompt(catalog)
    messages: list[BaseMessage] = [SystemMessage(content=sys), *chat_messages]
    chat = build_chat_model(settings)
    tool_trace: list[dict[str, Any]] = []
    # 6. ReAct 主循环：每轮推理后分支至终答、工具调用或输出纠错
    for round_idx in range(1, max_iter + 1):
        # 调用模型并追加助手原文
        try:
            reply = await chat.ainvoke(messages)
        except Exception:
            logger.exception("react LLM invoke failed at round %s", round_idx)
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "error",
                        json.dumps(
                            {"message": f"ReAct 第 {round_idx} 轮模型调用失败"},
                            ensure_ascii=False,
                        ),
                    )
            return {
                "outcome": "failed",
                "error_message": "ReAct 模型调用失败",
                "summary": None,
                "replan_requested": False,
            }

        raw_content = getattr(reply, "content", None)
        text = raw_content if isinstance(raw_content, str) else str(raw_content or "")
        messages.append(AIMessage(content=text))
        # 解析单轮 JSON；失败则 step_start 与 parse_error 后返回失败
        data = parse_llm_json_object(text)
        round_title = f"ReAct 第 {round_idx} 轮"
        round_sid = f"react-{round_idx}"

        async def _emit_step_start(extra: dict[str, Any] | None = None) -> None:
            payload: dict[str, Any] = {
                "step_id": round_sid,
                "title": round_title,
            }
            if extra:
                payload.update(extra)
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_start",
                        json.dumps(payload, ensure_ascii=False),
                    )

        if not data:
            await _emit_step_start()
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_end",
                        json.dumps(
                            {"step_id": round_sid, "status": "parse_error"},
                            ensure_ascii=False,
                        ),
                    )
            return {
                "outcome": "failed",
                "error_message": "ReAct 输出无法解析为 JSON",
                "summary": None,
                "replan_requested": False,
            }

        thought_str = _pick_thought(data)
        await _emit_step_start({"thought": thought_str} if thought_str else None)

        fa = _pick_final_answer(data)
        action = _pick_action(data)

        # 存在 final_answer：落库 step_end、流式写入总结并成功返回
        if fa:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_end",
                        json.dumps(
                            {"step_id": round_sid, "status": "final_answer"},
                            ensure_ascii=False,
                        ),
                    )
            tool_trace.append(
                {
                    "round": round_idx,
                    "thought": thought_str,
                    "final_answer": fa,
                }
            )
            full_t = thought_str or ""
            full_a = fa
            # 流式分批写入 llm_stream_delta（与 plan_execute 执行节点对齐）
            batcher = _StreamDeltaBatcher(task_id, round_sid)
            try:
                step = max(30, len(full_a) // 12)
                if full_t:
                    for i in range(0, len(full_t), step):
                        await batcher.add("thinking", full_t[i : i + step])
                for i in range(0, len(full_a), step):
                    await batcher.add("answer", full_a[i : i + step])
            finally:
                await batcher.flush()
            if full_t.strip():
                summary = f"{_TK_O}{full_t.strip()}{_TK_C}\n\n{full_a}"
            else:
                summary = full_a
            return {
                "outcome": "success",
                "summary": summary,
                "replan_requested": False,
            }

        # 存在 action：校验工具名、落库 tool 事件、执行并拼接 Observation
        if action:
            name = action
            if name not in tool_names:
                err = f"ReAct 声明了未注册工具: {name}"
                async with AsyncSessionLocal() as db:
                    async with db.begin():
                        await event_repository.append_event(
                            db,
                            task_id,
                            "execution",
                            "error",
                            json.dumps({"message": err}, ensure_ascii=False),
                        )
                        await event_repository.append_event(
                            db,
                            task_id,
                            "execution",
                            "step_end",
                            json.dumps(
                                {"step_id": round_sid, "status": "unknown_tool"},
                                ensure_ascii=False,
                            ),
                        )
                return {
                    "outcome": "failed",
                    "error_message": err,
                    "summary": None,
                    "replan_requested": False,
                }
            args = _pick_action_input(data)

            # 与对话区对齐：在 tool_call 落库前流式写入本回合「思考」「行动」，便于 SSE 只展示最新一轮
            full_t = thought_str or ""
            action_text = (
                f"调用工具：{name}\n{json.dumps(args, ensure_ascii=False, indent=2)}"
            )
            stream_batcher = _StreamDeltaBatcher(task_id, round_sid)
            try:
                if full_t:
                    t_step = max(30, len(full_t) // 12)
                    for i in range(0, len(full_t), t_step):
                        await stream_batcher.add("thinking", full_t[i : i + t_step])
                a_step = max(36, len(action_text) // 14)
                for i in range(0, len(action_text), a_step):
                    await stream_batcher.add("action", action_text[i : i + a_step])
            finally:
                await stream_batcher.flush()

            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "tool",
                        "tool_call",
                        json.dumps(
                            {
                                "step_id": round_sid,
                                "tool": name,
                                "args": args,
                            },
                            ensure_ascii=False,
                        ),
                    )
            exec_out = await tool_registry.execute(name, args)
            ok = bool(exec_out.get("ok"))
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "tool",
                        "tool_result",
                        json.dumps(
                            {
                                "step_id": round_sid,
                                "tool": name,
                                "ok": ok,
                                "result": exec_out.get("data"),
                                "error": exec_out.get("error"),
                            },
                            ensure_ascii=False,
                        ),
                    )
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_end",
                        json.dumps(
                            {
                                "step_id": round_sid,
                                "status": "failed" if not ok else "ok",
                            },
                            ensure_ascii=False,
                        ),
                    )
            tool_trace.append(
                {
                    "round": round_idx,
                    "thought": thought_str,
                    "tool": name,
                    "args": args,
                    "ok": ok,
                    "data": exec_out.get("data"),
                    "error": exec_out.get("error"),
                }
            )
            _append_observation(
                messages,
                {
                    "tool": name,
                    "ok": ok,
                    "result": exec_out.get("data"),
                    "error": exec_out.get("error"),
                },
            )
            if not ok:
                # 工具失败：写 error 事件并以 failed 终态返回
                err = str(exec_out.get("error") or "工具执行失败")
                async with AsyncSessionLocal() as db:
                    async with db.begin():
                        await event_repository.append_event(
                            db,
                            task_id,
                            "execution",
                            "error",
                            json.dumps({"message": err}, ensure_ascii=False),
                        )
                return {
                    "outcome": "failed",
                    "error_message": err,
                    "summary": None,
                    "replan_requested": False,
                }
            # 工具成功：进入下一轮 ReAct
            continue

        # 既无终答也无有效 action：落库无效形状；达上限则失败，否则注入纠错提示后继续
        logger.warning(
            "react round %s: missing final_answer and action after alias normalize; keys=%s",
            round_idx,
            list(data.keys()),
        )
        excerpt = text.strip()
        if len(excerpt) > 1200:
            excerpt = excerpt[:1200] + "…"
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await event_repository.append_event(
                    db,
                    task_id,
                    "execution",
                    "step_end",
                    json.dumps(
                        {
                            "step_id": round_sid,
                            "status": "invalid_react_shape",
                            "raw_excerpt": excerpt,
                        },
                        ensure_ascii=False,
                    ),
                )
        if round_idx >= max_iter:
            return {
                "outcome": "failed",
                "error_message": "ReAct 输出缺少 final_answer 与有效 action（已达最大轮次）",
                "summary": None,
                "replan_requested": False,
            }
        messages.append(HumanMessage(content=_REACT_SHAPE_NUDGE))
        continue

    # 7. 已耗尽迭代轮次仍未终态：落库 error 并以 failed 返回
    err = f"ReAct 超过最大迭代次数（{max_iter}）"
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "execution",
                "error",
                json.dumps({"message": err}, ensure_ascii=False),
            )
    return {
        "outcome": "failed",
        "error_message": err,
        "summary": None,
        "replan_requested": False,
    }
