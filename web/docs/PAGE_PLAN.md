# AskFlow 前端页面规划

> 技术栈：React 19 + Vite + TypeScript + React Router v7 + Zustand + shadcn/ui + Tailwind CSS

## 1. 规划结论

基于当前后端接口，前端拆为 3 个区域：

- **公共鉴权区**：登录、注册
- **用户工作台** (`/app/*`)：智能问答、历史会话、我的工单
- **管理后台** (`/admin/*`)：数据看板、知识库文档、意图配置

当前后端更适合先做一个"聊天驱动"的前端，而不是完整 CRM。已提供的核心能力集中在：

- JWT 登录注册
- WebSocket 流式聊天
- 会话与消息历史
- 用户自己的工单创建与查询
- 管理端文档管理
- 管理端意图配置
- 管理端统计看板

已知边界（影响前端设计）：

- 已提供 `GET /api/v1/admin/auth/me`，但登录后仍可直接从 JWT 中解析角色，减少一次额外请求
- 已提供会话重命名、删除、归档接口，当前前端仅缺少列表操作入口
- 已提供管理端工单列表接口，可支持客服/管理员查看全部工单
- 没有文档详情、预览、下载接口
- 已提供意图配置删除接口，删除按钮可按 admin 权限暴露
- 没有用户管理接口

**策略**：先把"用户聊天 + 用户工单 + 管理知识库/意图/看板"做完整，缺失接口列入第二阶段。

## 2. 路由结构

### 公共页面

| 路由 | 页面 | 角色 |
|------|------|------|
| `/login` | 登录页 | 公开 |
| `/register` | 注册页 | 公开 |

### 用户端

| 路由 | 页面 | 角色 |
|------|------|------|
| `/app/chat` | 智能问答主页 | user / agent / admin |
| `/app/chat/:conversationId` | 指定会话页 | user / agent / admin |
| `/app/tickets` | 我的工单列表 | user / agent / admin |
| `/app/tickets/:ticketId` | 工单详情页 | user / agent / admin |

### 管理端

| 路由 | 页面 | 角色 |
|------|------|------|
| `/admin/dashboard` | 数据看板 | agent / admin |
| `/admin/documents` | 知识库文档管理 | agent / admin |
| `/admin/intents` | 意图配置管理 | agent / admin，写操作仅 admin |

## 3. 页面规划明细

### 3.1 登录页 `/login`

目标：完成账号登录并建立前端登录态。

页面模块：

- 用户名输入框
- 密码输入框
- 登录按钮
- 登录失败提示（shadcn/ui `Alert`）
- 跳转注册入口

接口映射：

- `POST /api/v1/admin/auth/login`

前端处理要点：

- 保存 `access_token` 到 Zustand auth store（持久化到 `localStorage`）
- 从 JWT 中解析 `sub`、`role`、`exp`
- 根据 `role` 决定默认跳转：
  - `user` -> `/app/chat`
  - `agent` / `admin` -> `/admin/dashboard`
- 页头展示用户名可继续使用登录表单中的用户名缓存值；如需刷新资料，可调用 `GET /api/v1/admin/auth/me`

React 组件：

- `LoginPage` -> `pages/Auth/LoginPage.tsx`
- 使用 shadcn/ui `Card`、`Input`、`Button`、`Label`

### 3.2 注册页 `/register`

目标：创建普通用户账号。

页面模块：

- 用户名、邮箱、密码、确认密码
- 注册按钮
- 注册结果反馈（shadcn/ui `Toast`）

接口映射：

- `POST /api/v1/admin/auth/register`

React 组件：

- `RegisterPage` -> `pages/Auth/RegisterPage.tsx`
- 使用 `react-hook-form` + `zod` 做表单校验

### 3.3 智能问答页 `/app/chat`

目标：作为核心工作台，承载提问、流式回答、来源展示、意图提示、会话切换、转工单。

建议页面布局（三栏）：

```
+--------------------+--------------------------+------------------+
| ConversationList   | ChatArea                 | InfoPanel        |
| - 新建会话按钮     | - 会话标题               | - 意图标签       |
| - 会话列表         | - MessageList            | - 来源卡片       |
|                    | - SourceChips            | - 快捷创建工单   |
|                    | - ChatInput + 发送/停止  |                  |
+--------------------+--------------------------+------------------+
```

接口映射：

- `GET /api/v1/chat/conversations` — 会话列表
- `POST /api/v1/chat/conversations` — 新建会话
- `GET /api/v1/chat/conversations/{id}/messages` — 历史消息
- `WS /api/v1/chat/ws/{token}` — 流式聊天

核心交互流程：

1. 首次进入页面，拉取会话列表
2. 用户点击某个会话，加载历史消息
3. 用户发送消息后，走 WebSocket 流式接收
4. 服务端返回 `intent` 时，在 InfoPanel 展示意图标签
5. 服务端返回 `source` 或 `message_end` 时，展示知识来源
6. 用户点击"停止回答"发送 `cancel`

React 组件：

| 组件 | 文件路径 | 说明 |
|------|----------|------|
| `ChatPage` | `pages/App/ChatPage.tsx` | 页面容器，三栏布局 |
| `ConversationList` | `components/chat/ConversationList.tsx` | 会话列表 |
| `MessageList` | `components/chat/MessageList.tsx` | 消息流 |
| `MessageBubble` | `components/chat/MessageBubble.tsx` | 单条消息气泡 |
| `ChatInput` | `components/chat/ChatInput.tsx` | 输入框 + 发送/停止 |
| `SourceChips` | `components/chat/SourceChips.tsx` | 来源引用卡片 |
| `IntentBadge` | `components/chat/IntentBadge.tsx` | 意图标签 |

设计注意点：

- `conversation_id` 可以为空，后端会自动创建新会话
- 但为了让左侧列表体验更稳定，建议前端点击"新建会话"时先调用 `POST /conversations`
- 当前后端已支持会话重命名、删除、归档，前端下一步可在会话列表中补齐对应入口
- 当前没有消息分页接口，长会话需要前端考虑虚拟滚动

### 3.4 工单创建弹窗

目标：把聊天过程中无法解决的问题转成工单。

推荐挂载位置：

- 聊天页 InfoPanel 中的"创建工单"按钮
- 聊天页回答失败后引导

页面模块：

- 工单类型、标题、问题描述、优先级
- 关联会话 ID（自动填充）
- 附加内容 JSON 录入区

接口映射：

- `POST /api/v1/tickets`

React 组件：

- `CreateTicketDialog` -> `components/ticket/CreateTicketDialog.tsx`
- 使用 shadcn/ui `Dialog`、`Select`、`Textarea`

### 3.5 我的工单列表页 `/app/tickets`

目标：让当前登录用户查看自己的工单处理状态。

页面模块：

- 状态筛选（shadcn/ui `Tabs` 或 `Select`）
- 工单列表（shadcn/ui `Table`）
- 加载更多按钮（当前 `total` 不准确，不用分页器）

接口映射：

- `GET /api/v1/tickets?limit=&offset=`

列表字段：标题、类型、状态（`Badge`）、优先级、创建时间、关联会话

React 组件：

- `TicketsPage` -> `pages/App/TicketsPage.tsx`

说明：

- 当前接口只返回"当前用户自己的工单"
- `total` 已返回真实总数，前端可按分页器或"加载更多"两种方式实现

### 3.6 工单详情页 `/app/tickets/:ticketId`

目标：查看工单详情与状态变化。

页面模块：

- 基本信息卡片
- 问题描述
- 附加内容展示
- 关联会话跳转入口
- 状态修改（仅 agent/admin）

接口映射：

- `GET /api/v1/tickets/{ticket_id}`
- `PUT /api/v1/tickets/{ticket_id}`

React 组件：

- `TicketDetailPage` -> `pages/App/TicketDetailPage.tsx`

权限边界：

- 普通用户可关闭自己的工单
- agent/admin 可修改状态：`pending` → `processing` → `resolved` → `closed`

### 3.7 管理看板 `/admin/dashboard`

目标：展示系统总体运行情况。

页面模块：

- 核心指标卡片（4 宫格）
- 工单状态分布图
- 意图分布图
- 平均置信度

接口映射：

- `GET /api/v1/admin/analytics`

字段映射：

- `total_conversations` / `total_messages` / `total_tickets` / `total_documents`
- `tickets_by_status` — 环形图或横向柱状图
- `intent_distribution` — 柱状图
- `avg_confidence` — 数字卡片

React 组件：

- `DashboardPage` -> `pages/Admin/DashboardPage.tsx`
- `StatCard` -> `components/common/StatCard.tsx`
- 图表推荐：`recharts`（轻量、React 原生）

### 3.8 文档管理页 `/admin/documents`

目标：管理知识库文档的上传、索引、筛选与删除。

页面模块：

- 顶部上传区（`Dialog` + 文件拖拽）
- 状态筛选 Tabs
- 文档列表表格
- 行内操作（重建索引、删除）

接口映射：

- `GET /api/v1/admin/documents`
- `POST /api/v1/embedding/documents`（`multipart/form-data`）
- `POST /api/v1/embedding/documents/{doc_id}/reindex`
- `DELETE /api/v1/admin/documents/{doc_id}`

列表字段：标题、来源、文件名、状态、分块数、创建时间、索引时间

权限：

- `agent/admin` 都可上传文档
- 只有 `admin` 显示删除和重建索引按钮

React 组件：

- `DocumentsPage` -> `pages/Admin/DocumentsPage.tsx`
- `UploadDocumentDialog` -> `components/document/UploadDocumentDialog.tsx`

### 3.9 意图配置页 `/admin/intents`

目标：管理 Agent 的意图识别配置。

页面模块：

- 意图列表（shadcn/ui `Table`）
- 新建/编辑意图弹窗（shadcn/ui `Dialog` + `Sheet`）

接口映射：

- `GET /api/v1/admin/intents`
- `POST /api/v1/admin/intents`
- `PUT /api/v1/admin/intents/{config_id}`
- `DELETE /api/v1/admin/intents/{config_id}`

表单字段：`name`、`display_name`、`description`、`route_target`、`keywords`、`examples`、`confidence_threshold`、`is_active`、`priority`

设计注意点：

- 当前列表接口只返回 `is_active = true` 的配置
- 删除按钮仅对 `admin` 展示
- `keywords`、`examples` 在响应里是 `dict | null`，前端需要兼容

React 组件：

- `IntentsPage` -> `pages/Admin/IntentsPage.tsx`
- `IntentFormDialog` -> `components/intent/IntentFormDialog.tsx`

## 4. 全局前端模块

### 4.1 鉴权模块

| 模块 | 位置 | 说明 |
|------|------|------|
| Auth Store | `stores/authStore.ts` | Zustand store，管理 token/user/role |
| JWT 解析 | `services/jwt.ts` | 解码 JWT payload，提取 sub/role/exp |
| Route Guard | `router/guards.tsx` | React Router loader/组件，检查登录态和角色 |
| API Client | `services/api.ts` | fetch 封装，自动挂 `Authorization: Bearer` |

### 4.2 WebSocket 会话模块

| 模块 | 位置 | 说明 |
|------|------|------|
| useWebSocket | `hooks/useWebSocket.ts` | 自定义 Hook：连接、心跳、重连、消息分发 |
| Chat Store | `stores/chatStore.ts` | Zustand store：会话列表、消息、流式 token 聚合 |
| Protocol Types | `types/chat.ts` | ClientMessage / ServerMessage TypeScript 类型 |

### 4.3 API 请求模块

| 模块 | 位置 | 说明 |
|------|------|------|
| apiClient | `services/api.ts` | 统一请求封装，处理 401 跳登录 |
| API Types | `types/api.ts` | `APIResponse<T>`、`PaginatedResponse<T>` |
| Service 层 | `services/*.ts` | 按领域拆分：auth、chat、ticket、document、admin |

### 4.4 通用 UI 组件

基于 shadcn/ui 扩展的业务组件：

| 组件 | 说明 |
|------|------|
| `AppLayout` | 应用主框架：侧边栏 + 顶栏 + 内容区 |
| `AppSidebar` | 角色感知的侧边导航 |
| `PageHeader` | 页面标题 + 面包屑 |
| `StatCard` | 统计数字卡片 |
| `StatusBadge` | 状态标签（工单/文档状态） |
| `EmptyState` | 空状态占位 |
| `ConfirmDialog` | 确认操作弹窗 |

## 5. 导航结构

### 用户端导航

- 智能问答 (`/app/chat`)
- 我的工单 (`/app/tickets`)

### 管理端导航

- 数据看板 (`/admin/dashboard`)
- 文档管理 (`/admin/documents`)
- 意图配置 (`/admin/intents`)

说明：

- `agent` 和 `admin` 仍然保留"智能问答"入口
- 根据 JWT 中的 `role` 动态展示菜单项
- 用户端和管理端共用 `AppLayout`，侧边栏按角色渲染不同菜单

## 6. 页面优先级

### P0：必须先做

- 登录页
- 智能问答页（核心工作台）
- 我的工单列表页
- 工单详情页
- 管理看板
- 文档管理页

### P1：第二批

- 注册页
- 意图配置页
- 聊天页中的工单创建弹窗

### P2：依赖后端补充后再做

- 会话管理 UI（重命名/删除/归档入口）
- 工单管理总览（管理端）
- 文档预览页
- 用户管理页
- 更完整的意图配置中心

## 7. 后端缺口清单

如果希望前端页面更完整，建议后端补充以下接口：

1. **文档详情接口** — 元数据详情、原文预览、下载地址
2. **用户管理接口** — 用户列表、禁用、角色变更
3. **意图配置完整列表** — 当前列表仍偏向激活项管理场景

## 8. 开发任务拆分

按模块独立开发，每个模块包含：页面 + 组件 + Store + Service + 类型定义

1. 鉴权与路由守卫
2. AppLayout + 导航
3. 聊天工作台（含 WebSocket）
4. 工单模块
5. 管理看板
6. 文档管理
7. 意图配置
