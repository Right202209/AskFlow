import { Outlet, NavLink, useNavigate } from "react-router";
import {
  MessageSquare,
  Ticket,
  BarChart3,
  FileText,
  Settings,
  LogOut,
} from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { cn } from "@/lib/utils";

const allMenuItems = [
  { label: "智能问答", path: "/app/chat", icon: MessageSquare },
  { label: "我的工单", path: "/app/tickets", icon: Ticket },
  { label: "数据看板", path: "/admin/dashboard", icon: BarChart3, roles: ["agent", "admin"] },
  { label: "文档管理", path: "/admin/documents", icon: FileText, roles: ["agent", "admin"] },
  { label: "意图配置", path: "/admin/intents", icon: Settings, roles: ["agent", "admin"] },
] as const;

export function AppLayout() {
  const { username, role, logout } = useAuthStore();
  const navigate = useNavigate();

  const menuItems = allMenuItems.filter(
    (item) => !("roles" in item) || (role && (item.roles as readonly string[]).includes(role)),
  );

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="flex w-60 flex-col border-r bg-sidebar">
        <div className="flex h-14 items-center border-b px-4">
          <span className="text-lg font-semibold">AskFlow</span>
        </div>

        <nav className="flex-1 space-y-1 p-2">
          {menuItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t p-3">
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{username}</p>
              <p className="text-xs text-muted-foreground">{role}</p>
            </div>
            <button
              onClick={handleLogout}
              className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
              title="退出登录"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
