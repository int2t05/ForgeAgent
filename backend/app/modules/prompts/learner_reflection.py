"""Learner 反思阶段：口头反馈式 Reflection（零权重训练），仅输出结构化 JSON。"""

from __future__ import annotations

import json
from typing import Any

from app.modules.workflow.state import AgentState


LEARNER_REFLECTION_SYSTEM = """你是 Agent 的 Learner（学习与反思）模块。根据本回合的执行材料做简短的自我反思：
- 归纳可复用的经验、踩坑与纠错建议（自然语言，写入团队共享黑板，供下一轮 Planner 阅读）；
- 判断在用户目标是否很可能已充分达成、且无需再改计划；若仍明显不足、工具结果矛盾、或遗漏关键步骤，则应请求再回到 Planner 重新规划（request_replan=true）。

务必只输出一个 JSON 对象，不要 markdown 代码块、不要额外说明。

【输出 JSON 形状】
{"reflection":"多句中文反思与可执行提示，可含分条但不要 markdown","request_replan":true或false,"rationale":"一句话说明为何需要或不需要再规划"}

【约束】
- reflection 要具体，便于下一轮 Planner 据此改步骤；避免空泛套话。
- 若本回合 outcome 为失败（任务已终止），request_replan 必须为 false。
- 若用户需求简单且本回合已成功交付清晰最终答案，request_replan 应为 false。
- 当上下文中已标明「剩余重规划次数为 0」时，request_replan 必须为 false。"""


def build_learner_reflection_user_payload(state: AgentState) -> str:
    """组装供 Learner 反思模型阅读的结构化上下文（紧凑 JSON 字符串）。"""
    trace: list[dict[str, Any]] = list(state.get("actor_tool_trace") or [])
    plan_steps = state.get("plan_steps") or []
    max_r = int(state.get("max_replan_attempts") or 0)
    replan_count = int(state.get("replan_count") or 0)
    remaining = max(0, max_r - replan_count)

    body: dict[str, Any] = {
        "user_goal": (state.get("user_message") or "").strip(),
        "outcome": state.get("outcome"),
        "error_message": state.get("error_message"),
        "actor_replan_flag": bool(state.get("replan_requested")),
        "replan_count": replan_count,
        "max_replan_attempts": max_r,
        "remaining_replan_cycles": remaining,
        "plan_steps_titles": [str(s.get("title") or "") for s in plan_steps],
        "tool_trace_summary": trace,
    }
    summary = state.get("summary")
    if isinstance(summary, str) and summary.strip():
        s = summary.strip()
        body["actor_answer_excerpt"] = s[:4000] + ("…" if len(s) > 4000 else "")

    tail = (state.get("blackboard_notes") or [])[-5:]
    if tail:
        body["prior_blackboard_tail"] = tail

    return json.dumps(body, ensure_ascii=False)
