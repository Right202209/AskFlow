# AskFlow 前端路由与组件架构

> 技术栈：React 19 + React Router v7 + Zustand + shadcn/ui + Tailwind CSS

## 1. 路由表

使用 React Router v7 的 `createBrowserRouter`，Vite dev server 代理 API 请求到后端。

| 路由 | 页面组件 | 权限 | 主要接口 |
|------|----------|------|----------|
| `/login` | `LoginPage` | 公开 | `POST /api/v1/admin/auth/login` |
| `/register` | `RegisterPage` | 公开 | `POST /api/v1/admin/auth/register` |
| `/app/chat` | `ChatPage` | 登录用户 | `GET/POST conversations`, `WS /ws/{token}` |
| `/app/chat/:conversationId` | `ChatPage` | 登录用户 | 同上 + `GET messages` |
| `/app/tickets` | `TicketsPage` | 登录用户 | `GET /api/v1/tickets` |
| `/app/tickets/:ticketId` | `TicketDetailPage` | 登录用户 | `GET/PUT /api/v1/tickets/{id}` |
| `/admin/dashboard` | `DashboardPage` | agent/admin | `GET /api/v1/admin/analytics` |
| `/admin/documents` | `DocumentsPage` | agent/admin | `GET docs`, `POST upload`, `DELETE` |
| `/admin/intents` | `IntentsPage` | agent/admin | `GET/POST/PUT intents` |

### 路由配置

```tsx
// router/index.tsx
const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/register",
    element: <RegisterPage />,
  },
  {
    element: <RequireAuth><AppLayout /></RequireAuth>,
    children: [
      { path: "/app/chat", element: <ChatPage /> },
      { path: "/app/chat/:conversationId", element: <ChatPage /> },
      { path: "/app/tickets", element: <TicketsPage /> },
      { path: "/app/tickets/:ticketId", element: <TicketDetailPage /> },
      {
        element: <RequireRole roles={["agent", "admin"]} />,
        children: [
          { path: "/admin/dashboard", element: <DashboardPage /> },
          { path: "/admin/documents", element: <DocumentsPage /> },
          { path: "/admin/intents", element: <IntentsPage /> },
        ],
      },
    ],
  },
  { path: "/", element: <Navigate to="/app/chat" replace /> },
  { path: "*", element: <NotFoundPage /> },
]);
```

### 路由守卫

```tsx
// router/guards.tsx

// 检查登录态，未登录重定向到 /login
function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const location = useLocation();
  if (!token) return <Navigate to="/login" state={{ from: location }} replace />;
  return <>{children}</>;
}

// 检查角色，不匹配重定向到 /app/chat
function RequireRole({ roles }: { roles: string[] }) {
  const role = useAuthStore((s) => s.role);
  if (!role || !roles.includes(role)) return <Navigate to="/app/chat" replace />;
  return <Outlet />;
}
```

## 2. 页面布局

### 鉴权页面（无框架）

```
+------------------------------------------------------+
|                                                      |
|              品牌标识 + 登录/注册卡片                 |
|                                                      |
+------------------------------------------------------+
```

### 应用主框架 `AppLayout`

```
+------------------+-----------------------------------+
| AppSidebar       | PageHeader                        |
|                  | - 面包屑 / 页面标题               |
| - 品牌标识       | - 用户头像 / 退出                 |
| - 导航菜单       +-----------------------------------+
| - 角色感知       |                                   |
|                  |         <Outlet />                |
|                  |         页面主内容区               |
|                  |                                   |
+------------------+-----------------------------------+
```

侧边栏菜单按角色动态渲染：

```tsx
const menuItems = [
  // 所有角色可见
  { label: "智能问答", path: "/app/chat", icon: MessageSquare },
  { label: "我的工单", path: "/app/tickets", icon: Ticket },
  // agent/admin 可见
  { label: "数据看板", path: "/admin/dashboard", icon: BarChart3, roles: ["agent", "admin"] },
  { label: "文档管理", path: "/admin/documents", icon: FileText, roles: ["agent", "admin"] },
  { label: "意图配置", path: "/admin/intents", icon: Settings, roles: ["agent", "admin"] },
];
```

### 聊天页三栏布局

```
+--------------------+--------------------------+------------------+
| ConversationList   | ChatArea                 | InfoPanel        |
| 240px fixed        | flex-1                   | 280px fixed      |
|                    |                          |                  |
| [+ 新建会话]       | 消息标题                 | 意图标签         |
| ─────────────      | ─────────────            | ─────────────    |
| 会话 1 (active)    | UserBubble               | 来源引用卡片     |
| 会话 2             | AssistantBubble          |   - 标题         |
| 会话 3             |   (流式渲染中...)        |   - 分数         |
|                    |                          |   - 摘要         |
|                    |                          | ─────────────    |
|                    | ─────────────            | [创建工单]       |
|                    | [输入框] [发送] [停止]   |                  |
+--------------------+--------------------------+------------------+
```

## 3. 组件树

```
App
├── RouterProvider
│   ├── LoginPage
│   │   └── LoginForm (Card + Input + Button)
│   ├── RegisterPage
│   │   └── RegisterForm (Card + Input + Button)
│   ├── RequireAuth
│   │   └── AppLayout
│   │       ├── AppSidebar
│   │       ├── PageHeader
│   │       └── Outlet
│   │           ├── ChatPage
│   │           │   ├── ConversationList
│   │           │   │   └── ConversationItem
│   │           │   ├── ChatArea
│   │           │   │   ├── MessageList
│   │           │   │   │   └── MessageBubble
│   │           │   │   │       └── SourceChips
│   │           │   │   └── ChatInput
│   │           │   └── InfoPanel
│   │           │       ├── IntentBadge
│   │           │       └── CreateTicketDialog
│   │           ├── TicketsPage
│   │           │   ├── TicketFilters (Tabs)
│   │           │   └── TicketTable
│   │           ├── TicketDetailPage
│   │           │   ├── TicketInfoCard
│   │           │   └── TicketStatusForm
│   │           ├── RequireRole
│   │           │   ├── DashboardPage
│   │           │   │   ├── StatCard (x4)
│   │           │   │   ├── TicketStatusChart
│   │           │   │   └── IntentDistributionChart
│   │           │   ├── DocumentsPage
│   │           │   │   ├── UploadDocumentDialog
│   │           │   │   ├── DocumentFilters (Tabs)
│   │           │   │   └── DocumentTable
│   │           │   └── IntentsPage
│   │           │       ├── IntentTable
│   │           │       └── IntentFormDialog
│   │           └── NotFoundPage
```

## 4. 状态管理 (Zustand)

### Auth Store

```tsx
// stores/authStore.ts
interface AuthState {
  token: string | null;
  username: string | null;
  role: "user" | "agent" | "admin" | null;
  userId: string | null;
  login: (token: string, username: string) => void;
  logout: () => void;
}
```

持久化：`zustand/middleware` 的 `persist`，存储到 `localStorage`，key = `askflow-auth`。

### Chat Store

```tsx
// stores/chatStore.ts
interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  messages: Record<string, Message[]>;       // conversationId -> messages
  streamingTokens: string;                   // 当前流式回答的累积文本
  isStreaming: boolean;
  intent: { label: string; confidence: number } | null;
  sources: Source[];

  // actions
  setConversations: (conversations: Conversation[]) => void;
  selectConversation: (id: string) => void;
  appendToken: (token: string) => void;
  finalizeMessage: () => void;
  setIntent: (intent: { label: string; confidence: number } | null) => void;
  setSources: (sources: Source[]) => void;
}
```

### Ticket Store

```tsx
// stores/ticketStore.ts
interface TicketState {
  tickets: Ticket[];
  currentTicket: Ticket | null;
  isLoading: boolean;
  fetchTickets: (params?: { limit?: number; offset?: number }) => Promise<void>;
  fetchTicket: (id: string) => Promise<void>;
}
```

### Admin Store

```tsx
// stores/adminStore.ts
interface AdminState {
  analytics: AnalyticsData | null;
  documents: Document[];
  intents: IntentConfig[];
  fetchAnalytics: () => Promise<void>;
  fetchDocuments: () => Promise<void>;
  fetchIntents: () => Promise<void>;
}
```

## 5. Service 层

```
services/
├── api.ts              # fetch 封装，挂 Bearer token，处理 401
├── auth.ts             # login(), register()
├── chat.ts             # getConversations(), createConversation(), getMessages()
├── ticket.ts           # getTickets(), getTicket(), createTicket(), updateTicket()
├── document.ts         # getDocuments(), uploadDocument(), reindexDocument(), deleteDocument()
├── admin.ts            # getAnalytics(), getIntents(), createIntent(), updateIntent()
└── jwt.ts              # decodeToken() — 解析 JWT payload（不验签）
```

### API Client 模式

```tsx
// services/api.ts
async function apiClient<T>(path: string, options?: RequestInit): Promise<T> {
  const token = useAuthStore.getState().token;
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (res.status === 401) {
    useAuthStore.getState().logout();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  const json = await res.json();
  if (!json.success) throw new Error(json.error || "Request failed");
  return json.data;
}
```

## 6. WebSocket Hook

```tsx
// hooks/useWebSocket.ts
function useWebSocket(token: string | null) {
  // 连接管理
  // 心跳 ping/pong（30 秒间隔）
  // 断线自动重连（指数退避，最大 5 次）
  // 消息分发到 chatStore

  // 暴露方法
  return {
    sendMessage: (conversationId: string, content: string) => void,
    cancelGeneration: () => void,
    isConnected: boolean,
  };
}
```

消息类型映射：

| 服务端消息类型 | 前端处理 |
|---------------|----------|
| `token` | `chatStore.appendToken(data.content)` |
| `message_end` | `chatStore.finalizeMessage()` |
| `error` | Toast 提示错误 |
| `intent` | `chatStore.setIntent(data)` |
| `source` | `chatStore.setSources(data.sources)` |
| `ticket` | Toast 提示 + 跳转工单详情 |
| `pong` | 重置心跳计时器 |

## 7. TypeScript 类型定义

```
types/
├── api.ts              # APIResponse<T>, PaginatedResponse<T>
├── auth.ts             # LoginRequest, LoginResponse, RegisterRequest
├── chat.ts             # Conversation, Message, ClientMessage, ServerMessage
├── ticket.ts           # Ticket, CreateTicketRequest, UpdateTicketRequest
├── document.ts         # Document, UploadDocumentRequest
├── intent.ts           # IntentConfig, CreateIntentRequest, UpdateIntentRequest
└── admin.ts            # AnalyticsData
```

## 8. 目录结构总览

```
web/src/
├── main.tsx                 # 入口
├── App.tsx                  # RouterProvider
├── router/
│   ├── index.tsx            # createBrowserRouter 配置
│   └── guards.tsx           # RequireAuth, RequireRole
├── pages/
│   ├── Auth/
│   │   ├── LoginPage.tsx
│   │   └── RegisterPage.tsx
│   ├── App/
│   │   ├── ChatPage.tsx
│   │   ├── TicketsPage.tsx
│   │   └── TicketDetailPage.tsx
│   ├── Admin/
│   │   ├── DashboardPage.tsx
│   │   ├── DocumentsPage.tsx
│   │   └── IntentsPage.tsx
│   └── NotFoundPage.tsx
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx
│   │   ├── AppSidebar.tsx
│   │   └── PageHeader.tsx
│   ├── chat/
│   │   ├── ConversationList.tsx
│   │   ├── ConversationItem.tsx
│   │   ├── MessageList.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── ChatInput.tsx
│   │   ├── SourceChips.tsx
│   │   ├── IntentBadge.tsx
│   │   └── InfoPanel.tsx
│   ├── ticket/
│   │   ├── TicketTable.tsx
│   │   ├── TicketFilters.tsx
│   │   ├── TicketInfoCard.tsx
│   │   ├── TicketStatusForm.tsx
│   │   └── CreateTicketDialog.tsx
│   ├── document/
│   │   ├── DocumentTable.tsx
│   │   ├── DocumentFilters.tsx
│   │   └── UploadDocumentDialog.tsx
│   ├── intent/
│   │   ├── IntentTable.tsx
│   │   └── IntentFormDialog.tsx
│   ├── common/
│   │   ├── StatCard.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── EmptyState.tsx
│   │   └── ConfirmDialog.tsx
│   └── ui/                  # shadcn/ui 生成的基础组件
│       ├── button.tsx
│       ├── card.tsx
│       ├── dialog.tsx
│       ├── input.tsx
│       ├── table.tsx
│       └── ...
├── hooks/
│   ├── useWebSocket.ts
│   └── useMediaQuery.ts
├── stores/
│   ├── authStore.ts
│   ├── chatStore.ts
│   ├── ticketStore.ts
│   └── adminStore.ts
├── services/
│   ├── api.ts
│   ├── auth.ts
│   ├── chat.ts
│   ├── ticket.ts
│   ├── document.ts
│   ├── admin.ts
│   └── jwt.ts
├── types/
│   ├── api.ts
│   ├── auth.ts
│   ├── chat.ts
│   ├── ticket.ts
│   ├── document.ts
│   ├── intent.ts
│   └── admin.ts
└── styles/
    └── globals.css          # Tailwind directives + CSS variables
```
