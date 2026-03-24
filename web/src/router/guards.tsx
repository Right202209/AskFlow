import { Navigate, Outlet, useLocation } from "react-router";
import { useAuthStore } from "@/stores/authStore";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const location = useLocation();

  if (!isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

export function RequireRole({ roles }: { roles: string[] }) {
  const role = useAuthStore((s) => s.role);

  if (!role || !roles.includes(role)) {
    return <Navigate to="/app/chat" replace />;
  }

  return <Outlet />;
}
