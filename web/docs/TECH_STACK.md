# AskFlow 前端技术栈

## 核心依赖

| 类别 | 库 | 版本 | 用途 |
|------|-----|------|------|
| 框架 | React | 19.x | UI 框架 |
| 构建 | Vite | 6.x | 开发服务器 + 打包 |
| 语言 | TypeScript | 5.x | 类型安全 |
| 路由 | React Router | 7.x | SPA 路由 |
| 状态管理 | Zustand | 5.x | 轻量 Store |
| UI 组件 | shadcn/ui | — | 可定制组件（代码在项目中） |
| 样式 | Tailwind CSS | 4.x | 原子化 CSS |
| 图表 | Recharts | 2.x | 管理看板图表 |
| 表单 | react-hook-form + zod | — | 表单校验 |
| 图标 | Lucide React | — | 图标库（shadcn/ui 默认） |

## 项目约定

### 文件命名

- 组件：PascalCase（`ChatPage.tsx`、`MessageBubble.tsx`）
- Hook：camelCase，以 `use` 开头（`useWebSocket.ts`）
- Store：camelCase，以 `Store` 结尾（`authStore.ts`）
- Service：camelCase（`api.ts`、`chat.ts`）
- 类型：camelCase（`chat.ts`），类型名 PascalCase

### 目录结构

- `pages/` — 路由级页面组件，按区域分子目录（Auth / App / Admin）
- `components/` — 可复用组件，按领域分子目录（chat / ticket / document / intent / common / layout / ui）
- `hooks/` — 自定义 React Hooks
- `stores/` — Zustand Stores
- `services/` — API 调用层
- `types/` — TypeScript 类型定义

### 代码风格

- 函数组件 + Hooks，不使用 class 组件
- 不可变数据：Zustand Store 中使用 immer 或展开运算符
- 组件单一职责：每个文件 < 200 行
- 样式：Tailwind CSS class，避免内联 style
- 导出：命名导出，避免 default export（页面组件除外）

### API 调用

- 所有 API 调用经过 `services/api.ts` 统一封装
- 自动挂载 `Authorization: Bearer <token>`
- 401 响应自动清除登录态并跳转 `/login`
- 响应统一解包 `APIResponse<T>.data`

### 状态管理原则

- 服务端状态：Zustand Store + 手动 fetch（后续可迁移到 TanStack Query）
- 客户端状态：React 组件内 `useState`
- 持久化状态：Zustand `persist` middleware -> `localStorage`
- WebSocket 状态：专属 `chatStore` 管理流式消息
