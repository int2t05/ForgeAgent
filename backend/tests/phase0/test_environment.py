"""阶段0：仓库与环境基线（健康检查等与 docs/DEVELOP_ORDER 阶段0 对齐）。"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.phase0  # 标记
def test_health_endpoint():
    """后端可访问 GET /health；TestClient 会走 lifespan（含 init_db）。"""
    from app.main import app

    # TestClient 模拟 HTTP 请求 触发 FastAPI 的 lifespan 事件
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
