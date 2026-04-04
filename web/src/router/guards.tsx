import { Navigate, Outlet, useLocation } from "react-router";
import { isTokenExpired } from "@/services/jwt";
import { useAuthStore } from "@/stores/authStore";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((state) => state.token);
  const location = useLocation();
  const isAuthenticated = token !== null && !isTokenExpired(token);

  if (!isAuthenticated) {
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
