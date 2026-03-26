# 阶段3 测试说明（工具注册表 + MCP mock + Skills）

## 1. 测试如何归类

```text
backend/tests/
└── phase3/
    ├── conftest.py         # autouse 清表 + TestClient（与 phase2 同策略）
    └── test_tool_registry.py
```

根 `conftest.py` 继续负责将 `DATABASE_URL` 指向 `tests/test_runtime.sqlite`。

## 2. 实现与业务要点（摘要）

| 能力 | 说明 |
|------|------|
| **ToolRegistry** | 进程内快照；`GET /api/v1/tools` 只读该快照 |
| **启动刷新** | `app.main` lifespan 在 `init_db` 后 `tool_registry.refresh` |
| **按需刷新** | `PUT /api/v1/settings` 成功写入后再次 `refresh`，与 DB 一致 |
| **MCP（MVP）** | `settings.mcp` 中 `transport=mock` + 内嵌 `tools` 数组，无密钥、无外部进程 |
| **Skills** | `skills_paths` 下各目录的 `manifest.json`，字段 `tools[]` → `source=skill` |
| **合并** | 内置 → MCP → Skill；同名保留先出现的条目（内置优先） |

`phase3/conftest.py` 在 `drop_all` 前对全局 `engine.dispose()`，减轻 Windows 上 SQLite 与连接池占用导致的间歇锁库。

仓库示例：`skills/example_skill/manifest.json`。

## 3. 用例与断言要点

| 用例 | 断言要点 |
|------|----------|
| `test_tools_include_builtin_mcp_and_skill_after_settings` | PUT mock MCP + 示例 Skill 路径后，列表含 `builtin` / `mcp` / `skill` |
| `test_disabled_mcp_server_contributes_no_tools` | `enabled=false` 不产生工具 |
| `test_builtin_wins_on_name_collision` | Skill 与内置同名时仅保留内置 |

## 4. 如何运行

在 `backend/` 目录（Git Bash）：

```bash
source .venv/Scripts/activate
pytest tests/phase3 -q
pytest tests/phase2 tests/phase3 -q   # 与阶段2 回归
```

## 5. 文档与最佳实践

- MCP mock 与 manifest 字段约定：`best_practice/forgeagent-tool-registry-phase3.md`
