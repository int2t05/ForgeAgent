"""Planner prompts: skill selector system prompt + planner system prompt."""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------------------------------------------------

def _skill_catalog_lines(paths: list[str]) -> str:
    if not paths:
        return "*(none configured)*"
    lines: list[str] = []
    for p in paths:
        root = Path(p).expanduser()
        label = root.name.strip() or str(root)
        lines.append(f"- **`{label}`** — path: `{root}`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------------------
# Skill selector
# ---------------------------------------------------------------------------------------------------------------------

def build_skill_selector_system_prompt(*, configured_skill_paths: list[str]) -> str:
    """System prompt for the skill-selection LLM call (runs before the planner)."""
    catalog = _skill_catalog_lines(configured_skill_paths)
    return f"""You are a skill advisor for ForgeAgent.

## Task
Read the user's current goal and the conversation history. Decide which **skill directories** (if any) from the catalog below contain relevant SKILL.md instructions that would help the planner produce better steps.

## Output
Reply with **only one raw JSON object** (no fences, no prose) in this shape:
{{"skill_imports": ["label1", "label2"]}}

- Include zero or more labels from the catalog below.
- If no skill is relevant, reply: {{"skill_imports": []}}
- Do **not** invent labels not in the catalog.

### Available skill directories
{catalog}

## Hint
Only select a skill if its SKILL.md contains concrete guidance (e.g. design rules, coding conventions, UI patterns, domain knowledge) that directly applies to the user's goal. Prefer precision over breadth.
"""


_SKILL_SELECTOR_PARSE_RETRY_USER_HINT = (
    "Your last reply could not be parsed as the required JSON "
    "(root object must contain a non-empty `skill_imports` array; values must be strings "
    "from the catalog). Reply with **only** one raw JSON object—no markdown fences, no other text."
)


# ---------------------------------------------------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------------------------------------------------

def build_planner_system_prompt(*, configured_skill_paths: list[str] | None = None) -> str:
    """Return the planner system message (goal-level steps, strict JSON root object)."""
    catalog = _skill_catalog_lines(list(configured_skill_paths or []))
    return f"""You are a planning assistant for ForgeAgent.

## Task
Read the prior conversation and the user's current goal. Emit **only one JSON object** that lists abstract execution steps (what to achieve, not how to call tools).

## Optional: Skill context imports (no manifest / tools)
ForgeAgent may have **skill directories** registered in app settings. For any step that will benefit from extra instructions stored as **SKILL.md** inside a directory, set **`skill_imports`** on that step to an array of **directory labels** from the catalog below (e.g. `["example_skill"]`) or the exact configured path string.
Only directories listed here are allowed. Omit `skill_imports` when no extra skill text is needed. This is **not** tool calling—execution still binds tools separately.

### Available skill directories
{catalog}

## Output rules
- **Raw JSON only**: no markdown fences, no prose before or after the object.
- **Language for string fields**: use **Simplified Chinese** for `title`, and for `description` / `expected_output` when present (UI and team conventions).
- **Shape**: root object with `steps` array. Each step: `id`, `title`, optional `description`, `expected_output`, optional `skill_imports` (string array of catalog labels or paths).
- **At least one** step. Each step states outcomes and constraints only—**never** how to implement with tools.

## Forbidden in any step object
Do not include keys that imply tool invocation or API calls, including but not limited to:
`tool`, `args`, `tool_name`, `function`, `function_call`, `action`, or `parameters` when used as call arguments.
Do not invent or list available tools; execution chooses tools later.

## Quality
Steps must be self-contained so an executor can progress using only the step text and the user conversation."""
