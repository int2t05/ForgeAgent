# 阶段6 测试说明（前端壳）

## 1. 测试范围

阶段6 为前端壳搭建，测试以**构建验证**为主（非后端 pytest）。

```text
frontend/
├── src/
│   ├── types/        # TS 类型（与后端 Schema 对齐）
│   ├── lib/          # 工具函数
│   ├── api/          # 请求封装
│   ├── stores/       # Zustand 状态
│   ├── hooks/        # TanStack Query Hooks
│   ├── components/   # 布局 + 通用组件
│   ├── pages/        # 页面组件
│   ├── router.tsx    # 路由配置
│   ├── App.tsx       # 根组件
│   └── main.tsx      # 入口
```

## 2. 实现要点（摘要）

| 能力 | 说明 |
|------|------|
| **路由** | React Router 7 `createBrowserRouter`：`/`、`/tasks`、`/tasks/:taskId`、`/settings`、`/about`、`*` |
| **请求** | fetch 封装 `api/client.ts`；统一错误处理 `ApiRequestError` |
| **状态** | Zustand `sessionStore`：`sessionId` 持久化到 sessionStorage |
| **Query** | TanStack Query v5：`useTasks`、`useTaskDetail`、`useSettings`、`useTools`、`useSession` |
| **布局** | `AppLayout`（侧边栏 + Outlet）、`Sidebar`（NavLink）、`Header` |
| **页面** | 首页（任务创建 + 最近任务）、任务列表（筛选 + 分页）、任务详情（骨架）、设置、关于、404 |

## 3. 验证项

| 验证项 | 方法 | 期望 |
|--------|------|------|
| TypeScript 编译 | `npx tsc -b --noEmit` | exit 0，无类型错误 |
| ESLint | `npm run lint` | exit 0，无 error |
| Vite 构建 | `npm run build` | exit 0，`dist/` 产出 |
| 路由可访问 | `npm run dev` 后浏览器访问 `/`、`/tasks`、`/settings`、`/about` | 各页面正常渲染 |
| 无密钥泄露 | 检查 `dist/` 产物 | 不含 API Key 等敏感字符串 |

## 4. 如何运行

在 `frontend/` 目录：

```bash
npm install
npm run lint
npm run build
npm run dev       # 开发服务器，手动浏览验证
```

## 5. 文档与最佳实践

- 前端壳架构要点：`best_practice/react-frontend-shell-phase6.md`
