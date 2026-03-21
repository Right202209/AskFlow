import { state, persistSession, loadStoredConversations } from "./state.js";
import { apiRequest, isStaffRole } from "./api.js";
import { pushToast, setStatus } from "./toast.js";
import { connectWS, clearWS } from "./ws.js";
import { decodeJwtPayload } from "./dom.js";
import { emit, on } from "./events.js";
import { isPortalPage, isWorkspacePage, isAdminWorkspacePage, isUserWorkspacePage, workspaceUrlForRole, portalUrl } from "./page.js";

const el = {};

export function initAuth() {
    Object.assign(el, {
        authForm: document.getElementById("authForm"),
        authTitle: document.getElementById("authTitle"),
        authModeToggle: document.getElementById("authModeToggle"),
        authSubmitBtn: document.getElementById("authSubmitBtn"),
        username: document.getElementById("username"),
        email: document.getElementById("email"),
        emailField: document.getElementById("emailField"),
        password: document.getElementById("password"),
        userSummary: document.getElementById("userSummary"),
        userNameText: document.getElementById("userNameText"),
        userRolePill: document.getElementById("userRolePill"),
        logoutBtn: document.getElementById("logoutBtn"),
    });

    if (el.authForm) {
        el.authForm.addEventListener("submit", handleAuthSubmit);
    }
    if (el.authModeToggle) {
        el.authModeToggle.addEventListener("click", toggleAuthMode);
    }
    if (el.logoutBtn) {
        el.logoutBtn.addEventListener("click", logout);
    }

    on("auth:expired", () => logout());
}

function toggleAuthMode() {
    state.authMode = state.authMode === "login" ? "register" : "login";
    applyAuthMode();
}

export function applyAuthMode() {
    if (!el.authTitle || !el.authSubmitBtn || !el.authModeToggle || !el.emailField) return;
    const isRegister = state.authMode === "register";
    el.authTitle.textContent = isRegister ? "注册" : "登录";
    el.authSubmitBtn.textContent = isRegister ? "创建账号" : "登录并连接";
    el.authModeToggle.textContent = isRegister ? "切换到登录" : "切换到注册";
    el.emailField.classList.toggle("hidden", !isRegister);
}

async function handleAuthSubmit(event) {
    event.preventDefault();
    if (state.authMode === "register") {
        await register();
        return;
    }
    await login();
}

async function register() {
    const username = el.username.value.trim();
    const email = el.email.value.trim();
    const password = el.password.value;

    if (!username || !email || !password) {
        pushToast("注册需要填写用户名、邮箱和密码。", "error");
        return;
    }

    try {
        await apiRequest("/api/v1/admin/auth/register", {
            method: "POST",
            auth: false,
            body: { username, email, password },
        });
        pushToast("注册成功，请直接登录。", "success");
        state.authMode = "login";
        applyAuthMode();
        setStatus("注册完成，请登录。");
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`注册失败: ${error.message}`);
    }
}

async function login() {
    if (!el.username || !el.password) return;
    const username = el.username.value.trim();
    const password = el.password.value;

    if (!username || !password) {
        pushToast("请输入用户名和密码。", "error");
        return;
    }

    try {
        const data = await apiRequest("/api/v1/admin/auth/login", {
            method: "POST",
            auth: false,
            body: { username, password },
        });
        state.token = data.access_token;
        const payload = decodeJwtPayload(data.access_token);
        state.user = {
            username,
            role: payload.role || "user",
            userId: payload.sub || "",
        };
        state.conversations = loadStoredConversations();
        persistSession();

        if (isPortalPage()) {
            window.location.replace(workspaceUrlForRole(state.user.role));
            return;
        }

        updateAuthUI();
        setRoleCapabilities();
        emit("app:login");
        setStatus(`已登录为 ${username}，正在连接 WebSocket。`);
        await bootstrapApp(false);
        pushToast(`欢迎，${username}`, "success");
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`登录失败: ${error.message}`);
    }
}

export async function bootstrapApp(silent) {
    updateAuthUI();
    setRoleCapabilities();
    if (!silent) setStatus("正在初始化页面数据。");

    try {
        await connectWS();
    } catch (error) {
        pushToast("WebSocket 连接失败，系统会自动重连。", "error");
    }

    emit("app:bootstrap");
}

export function logout() {
    state.token = null;
    state.user = null;
    state.conversationSearch = "";
    state.conversationOnlyActive = false;
    state.ticketSearch = "";
    state.ticketStatusFilter = "";
    state.documentSearch = "";
    state.documentVisibleCount = 12;
    state.documentPageIncrement = 12;
    state.intentSearch = "";
    state.ticketPageSize = 20;
    state.ticketPageIncrement = 20;
    state.ticketReachedEnd = false;
    state.conversationId = null;
    state.conversations = [];
    state.messages = [];
    state.tickets = [];
    state.documentDetailId = null;
    state.documentDetailShowRaw = false;
    state.ticketDetail = null;
    state.ticketDetailInitial = null;
    state.documents = [];
    state.intents = [];
    state.intentImportPreview = null;
    state.intentFormInitial = null;
    state.intentDraftScope = "new";
    state.analytics = null;
    state.stream = null;
    state.pendingConversationTitle = "";

    persistSession();
    clearWS();
    updateAuthUI();
    setRoleCapabilities();
    emit("app:logout");
    setStatus("已退出登录。");
    pushToast("会话已清除。", "success");

    if (isWorkspacePage()) {
        window.location.replace(portalUrl());
    }
}

export function updateAuthUI() {
    const loggedIn = Boolean(state.token && state.user);
    el.authForm?.classList.toggle("hidden", loggedIn);
    el.authModeToggle?.classList.toggle("hidden", loggedIn);
    el.userSummary?.classList.toggle("hidden", !loggedIn);
    el.logoutBtn?.classList.toggle("hidden", !loggedIn);

    if (loggedIn && el.userNameText && el.userRolePill) {
        el.userNameText.textContent = state.user.username;
        el.userRolePill.textContent = state.user.role;
    }
}

export function setRoleCapabilities() {
    const canAccessStaffViews = isStaffRole();
    document.querySelectorAll(".admin-only").forEach((node) => {
        node.classList.toggle("hidden", !canAccessStaffViews);
    });
    emit("auth:roleChanged");
}

export function syncPageAccess() {
    if (!state.token || !state.user) {
        if (isWorkspacePage()) {
            window.location.replace(portalUrl());
            return false;
        }
        return true;
    }

    const workspaceUrl = workspaceUrlForRole(state.user.role);
    if (isPortalPage()) {
        window.location.replace(workspaceUrl);
        return false;
    }

    if (isAdminWorkspacePage() && !isStaffRole()) {
        window.location.replace(workspaceUrl);
        return false;
    }

    if (isUserWorkspacePage() && isStaffRole()) {
        window.location.replace(workspaceUrl);
        return false;
    }

    return true;
}
