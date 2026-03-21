import { restoreSession, VIEW_KEY, state } from "./state.js";
import { getDefaultView, isAdminWorkspacePage } from "./page.js";
import { initToast, setStatus } from "./toast.js";
import { initWS } from "./ws.js";
import { initRouter, setView } from "./router.js";
import { initShell } from "./shell.js";
import { initAuth, updateAuthUI, bootstrapApp, syncPageAccess } from "./auth.js";
import { initChat } from "./views/chat.js";
import { initTickets } from "./views/tickets.js";
import { initDocuments } from "./views/documents.js";
import { initIntents } from "./views/intents.js";
import { initAnalytics } from "./views/analytics.js";
import { initTools } from "./views/tools.js";

document.addEventListener("DOMContentLoaded", () => {
    state.activeView = localStorage.getItem(VIEW_KEY) || getDefaultView();

    initToast();
    initWS();
    initRouter();
    initShell();
    initAuth();
    initChat();
    initTickets();
    initTools();

    if (isAdminWorkspacePage()) {
        initDocuments();
        initIntents();
        initAnalytics();
    }

    restoreSession();
    if (!syncPageAccess()) return;

    updateAuthUI();
    setView(state.activeView);

    if (state.token) {
        bootstrapApp(true).catch(() => {});
    } else {
        setStatus("会话不存在，正在返回登录页。");
    }
});
