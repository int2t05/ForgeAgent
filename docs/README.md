# ForgeAgent 文档索引

本目录为 **现行文档清单**。实现细节以仓库代码与后端 **`GET /openapi.json`** 为准。

| 文档 | 说明 |
|------|------|
| [`architecture/OVERVIEW.md`](architecture/OVERVIEW.md) | **五大板块**总览：目录结构、前端、后端、Agent、数据与 API（浓缩索引） |
| [`architecture/TECH_DESIGN.md`](architecture/TECH_DESIGN.md) | 技术栈、数据模型、API 方向、环境与部署要点 |
| [`architecture/ARCH.md`](architecture/ARCH.md) | 前后端目录与模块职责（与当前 `app/core`、`app/shared`、`app/modules`、`frontend/src` 分层结构对齐） |
| [`conversation-flow.md`](conversation-flow.md) | 对话、SSE、流式与业务流程说明 |
| [`backend/业务流程文档.md`](backend/业务流程文档.md) | 后端业务流程与伪代码 |
| [`backend/TODO.md`](backend/TODO.md) | 后端与 Agent 迭代 TODO |
| [`performance-optimization.md`](performance-optimization.md) | 性能瓶颈与优化方向（SSE/DB/UI 等） |
| [`llm-context-prompt-optimization.md`](llm-context-prompt-optimization.md) | LLM 上下文预算、裁剪与提示词演进 |

**说明**：若你本地仍引用 `docs/product/PRD.md`、`docs/api/API.md`、`docs/guides/*` 等路径，请以当前仓库中实际存在的文件为准，或以 `TECH_DESIGN.md` + OpenAPI 为契约来源。
