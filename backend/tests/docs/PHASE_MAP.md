# 阶段 ↔ 测试对照表

与 [docs/DEVELOP_ORDER.md](../../docs/DEVELOP_ORDER.md) §3 一致。未列出阶段的目录/用例表示 **尚未在仓库中落地自动化测试**（可在该阶段开始时补充）。

| 阶段 | 焦点 | 测试目录 | pytest 标记 | 当前用例文件（示例） |
|------|------|----------|-------------|----------------------|
| 0 | 仓库与环境 | `tests/phase0/` | `phase0` | `test_environment.py` |
| 1 | 数据层 | `tests/phase1/` | `phase1` | `test_data_layer.py` |
| 2 | HTTP API（非流式） | `tests/phase2/`（预留） | `phase2` | — |
| 3 | 工具注册表 + MCP | `tests/phase3/` | `phase3` | `test_tool_registry.py` |
| 4 | Agent 运行时 | `tests/phase4/` | `phase4` | `test_agent_runtime.py` |
| 5 | SSE | `tests/phase5/` | `phase5` | `test_sse.py` |
| 6 | 前端壳 | `frontend` / E2E | — | 构建验证：`npm run lint && npm run build` |
| 7 | 前端监控闭环 | `frontend` / E2E | — | 说明见 [phase7.md](phase7.md)；`npm run build` |
| 8 | 质量与总验收 | `tests/` 各阶段聚合 + 契约 | `phase8`（可选） | 随实现补充 |

## 验收语句摘录（便于写用例时对照）

- **阶段0**：`GET /health` 可用；无密钥进入前端构建产物（由构建与仓库巡检保证，本目录可为空或仅后端探活）。
- **阶段1**：表 `tasks`、`task_events`、`sessions`、`messages`、`settings_kv` 可创建并读写；同一 `task_id` 下 `seq` **严格递增、唯一**。
- **阶段2+**：以 [docs/API.md](../../docs/API.md) 契约为准，在 `tests/phase2/` 起递增补充。

## 目录约定

- `tests/phaseN/`：仅放该阶段相关 `test_*.py` 与 **该阶段专用** `conftest.py`（若有）。
- `tests/conftest.py`：仅跨阶段共享钩子或极少量全局 fixture；无则保持占位注释即可。
- `tests/docs/`：仅人类可读说明，**不参与** pytest 收集。
