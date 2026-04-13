# AskFlow Frontend Tech Stack

> Last updated: 2026-04-06

## Core Dependencies

| Category | Library | Notes |
|----------|---------|-------|
| UI runtime | React 19 | application UI |
| Build tool | Vite 6 | local dev server and production build |
| Language | TypeScript 5.7 | strict typing |
| Router | React Router 7 | `createBrowserRouter`, guards, navigation |
| State | Zustand 5 | auth, chat, ticket, admin state |
| Forms | `react-hook-form`, `zod` | installed; current pages still use local state for most forms |
| Charts | Recharts 2 | admin dashboard charts |
| Icons | Lucide React | page and action icons |
| Styling | Tailwind CSS 4 | utility classes and design tokens |

## Styling Model

The frontend currently uses:

- Tailwind utility classes directly in components
- CSS custom properties in `web/src/styles/globals.css`
- theme tokens that resemble shadcn-style naming

What it does not currently use:

- a generated `components/ui/` directory
- a large shared component library

In other words, the project borrows token conventions from shadcn-style setups, but most UI is hand-built in page and feature components.

## Project Conventions

- file names:
  - pages/components: `PascalCase`
  - hooks/stores/services/types modules: `camelCase`
- imports:
  - use `@/` aliases for `web/src/*`
- syntax:
  - double quotes
  - semicolons
  - named exports are used broadly, including page modules
- routing:
  - `web/src/router/index.tsx` owns route definitions
  - `web/src/router/guards.tsx` owns auth/role guards
- API access:
  - `web/src/services/api.ts` wraps `fetch`
  - attaches bearer token automatically
  - clears auth state on `401`
- persistence:
  - `authStore` uses Zustand `persist` with key `askflow-auth`

## State Ownership

| State Type | Owner |
|------------|-------|
| auth token, role, user id | `authStore.ts` |
| conversations, messages, streaming state | `chatStore.ts` |
| ticket list and selected ticket | `ticketStore.ts` |
| analytics, documents, intents | `adminStore.ts` |
| transient form fields | component-local `useState` |

## WebSocket Ownership

`web/src/hooks/useWebSocket.ts` owns:

- socket lifecycle
- heartbeat timers
- reconnect backoff
- mapping server events into chat-store actions

`chatStore.ts` owns:

- conversation list
- cached message history
- streaming token accumulation
- intent/source side-panel state

## Current Technical Gaps

1. No frontend test runner is configured yet
2. The production build still emits a large-chunk warning
3. Forms are not yet standardized on `react-hook-form` despite the dependency being present
4. Some frontend document typings do not match the backend schema exactly
