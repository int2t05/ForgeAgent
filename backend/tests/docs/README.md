# 后端测试文档索引

与 `docs/DEVELOP_ORDER.md` 阶段对齐：**按目录归类**阶段测试，避免共用 `conftest` 污染环境与数据库。

| 阶段 | 测试目录 | 说明文档 |
|------|----------|----------|
| 0 | `tests/phase0/` | （可补充 `phase0.md`）环境与健康检查基线 |
| 1 | `tests/phase1/` | （可补充 `phase1.md`）数据层、内存 SQLite、`seq` 语义 |
| 2 | `tests/phase2/` | [phase2.md](phase2.md) HTTP REST、`TestClient`、任务闭环 |
| 3 | `tests/phase3/` | [phase3.md](phase3.md) 工具注册表、MCP mock、Skills |
| 4 | `tests/phase4/` | [phase4.md](phase4.md) LangGraph 运行时与重规划 |
| 5 | `tests/phase5/` | [phase5.md](phase5.md) SSE 任务事件流 |
| 6 | `frontend/` | [phase6.md](phase6.md) 前端壳（构建验证） |
| 7 | `frontend/` | [phase7.md](phase7.md) 监控闭环（SSE 时间线 + 构建验证） |
| 8 | `tests/phase8/` | [phase8.md](phase8.md) 总验收（E2E seq、列表契约、OpenAPI 巡检） |

**根目录 `tests/conftest.py`**：仅设置 `DATABASE_URL` → `tests/test_runtime.sqlite`，供 **阶段0 / 阶段2** 等经 `app.database` 访问库的调用使用；**不含** `autouse` 清表，以免波及其它阶段。

## 常用命令（在 `backend/` 下）

```bash
pytest -q                          # 全量
pytest tests/phase2 -q             # 仅阶段2 目录
pytest tests/phase4 -q             # 仅阶段4
pytest -m phase2 -q                # 仅带 @pytest.mark.phase2 的用例（跨目录也可用）
pytest -m phase4 -q                # 仅阶段4 标记
pytest tests/phase8 -q             # 阶段8 总验收目录
pytest -m phase8 -q                # 仅 @pytest.mark.phase8
```

## 原则

1. **各阶段自带 `conftest.py`**：fixture 与库 URL 不提升到 `tests/` 根目录，除非确为全仓共享且无 side effect。
2. **文档与目录同名**：阶段说明写在 `tests/docs/phaseN.md`，便于 Code Review 与新人对照里程碑验收。
