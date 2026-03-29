# React 前端壳架构 — ForgeAgent 阶段6 要点

## 目标

搭建 React + TypeScript 前端骨架：路由、请求封装、状态管理、布局导航；为阶段7（监控闭环）提供基础设施。

## 技术选型

```text
React 19 + TypeScript 5.9 + Vite 8 + Tailwind 4
React Router 7       — createBrowserRouter + RouterProvider
TanStack Query 5     — useQuery / useMutation 管理服务端状态
Zustand 5            — 轻量全局状态（仅 session_id）
```

## 分层架构

```text
Pages（路由页面）→ Components（可复用 UI）
    ↓                    ↓
  Hooks（数据逻辑）→ API（请求函数）→ 后端
    ↓
  Stores（跨页面共享状态）
  Types（TS 类型，与后端 Schema 对齐）
```

## 路径别名

```text
tsconfig.app.json:  "paths": { "@/*": ["src/*"] }
vite.config.ts:     alias: { "@": path.resolve(__dirname, "src") }
```

## API 请求封装要点

```text
client.ts:
  1. 基于 fetch，不引入 axios
  2. buildUrl(path, params) 拼接 API_BASE_URL
  3. request<T>() 统一 JSON 序列化 + 错误解析
  4. ApiRequestError 携带 status + body（对齐后端 ErrorResponse）
  5. 导出 get / post / put 三个便捷函数
```

## Zustand 持久化

```text
create<SessionState>()(
  persist(
    (set) => ({ sessionId, setSessionId, clearSession }),
    {
      name: "forgeagent-session",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ sessionId: state.sessionId }),
    }
  )
)
```

## React Router 布局路由

```text
createBrowserRouter([
  {
    element: <AppLayout />,    // 侧边栏 + <Outlet />
    children: [
      { index: true, element: <HomePage /> },
      { path: "tasks", ... },
      { path: "tasks/:taskId", ... },
      { path: "settings", ... },
      { path: "about", ... },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
])
```

## TanStack Query 配置

```text
new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
  },
})
```

## 避免 useEffect 中直接 setState

```text
// ✗ ESLint react-hooks/set-state-in-effect
useEffect(() => { setState(props.data) }, [props.data])

// ✓ 提取子组件，用 props 初始化 state + key 触发重置
<ChildForm key={stableKey} initialValue={data} />
```
