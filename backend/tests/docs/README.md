# 后端测试文档索引

与 `docs/DEVELOP_ORDER.md` 阶段对齐：**按目录归类**阶段测试，避免共用 `conftest` 污染环境与数据库。

| 阶段 | 测试目录 | 说明文档 |
|------|----------|----------|
| 0 | `tests/phase0/` | （可补充 `phase0.md`）环境与健康检查基线 |
| 1 | `tests/phase1/` | （可补充 `phase1.md`）数据层、内存 SQLite、`seq` 语义 |
| 2 | `tests/phase2/` | [phase2.md](phase2.md) HTTP REST、`TestClient`、Mock 任务 |

**根目录 `tests/conftest.py`**：仅设置 `DATABASE_URL` → `tests/test_runtime.sqlite`，供 **阶段0 / 阶段2** 等经 `app.database` 访问库的调用使用；**不含** `autouse` 清表，以免波及其它阶段。

## 常用命令（在 `backend/` 下）

```bash
pytest -q                          # 全量
pytest tests/phase2 -q             # 仅阶段2 目录
pytest -m phase2 -q                # 仅带 @pytest.mark.phase2 的用例（跨目录也可用）
```

## 原则

1. **各阶段自带 `conftest.py`**：fixture 与库 URL 不提升到 `tests/` 根目录，除非确为全仓共享且无 side effect。
2. **文档与目录同名**：阶段说明写在 `tests/docs/phaseN.md`，便于 Code Review 与新人对照里程碑验收。
