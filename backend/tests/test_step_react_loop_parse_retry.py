"""单步 ReAct：JSON 解析失败后按配置重试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.core.config import Settings
from app.modules.execution.step_react_loop import run_step_react_loop
from app.schemas.tools import ToolItem


class _DummyTx:
    async def __aenter__(self) -> "_DummyTx":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _DummyDB:
    def begin(self) -> _DummyTx:
        return _DummyTx()


class _DummySession:
    async def __aenter__(self) -> _DummyDB:
        return _DummyDB()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_step_react_retries_after_parse_fail_then_succeeds() -> None:
    bad = AIMessage(content="不是 JSON")
    good = AIMessage(content='{"thought":"t","final_answer":"已完成"}')
    invoke = AsyncMock(side_effect=[bad, good])
    chat = MagicMock()
    append_event = AsyncMock()

    settings = Settings(
        openai_api_key="sk-test",
        react_parse_max_attempts=2,
        react_max_tokens_per_step=99999,
    )

    with (
        patch(
            "app.modules.execution.step_react_loop.is_llm_configured",
            return_value=True,
        ),
        patch(
            "app.modules.execution.step_react_loop.build_chat_model",
            return_value=chat,
        ),
        patch(
            "app.modules.execution.step_react_loop.ainvoke_with_retry",
            invoke,
        ),
        patch(
            "app.modules.execution.step_react_loop.AsyncSessionLocal",
            return_value=_DummySession(),
        ),
        patch(
            "app.modules.execution.step_react_loop.event_repository.append_event",
            append_event,
        ),
    ):
        ok, calls, final = await run_step_react_loop(
            task_id="t1",
            step_id="step4",
            step={"id": "step4", "title": "执行"},
            user_message="处理任务",
            prior_tool_trace=[],
            tools=[ToolItem(name="read_file", description="d", source="builtin")],
            settings=settings,
            max_tool_tries=1,
            max_rounds=4,
        )

    assert ok is True
    assert calls == []
    assert final == "已完成"
    assert invoke.await_count == 2
    second_call_messages = invoke.await_args_list[1].args[1]
    contents = [str(getattr(m, "content", "")) for m in second_call_messages]
    assert "不是 JSON" in contents
    assert any("Invalid JSON" in c for c in contents)
