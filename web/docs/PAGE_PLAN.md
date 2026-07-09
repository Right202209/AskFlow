# AskFlow Frontend Page Plan

> Last updated: 2026-04-06

This file now reflects the current implementation rather than an aspirational page list.

## Current Scope

The frontend already covers three areas:

- Public auth pages
- User workspace under `/app/*`
- Staff/admin workspace under `/admin/*`

## Route Inventory

| Route | Page | Status | Main File |
|-------|------|--------|-----------|
| `/login` | Login | Implemented | `web/src/pages/Auth/LoginPage.tsx` |
| `/register` | Register | Implemented | `web/src/pages/Auth/RegisterPage.tsx` |
| `/app/chat` | Chat workspace | Implemented | `web/src/pages/App/ChatPage.tsx` |
| `/app/chat/:conversationId` | Chat workspace for a selected conversation | Implemented | `web/src/pages/App/ChatPage.tsx` |
| `/app/tickets` | My tickets | Implemented | `web/src/pages/App/TicketsPage.tsx` |
| `/app/tickets/:ticketId` | Ticket detail | Implemented | `web/src/pages/App/TicketDetailPage.tsx` |
| `/admin/dashboard` | Analytics dashboard | Implemented | `web/src/pages/Admin/DashboardPage.tsx` |
| `/admin/documents` | Document management | Implemented | `web/src/pages/Admin/DocumentsPage.tsx` |
| `/admin/intents` | Intent management | Implemented | `web/src/pages/Admin/IntentsPage.tsx` |

## Page Notes

### Login

- Submits to `POST /api/v1/admin/auth/login`
- Stores the JWT in `authStore`
- Redirects to `/app/chat`

Known limitation:

- login does not yet branch by role after success; staff users also land on `/app/chat`

### Register

- Submits to `POST /api/v1/admin/auth/register`
- Redirects back to `/login` on success

Known limitation:

- no toast or richer success feedback; errors render inline only

### Chat Workspace

Main composition:

- `ConversationList`
- `MessageList`
- `ChatComposer`
- `ChatInfoPanel`
- `CreateTicketDialog`

Implemented behavior:

- fetches conversations and message history
- opens a WebSocket session using the current JWT
- streams assistant tokens
- shows intent and source cards
- can create a ticket from the current conversation

Known limitations:

- no rename/archive/delete UI for conversations yet
- no global notification system for WebSocket errors or ticket success
- info panel is hidden on smaller viewports

### Tickets

Implemented behavior:

- list user tickets with client-side status filtering
- show ticket detail
- allow staff to update status
- allow normal users to close their own ticket

Known limitation:

- there is no staff-facing all-tickets page in the frontend yet, even though the backend exposes `GET /api/v1/admin/tickets`

### Dashboard

Implemented behavior:

- loads counts, ticket status distribution, intent distribution, and average confidence
- renders charts with Recharts

Known limitation:

- only exposes aggregate metrics; no drill-down or operational timeline views

### Documents

Implemented behavior:

- upload document
- filter the current list by status in the UI
- reindex and delete when the user is an admin

Known limitations:

- no preview/download flow
- frontend document types currently do not align with backend document status/schema exactly and should be corrected

### Intents

Implemented behavior:

- list intent configs
- inline create/edit modal for admins

Known limitations:

- no delete action in the current UI
- keywords, examples, and activation state are not editable from the current modal

## Shared Frontend Modules

| Area | Files |
|------|-------|
| Layout | `web/src/components/layout/AppLayout.tsx` |
| Auth state | `web/src/stores/authStore.ts` |
| Chat state | `web/src/stores/chatStore.ts` |
| Ticket state | `web/src/stores/ticketStore.ts` |
| Admin state | `web/src/stores/adminStore.ts` |
| WebSocket | `web/src/hooks/useWebSocket.ts` |
| API wrappers | `web/src/services/*.ts` |

## Highest-Priority Next UI Work

1. Add frontend tests for `useWebSocket`, `CreateTicketDialog`, and ticket detail permissions
2. Add conversation actions for rename/archive/delete
3. Add a staff ticket overview page using `/api/v1/admin/tickets`
4. Align document types with backend responses
5. Add toast/notification support
