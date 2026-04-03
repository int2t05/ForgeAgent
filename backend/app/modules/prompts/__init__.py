"""Unified prompts for Plan-Act-Learn triangle.

All prompts are in English for consistency and efficiency.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.schemas.tools import ToolItem


def _skill_catalog_lines(paths: list[str]) -> str:
    if not paths:
        return "*(none)*"
    return "\n".join(f"- `{Path(p).name}` — `{p}`" for p in paths)


def tools_catalog_for_prompt(tools: Sequence[ToolItem]) -> str:
    """Serialize tool registry for LLM consumption."""
    catalog = [
        {
            "name": t.name,
            "description": t.description,
            "source": t.source,
            **({"read_only": t.read_only} if t.read_only is not None else {}),
            **({"parameters": t.parameters} if t.parameters else {}),
        }
        for t in tools
    ]
    return json.dumps(catalog, ensure_ascii=False, indent=2)


# =====================================================================================================================
# PLAN MODULE
# =====================================================================================================================

PLAN_SKILL_SELECTOR_SYSTEM = """You are a skill advisor. Select relevant skill directories for the user's goal.

## Output
Only one JSON object: {{"skill_imports": ["label1", "label2"]}}
- Empty if no skill is relevant: {{"skill_imports": []}}
- No markdown fences, no extra text.

## Available Skills
{catalog}

## Rule
Select only skills with concrete guidance directly applicable to the goal."""


PLAN_PLANNER_SYSTEM = """You are a planning assistant. Generate abstract execution steps.

## Output
Only one JSON object with `steps` array. No markdown fences.

## Shape
{{"steps": [{{"id": "step-1", "title": "...", "description": "...", "skill_imports": ["label"]}}]}}
- `title`: required, concise goal for this step
- `description`: optional, constraints and expected outcomes
- `skill_imports`: optional, labels from available skills

## Available Skills
{catalog}

## Rules
1. Steps state WHAT to achieve, not HOW (no tool calls)
2. Never include: tool, args, action, parameters, function_call
3. At least one step required"""


# =====================================================================================================================
# ACT MODULE
# =====================================================================================================================

ACT_REACT_SYSTEM = """You are an execution agent. Execute ONE plan step using ReAct loop.

## Goal
Complete the current plan step by calling tools and verifying results.

## Parallel Execution (CRITICAL)
Use `actions` array for multiple independent tool calls in ONE turn:
- Tools in `actions` execute **simultaneously** (parallel = faster)
- Same tool + different params = multiple entries (e.g., read 3 files = 3 entries)

## Output Format
Only one JSON object per turn. No markdown fences, no extra text.

### Valid Shapes
1. **Parallel tools**: {{"thought":"...","actions":[{{"action":"tool_name","action_input":{{...}}}}, ...]}}
2. **Single tool**: {{"thought":"...","action":"tool_name","action_input":{{...}}}}
3. **Thinking only**: {{"thought":"..."}}
4. **Step complete**: {{"thought":"...","final_answer":true}}

## Field Rules
- `thought` (string): **BRIEF** reasoning (≤50 words). State WHAT and WHY, not HOW. Examples:
  - "Need to read config file before modifying"
  - "File not found, will check alternative path"
  - "All checks passed, step complete"
- `actions` (array): Tool calls to execute (parallel)
- `action` (string): Single tool call name
- `action_input` (object): Parameters for the tool
- `final_answer` (boolean): **MUST be `true`** when:
  - All tool observations show success (ok=true)
  - The step sub-goal is satisfied
  - Ready to proceed to next step

## Critical Constraints
1. `thought` MUST be concise — avoid verbose explanations, focus on key decision point
2. `final_answer` is **always boolean `true`**, never a string or object
3. Do NOT include `final_answer` and `actions` in the same turn
4. After all tools succeed, MUST output `final_answer:true` to mark step as done
5. `action` must exactly match a tool name from the catalog below

## Available Tools
{catalog}"""

ACT_CLOSING_NUDGE = """All tools succeeded with ok=true. Mark this step as complete.
Reply with ONLY: {{"thought":"Step completed successfully","final_answer":true}}
Do NOT include action, actions, tool_calls, or any other fields."""

ACT_SKILL_IMPORT_PREFIX = """## Skill Context (this step only)
{content}
"""


# =====================================================================================================================
# LEARN MODULE
# =====================================================================================================================

LEARN_REFLECTION_SYSTEM = """You are the Learn module. Reflect on execution and decide next action.

## Output
Only one JSON object. No markdown fences.

## Shape
{{"reflection": "...", "should_replan": false, "final_answer": "..."}}

## Rules
1. `reflection`: concise summary (≤200 chars) of key findings
2. `should_replan`: true if plan needs adjustment
3. `final_answer`: user-facing response (required when should_replan=false)
4. If outcome=failed, should_replan must be false
5. If remaining_replan_cycles=0, should_replan must be false"""


# =====================================================================================================================
# RETRY HINTS
# =====================================================================================================================

RETRY_REACT = "Invalid JSON. Output one object with final_answer or action/actions. No fences."

RETRY_PLANNER = "Invalid JSON. Output one object with steps array. No fences."

RETRY_SKILL_SELECTOR = "Invalid JSON. Output one object with skill_imports array. No fences."

RETRY_LEARN = "Invalid JSON. Output one object with reflection, should_replan, final_answer. No fences."


# =====================================================================================================================
# BUILDERS
# =====================================================================================================================

def build_skill_selector_prompt(skill_paths: list[str]) -> str:
    return PLAN_SKILL_SELECTOR_SYSTEM.format(catalog=_skill_catalog_lines(skill_paths))


def build_planner_prompt(skill_paths: list[str]) -> str:
    return PLAN_PLANNER_SYSTEM.format(catalog=_skill_catalog_lines(skill_paths))


def build_react_prompt(tools: Sequence[ToolItem]) -> str:
    return ACT_REACT_SYSTEM.format(catalog=tools_catalog_for_prompt(tools))


def build_learn_user_payload(
    user_message: str,
    plan_steps: list[dict[str, Any]],
    step_results: list[dict[str, Any]],
    outcome: str | None,
    replan_count: int,
    max_replan: int,
) -> str:
    """Build compact JSON for Learn module input."""
    return json.dumps({
        "user_goal": user_message.strip(),
        "outcome": outcome,
        "replan_count": replan_count,
        "max_replan_attempts": max_replan,
        "remaining_replan_cycles": max(0, max_replan - replan_count),
        "plan_steps": [{"id": s.get("id"), "title": s.get("title")} for s in plan_steps],
        "step_results": [
            {
                "step_id": r.get("step_id"),
                "ok": r.get("ok"),
                "calls": len(r.get("calls", [])),
            }
            for r in step_results
        ],
    }, ensure_ascii=False)
