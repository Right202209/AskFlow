# AskFlow Frontend Routes and Composition

> Last updated: 2026-04-06

This document reflects the actual router and component structure in `web/src/`.

## Router Table

| Route | Guard | Page |
|-------|-------|------|
| `/login` | none | `LoginPage` |
| `/register` | none | `RegisterPage` |
| `/app/chat` | `RequireAuth` | `ChatPage` |
| `/app/chat/:conversationId` | `RequireAuth` | `ChatPage` |
| `/app/tickets` | `RequireAuth` | `TicketsPage` |
| `/app/tickets/:ticketId` | `RequireAuth` | `TicketDetailPage` |
| `/admin/dashboard` | `RequireAuth` + `RequireRole(["agent", "admin"])` | `DashboardPage` |
| `/admin/documents` | `RequireAuth` + `RequireRole(["agent", "admin"])` | `DocumentsPage` |
| `/admin/intents` | `RequireAuth` + `RequireRole(["agent", "admin"])` | `IntentsPage` |
| `/` | none | redirect to `/app/chat` |

There is currently no explicit not-found route.

## Router Shape

```tsx
createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
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
]);
```

## Layout Model

`AppLayout` is the shared shell for authenticated pages.

Current behavior:

- left sidebar only
- role-aware navigation
- username and role summary
- logout action
- no separate page header component

Sidebar entries:

- all users: chat, my tickets
- agent/admin only: dashboard, documents, intents

## Component Composition

### Chat

```text
ChatPage
├── ConversationList
├── MessageList
├── ChatComposer
├── ChatInfoPanel
└── CreateTicketDialog
```

### Tickets

```text
TicketsPage
└── table-based list

TicketDetailPage
└── inline status/edit panels
```

### Admin

```text
DashboardPage
└── inline StatCard helper + charts

DocumentsPage
└── table-based list + upload/reindex/delete actions

IntentsPage
└── table-based list + local IntentFormDialog
```

## State and Service Mapping

| Concern | Store / Service |
|---------|-----------------|
| auth | `authStore.ts`, `services/auth.ts`, `services/jwt.ts` |
| chat | `chatStore.ts`, `services/chat.ts`, `hooks/useWebSocket.ts` |
| tickets | `ticketStore.ts`, `services/ticket.ts` |
| admin analytics/intents | `adminStore.ts`, `services/admin.ts` |
| documents | `adminStore.ts`, `services/document.ts` |

## WebSocket Flow

`useWebSocket.ts` is responsible for:

- opening the socket from the current JWT
- ping/pong heartbeats every 30 seconds
- reconnect attempts with exponential backoff
- dispatching incoming server messages into `chatStore`

Handled server message types:

- `token`
- `message_end`
- `intent`
- `source`
- `error`
- `pong`

## Known Constraints

1. No not-found route
2. No global toast or notification layer
3. No frontend route for the admin all-tickets API
4. Document response types need alignment with backend schema
