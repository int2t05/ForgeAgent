# 阶段0 测试说明

## 目标

对齐 [docs/DEVELOP_ORDER.md](../../docs/DEVELOP_ORDER.md) **阶段0 · 仓库与环境**：后端进程可启动，健康检查可用于探活。

## 用例

| 用例 | 文件 | 说明 |
|------|------|------|
| `test_health_endpoint` | `tests/phase0/test_environment.py` | 使用 `TestClient` 请求 `GET /health`，期望 `200` 且 `{"status":"ok"}` |

## 注意

- `TestClient` 上下文会执行应用的 **lifespan**，因此会触发 `init_db()`（与真实启动一致）。默认 `DATABASE_URL` 可能在当前工作目录下创建/使用 SQLite 文件；CI 中若需隔离，可为进程设置内存库等环境变量后再导入应用（需在实现上保证引擎在配置就绪后构建——当前 MVP 在模块导入时创建引擎，故本地/CI 以文档约定工作目录为准）。

## 运行

```bash
cd backend
pytest tests/phase0/ -v
# 或
pytest -m phase0 -v
```
