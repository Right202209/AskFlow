import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { ToastViewport } from "@/components/layout/ToastViewport";
import { router } from "@/router";
import { configureApiClient } from "@/services/api";
import { useAuthStore } from "@/stores/authStore";
import { toastError } from "@/stores/toastStore";
import "@/styles/globals.css";

configureApiClient({
  getToken: () => useAuthStore.getState().token,
  onUnauthorized: () => {
    useAuthStore.getState().logout();
    if (window.location.pathname !== "/login") {
      toastError("登录已失效", "请重新登录后继续操作。");
      router.navigate("/login", { replace: true });
    }
  },
});

function App() {
  return (
    <>
      <RouterProvider router={router} />
      <ToastViewport />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
