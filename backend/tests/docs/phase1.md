# 阶段1 测试说明

## 目标

对齐 [docs/DEVELOP_ORDER.md](../../docs/DEVELOP_ORDER.md) **阶段1 · 数据层**：SQLite + SQLAlchemy 2.0 async；五张表可 `create_all` 并可读写；同一 `task_id` 下 `task_events.seq` **严格递增**且表级 **唯一**。

设计依据见 [docs/TECH_DESIGN.md](../../docs/TECH_DESIGN.md) §3。

## 用例

| 用例 | 文件 | 说明 |
|------|------|------|
| `test_metadata_registers_core_tables` | `tests/phase1/test_data_layer.py` | 导入 ORM 后 `Base.metadata` 含 `tasks`、`task_events`、`sessions`、`messages`、`settings_kv` |
| `test_create_all_sqlite_tables_exist` | 同上 | 内存库 `create_all` 后 `sqlite_master` 可见上述物理表名 |
| `test_task_event_seq_monotonic_and_unique` | 同上 | `append_event` 连续写入得 `seq` 1,2,3；手工插入重复 `(task_id, seq)` 触发 `IntegrityError` |
| `test_session_task_message_settings_chain` | 同上 | 会话、任务、消息、`settings_kv` 链式写入并可查询 |

## Fixture

- `async_engine`、`db_session` 定义在 `tests/phase1/conftest.py`：内存 SQLite + `StaticPool`，与运行时文件库相互独立。

## 运行

```bash
cd backend
pytest tests/phase1/ -v
# 或
pytest -m phase1 -v
```
