# 阶段4 测试说明（Agent 运行时 / LangGraph）

## 1. 测试如何归类

```text
backend/tests/
└── phase4/
    ├── conftest.py          # autouse 清表 + TestClient
    └── test_agent_runtime.py
```

根 `conftest.py` 仍将 `DATABASE_URL` 指向 `tests/test_runtime.sqlite`。

## 2. 实现与业务要点（摘要）

| 能力 | 说明 |
|------|------|
| **最小图** | `START → planner → executor →` 条件边；`replan → replan_record → planner`；`done → END` |
| **规划** | `planner` 写 `task_events.kind=plan_created`（MVP 确定性两步计划，无 LLM） |
| **执行** | `executor` 逐步写 `step_start`；正常路径 `outcome=success` |
| **重规划** | 初始 `force_replan_budget`：消息含 `__FORCE_REPLAN__` 则为 1；每次成功请求重规划消耗 1，避免同一用户文本在每轮执行末尾反复触发 |
| **持久化** | `replan_record`：`tasks.plan_version += 1`，并追加 `kind=replan`（`module=planning`） |
| **上限** | `Settings.max_replan_attempts`（环境变量 `MAX_REPLAN_ATTEMPTS`，默认 3）；超出则 `outcome=failed` 与 `error` 事件 |
| **终态** | `task_service.run_agent_task` 在 `ainvoke` 后根据 `outcome` 更新 `tasks.status/summary/error_message` |

## 3. 用例与断言要点

| 用例 | 断言要点 |
|------|----------|
| `test_langgraph_success_normal_message` | 成功、`plan_version==1`、至少两次 `step_start` |
| `test_replan_bumps_plan_version_and_emits_replan_event` | `MAX_REPLAN_ATTEMPTS=1` + 强制令牌 → 最终成功、`plan_version==2`、存在 `replan` 事件 |
| `test_max_replan_zero_fails_when_forced` | `MAX_REPLAN_ATTEMPTS=0` + 强制令牌 → `failed` 且 `error_message` 含「重规划」 |

## 4. 如何运行

在 `backend/` 目录（Git Bash）：

```bash
source .venv/Scripts/activate
pytest tests/phase4 -q
pytest tests/phase2 tests/phase3 tests/phase4 -q
```

## 5. 文档与最佳实践

- LangGraph 最小图与异步节点：`best_practice/forgeagent-langgraph-phase4.md`
