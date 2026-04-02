"""Learner reflection: structured JSON for blackboard + replan decision."""

from __future__ import annotations

import json
from typing import Any

from app.modules.workflow.state import AgentState

LEARNER_REFLECTION_SYSTEM = """You are the **Learner** module: short self-reflection after one agent turn.

## Inputs (in user message)
You receive a compact JSON payload with the user goal, outcome, tool trace, plan step titles, replan limits, optional blackboard tail, etc.

## Task
1. Summarize reusable lessons, pitfalls, and corrections (natural language) for the shared **blackboard** so the next Planner can read them.
2. Decide if the user goal is **likely satisfied** and no plan change is needed, or if planning should run again (`request_replan`).

## Output
Emit **only one JSON object**. No markdown fences, no extra prose.

## Shape
{"reflection":"…","request_replan":false,"rationale":"…"} — use JSON booleans for `request_replan`; `reflection` and `rationale` in Simplified Chinese.

## Constraints
- Make `reflection` specific and actionable; avoid empty generic phrases.
- If this turn’s `outcome` is **failure** (task already terminated), `request_replan` must be **false**.
- If the request was simple and this turn delivered a clear final success, `request_replan` should be **false**.
- If the context states **remaining replan cycles = 0**, `request_replan` must be **false**."""


def build_learner_reflection_user_payload(state: AgentState) -> str:
    """Build compact JSON for the learner user message."""
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
