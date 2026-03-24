import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { router } from "@/router";
import { configureApiClient } from "@/services/api";
import { useAuthStore } from "@/stores/authStore";
import "@/styles/globals.css";

function App() {
  const logout = useAuthStore((s) => s.logout);

  useEffect(() => {
    configureApiClient({
      getToken: () => useAuthStore.getState().token,
      onUnauthorized: () => {
        logout();
        window.location.href = "/login";
      },
    });
  }, [logout]);

  return <RouterProvider router={router} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
