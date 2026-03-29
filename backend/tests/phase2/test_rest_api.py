"""阶段2：REST API 契约与 Mock 任务闭环（见 tests/docs/phase2.md）。"""

import time

import pytest
from fastapi.testclient import TestClient


@pytest.mark.phase2
def test_health(client: TestClient) -> None:
    """探活路由返回约定 JSON。"""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.phase2
def test_sessions_messages_tasks_flow(client: TestClient) -> None:
    """会话 → 任务 → Mock 成功 → 详情含 plan → 事件顺序与 after_seq 语义。"""
    # 1. 创建会话
    r = client.post("/api/v1/sessions", json={"title": "t1"})
    assert r.status_code == 200
    sid = r.json()["session_id"]

    # 2. 初始无消息
    r = client.get(f"/api/v1/sessions/{sid}/messages")
    assert r.status_code == 200
    assert r.json()["messages"] == []

    # 3. 创建任务并记录返回的流路径
    r = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "user_message": "hello"},
    )
    assert r.status_code == 200
    body = r.json()
    tid = body["task_id"]
    assert body["events_stream_path"] == f"/api/v1/tasks/{tid}/events/stream"

    # 4. 用户消息已入库（助手回复在任务成功后异步写入，快机器上可能已 2 条）
    r = client.get(f"/api/v1/sessions/{sid}/messages")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"] == "hello"

    # 5. 轮询直至 Mock 将任务置为 success
    deadline = time.time() + 3.0
    st = None
    while time.time() < deadline:
        r2 = client.get(f"/api/v1/tasks/{tid}")
        assert r2.status_code == 200
        st = r2.json()["status"]
        if st == "success":
            break
        time.sleep(0.05)
    assert st == "success"

    # 5b. 成功后会话内应有助手消息
    r = client.get(f"/api/v1/sessions/{sid}/messages")
    msgs_after = r.json()["messages"]
    assert any(m["role"] == "assistant" for m in msgs_after)

    # 6. 详情含 plan.steps
    detail = client.get(f"/api/v1/tasks/{tid}").json()
    assert detail["plan"] is not None
    assert "steps" in detail["plan"]

    # 7. 事件升序且首条为 plan_created
    ev = client.get(f"/api/v1/tasks/{tid}/events").json()["events"]
    assert len(ev) >= 2
    assert ev[0]["seq"] < ev[1]["seq"]
    assert ev[0]["kind"] == "plan_created"

    # 8. after_seq 仅返回更大 seq
    after = client.get(
        f"/api/v1/tasks/{tid}/events",
        params={"after_seq": ev[0]["seq"]},
    ).json()["events"]
    assert all(e["seq"] > ev[0]["seq"] for e in after)


@pytest.mark.phase2
def test_task_unknown_session(client: TestClient) -> None:
    """非法 session_id 创建任务应 404。"""
    r = client.post(
        "/api/v1/tasks",
        json={
            "session_id": "00000000-0000-0000-0000-000000000000",
            "user_message": "x",
        },
    )
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


@pytest.mark.phase2
def test_settings_roundtrip_and_rejects_secret_key(client: TestClient) -> None:
    """设置读写一致；含 api_key 字段名则拒绝。"""
    r = client.put(
        "/api/v1/settings",
        json={"mcp": [{"name": "a", "url": "http://x"}], "skills_paths": ["/tmp/sk"]},
    )
    assert r.status_code == 200
    r = client.get("/api/v1/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["mcp"][0]["name"] == "a"
    assert data["skills_paths"] == ["/tmp/sk"]

    r = client.put(
        "/api/v1/settings",
        json={"mcp": [{"api_key": "x"}], "skills_paths": []},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "SECRET_FIELD"


@pytest.mark.phase2
def test_tools_list(client: TestClient) -> None:
    """工具列表至少包含内置项。"""
    r = client.get("/api/v1/tools")
    assert r.status_code == 200
    tools = r.json()["tools"]
    assert len(tools) >= 1
    assert tools[0]["source"] == "builtin"
