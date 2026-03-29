"""阶段5：GET /tasks/{id}/events/stream（SSE）与 REST 事件对齐。"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.phase5


def _parse_sse_events(raw: bytes) -> list[dict[str, Any]]:
    """将原始 SSE 正文解析为若干条 {id, event, data dict}。"""
    out: list[dict[str, Any]] = []
    for block in raw.split(b"\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith(b":"):
            continue
        sid: str | None = None
        ev: str | None = None
        data_line: str | None = None
        for line in block.decode("utf-8", errors="replace").split("\n"):
            if line.startswith("id:"):
                sid = line[3:].strip()
            elif line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data_line = line[5:].strip()
        if data_line is None:
            continue
        payload = json.loads(data_line)
        out.append({"id": sid, "event": ev, "data": payload})
    return out


def test_sse_unknown_task_returns_404(client: TestClient) -> None:
    """不存在任务时不得挂流，应 404。"""
    r = client.get(
        "/api/v1/tasks/00000000-0000-0000-0000-000000000001/events/stream",
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


def test_sse_streams_events_until_task_done(client: TestClient) -> None:
    """流式输出与 GET /events 一致；终态后连接结束。"""
    r = client.post("/api/v1/sessions", json={"title": "sse"})
    sid = r.json()["session_id"]
    r = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "user_message": "hello"},
    )
    tid = r.json()["task_id"]

    with client.stream(
        "GET",
        f"/api/v1/tasks/{tid}/events/stream",
        headers={"Accept": "text/event-stream"},
    ) as stream:
        assert stream.status_code == 200
        assert stream.headers.get("content-type", "").startswith("text/event-stream")
        # read() 在服务端关闭流后返回完整正文（轮询 SSE 直至终态稳定）
        raw = stream.read()
    parsed = _parse_sse_events(raw)
    assert len(parsed) >= 2
    kinds = [p["data"]["kind"] for p in parsed]
    assert kinds[0] == "plan_created"
    assert "step_start" in kinds

    rest_events = client.get(f"/api/v1/tasks/{tid}/events").json()["events"]
    for i, p in enumerate(parsed):
        assert p["data"]["seq"] == rest_events[i]["seq"]
        assert p["data"]["kind"] == rest_events[i]["kind"]
        assert p["event"] == rest_events[i]["kind"]


def test_sse_after_seq_emits_only_newer(client: TestClient) -> None:
    """after_seq 仅推送更大 seq（与 REST after_seq 一致）。"""
    r = client.post("/api/v1/sessions", json={})
    sid = r.json()["session_id"]
    r = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "user_message": "x"},
    )
    tid = r.json()["task_id"]

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if client.get(f"/api/v1/tasks/{tid}").json()["status"] in (
            "success",
            "failed",
        ):
            break
        time.sleep(0.05)

    ev = client.get(f"/api/v1/tasks/{tid}/events").json()["events"]
    assert len(ev) >= 2
    first_seq = int(ev[0]["seq"])

    with client.stream(
        "GET",
        f"/api/v1/tasks/{tid}/events/stream",
        params={"after_seq": first_seq},
        headers={"Accept": "text/event-stream"},
    ) as stream:
        assert stream.status_code == 200
        buf = stream.read()

    parsed = _parse_sse_events(buf)
    assert len(parsed) >= 1
    assert all(p["data"]["seq"] > first_seq for p in parsed)
