"""规划 LLM：JSON 解析失败时的重试行为。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import Settings
from app.modules.planning import llm as planner_llm
from app.modules.planning.llm import plan_steps_with_llm


def test_normalize_steps_resolves_skill_imports_to_configured_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        sk = Path(tmp) / "my_skill"
        sk.mkdir()
        root = str(sk)
        data = {
            "steps": [
                {
                    "id": "1",
                    "title": "一步",
                    "skill_imports": ["my_skill"],
                },
            ],
        }
        out = planner_llm._normalize_steps(data, configured_skill_paths=[root, "/nope"])
        assert out == [
            {"id": "1", "title": "一步", "skill_imports": [root]},
        ]


@pytest.mark.asyncio
async def test_plan_steps_retries_after_invalid_json_then_succeeds() -> None:
    bad = AIMessage(content="此处仅为说明，不是 JSON")
    good = AIMessage(
        content='{"steps":[{"id":"1","title":"一步","description":"描述"}]}'
    )
    invoke = AsyncMock(side_effect=[bad, good])
    chat = MagicMock()

    settings = Settings(
        openai_api_key="sk-test",
        planner_parse_max_attempts=3,
    )

    with (
        patch(
            "app.modules.planning.llm.is_llm_configured",
            return_value=True,
        ),
        patch(
            "app.modules.planning.llm.build_chat_model",
            return_value=chat,
        ),
        patch(
            "app.modules.planning.llm.ainvoke_with_retry",
            invoke,
        ),
    ):
        steps = await plan_steps_with_llm(
            [HumanMessage(content="做个计划")],
            settings,
        )

    assert steps == [
        {"id": "1", "title": "一步", "description": "描述"},
    ]
    assert invoke.await_count == 2
    # 第二轮应带上首轮助手输出 + 纠偏用户消息
    second_call_messages = invoke.await_args_list[1].args[1]
    assert second_call_messages[-2] is bad
    assert "Invalid JSON" in (second_call_messages[-1].content or "")


@pytest.mark.asyncio
async def test_plan_steps_falls_back_after_all_parse_attempts_fail() -> None:
    bad = AIMessage(content="still not json")
    invoke = AsyncMock(return_value=bad)
    chat = MagicMock()

    settings = Settings(
        openai_api_key="sk-test",
        planner_parse_max_attempts=2,
    )

    with (
        patch("app.modules.planning.llm.is_llm_configured", return_value=True),
        patch("app.modules.planning.llm.build_chat_model", return_value=chat),
        patch("app.modules.planning.llm.ainvoke_with_retry", invoke),
    ):
        steps = await plan_steps_with_llm([], settings)

    assert invoke.await_count == 2
    assert len(steps) >= 1
    assert all("title" in s for s in steps)
