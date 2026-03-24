import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { router } from "@/router";
import { configureApiClient } from "@/services/api";
import { useAuthStore } from "@/stores/authStore";
import "@/styles/globals.css";

configureApiClient({
  getToken: () => useAuthStore.getState().token,
  onUnauthorized: () => {
    useAuthStore.getState().logout();
    if (window.location.pathname !== "/login") {
      router.navigate("/login", { replace: true });
    }
  },
});

function App() {
  return <RouterProvider router={router} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
