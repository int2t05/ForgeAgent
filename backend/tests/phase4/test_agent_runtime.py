"""阶段4：LangGraph 运行时、重规划与任务终态（见 tests/docs/phase4.md）。"""

import time

import pytest
from fastapi.testclient import TestClient

_FORCE = "__FORCE_REPLAN__"


def _wait_task_status(client: TestClient, task_id: str, want: str, *, seconds: float = 8.0) -> None:
    """轮询任务状态直至 want 或超时。"""
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        r = client.get(f"/api/v1/tasks/{task_id}")
        assert r.status_code == 200
        last = r.json()["status"]
        if last == want:
            return
        time.sleep(0.05)
    msg = f"timeout waiting status {want!r}, last={last!r}"
    raise AssertionError(msg)


@pytest.mark.phase4
def test_langgraph_success_normal_message(client: TestClient) -> None:
    """无重规划令牌时任务成功，事件含 plan_created 与多步 step_start。"""
    r = client.post("/api/v1/sessions", json={"title": "p4"})
    sid = r.json()["session_id"]
    r = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "user_message": "hello phase4"},
    )
    assert r.status_code == 200
    tid = r.json()["task_id"]
    _wait_task_status(client, tid, "success")

    detail = client.get(f"/api/v1/tasks/{tid}").json()
    assert detail["status"] == "success"
    assert detail["plan_version"] == 1
    assert detail["plan"] is not None
    assert "steps" in detail["plan"]

    ev = client.get(f"/api/v1/tasks/{tid}/events").json()["events"]
    kinds = [e["kind"] for e in ev]
    assert "plan_created" in kinds
    assert kinds.count("step_start") >= 2


@pytest.mark.phase4
def test_replan_bumps_plan_version_and_emits_replan_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """含 __FORCE_REPLAN__ 且允许 1 次重规划：version++ 且存在 replan 事件，最终仍可成功。"""
    monkeypatch.setenv("MAX_REPLAN_ATTEMPTS", "1")
    r = client.post("/api/v1/sessions", json={})
    sid = r.json()["session_id"]
    r = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "user_message": f"need replan {_FORCE}"},
    )
    tid = r.json()["task_id"]
    _wait_task_status(client, tid, "success")

    detail = client.get(f"/api/v1/tasks/{tid}").json()
    assert detail["plan_version"] == 2
    ev = client.get(f"/api/v1/tasks/{tid}/events").json()["events"]
    assert any(e["kind"] == "replan" for e in ev)


@pytest.mark.phase4
def test_max_replan_zero_fails_when_forced(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """max_replan_attempts=0 时强制重规划令牌导致失败终态与错误信息。"""
    monkeypatch.setenv("MAX_REPLAN_ATTEMPTS", "0")
    r = client.post("/api/v1/sessions", json={})
    sid = r.json()["session_id"]
    r = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "user_message": _FORCE},
    )
    tid = r.json()["task_id"]
    _wait_task_status(client, tid, "failed")
    detail = client.get(f"/api/v1/tasks/{tid}").json()
    assert detail["status"] == "failed"
    assert detail["error_message"]
    assert "重规划" in detail["error_message"]
