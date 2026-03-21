import { restoreSession, VIEW_KEY } from "./state.js";
import { initToast, setStatus } from "./toast.js";
import { initWS } from "./ws.js";
import { initRouter, setView } from "./router.js";
import { initAuth, applyAuthMode, updateAuthUI, bootstrapApp } from "./auth.js";
import { initChat } from "./views/chat.js";
import { initTickets } from "./views/tickets.js";
import { initDocuments } from "./views/documents.js";
import { initIntents } from "./views/intents.js";
import { initAnalytics } from "./views/analytics.js";
import { initTools } from "./views/tools.js";
import { state } from "./state.js";

document.addEventListener("DOMContentLoaded", () => {
    initToast();
    initWS();
    initRouter();
    initAuth();
    initChat();
    initTickets();
    initDocuments();
    initIntents();
    initAnalytics();
    initTools();

    restoreSession();
    setView(localStorage.getItem(VIEW_KEY) || "chat");
    applyAuthMode();
    updateAuthUI();

    if (state.token) {
        bootstrapApp(true).catch(() => {});
    } else {
        setStatus("等待登录。");
    }
});
