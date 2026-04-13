import { createBrowserRouter, Navigate } from "react-router";
import { RequireAuth, RequireRole } from "./guards";
import { AppLayout } from "@/components/layout/AppLayout";
import { LoginPage } from "@/pages/Auth/LoginPage";
import { RegisterPage } from "@/pages/Auth/RegisterPage";
import { ChatPage } from "@/pages/App/ChatPage";
import { TicketsPage } from "@/pages/App/TicketsPage";
import { TicketDetailPage } from "@/pages/App/TicketDetailPage";
import { DashboardPage } from "@/pages/Admin/DashboardPage";
import { DocumentsPage } from "@/pages/Admin/DocumentsPage";
import { IntentsPage } from "@/pages/Admin/IntentsPage";
import { TicketsOverviewPage } from "@/pages/Admin/TicketsOverviewPage";

export const router = createBrowserRouter([
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
          { path: "/admin/tickets", element: <TicketsOverviewPage /> },
          { path: "/admin/documents", element: <DocumentsPage /> },
          { path: "/admin/intents", element: <IntentsPage /> },
        ],
      },
    ],
  },
  { path: "/", element: <Navigate to="/app/chat" replace /> },
]);
