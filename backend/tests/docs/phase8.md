# 阶段8 测试说明（质量与总验收）

对齐 [docs/DEVELOP_ORDER.md](../../docs/DEVELOP_ORDER.md) **阶段8 · 质量与验收**：在后端自动化中聚合 **端到端成功路径**、**任务列表契约** 与 **OpenAPI 核心路径巡检**；与 [docs/TECH_DESIGN.md](../../docs/TECH_DESIGN.md) 中同一 `task_id` 下 `seq` 从 1 起连续递增的语义一致。

## 自动化（本仓库）

| 目录 / 标记 | 内容 |
|-------------|------|
| `tests/phase8/` | 总验收用例（真实 LangGraph 执行路径，非 Mock） |
| `@pytest.mark.phase8` | 仅跑阶段8：`pytest -m phase8` |

### 用例摘要

- **`test_acceptance_e2e_event_seq_strictly_consecutive`**：创建会话与任务 → 轮询至 `success` → 拉取 `/events`，断言 `seq` 为 `1..n` 无跳号，且字段含 `module` / `kind` / `ts`。
- **`test_acceptance_task_list_contract_and_status_filter`**：同上先造一条成功任务 → `GET /api/v1/tasks` 校验 `items` / `total`；`status=success` 筛选结果中包含该 `task_id`。
- **`test_acceptance_openapi_exposes_core_routes`**：`GET /openapi.json` 中路径包含 `/health`、`/api/v1/tasks`、`/api/v1/sessions`、`/api/v1/settings`、`/api/v1/tools`。

### 隔离策略

- `tests/phase8/conftest.py`：每个用例前 `drop_all` + `create_all`（与阶段2 类似），避免与全量跑测时的数据串扰。
- 仍依赖根目录 `tests/conftest.py` 将 `DATABASE_URL` 指向 `tests/test_runtime.sqlite`。

## 与前置阶段的关系

| 能力 | 主要覆盖目录 |
|------|----------------|
| `seq` / 事件存储 | `tests/phase1/`、`tests/phase5/` |
| REST 与 `after_seq` | `tests/phase2/` |
| Agent 图与终态 | `tests/phase4/` |
| SSE | `tests/phase5/` |

阶段8 **不重复** 底层单元场景，而是串起 **真实创建任务 → 执行完成 → 列表与 OpenAPI** 的回归门槛。

## 常用命令（在 `backend/` 下）

```bash
pytest tests/phase8 -v
pytest -m phase8 -v
```

## 手工验收

仍以 [docs/DEVELOP_ORDER.md](../../docs/DEVELOP_ORDER.md) **§6 手工验收清单** 为准（创建会话 → 任务 → 计划/时间线/终态、失败与重规划可见性、设置与工具列表、无密钥泄露等）；阶段8 自动化 **不能替代** 该清单中的浏览器与网络面板检查。
