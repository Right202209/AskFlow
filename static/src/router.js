import { state, VIEW_META, VIEW_KEY } from "./state.js";
import { setStatus, pushToast } from "./toast.js";
import { isStaffRole } from "./api.js";
import { emit } from "./events.js";

let viewTitleEl = null;
let viewHintEl = null;

export function initRouter() {
    viewTitleEl = document.getElementById("viewTitle");
    viewHintEl = document.getElementById("viewHint");

    document.getElementById("navList").addEventListener("click", handleNavClick);
    document.getElementById("refreshCurrentViewBtn").addEventListener("click", refreshCurrentView);
}

function handleNavClick(event) {
    const button = event.target.closest("[data-view]");
    if (!button) return;

    const view = button.dataset.view;
    if ((view === "documents" || view === "intents" || view === "analytics") && !isStaffRole()) {
        pushToast("当前角色无权限访问该页面。", "error");
        return;
    }
    setView(view);
}

export function setView(view) {
    if (!VIEW_META[view]) return;

    if ((view === "documents" || view === "intents" || view === "analytics") && !isStaffRole()) {
        view = "chat";
    }

    state.activeView = view;
    localStorage.setItem(VIEW_KEY, view);

    document.querySelectorAll(".view").forEach((node) => {
        node.classList.toggle("active", node.id === `view-${view}`);
    });
    document.querySelectorAll(".nav-item").forEach((node) => {
        node.classList.toggle("active", node.dataset.view === view);
    });

    viewTitleEl.textContent = VIEW_META[view].title;
    viewHintEl.textContent = VIEW_META[view].hint;
}

function refreshCurrentView() {
    if (state.activeView === "tools") {
        setStatus("工具页无需统一刷新，请按表单单独触发接口。");
        return;
    }
    emit("view:refresh", state.activeView);
}
