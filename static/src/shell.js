import { state, VIEW_META } from "./state.js";
import { on } from "./events.js";

const el = {};

export function initShell() {
    Object.assign(el, {
        heroSession: document.getElementById("heroSession"),
        heroSocket: document.getElementById("heroSocket"),
        heroConversationCount: document.getElementById("heroConversationCount"),
        heroTicketCount: document.getElementById("heroTicketCount"),
        heroWorkspace: document.getElementById("heroWorkspace"),
        heroStatusBadge: document.getElementById("heroStatusBadge"),
    });

    on("app:login", renderShell);
    on("app:logout", renderShell);
    on("app:bootstrap", renderShell);
    on("auth:roleChanged", renderShell);
    on("ws:stateChange", renderShell);
    on("analytics:updateSummary", renderShell);
    on("view:changed", renderShell);

    renderShell();
}

function renderShell() {
    const viewMeta = VIEW_META[state.activeView] || VIEW_META.chat;
    const role = state.user?.role || "guest";
    const sessionLabel = state.user ? state.user.username : "Guest";
    const socketLabel = connectionLabel(state.connectionState);

    el.heroSession.textContent = sessionLabel;
    el.heroSocket.textContent = socketLabel;
    el.heroConversationCount.textContent = String(state.conversations.length);
    el.heroTicketCount.textContent = String(state.tickets.length);
    el.heroWorkspace.textContent = viewMeta.title;
    el.heroStatusBadge.textContent = role;
    el.heroStatusBadge.dataset.state = state.connectionState;
}

function connectionLabel(kind) {
    if (kind === "connected") return "Online";
    if (kind === "connecting") return "Connecting";
    if (kind === "error") return "Interrupted";
    return "Idle";
}
