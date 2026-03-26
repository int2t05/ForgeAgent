# ForgeAgent 阶段3：统一工具注册表（内置 / MCP mock / Skill）

## 1. 目标

- `GET /api/v1/tools` 与进程内 **单一注册表快照** 一致。
- MCP 在 MVP 中可用 **文档化 mock**（无密钥、无需真实 MCP Server）。
- Skills 按目录 `manifest.json` 声明工具元数据，`source=skill`。

## 2. settings.mcp 中的 mock（伪代码）

```json
{
  "mcp": [
    {
      "name": "local-mock",
      "enabled": true,
      "transport": "mock",
      "tools": [
        {
          "name": "weather_lookup",
          "description": "占位：天气查询",
          "read_only": true
        }
      ]
    }
  ],
  "skills_paths": ["/abs/path/to/skill_root"]
}
```

- `enabled: false`：整段 Server 忽略。
- 未实现 `transport: stdio|sse` 等与真实 MCP 拉取时，非 mock 项 **静默跳过**（避免误将「未连接」当成错误列表）。

## 3. Skill manifest（伪代码）

路径：`{skill_root}/manifest.json`

```json
{
  "name": "my_skill",
  "tools": [
    { "name": "do_x", "description": "说明", "read_only": true }
  ]
}
```

## 4. 合并优先级（防同名）

顺序：**builtin → mcp → skill**；若后段出现与前面 **同名** 的 `name`，则丢弃后段条目（内置优先）。

## 5. 刷新时机

1. 应用 `lifespan` 启动：`init_db` 后 `refresh`。
2. `PUT /api/v1/settings` 成功后：`refresh`，保证列表立即更新。
