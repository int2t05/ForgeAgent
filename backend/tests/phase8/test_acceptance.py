"""阶段8：质量与总验收聚合（对齐 docs/DEVELOP_ORDER.md §3 阶段8）。"""

import time

import pytest
from fastapi.testclient import TestClient


def _wait_task_success(client: TestClient, task_id: str, *, seconds: float = 12.0) -> None:
    """轮询直至任务 success 或超时。"""
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        r = client.get(f"/api/v1/tasks/{task_id}")
        assert r.status_code == 200
        last = r.json()["status"]
        if last == "success":
            return
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting success, last={last!r}")


@pytest.mark.phase8
def test_acceptance_e2e_event_seq_strictly_consecutive(
    client: TestClient,
) -> None:
    """端到端成功路径：同一 task_id 下事件 seq 从 1 起连续无跳号（与 TECH_DESIGN §3.2 一致）。"""
    r = client.post("/api/v1/sessions", json={"title": "acceptance"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    r = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "user_message": "phase8 seq check"},
    )
    assert r.status_code == 200
    tid = r.json()["task_id"]
    _wait_task_success(client, tid)

    # 1. 任务已进入终态 success
    detail = client.get(f"/api/v1/tasks/{tid}").json()
    assert detail["status"] == "success"
    # 2. 事件序列连续递增
    events = client.get(f"/api/v1/tasks/{tid}/events").json()["events"]
    assert len(events) >= 2
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(1, len(seqs) + 1))
    for i, e in enumerate(events):
        assert e["seq"] == i + 1
        assert "module" in e and "kind" in e and "ts" in e


@pytest.mark.phase8
def test_acceptance_task_list_contract_and_status_filter(
    client: TestClient,
) -> None:
    """任务列表契约 items/total；成功任务可被 status=success 筛出。"""
    r = client.post("/api/v1/sessions", json={})
    sid = r.json()["session_id"]
    r = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "user_message": "phase8 list"},
    )
    tid = r.json()["task_id"]
    _wait_task_success(client, tid)

    r = client.get("/api/v1/tasks", params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body
    assert isinstance(body["items"], list)
    assert body["total"] >= 1

    r = client.get(
        "/api/v1/tasks",
        params={"status": "success", "limit": 100, "offset": 0},
    )
    assert r.status_code == 200
    ok_ids = {item["id"] for item in r.json()["items"]}
    assert tid in ok_ids


@pytest.mark.phase8
def test_acceptance_openapi_exposes_core_routes(client: TestClient) -> None:
    """OpenAPI 包含健康检查与核心业务路径，便于契约巡检。"""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths: dict[str, object] = r.json()["paths"]
    assert "/health" in paths
    assert "/api/v1/tasks" in paths
    assert "/api/v1/sessions" in paths
    assert "/api/v1/settings" in paths
    assert "/api/v1/tools" in paths
