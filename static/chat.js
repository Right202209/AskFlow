const API_BASE = window.location.origin;
const SESSION_KEY = "askflow.session";
const VIEW_KEY = "askflow.view";
const INTENT_DRAFT_KEY = "askflow.intentDraft";

const VIEW_META = {
    chat: {
        title: "对话工作台",
        hint: "登录后可直接通过 WebSocket 发起流式会话。",
    },
    tickets: {
        title: "工单中心",
        hint: "提交问题工单，并追踪当前登录用户的工单状态。",
    },
    documents: {
        title: "知识库文档",
        hint: "上传、筛选和维护向量检索使用的知识文档。",
    },
    intents: {
        title: "意图配置",
        hint: "管理规则化意图定义，校准路由阈值和关键词样本。",
    },
    analytics: {
        title: "分析看板",
        hint: "查看对话量、消息量、工单状态和意图分布。",
    },
    tools: {
        title: "接口调试",
        hint: "直接调用 RAG 查询和意图分类接口，验证服务能力。",
    },
};

const state = {
    authMode: "login",
    token: null,
    user: null,
    ws: null,
    manualDisconnect: false,
    reconnectTimer: null,
    heartbeatTimer: null,
    activeView: "chat",
    conversationSearch: "",
    conversationOnlyActive: false,
    ticketSearch: "",
    ticketStatusFilter: "",
    documentSearch: "",
    documentVisibleCount: 12,
    documentPageIncrement: 12,
    intentSearch: "",
    ticketPageSize: 20,
    ticketPageIncrement: 20,
    ticketReachedEnd: false,
    conversationId: null,
    conversations: [],
    messages: [],
    tickets: [],
    documentDetailId: null,
    documentDetailShowRaw: false,
    ticketDetail: null,
    ticketDetailInitial: null,
    documents: [],
    intents: [],
    intentImportPreview: null,
    intentFormInitial: null,
    intentDraftScope: "new",
    analytics: null,
    stream: null,
    connectionState: "idle",
    pendingConversationTitle: "",
};

const el = {};

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    bindEvents();
    renderEmptyStates();
    restoreSession();
    setView(localStorage.getItem(VIEW_KEY) || "chat");
    applyAuthMode();
    updateAuthUI();
    renderConversationList();
    renderMessages();
    resetIntentForm({ restoreDraft: Boolean(state.user) });

    if (state.token) {
        bootstrapApp(true).catch(() => {});
    } else {
        setStatus("等待登录。");
    }
});

function cacheElements() {
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
        connectionDot: document.getElementById("connectionDot"),
        connectionText: document.getElementById("connectionText"),
        navList: document.getElementById("navList"),
        viewTitle: document.getElementById("viewTitle"),
        viewHint: document.getElementById("viewHint"),
        refreshCurrentViewBtn: document.getElementById("refreshCurrentViewBtn"),
        conversationList: document.getElementById("conversationList"),
        conversationSearch: document.getElementById("conversationSearch"),
        conversationOnlyActive: document.getElementById("conversationOnlyActive"),
        newConversationBtn: document.getElementById("newConversationBtn"),
        chatConversationTitle: document.getElementById("chatConversationTitle"),
        conversationMeta: document.getElementById("conversationMeta"),
        messages: document.getElementById("messages"),
        messageInput: document.getElementById("messageInput"),
        sendBtn: document.getElementById("sendBtn"),
        cancelBtn: document.getElementById("cancelBtn"),
        loadHistoryBtn: document.getElementById("loadHistoryBtn"),
        ticketForm: document.getElementById("ticketForm"),
        ticketType: document.getElementById("ticketType"),
        ticketTitle: document.getElementById("ticketTitle"),
        ticketDescription: document.getElementById("ticketDescription"),
        ticketPriority: document.getElementById("ticketPriority"),
        refreshTicketsBtn: document.getElementById("refreshTicketsBtn"),
        ticketListHint: document.getElementById("ticketListHint"),
        ticketSearch: document.getElementById("ticketSearch"),
        ticketStatusFilter: document.getElementById("ticketStatusFilter"),
        ticketList: document.getElementById("ticketList"),
        ticketListMeta: document.getElementById("ticketListMeta"),
        ticketLoadMoreBtn: document.getElementById("ticketLoadMoreBtn"),
        ticketLookupForm: document.getElementById("ticketLookupForm"),
        ticketLookupId: document.getElementById("ticketLookupId"),
        ticketLookupBtn: document.getElementById("ticketLookupBtn"),
        ticketDetailResetBtn: document.getElementById("ticketDetailResetBtn"),
        ticketDetailContainer: document.getElementById("ticketDetailContainer"),
        documentForm: document.getElementById("documentForm"),
        documentTitle: document.getElementById("documentTitle"),
        documentSource: document.getElementById("documentSource"),
        documentFile: document.getElementById("documentFile"),
        documentSearch: document.getElementById("documentSearch"),
        documentStatusFilter: document.getElementById("documentStatusFilter"),
        refreshDocumentsBtn: document.getElementById("refreshDocumentsBtn"),
        documentList: document.getElementById("documentList"),
        documentListMeta: document.getElementById("documentListMeta"),
        documentLoadMoreBtn: document.getElementById("documentLoadMoreBtn"),
        documentDetailDrawer: document.getElementById("documentDetailDrawer"),
        intentForm: document.getElementById("intentForm"),
        intentFormTitle: document.getElementById("intentFormTitle"),
        intentId: document.getElementById("intentId"),
        intentName: document.getElementById("intentName"),
        intentDisplayName: document.getElementById("intentDisplayName"),
        intentRouteTarget: document.getElementById("intentRouteTarget"),
        intentDescription: document.getElementById("intentDescription"),
        intentKeywords: document.getElementById("intentKeywords"),
        intentExamples: document.getElementById("intentExamples"),
        intentThreshold: document.getElementById("intentThreshold"),
        intentPriority: document.getElementById("intentPriority"),
        intentIsActive: document.getElementById("intentIsActive"),
        intentDraftHint: document.getElementById("intentDraftHint"),
        intentDraftMeta: document.getElementById("intentDraftMeta"),
        intentDiffPreview: document.getElementById("intentDiffPreview"),
        resetIntentFormBtn: document.getElementById("resetIntentFormBtn"),
        intentSearch: document.getElementById("intentSearch"),
        exportIntentsBtn: document.getElementById("exportIntentsBtn"),
        importIntentsBtn: document.getElementById("importIntentsBtn"),
        importIntentsFile: document.getElementById("importIntentsFile"),
        intentImportPreview: document.getElementById("intentImportPreview"),
        refreshIntentsBtn: document.getElementById("refreshIntentsBtn"),
        intentList: document.getElementById("intentList"),
        refreshAnalyticsBtn: document.getElementById("refreshAnalyticsBtn"),
        analyticsMetrics: document.getElementById("analyticsMetrics"),
        analyticsSummary: document.getElementById("analyticsSummary"),
        analyticsRecentConversations: document.getElementById("analyticsRecentConversations"),
        analyticsRecentTickets: document.getElementById("analyticsRecentTickets"),
        ticketStatusBars: document.getElementById("ticketStatusBars"),
        intentDistributionBars: document.getElementById("intentDistributionBars"),
        ragForm: document.getElementById("ragForm"),
        ragQuestion: document.getElementById("ragQuestion"),
        ragTopK: document.getElementById("ragTopK"),
        ragResult: document.getElementById("ragResult"),
        classifyForm: document.getElementById("classifyForm"),
        classifyMessage: document.getElementById("classifyMessage"),
        classifyResult: document.getElementById("classifyResult"),
        statusText: document.getElementById("statusText"),
        toastStack: document.getElementById("toastStack"),
    });
}

function bindEvents() {
    el.authForm.addEventListener("submit", handleAuthSubmit);
    el.authModeToggle.addEventListener("click", toggleAuthMode);
    el.logoutBtn.addEventListener("click", logout);
    el.navList.addEventListener("click", handleNavClick);
    el.refreshCurrentViewBtn.addEventListener("click", refreshCurrentView);
    el.newConversationBtn.addEventListener("click", startNewConversation);
    el.sendBtn.addEventListener("click", sendMessage);
    el.cancelBtn.addEventListener("click", cancelGeneration);
    el.loadHistoryBtn.addEventListener("click", () => {
        if (state.conversationId) {
            loadConversationMessages(state.conversationId);
        } else {
            pushToast("当前没有选中的会话。", "error");
        }
    });
    el.messageInput.addEventListener("keydown", handleComposerKeydown);

    el.ticketForm.addEventListener("submit", handleCreateTicket);
    el.refreshTicketsBtn.addEventListener("click", refreshTickets);
    el.ticketList.addEventListener("click", handleTicketListClick);
    el.ticketLoadMoreBtn.addEventListener("click", handleLoadMoreTickets);
    el.ticketLookupForm.addEventListener("submit", handleTicketLookupSubmit);
    el.ticketDetailResetBtn.addEventListener("click", resetTicketDetail);
    el.ticketDetailContainer.addEventListener("click", handleTicketDetailClick);
    el.ticketDetailContainer.addEventListener("input", handleTicketDetailInput);
    el.ticketDetailContainer.addEventListener("change", handleTicketDetailInput);
    el.conversationList.addEventListener("click", handleConversationListClick);
    el.conversationSearch.addEventListener("input", handleConversationSearch);
    el.conversationOnlyActive.addEventListener("change", handleConversationSearch);
    el.ticketSearch.addEventListener("input", handleTicketFilterChange);
    el.ticketStatusFilter.addEventListener("change", handleTicketFilterChange);

    el.documentForm.addEventListener("submit", handleUploadDocument);
    el.refreshDocumentsBtn.addEventListener("click", refreshDocuments);
    el.documentStatusFilter.addEventListener("change", handleDocumentStatusFilterChange);
    el.documentSearch.addEventListener("input", handleDocumentSearch);
    el.documentLoadMoreBtn.addEventListener("click", handleLoadMoreDocuments);
    el.documentList.addEventListener("click", handleDocumentListClick);
    el.documentDetailDrawer.addEventListener("click", handleDocumentDetailDrawerClick);

    el.intentForm.addEventListener("submit", handleIntentSubmit);
    el.intentForm.addEventListener("input", handleIntentFormInput);
    el.intentForm.addEventListener("change", handleIntentFormInput);
    el.resetIntentFormBtn.addEventListener("click", resetIntentForm);
    el.intentSearch.addEventListener("input", handleIntentSearch);
    el.exportIntentsBtn.addEventListener("click", handleExportIntents);
    el.importIntentsBtn.addEventListener("click", () => el.importIntentsFile.click());
    el.importIntentsFile.addEventListener("change", handleImportIntentsFile);
    el.intentImportPreview.addEventListener("click", handleIntentImportPreviewClick);
    el.refreshIntentsBtn.addEventListener("click", refreshIntents);
    el.intentList.addEventListener("click", handleIntentListClick);

    el.refreshAnalyticsBtn.addEventListener("click", refreshAnalytics);
    el.ragForm.addEventListener("submit", handleRagQuery);
    el.classifyForm.addEventListener("submit", handleClassifyIntent);
}

function renderEmptyStates() {
    el.ragResult.textContent = "暂无结果";
    el.classifyResult.textContent = "暂无结果";
    el.analyticsMetrics.innerHTML = emptyState("登录后查看指标概览。");
    el.analyticsSummary.innerHTML = emptyState("登录后查看运营摘要。");
    el.analyticsRecentConversations.innerHTML = emptyState("登录后查看本地会话摘要。");
    el.analyticsRecentTickets.innerHTML = emptyState("登录后查看最近工单。");
    el.ticketStatusBars.innerHTML = emptyState("暂无工单状态数据。");
    el.intentDistributionBars.innerHTML = emptyState("暂无意图分布数据。");
    el.ticketList.innerHTML = emptyState("暂无工单。");
    el.ticketListMeta.textContent = "默认加载最近 20 条工单。";
    el.ticketLoadMoreBtn.disabled = true;
    el.ticketDetailContainer.innerHTML = emptyState("输入工单 ID 查看详情。");
    el.documentList.innerHTML = emptyState("暂无文档。");
    el.documentListMeta.textContent = "默认显示最近 12 条文档。";
    el.documentLoadMoreBtn.disabled = true;
    el.documentDetailDrawer.classList.add("hidden");
    el.documentDetailDrawer.innerHTML = "";
    el.intentList.innerHTML = emptyState("暂无意图配置。");
    el.intentImportPreview.classList.add("hidden");
    el.intentImportPreview.innerHTML = "";
    el.intentDraftHint.textContent = "尚未修改。";
    el.intentDraftHint.classList.remove("error-text");
    el.intentDraftMeta.textContent = "草稿会自动保存在本地。";
    el.intentDiffPreview.innerHTML = "";
    el.intentDiffPreview.classList.add("hidden");
}

function restoreSession() {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) {
        return;
    }

    try {
        const session = JSON.parse(raw);
        state.token = session.token || null;
        state.user = session.user || null;
        state.conversationId = session.conversationId || null;
        state.conversations = loadStoredConversations();
    } catch (error) {
        localStorage.removeItem(SESSION_KEY);
    }
}

function persistSession() {
    if (!state.token || !state.user) {
        localStorage.removeItem(SESSION_KEY);
        return;
    }

    localStorage.setItem(
        SESSION_KEY,
        JSON.stringify({
            token: state.token,
            user: state.user,
            conversationId: state.conversationId,
        }),
    );
}

function toggleAuthMode() {
    state.authMode = state.authMode === "login" ? "register" : "login";
    applyAuthMode();
}

function applyAuthMode() {
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
        resetIntentForm({ restoreDraft: true });
        persistSession();
        updateAuthUI();
        setStatus(`已登录为 ${username}，正在连接 WebSocket。`);
        await bootstrapApp(false);
        pushToast(`欢迎，${username}`, "success");
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`登录失败: ${error.message}`);
    }
}

async function bootstrapApp(silent) {
    updateAuthUI();
    setRoleCapabilities();
    if (!silent) {
        setStatus("正在初始化页面数据。");
    }

    try {
        await connectWS();
    } catch (error) {
        pushToast("WebSocket 连接失败，系统会自动重连。", "error");
    }

    renderConversationList();
    if (state.conversationId) {
        updateConversationHeader();
        await loadConversationMessages(state.conversationId);
    }

    await refreshTickets(true);

    if (isStaffRole()) {
        await refreshDocuments(true);
        await refreshIntents(true);
        await refreshAnalytics(true);
    } else {
        el.documentList.innerHTML = emptyState("当前角色无知识库权限。");
        el.documentListMeta.textContent = "当前角色无知识库权限。";
        el.documentLoadMoreBtn.disabled = true;
        el.documentDetailDrawer.classList.add("hidden");
        el.documentDetailDrawer.innerHTML = "";
        el.intentList.innerHTML = emptyState("当前角色无意图管理权限。");
        el.analyticsMetrics.innerHTML = emptyState("当前角色无统计查看权限。");
        el.analyticsSummary.innerHTML = emptyState("当前角色无统计查看权限。");
        el.analyticsRecentConversations.innerHTML = emptyState("当前角色无统计查看权限。");
        el.analyticsRecentTickets.innerHTML = emptyState("当前角色无统计查看权限。");
        el.ticketStatusBars.innerHTML = emptyState("当前角色无统计查看权限。");
        el.intentDistributionBars.innerHTML = emptyState("当前角色无统计查看权限。");
    }
}

function logout() {
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
    el.conversationSearch.value = "";
    el.conversationOnlyActive.checked = false;
    el.ticketSearch.value = "";
    el.ticketStatusFilter.value = "";
    el.documentSearch.value = "";
    el.intentSearch.value = "";
    el.importIntentsFile.value = "";
    persistSession();
    clearWS();
    updateAuthUI();
    setRoleCapabilities();
    renderConversationList();
    renderMessages();
    renderEmptyStates();
    resetIntentForm({ restoreDraft: false });
    resetTicketDetail();
    setStatus("已退出登录。");
    pushToast("会话已清除。", "success");
}

function updateAuthUI() {
    const loggedIn = Boolean(state.token && state.user);
    el.authForm.classList.toggle("hidden", loggedIn);
    el.authModeToggle.classList.toggle("hidden", loggedIn);
    el.userSummary.classList.toggle("hidden", !loggedIn);
    el.logoutBtn.classList.toggle("hidden", !loggedIn);

    if (loggedIn) {
        el.userNameText.textContent = state.user.username;
        el.userRolePill.textContent = state.user.role;
    }

    syncSendButtonState();
}

function setRoleCapabilities() {
    const canAccessStaffViews = isStaffRole();
    document.querySelectorAll(".admin-only").forEach((node) => {
        node.classList.toggle("hidden", !canAccessStaffViews);
    });

    const adminEditable = isAdminRole();
    Array.from(el.intentForm.elements).forEach((field) => {
        if (field.id === "intentId") {
            return;
        }
        field.disabled = !adminEditable;
    });

    el.documentForm.querySelectorAll("input, button").forEach((field) => {
        field.disabled = !canAccessStaffViews;
    });

    el.exportIntentsBtn.disabled = !canAccessStaffViews;
    el.importIntentsBtn.disabled = !adminEditable;
    el.importIntentsFile.disabled = !adminEditable;

    el.ticketListHint.textContent = canAccessStaffViews
        ? "列表接口当前只返回当前登录用户的工单；可在下方通过工单 ID 查看并处理指定工单。"
        : "当前接口返回当前登录用户的工单列表；你只能关闭自己的工单。";
}

function handleNavClick(event) {
    const button = event.target.closest("[data-view]");
    if (!button) {
        return;
    }

    const view = button.dataset.view;
    if ((view === "documents" || view === "intents" || view === "analytics") && !isStaffRole()) {
        pushToast("当前角色无权限访问该页面。", "error");
        return;
    }

    setView(view);
}

function setView(view) {
    if (!VIEW_META[view]) {
        return;
    }

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

    el.viewTitle.textContent = VIEW_META[view].title;
    el.viewHint.textContent = VIEW_META[view].hint;
}

async function refreshCurrentView() {
    switch (state.activeView) {
        case "chat":
            if (state.conversationId) {
                await loadConversationMessages(state.conversationId);
            } else {
                renderConversationList();
            }
            break;
        case "tickets":
            await refreshTickets();
            break;
        case "documents":
            await refreshDocuments();
            break;
        case "intents":
            await refreshIntents();
            break;
        case "analytics":
            await refreshAnalytics();
            break;
        case "tools":
            setStatus("工具页无需统一刷新，请按表单单独触发接口。");
            break;
        default:
            break;
    }
}

async function connectWS() {
    if (!state.token) {
        return;
    }

    clearReconnectTimer();
    clearHeartbeatTimer();

    if (state.ws && state.ws.readyState <= WebSocket.OPEN) {
        state.manualDisconnect = true;
        state.ws.close();
    }

    state.manualDisconnect = false;
    setConnectionState("connecting", "正在连接");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/v1/chat/ws/${state.token}`;

    await new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl);
        state.ws = ws;
        let settled = false;

        ws.onopen = () => {
            setConnectionState("connected", "已连接");
            state.heartbeatTimer = window.setInterval(() => {
                if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                    state.ws.send(JSON.stringify({ type: "ping" }));
                }
            }, 30000);
            syncSendButtonState();
            if (!settled) {
                settled = true;
                resolve();
            }
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            handleServerMessage(message);
        };

        ws.onerror = () => {
            setConnectionState("error", "连接异常");
            syncSendButtonState();
            if (!settled) {
                settled = true;
                reject(new Error("WebSocket error"));
            }
        };

        ws.onclose = () => {
            clearHeartbeatTimer();
            syncSendButtonState();

            if (!settled) {
                settled = true;
                reject(new Error("WebSocket closed"));
            }

            if (state.manualDisconnect || !state.token) {
                setConnectionState("idle", "未连接");
                return;
            }

            if (ws.code === 4001) {
                pushToast("登录已失效，请重新登录。", "error");
                logout();
                return;
            }

            setConnectionState("error", "连接断开");
            setStatus("WebSocket 已断开，3 秒后自动重连。");
            state.reconnectTimer = window.setTimeout(() => {
                connectWS().catch(() => {});
            }, 3000);
        };
    });
}

function clearWS() {
    clearReconnectTimer();
    clearHeartbeatTimer();
    if (state.ws) {
        state.manualDisconnect = true;
        state.ws.close();
        state.ws = null;
    }
    setConnectionState("idle", "未连接");
    syncSendButtonState();
}

function clearReconnectTimer() {
    if (state.reconnectTimer) {
        window.clearTimeout(state.reconnectTimer);
        state.reconnectTimer = null;
    }
}

function clearHeartbeatTimer() {
    if (state.heartbeatTimer) {
        window.clearInterval(state.heartbeatTimer);
        state.heartbeatTimer = null;
    }
}

function setConnectionState(kind, text) {
    state.connectionState = kind;
    el.connectionDot.classList.remove("connected", "connecting", "error");
    if (kind === "connected") {
        el.connectionDot.classList.add("connected");
    } else if (kind === "connecting") {
        el.connectionDot.classList.add("connecting");
    } else if (kind === "error") {
        el.connectionDot.classList.add("error");
    }
    el.connectionText.textContent = text;
}

function syncSendButtonState() {
    const connected = state.ws && state.ws.readyState === WebSocket.OPEN;
    el.sendBtn.disabled = !(state.token && connected && !state.stream);
    el.cancelBtn.classList.toggle("hidden", !state.stream);
}

async function startNewConversation() {
    if (!requireAuth()) {
        return;
    }

    const title = `新会话 ${formatTime(new Date())}`;
    try {
        const data = await apiRequest("/api/v1/chat/conversations", {
            method: "POST",
            body: { title },
        });
        const conversation = mapConversation(data);
        upsertConversation({
            ...conversation,
            title: title,
            lastMessage: "",
        });
        state.conversationId = conversation.id;
        state.messages = [];
        persistSession();
        renderConversationList();
        renderMessages();
        updateConversationHeader();
        setStatus("已创建新会话。");
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`创建会话失败: ${error.message}`);
    }
}

function loadStoredConversations() {
    if (!state.user?.userId) {
        return [];
    }

    const raw = localStorage.getItem(conversationStorageKey());
    if (!raw) {
        return [];
    }

    try {
        const list = JSON.parse(raw);
        return Array.isArray(list) ? list.sort(sortByUpdatedAt) : [];
    } catch (error) {
        localStorage.removeItem(conversationStorageKey());
        return [];
    }
}

function saveStoredConversations() {
    if (!state.user?.userId) {
        return;
    }
    localStorage.setItem(conversationStorageKey(), JSON.stringify(state.conversations));
}

function conversationStorageKey() {
    return `askflow.conversations.${state.user.userId}`;
}

function upsertConversation(conversation) {
    const existingIndex = state.conversations.findIndex((item) => item.id === conversation.id);
    if (existingIndex >= 0) {
        state.conversations[existingIndex] = {
            ...state.conversations[existingIndex],
            ...conversation,
        };
    } else {
        state.conversations.push(conversation);
    }

    state.conversations.sort(sortByUpdatedAt);
    saveStoredConversations();
    renderConversationList();
}

function renderConversationList() {
    if (!state.conversations.length) {
        el.conversationList.innerHTML = emptyState("暂无会话，点击“新建会话”或直接发送消息创建。");
        if (state.analytics) {
            renderAnalyticsSummary();
        }
        return;
    }

    const conversations = getFilteredConversations();
    if (!conversations.length) {
        el.conversationList.innerHTML = emptyState("没有匹配的会话。");
        return;
    }

    el.conversationList.innerHTML = conversations
        .map((conversation) => `
            <article class="conversation-card ${conversation.id === state.conversationId ? "active" : ""}">
                <button class="conversation-item"
                    data-action="select-conversation"
                    data-conversation-id="${escapeHtml(conversation.id)}" type="button">
                    <strong>${escapeHtml(conversation.title || "未命名会话")}</strong>
                    <div>${escapeHtml((conversation.lastMessage || "暂无消息").slice(0, 80))}</div>
                    <div class="mini-meta">
                        <span>${escapeHtml(formatRelative(conversation.updatedAt || conversation.createdAt))}</span>
                        <span>${escapeHtml((conversation.id || "").slice(0, 8))}</span>
                    </div>
                </button>
                <div class="conversation-actions">
                    <button class="icon-btn" data-action="rename-conversation" data-conversation-id="${escapeHtml(conversation.id)}" type="button">改名</button>
                    <button class="icon-btn" data-action="remove-conversation" data-conversation-id="${escapeHtml(conversation.id)}" type="button">移除</button>
                </div>
            </article>
        `)
        .join("");

    if (state.analytics) {
        renderAnalyticsSummary();
    }
}

function getFilteredConversations() {
    const keyword = state.conversationSearch.trim().toLowerCase();
    return state.conversations.filter((conversation) => {
        if (state.conversationOnlyActive && conversation.id !== state.conversationId) {
            return false;
        }

        if (!keyword) {
            return true;
        }

        const haystack = [
            conversation.title,
            conversation.lastMessage,
            conversation.id,
        ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

        return haystack.includes(keyword);
    });
}

function handleConversationSearch() {
    state.conversationSearch = el.conversationSearch.value.trim();
    state.conversationOnlyActive = el.conversationOnlyActive.checked;
    renderConversationList();
}

async function selectConversation(conversationId) {
    state.conversationId = conversationId;
    persistSession();
    renderConversationList();
    updateConversationHeader();
    await loadConversationMessages(conversationId);
}

async function loadConversationMessages(conversationId) {
    if (!requireAuth()) {
        return;
    }

    try {
        const data = await apiRequest(`/api/v1/chat/conversations/${conversationId}/messages`);
        state.messages = data.map(mapHistoryMessage);
        persistSession();
        renderMessages();
        updateConversationHeader();
        populateTicketDraft();
        setStatus("已加载会话历史。");
    } catch (error) {
        state.messages = [];
        if (error.message.includes("Conversation not found")) {
            removeConversation(conversationId);
            if (state.conversationId === conversationId) {
                state.conversationId = null;
                persistSession();
            }
        }
        renderMessages();
        pushToast(error.message, "error");
        setStatus(`加载历史失败: ${error.message}`);
    }
}

function updateConversationHeader() {
    const current = state.conversations.find((item) => item.id === state.conversationId);
    el.chatConversationTitle.textContent = current?.title || "请选择或创建会话";
    el.conversationMeta.textContent = state.conversationId
        ? `会话 ID: ${state.conversationId.slice(0, 8)} · ${state.messages.length} 条消息`
        : "消息历史会在切换会话时重新加载。";
}

function removeConversation(conversationId) {
    state.conversations = state.conversations.filter((item) => item.id !== conversationId);
    saveStoredConversations();
    if (state.conversationId === conversationId) {
        state.conversationId = null;
        state.messages = [];
        persistSession();
        renderMessages();
    }
    renderConversationList();
}

async function handleConversationListClick(event) {
    const action = event.target.dataset.action;
    const conversationId = event.target.dataset.conversationId;
    if (!action || !conversationId) {
        return;
    }

    if (action === "select-conversation") {
        await selectConversation(conversationId);
        return;
    }

    if (action === "rename-conversation") {
        const current = state.conversations.find((item) => item.id === conversationId);
        const nextTitle = window.prompt("输入新的本地会话名称", current?.title || "");
        if (nextTitle == null) {
            return;
        }
        const trimmed = nextTitle.trim();
        if (!trimmed) {
            pushToast("会话名称不能为空。", "error");
            return;
        }
        upsertConversation({
            id: conversationId,
            title: trimmed,
            updatedAt: new Date().toISOString(),
        });
        if (state.conversationId === conversationId) {
            updateConversationHeader();
        }
        pushToast("本地会话名称已更新。", "success");
        return;
    }

    if (action === "remove-conversation") {
        removeConversation(conversationId);
        pushToast("会话已从本地列表移除。", "success");
    }
}

function renderMessages() {
    if (!state.messages.length) {
        el.messages.innerHTML = emptyState("当前会话暂无消息。发送第一条问题开始流式对话。");
        updateConversationHeader();
        return;
    }

    el.messages.innerHTML = state.messages.map(renderMessageCard).join("");
    scrollMessagesToEnd();
    updateConversationHeader();
}

function renderMessageCard(message) {
    const sources = extractSources(message.sources);
    const intentChip = message.intent
        ? `<span class="chip intent">${escapeHtml(message.intent)}${message.confidence ? ` ${(message.confidence * 100).toFixed(0)}%` : ""}</span>`
        : "";
    const ticketChip = message.ticketId
        ? `<span class="chip ticket">Ticket ${escapeHtml(message.ticketId.slice(0, 8))}</span>`
        : "";

    return `
        <article class="message ${escapeHtml(message.role)}" data-message-id="${escapeHtml(message.id)}">
            <div class="message-header">
                <strong>${escapeHtml(roleLabel(message.role))}</strong>
                <span>${escapeHtml(formatRelative(message.createdAt))}</span>
            </div>
            <div class="message-content">${escapeHtml(message.content || "")}</div>
            <div class="message-meta">${intentChip}${ticketChip}</div>
            ${sources.length ? renderSources(sources) : ""}
        </article>
    `;
}

function appendMessage(message) {
    if (el.messages.querySelector(".empty-state")) {
        el.messages.innerHTML = "";
    }
    state.messages.push(message);
    el.messages.insertAdjacentHTML("beforeend", renderMessageCard(message));
    scrollMessagesToEnd();
    updateConversationHeader();
}

async function sendMessage() {
    if (!requireAuth()) {
        return;
    }

    const content = el.messageInput.value.trim();
    if (!content) {
        return;
    }

    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
        pushToast("连接尚未建立，正在尝试重连。", "error");
        connectWS().catch(() => {});
        return;
    }

    if (!state.conversationId) {
        try {
            await createConversationForMessage(content);
        } catch (error) {
            setStatus(`会话预创建失败，将由 WebSocket 自动分配会话: ${error.message}`);
        }
    }

    const userMessage = {
        id: `local-user-${Date.now()}`,
        role: "user",
        content,
        createdAt: new Date().toISOString(),
    };
    appendMessage(userMessage);
    state.pendingConversationTitle = deriveConversationTitle(content);
    if (state.conversationId) {
        upsertConversation({
            id: state.conversationId,
            title: state.pendingConversationTitle,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            lastMessage: content,
        });
    }

    const assistantMessage = {
        id: `local-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        intent: null,
        confidence: null,
        sources: [],
        ticketId: null,
    };

    appendMessage(assistantMessage);
    state.stream = {
        messageId: assistantMessage.id,
        pendingSources: [],
        pendingIntent: null,
        pendingTicketId: null,
    };
    syncSendButtonState();

    state.ws.send(JSON.stringify({
        type: "message",
        conversation_id: state.conversationId,
        content,
        timestamp: Math.floor(Date.now() / 1000),
    }));

    el.messageInput.value = "";
    populateTicketDraft();
    setStatus("消息已发送，等待流式返回。");
}

async function createConversationForMessage(content) {
    const data = await apiRequest("/api/v1/chat/conversations", {
        method: "POST",
        body: { title: deriveConversationTitle(content) },
    });
    const conversation = mapConversation(data);
    state.conversationId = conversation.id;
    persistSession();
    upsertConversation({
        ...conversation,
        title: deriveConversationTitle(content),
        lastMessage: content,
    });
    updateConversationHeader();
}

function cancelGeneration() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: "cancel" }));
        setStatus("已请求停止生成。");
    }
}

function handleServerMessage(message) {
    if (message.conversation_id) {
        state.conversationId = message.conversation_id;
        persistSession();
        upsertConversation({
            id: message.conversation_id,
            title: currentConversationTitle() !== "未命名会话" ? currentConversationTitle() : (state.pendingConversationTitle || "未命名会话"),
            updatedAt: new Date().toISOString(),
        });
    }

    switch (message.type) {
        case "token":
            handleTokenMessage(message);
            break;
        case "intent":
            handleIntentMessage(message);
            break;
        case "source":
            if (state.stream) {
                state.stream.pendingSources = message.data.sources || [];
            }
            break;
        case "ticket":
            handleTicketMessage(message);
            break;
        case "message_end":
            finalizeStream(message.data.sources || []);
            break;
        case "error":
            finalizeStream([]);
            pushToast(message.data.content || "发生错误。", "error");
            setStatus(message.data.content || "发生错误。");
            break;
        case "pong":
            break;
        default:
            break;
    }
}

function handleTokenMessage(message) {
    if (!state.stream) {
        return;
    }

    const target = state.messages.find((item) => item.id === state.stream.messageId);
    if (!target) {
        return;
    }

    target.content += message.data.content || "";
    target.createdAt = new Date().toISOString();
    patchMessageCard(target);
    scrollMessagesToEnd();
}

function handleIntentMessage(message) {
    if (!state.stream) {
        return;
    }

    const target = state.messages.find((item) => item.id === state.stream.messageId);
    if (!target) {
        return;
    }

    target.intent = message.data.label;
    target.confidence = message.data.confidence;
    patchMessageCard(target);
}

function handleTicketMessage(message) {
    const ticketId = message.data.ticket_id;
    if (state.stream) {
        const target = state.messages.find((item) => item.id === state.stream.messageId);
        if (target) {
            target.ticketId = ticketId;
            patchMessageCard(target);
        }
    }

    refreshTickets(true);
    if (state.ticketDetail && state.ticketDetail.id === ticketId) {
        fetchTicketDetail(ticketId, true);
    }
    pushToast(message.data.message || `工单 ${ticketId} 状态已更新。`, "success");
}

function finalizeStream(inlineSources) {
    if (!state.stream) {
        syncSendButtonState();
        return;
    }

    const target = state.messages.find((item) => item.id === state.stream.messageId);
    if (target) {
        target.sources = inlineSources.length ? inlineSources : state.stream.pendingSources;
        patchMessageCard(target);
        upsertConversation({
            id: state.conversationId,
            title: currentConversationTitle(),
            updatedAt: new Date().toISOString(),
            lastMessage: target.content || "已收到回复",
        });
    }

    state.stream = null;
    state.pendingConversationTitle = "";
    syncSendButtonState();
    populateTicketDraft();
    setStatus("回答生成完成。");
}

function patchMessageCard(message) {
    const existing = el.messages.querySelector(`[data-message-id="${cssEscape(message.id)}"]`);
    if (!existing) {
        return;
    }
    existing.outerHTML = renderMessageCard(message);
}

function populateTicketDraft() {
    const latestUserMessage = [...state.messages].reverse().find((item) => item.role === "user");
    if (!latestUserMessage) {
        return;
    }

    if (!el.ticketTitle.value.trim()) {
        el.ticketTitle.value = deriveConversationTitle(latestUserMessage.content);
    }
    if (!el.ticketDescription.value.trim()) {
        el.ticketDescription.value = latestUserMessage.content;
    }
}

async function handleCreateTicket(event) {
    event.preventDefault();

    if (!requireAuth()) {
        return;
    }

    const title = el.ticketTitle.value.trim();
    const type = el.ticketType.value.trim();
    if (!title || !type) {
        pushToast("工单标题和类型不能为空。", "error");
        return;
    }

    try {
        await apiRequest("/api/v1/tickets", {
            method: "POST",
            body: {
                type,
                title,
                description: el.ticketDescription.value.trim() || null,
                priority: el.ticketPriority.value,
                conversation_id: state.conversationId || null,
                content: {
                    source: "web-console",
                    message_count: state.messages.length,
                },
            },
        });
        el.ticketForm.reset();
        el.ticketType.value = "fault_report";
        el.ticketPriority.value = "medium";
        await refreshTickets();
        pushToast("工单已创建。", "success");
        setStatus("工单创建成功。");
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`工单创建失败: ${error.message}`);
    }
}

async function refreshTickets(silent) {
    if (!state.token) {
        el.ticketList.innerHTML = emptyState("登录后查看工单。");
        el.ticketListMeta.textContent = "登录后查看工单。";
        el.ticketLoadMoreBtn.disabled = true;
        return;
    }

    try {
        const data = await apiRequest(`/api/v1/tickets?limit=${state.ticketPageSize}&offset=0`);
        state.tickets = Array.isArray(data) ? data : [];
        state.ticketReachedEnd = state.tickets.length < state.ticketPageSize;
        renderTicketList();
        if (!silent) {
            setStatus("工单列表已刷新。");
        }
    } catch (error) {
        el.ticketList.innerHTML = emptyState(error.message);
        el.ticketListMeta.textContent = error.message;
        el.ticketLoadMoreBtn.disabled = true;
        if (!silent) {
            pushToast(error.message, "error");
            setStatus(`工单加载失败: ${error.message}`);
        }
    }
}

function renderTicketList() {
    if (!state.tickets.length) {
        el.ticketList.innerHTML = emptyState("暂无工单。");
        updateTicketListMeta();
        if (state.analytics) {
            renderAnalyticsSummary();
        }
        return;
    }

    const tickets = getFilteredTickets();
    if (!tickets.length) {
        el.ticketList.innerHTML = emptyState("没有匹配的工单。");
        updateTicketListMeta();
        if (state.analytics) {
            renderAnalyticsSummary();
        }
        return;
    }

    el.ticketList.innerHTML = tickets
        .map((ticket) => `
            <article class="record-card">
                <strong>${escapeHtml(ticket.title)}</strong>
                <p>${escapeHtml(ticket.description || "暂无描述")}</p>
                <div class="mini-meta">
                    <span class="status-pill">${escapeHtml(ticket.status)}</span>
                    <span>${escapeHtml(ticket.priority)}</span>
                    <span>${escapeHtml(formatRelative(ticket.created_at))}</span>
                </div>
                <div class="card-actions">${renderTicketActionGroup(ticket, "list")}</div>
            </article>
        `)
        .join("");

    updateTicketListMeta();
    if (state.analytics) {
        renderAnalyticsSummary();
    }
}

function getFilteredTickets() {
    const keyword = state.ticketSearch.trim().toLowerCase();
    return state.tickets.filter((ticket) => {
        if (state.ticketStatusFilter && ticket.status !== state.ticketStatusFilter) {
            return false;
        }

        if (!keyword) {
            return true;
        }

        const haystack = [
            ticket.title,
            ticket.description,
            ticket.id,
            ticket.conversation_id,
        ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

        return haystack.includes(keyword);
    });
}

function handleTicketFilterChange() {
    state.ticketSearch = el.ticketSearch.value.trim();
    state.ticketStatusFilter = el.ticketStatusFilter.value;
    renderTicketList();
}

function updateTicketListMeta() {
    const visibleCount = getFilteredTickets().length;
    const filtered = Boolean(state.ticketSearch || state.ticketStatusFilter);

    if (!state.tickets.length) {
        el.ticketListMeta.textContent = "当前没有已加载工单。";
    } else if (filtered) {
        el.ticketListMeta.textContent = `已加载 ${state.tickets.length} 条，筛选后 ${visibleCount} 条。`;
    } else if (state.ticketReachedEnd) {
        el.ticketListMeta.textContent = `已加载 ${state.tickets.length} 条，当前没有更多工单。`;
    } else {
        el.ticketListMeta.textContent = `已加载 ${state.tickets.length} 条，可继续加载更多。`;
    }

    el.ticketLoadMoreBtn.disabled = !state.token || state.ticketReachedEnd;
    el.ticketLoadMoreBtn.textContent = state.ticketReachedEnd ? "已无更多" : `再加载 ${state.ticketPageIncrement} 条`;
}

async function handleLoadMoreTickets() {
    if (!requireAuth()) {
        return;
    }

    if (state.ticketReachedEnd) {
        pushToast("当前没有更多工单。", "info");
        return;
    }

    state.ticketPageSize += state.ticketPageIncrement;
    await refreshTickets();
}

function renderTicketActionGroup(ticket, scope) {
    const actions = [];
    const selectId = `${scope}-ticket-select-${ticket.id}`;

    if (isStaffRole()) {
        actions.push(`
            <select data-ticket-select="${escapeHtml(selectId)}">
                ${["pending", "processing", "resolved", "closed"]
                    .map((status) => `<option value="${status}" ${ticket.status === status ? "selected" : ""}>${status}</option>`)
                    .join("")}
            </select>
        `);
        actions.push(`
            <button class="secondary-btn small" data-action="update-ticket" data-ticket-id="${escapeHtml(ticket.id)}" data-select-id="${escapeHtml(selectId)}" type="button">更新状态</button>
        `);
    } else if (ticket.status !== "closed") {
        actions.push(`
            <button class="secondary-btn small" data-action="close-ticket" data-ticket-id="${escapeHtml(ticket.id)}" type="button">关闭工单</button>
        `);
    }

    actions.push(`
        <button class="ghost-btn small" data-action="load-ticket-detail" data-ticket-id="${escapeHtml(ticket.id)}" type="button">查看详情</button>
    `);

    if (ticket.conversation_id) {
        actions.push(`
            <button class="ghost-btn small" data-action="open-ticket-conversation" data-conversation-id="${escapeHtml(ticket.conversation_id)}" type="button">打开会话</button>
        `);
    }

    return actions.join("");
}

async function handleTicketListClick(event) {
    const action = event.target.dataset.action;
    if (!action) {
        return;
    }

    if (action === "open-ticket-conversation") {
        const conversationId = event.target.dataset.conversationId;
        if (!conversationId) {
            return;
        }
        upsertConversation({
            id: conversationId,
            title: `工单关联会话 ${conversationId.slice(0, 8)}`,
            updatedAt: new Date().toISOString(),
        });
        setView("chat");
        await selectConversation(conversationId);
        return;
    }

    if (action === "update-ticket") {
        const ticketId = event.target.dataset.ticketId;
        const selectId = event.target.dataset.selectId;
        const select = el.ticketList.querySelector(`[data-ticket-select="${cssEscape(selectId)}"]`);
        if (!ticketId || !select) {
            return;
        }

        await updateTicket(ticketId, { status: select.value }, `工单状态已更新为 ${select.value}。`);
        return;
    }

    if (action === "close-ticket") {
        const ticketId = event.target.dataset.ticketId;
        if (!ticketId) {
            return;
        }
        await updateTicket(ticketId, { status: "closed" }, "工单已关闭。");
        return;
    }

    if (action === "load-ticket-detail") {
        const ticketId = event.target.dataset.ticketId;
        if (!ticketId) {
            return;
        }
        el.ticketLookupId.value = ticketId;
        await fetchTicketDetail(ticketId);
    }
}

async function handleTicketLookupSubmit(event) {
    event.preventDefault();

    if (!requireAuth()) {
        return;
    }

    const ticketId = el.ticketLookupId.value.trim();
    if (!ticketId) {
        pushToast("请输入工单 ID。", "error");
        return;
    }

    await fetchTicketDetail(ticketId);
}

function resetTicketDetail() {
    state.ticketDetail = null;
    state.ticketDetailInitial = null;
    el.ticketLookupId.value = "";
    el.ticketDetailResetBtn.classList.add("hidden");
    el.ticketDetailContainer.innerHTML = emptyState("输入工单 ID 查看详情。");
}

async function fetchTicketDetail(ticketId, silent) {
    try {
        const ticket = await apiRequest(`/api/v1/tickets/${ticketId}`);
        state.ticketDetail = ticket;
        state.ticketDetailInitial = createTicketDetailSnapshot(ticket);
        renderTicketDetail();
        el.ticketDetailResetBtn.classList.remove("hidden");
        if (!silent) {
            setStatus("工单详情已加载。");
        }
    } catch (error) {
        state.ticketDetail = null;
        state.ticketDetailInitial = null;
        el.ticketDetailContainer.innerHTML = emptyState(error.message);
        if (!silent) {
            pushToast(error.message, "error");
            setStatus(`工单详情加载失败: ${error.message}`);
        }
    }
}

function renderTicketDetail() {
    if (!state.ticketDetail) {
        el.ticketDetailContainer.innerHTML = emptyState("输入工单 ID 查看详情。");
        return;
    }

    const ticket = state.ticketDetail;
    const canEditStaffFields = isStaffRole();
    const canCloseOwn = !isStaffRole() && ticket.status !== "closed";

    el.ticketDetailContainer.innerHTML = `
        <article class="record-card ticket-detail-card">
            <strong>${escapeHtml(ticket.title)}</strong>
            <div class="mini-meta">
                <span class="status-pill">${escapeHtml(ticket.status)}</span>
                <span>${escapeHtml(ticket.priority)}</span>
                <span>${escapeHtml(ticket.id)}</span>
            </div>
            <p>${escapeHtml(ticket.description || "暂无描述")}</p>
            <div class="mini-meta">
                <span>创建时间: ${escapeHtml(formatRelative(ticket.created_at))}</span>
                <span>处理人: ${escapeHtml(ticket.assignee || "-")}</span>
                ${ticket.conversation_id ? `<span>会话: ${escapeHtml(ticket.conversation_id)}</span>` : ""}
            </div>
            <form class="stack-form ticket-edit-form" id="ticketDetailEditForm">
                <div class="ticket-detail-status-line">
                    <span class="subtle-text" id="ticketDetailDirtyHint">尚未修改。</span>
                </div>
                <div class="inline-grid">
                    <label>
                        <span>状态</span>
                        <select id="ticketDetailStatus" ${!canEditStaffFields && !canCloseOwn ? "disabled" : ""}>
                            ${buildTicketStatusOptions(ticket.status, canEditStaffFields)}
                        </select>
                    </label>
                    <label>
                        <span>优先级</span>
                        <select id="ticketDetailPriority" ${canEditStaffFields ? "" : "disabled"}>
                            ${["low", "medium", "high", "urgent"]
                                .map((priority) => `<option value="${priority}" ${ticket.priority === priority ? "selected" : ""}>${priority}</option>`)
                                .join("")}
                        </select>
                    </label>
                </div>
                <label>
                    <span>处理人</span>
                    <input type="text" id="ticketDetailAssignee" value="${escapeHtml(ticket.assignee || "")}" ${canEditStaffFields ? "" : "disabled"} placeholder="agent-01">
                </label>
                <label>
                    <span>扩展内容（JSON）</span>
                    <textarea id="ticketDetailContent" rows="6" ${canEditStaffFields ? "" : "disabled"}>${escapeHtml(formatTicketContent(ticket.content))}</textarea>
                </label>
                <div class="card-actions">
                    ${canEditStaffFields ? `<button class="primary-btn small" id="ticketDetailSaveBtn" data-action="save-ticket-detail" data-ticket-id="${escapeHtml(ticket.id)}" type="button">保存工单</button>` : ""}
                    ${canCloseOwn ? `<button class="secondary-btn small" data-action="close-ticket-detail" data-ticket-id="${escapeHtml(ticket.id)}" type="button">关闭工单</button>` : ""}
                    ${ticket.conversation_id ? `<button class="ghost-btn small" data-action="open-ticket-conversation" data-conversation-id="${escapeHtml(ticket.conversation_id)}" type="button">打开关联会话</button>` : ""}
                </div>
            </form>
        </article>
    `;
    updateTicketDetailDirtyState();
}

function buildTicketStatusOptions(currentStatus, canEditStaffFields) {
    const allowed = canEditStaffFields ? ["pending", "processing", "resolved", "closed"] : ["closed"];
    return allowed
        .map((status) => `<option value="${status}" ${currentStatus === status ? "selected" : ""}>${status}</option>`)
        .join("");
}

function formatTicketContent(content) {
    if (!content) {
        return "";
    }
    try {
        return JSON.stringify(content, null, 2);
    } catch (error) {
        return "";
    }
}

function createTicketDetailSnapshot(ticket) {
    return {
        status: ticket.status,
        priority: ticket.priority,
        assignee: ticket.assignee || "",
        contentRaw: formatTicketContent(ticket.content),
    };
}

function readTicketDetailDraft() {
    const statusNode = document.getElementById("ticketDetailStatus");
    const priorityNode = document.getElementById("ticketDetailPriority");
    const assigneeNode = document.getElementById("ticketDetailAssignee");
    const contentNode = document.getElementById("ticketDetailContent");

    if (!statusNode || !priorityNode || !assigneeNode || !contentNode) {
        return null;
    }

    const contentRaw = contentNode.value.trim();
    let parsedContent = null;
    let contentError = "";

    if (contentRaw) {
        try {
            parsedContent = JSON.parse(contentRaw);
        } catch (error) {
            contentError = "扩展内容不是合法 JSON。";
        }
    }

    return {
        status: statusNode.value,
        priority: priorityNode.value,
        assignee: assigneeNode.value.trim(),
        contentRaw,
        content: parsedContent,
        contentError,
    };
}

function updateTicketDetailDirtyState() {
    const hint = document.getElementById("ticketDetailDirtyHint");
    const saveBtn = document.getElementById("ticketDetailSaveBtn");
    if (!hint || !state.ticketDetailInitial) {
        return;
    }

    const draft = readTicketDetailDraft();
    if (!draft) {
        return;
    }

    if (draft.contentError) {
        hint.textContent = draft.contentError;
        hint.classList.add("error-text");
        if (saveBtn) {
            saveBtn.disabled = true;
        }
        return;
    }

    const dirty =
        draft.status !== state.ticketDetailInitial.status
        || draft.priority !== state.ticketDetailInitial.priority
        || draft.assignee !== state.ticketDetailInitial.assignee
        || draft.contentRaw !== state.ticketDetailInitial.contentRaw;

    hint.textContent = dirty ? "存在未保存修改。" : "尚未修改。";
    hint.classList.toggle("error-text", false);
    if (saveBtn) {
        saveBtn.disabled = !dirty;
    }
}

function handleTicketDetailInput() {
    updateTicketDetailDirtyState();
}

async function handleTicketDetailClick(event) {
    const action = event.target.dataset.action;
    if (!action) {
        return;
    }

    if (action === "open-ticket-conversation") {
        const conversationId = event.target.dataset.conversationId;
        if (!conversationId) {
            return;
        }
        upsertConversation({
            id: conversationId,
            title: `工单关联会话 ${conversationId.slice(0, 8)}`,
            updatedAt: new Date().toISOString(),
        });
        setView("chat");
        await selectConversation(conversationId);
        return;
    }

    const ticketId = event.target.dataset.ticketId;
    if (!ticketId) {
        return;
    }

    if (action === "close-ticket-detail") {
        await updateTicket(ticketId, { status: "closed" }, "工单已关闭。");
        return;
    }

    if (action === "save-ticket-detail") {
        const draft = readTicketDetailDraft();
        if (!draft) {
            return;
        }
        if (draft.contentError) {
            pushToast(draft.contentError, "error");
            return;
        }

        const payload = {
            status: draft.status,
            priority: draft.priority,
            assignee: draft.assignee || null,
            content: draft.contentRaw ? draft.content : null,
        };
        await updateTicket(ticketId, payload, "工单详情已更新。", true);
    }
}

async function updateTicket(ticketId, payload, successMessage, refreshDetail) {
    try {
        await apiRequest(`/api/v1/tickets/${ticketId}`, {
            method: "PUT",
            body: payload,
        });
        await refreshTickets(true);
        if (refreshDetail) {
            await fetchTicketDetail(ticketId, true);
        } else if (state.ticketDetail && state.ticketDetail.id === ticketId) {
            await fetchTicketDetail(ticketId, true);
        }
        pushToast(successMessage, "success");
        setStatus(successMessage);
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`工单更新失败: ${error.message}`);
    }
}

async function handleUploadDocument(event) {
    event.preventDefault();

    if (!requireStaffRole()) {
        return;
    }

    if (!el.documentFile.files.length) {
        pushToast("请选择上传文件。", "error");
        return;
    }

    const formData = new FormData();
    formData.append("title", el.documentTitle.value.trim() || el.documentFile.files[0].name);
    formData.append("source", el.documentSource.value.trim());
    formData.append("file", el.documentFile.files[0]);

    try {
        await apiRequest("/api/v1/embedding/documents", {
            method: "POST",
            body: formData,
            isFormData: true,
        });
        el.documentForm.reset();
        await refreshDocuments();
        pushToast("文档已上传并开始索引。", "success");
        setStatus("文档上传成功。");
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`文档上传失败: ${error.message}`);
    }
}

async function refreshDocuments(silent) {
    if (!isStaffRole()) {
        el.documentList.innerHTML = emptyState("当前角色无知识库权限。");
        el.documentListMeta.textContent = "当前角色无知识库权限。";
        el.documentLoadMoreBtn.disabled = true;
        return;
    }

    const status = el.documentStatusFilter.value;
    const query = status ? `?status=${encodeURIComponent(status)}` : "";

    try {
        const data = await apiRequest(`/api/v1/admin/documents${query}`);
        state.documents = Array.isArray(data) ? data : [];
        renderDocumentList();
        if (!silent) {
            setStatus("文档列表已刷新。");
        }
    } catch (error) {
        el.documentList.innerHTML = emptyState(error.message);
        el.documentListMeta.textContent = error.message;
        el.documentLoadMoreBtn.disabled = true;
        if (!silent) {
            pushToast(error.message, "error");
            setStatus(`文档加载失败: ${error.message}`);
        }
    }
}

function renderDocumentList() {
    if (!state.documents.length) {
        el.documentList.innerHTML = emptyState("暂无文档。");
        syncDocumentDetailDrawer();
        updateDocumentListMeta();
        return;
    }

    const documents = getFilteredDocuments();
    if (!documents.length) {
        el.documentList.innerHTML = emptyState("没有匹配的文档。");
        syncDocumentDetailDrawer();
        updateDocumentListMeta();
        return;
    }

    el.documentList.innerHTML = documents
        .slice(0, state.documentVisibleCount)
        .map((doc) => `
            <article class="record-card">
                <strong>${escapeHtml(doc.title)}</strong>
                <p>${escapeHtml(doc.source || doc.file_path || "未填写来源")}</p>
                <div class="mini-meta">
                    <span class="status-pill">${escapeHtml(doc.status)}</span>
                    <span>${escapeHtml(`${doc.chunk_count || 0} chunks`)}</span>
                    <span>${escapeHtml(formatRelative(doc.created_at))}</span>
                </div>
                <div class="card-actions">
                    <button class="ghost-btn small" data-action="view-document" data-document-id="${escapeHtml(doc.id)}" type="button">查看详情</button>
                    ${isAdminRole() ? `<button class="secondary-btn small" data-action="reindex-document" data-document-id="${escapeHtml(doc.id)}" type="button">重建索引</button>` : ""}
                    ${isAdminRole() ? `<button class="danger-btn small" data-action="delete-document" data-document-id="${escapeHtml(doc.id)}" type="button">删除文档</button>` : ""}
                </div>
            </article>
        `)
        .join("");

    syncDocumentDetailDrawer();
    updateDocumentListMeta();
}

function getFilteredDocuments() {
    const keyword = state.documentSearch.trim().toLowerCase();
    return state.documents.filter((doc) => {
        if (!keyword) {
            return true;
        }

        const haystack = [
            doc.title,
            doc.source,
            doc.file_path,
            doc.id,
        ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

        return haystack.includes(keyword);
    });
}

function handleDocumentSearch() {
    state.documentSearch = el.documentSearch.value.trim();
    state.documentVisibleCount = state.documentPageIncrement;
    renderDocumentList();
}

function handleDocumentStatusFilterChange() {
    state.documentVisibleCount = state.documentPageIncrement;
    refreshDocuments();
}

function updateDocumentListMeta() {
    const filteredCount = getFilteredDocuments().length;
    const visibleCount = Math.min(filteredCount, state.documentVisibleCount);
    const hasMore = filteredCount > visibleCount;

    if (!state.documents.length) {
        el.documentListMeta.textContent = "当前没有已加载文档。";
    } else if (!filteredCount) {
        el.documentListMeta.textContent = `已加载 ${state.documents.length} 条文档，当前筛选无匹配结果。`;
    } else if (hasMore) {
        el.documentListMeta.textContent = `当前展示 ${visibleCount}/${filteredCount} 条，已加载总计 ${state.documents.length} 条。`;
    } else {
        el.documentListMeta.textContent = `当前展示 ${visibleCount} 条，已无更多匹配文档。`;
    }

    el.documentLoadMoreBtn.disabled = !isStaffRole() || !hasMore;
    el.documentLoadMoreBtn.textContent = hasMore ? `再显示 ${state.documentPageIncrement} 条` : "已全部显示";
}

function handleLoadMoreDocuments() {
    const filteredCount = getFilteredDocuments().length;
    if (state.documentVisibleCount >= filteredCount) {
        pushToast("当前没有更多文档。", "info");
        return;
    }

    state.documentVisibleCount += state.documentPageIncrement;
    renderDocumentList();
}

function handleDocumentDetailDrawerClick(event) {
    const action = event.target.dataset.action;
    if (!action) {
        return;
    }

    if (action === "close-document-detail") {
        state.documentDetailId = null;
        state.documentDetailShowRaw = false;
        renderDocumentDetailDrawer();
        return;
    }

    if (action === "toggle-document-raw") {
        state.documentDetailShowRaw = !state.documentDetailShowRaw;
        renderDocumentDetailDrawer();
        return;
    }

    if (action === "copy-document-raw") {
        const selected = state.documents.find((doc) => doc.id === state.documentDetailId);
        if (!selected) {
            return;
        }
        const rawEntry = buildDocumentDetailEntries(selected).find((entry) => entry.key === "raw");
        if (!rawEntry) {
            return;
        }
        copyTextToClipboard(rawEntry.value)
            .then(() => {
                pushToast("原始 JSON 已复制。", "success");
            })
            .catch((error) => {
                pushToast(error.message, "error");
            });
    }
}

async function handleDocumentListClick(event) {
    const action = event.target.dataset.action;
    const documentId = event.target.dataset.documentId;
    if (!action || !documentId) {
        return;
    }

    if (action === "view-document") {
        state.documentDetailId = documentId;
        state.documentDetailShowRaw = false;
        renderDocumentDetailDrawer();
        return;
    }

    if (!isAdminRole()) {
        return;
    }

    try {
        if (action === "reindex-document") {
            await apiRequest(`/api/v1/embedding/documents/${documentId}/reindex`, {
                method: "POST",
                body: {},
            });
            pushToast("已触发重建索引。", "success");
            setStatus("文档重建索引请求已提交。");
        }

        if (action === "delete-document") {
            await apiRequest(`/api/v1/admin/documents/${documentId}`, {
                method: "DELETE",
            });
            if (state.documentDetailId === documentId) {
                state.documentDetailId = null;
                state.documentDetailShowRaw = false;
            }
            pushToast("文档已删除。", "success");
            setStatus("文档删除成功。");
        }

        await refreshDocuments(true);
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`文档操作失败: ${error.message}`);
    }
}

function syncDocumentDetailDrawer() {
    if (!state.documentDetailId) {
        renderDocumentDetailDrawer();
        return;
    }

    const exists = state.documents.some((doc) => doc.id === state.documentDetailId);
    if (!exists) {
        state.documentDetailId = null;
    }
    renderDocumentDetailDrawer();
}

function renderDocumentDetailDrawer() {
    const selected = state.documents.find((doc) => doc.id === state.documentDetailId);
    if (!selected) {
        el.documentDetailDrawer.classList.add("hidden");
        el.documentDetailDrawer.innerHTML = "";
        return;
    }

    const details = buildDocumentDetailEntries(selected);
    const rawEntry = details.find((entry) => entry.key === "raw");
    const baseEntries = details.filter((entry) => entry.key !== "raw");
    el.documentDetailDrawer.classList.remove("hidden");
    el.documentDetailDrawer.innerHTML = `
        <div class="panel-heading">
            <div>
                <p class="eyebrow">Document Detail</p>
                <h3>${escapeHtml(selected.title || "未命名文档")}</h3>
            </div>
            <button class="ghost-btn small" data-action="close-document-detail" data-document-id="${escapeHtml(selected.id)}" type="button">收起</button>
        </div>
        <div class="mini-meta">
            <span class="status-pill">${escapeHtml(selected.status || "-")}</span>
            <span>${escapeHtml(`${selected.chunk_count || 0} chunks`)}</span>
            <span>${escapeHtml((selected.id || "").slice(0, 8))}</span>
        </div>
        <div class="card-list">
            ${baseEntries
                .map((entry) => `
                    <article class="record-card compact-card">
                        <strong>${escapeHtml(entry.label)}</strong>
                        <p class="prewrap-text">${escapeHtml(entry.value)}</p>
                    </article>
                `)
                .join("")}
            ${rawEntry ? `
                <article class="record-card compact-card">
                    <div class="panel-heading">
                        <div>
                            <strong>${escapeHtml(rawEntry.label)}</strong>
                        </div>
                        <div class="toolbar-row">
                            <button class="ghost-btn small" data-action="copy-document-raw" type="button">复制完整 JSON</button>
                            <button class="ghost-btn small" data-action="toggle-document-raw" type="button">${state.documentDetailShowRaw ? "折叠 JSON" : "展开 JSON"}</button>
                        </div>
                    </div>
                    ${state.documentDetailShowRaw ? `<p class="prewrap-text">${escapeHtml(rawEntry.value)}</p>` : `<p class="subtle-text">点击展开查看完整原始字段。</p>`}
                </article>
            ` : ""}
        </div>
    `;
}

function buildDocumentDetailEntries(doc) {
    const entries = [
        ["来源", doc.source || "空"],
        ["文件路径", doc.file_path || "空"],
        ["创建时间", doc.created_at ? formatRelative(doc.created_at) : "空"],
        ["更新时间", doc.updated_at ? formatRelative(doc.updated_at) : "空"],
    ];

    if (doc.content) {
        entries.push(["正文摘要", typeof doc.content === "string" ? doc.content : JSON.stringify(doc.content, null, 2)]);
    }

    entries.push(["完整记录 JSON", JSON.stringify(doc, null, 2), "raw"]);

    return entries.map(([label, value, key]) => ({
        key: key || label,
        label,
        value: value || "空",
    }));
}

async function refreshIntents(silent) {
    if (!isStaffRole()) {
        el.intentList.innerHTML = emptyState("当前角色无意图管理权限。");
        return;
    }

    try {
        const data = await apiRequest("/api/v1/admin/intents");
        state.intents = data;
        renderIntentList();
        if (!silent) {
            setStatus("意图列表已刷新。");
        }
    } catch (error) {
        el.intentList.innerHTML = emptyState(error.message);
        if (!silent) {
            pushToast(error.message, "error");
            setStatus(`意图加载失败: ${error.message}`);
        }
    }
}

function renderIntentList() {
    if (!state.intents.length) {
        el.intentList.innerHTML = emptyState("暂无启用中的意图配置。");
        return;
    }

    const intents = getFilteredIntents();
    if (!intents.length) {
        el.intentList.innerHTML = emptyState("没有匹配的意图配置。");
        return;
    }

    el.intentList.innerHTML = intents
        .map((intent) => `
            <article class="record-card">
                <strong>${escapeHtml(intent.display_name)}</strong>
                <p>${escapeHtml(intent.description || intent.route_target)}</p>
                <div class="mini-meta">
                    <span class="status-pill">${escapeHtml(intent.name)}</span>
                    <span>${escapeHtml(`route: ${intent.route_target}`)}</span>
                    <span>${escapeHtml(`priority: ${intent.priority}`)}</span>
                </div>
                <div class="mini-meta">
                    <span>${escapeHtml(`threshold: ${intent.confidence_threshold}`)}</span>
                    <span>${escapeHtml(`keywords: ${normalizeArray(intent.keywords).join(", ") || "-"}`)}</span>
                </div>
                <div class="card-actions">
                    <button class="secondary-btn small" data-action="edit-intent" data-intent-id="${escapeHtml(intent.id)}" type="button">编辑</button>
                </div>
            </article>
        `)
        .join("");
}

function getFilteredIntents() {
    const keyword = state.intentSearch.trim().toLowerCase();
    return state.intents.filter((intent) => {
        if (!keyword) {
            return true;
        }

        const haystack = [
            intent.display_name,
            intent.name,
            intent.route_target,
            intent.description,
            normalizeArray(intent.keywords).join(" "),
        ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

        return haystack.includes(keyword);
    });
}

function handleIntentSearch() {
    state.intentSearch = el.intentSearch.value.trim();
    renderIntentList();
}

function handleExportIntents() {
    if (!requireStaffRole()) {
        return;
    }

    const payload = {
        exported_at: new Date().toISOString(),
        total: state.intents.length,
        intents: state.intents.map((intent) => ({
            name: intent.name,
            display_name: intent.display_name,
            route_target: intent.route_target,
            description: intent.description || null,
            keywords: normalizeArray(intent.keywords),
            examples: normalizeArray(intent.examples),
            confidence_threshold: intent.confidence_threshold,
            is_active: Boolean(intent.is_active),
            priority: intent.priority,
        })),
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `askflow-intents-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    pushToast("意图配置已导出。", "success");
}

async function handleImportIntentsFile(event) {
    if (!isAdminRole()) {
        pushToast("只有管理员可以导入意图配置。", "error");
        event.target.value = "";
        return;
    }

    const file = event.target.files?.[0];
    if (!file) {
        return;
    }

    try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        const intents = Array.isArray(parsed) ? parsed : parsed.intents;
        if (!Array.isArray(intents) || !intents.length) {
            throw new Error("JSON 中未找到 intents 数组。");
        }

        prepareIntentImportPreview(file.name, intents);
        event.target.value = "";
    } catch (error) {
        pushToast(error.message || "导入失败。", "error");
        setStatus(`意图导入失败: ${error.message || "未知错误"}`);
        event.target.value = "";
    }
}

function prepareIntentImportPreview(filename, intents) {
    const normalizedItems = intents.map((raw) => normalizeImportedIntent(raw));
    const duplicateIdCounts = new Map();
    const duplicateNameCounts = new Map();

    normalizedItems.forEach((item) => {
        if (item.id) {
            duplicateIdCounts.set(item.id, (duplicateIdCounts.get(item.id) || 0) + 1);
        }
        duplicateNameCounts.set(item.name, (duplicateNameCounts.get(item.name) || 0) + 1);
    });

    const existingById = new Map(state.intents.map((intent) => [intent.id, intent]));
    const existingByName = new Map(state.intents.map((intent) => [intent.name, intent]));
    const previewItems = normalizedItems.map((normalized) => {
        const existing = (normalized.id && existingById.get(normalized.id)) || existingByName.get(normalized.name);
        const validationErrors = [];
        if (normalized.id && duplicateIdCounts.get(normalized.id) > 1) {
            validationErrors.push("导入文件中存在重复 id");
        }
        if (duplicateNameCounts.get(normalized.name) > 1) {
            validationErrors.push("导入文件中存在重复 name");
        }
        const changedFields = existing ? diffImportedIntentFields(existing, normalized) : [];
        const mode = validationErrors.length
            ? "invalid"
            : !existing
                ? "create"
                : changedFields.length
                    ? "update"
                    : "noop";
        return {
            ...normalized,
            mode,
            target_id: existing?.id || null,
            target_name: existing?.name || null,
            changed_fields: changedFields,
            validation_errors: validationErrors,
            run_status: "pending",
            error_message: "",
        };
    });

    state.intentImportPreview = {
        filename,
        created: previewItems.filter((item) => item.mode === "create").length,
        updated: previewItems.filter((item) => item.mode === "update").length,
        noop: previewItems.filter((item) => item.mode === "noop").length,
        invalid: previewItems.filter((item) => item.mode === "invalid").length,
        failed: 0,
        items: previewItems,
    };
    renderIntentImportPreview();
    pushToast(`导入预览已生成：${filename}`, "success");
}

async function applyIntentImportPreview() {
    if (!isAdminRole()) {
        throw new Error("只有管理员可以导入意图配置。");
    }

    if (!state.intentImportPreview?.items?.length) {
        return;
    }

    if (state.intentImportPreview.invalid) {
        throw new Error("导入预览中存在重复项，请先修正 JSON 文件。");
    }

    let created = 0;
    let updated = 0;
    let noop = 0;
    let failed = 0;

    for (const normalized of state.intentImportPreview.items) {
        if (normalized.run_status === "success" || normalized.run_status === "skipped") {
            continue;
        }

        if (normalized.mode === "noop") {
            normalized.run_status = "skipped";
            noop += 1;
            continue;
        }

        try {
            if (normalized.mode === "update" && normalized.target_id) {
                await apiRequest(`/api/v1/admin/intents/${normalized.target_id}`, {
                    method: "PUT",
                    body: {
                        display_name: normalized.display_name,
                        route_target: normalized.route_target,
                        description: normalized.description,
                        keywords: normalized.keywords,
                        examples: normalized.examples,
                        confidence_threshold: normalized.confidence_threshold,
                        is_active: normalized.is_active,
                        priority: normalized.priority,
                    },
                });
                normalized.run_status = "success";
                normalized.error_message = "";
                updated += 1;
                continue;
            }

            await apiRequest("/api/v1/admin/intents", {
                method: "POST",
                body: {
                    name: normalized.name,
                    display_name: normalized.display_name,
                    route_target: normalized.route_target,
                    description: normalized.description,
                    keywords: normalized.keywords,
                    examples: normalized.examples,
                    confidence_threshold: normalized.confidence_threshold,
                    is_active: normalized.is_active,
                    priority: normalized.priority,
                },
            });
            normalized.run_status = "success";
            normalized.error_message = "";
            created += 1;
        } catch (error) {
            normalized.run_status = "failed";
            normalized.error_message = error.message || "未知错误";
            failed += 1;
        }
    }

    state.intentImportPreview.created = state.intentImportPreview.items.filter((item) => item.mode === "create").length;
    state.intentImportPreview.updated = state.intentImportPreview.items.filter((item) => item.mode === "update").length;
    state.intentImportPreview.noop = state.intentImportPreview.items.filter((item) => item.mode === "noop").length;
    state.intentImportPreview.failed = state.intentImportPreview.items.filter((item) => item.run_status === "failed").length;

    await refreshIntents(true);
    resetIntentForm({ restoreDraft: false });
    if (state.intentImportPreview.failed === 0) {
        clearIntentImportPreview();
        pushToast(`意图导入完成：新增 ${created} 条，更新 ${updated} 条，跳过 ${noop} 条。`, "success");
        setStatus(`意图导入完成：新增 ${created} 条，更新 ${updated} 条，跳过 ${noop} 条。`);
        return;
    }

    renderIntentImportPreview();
    pushToast(`意图导入部分失败：新增 ${created} 条，更新 ${updated} 条，失败 ${state.intentImportPreview.failed} 条。`, "error");
    setStatus(`意图导入部分失败：新增 ${created} 条，更新 ${updated} 条，失败 ${state.intentImportPreview.failed} 条。请检查预览明细。`);
}

function handleIntentImportPreviewClick(event) {
    const action = event.target.dataset.action;
    if (!action) {
        return;
    }

    if (action === "cancel-intent-import-preview") {
        clearIntentImportPreview();
        return;
    }

    if (action === "apply-intent-import-preview") {
        applyIntentImportPreview().catch((error) => {
            pushToast(error.message || "导入失败。", "error");
            setStatus(`意图导入失败: ${error.message || "未知错误"}`);
        });
    }
}

function clearIntentImportPreview() {
    state.intentImportPreview = null;
    renderIntentImportPreview();
}

function renderIntentImportPreview() {
    if (!state.intentImportPreview) {
        el.intentImportPreview.classList.add("hidden");
        el.intentImportPreview.innerHTML = "";
        return;
    }

    el.intentImportPreview.classList.remove("hidden");
    el.intentImportPreview.innerHTML = `
        <div class="panel-heading">
            <div>
                <p class="eyebrow">Import Preview</p>
                <h3>${escapeHtml(state.intentImportPreview.filename || "意图导入预览")}</h3>
            </div>
            <div class="toolbar-row">
                <button class="ghost-btn small" data-action="cancel-intent-import-preview" type="button">取消</button>
                <button class="primary-btn small" data-action="apply-intent-import-preview" type="button" ${state.intentImportPreview.invalid ? "disabled" : ""}>确认导入</button>
            </div>
        </div>
        <div class="mini-meta">
            <span>新增 ${escapeHtml(String(state.intentImportPreview.created))} 条</span>
            <span>更新 ${escapeHtml(String(state.intentImportPreview.updated))} 条</span>
            <span>跳过 ${escapeHtml(String(state.intentImportPreview.noop || 0))} 条</span>
            <span>非法 ${escapeHtml(String(state.intentImportPreview.invalid || 0))} 条</span>
            <span>失败 ${escapeHtml(String(state.intentImportPreview.failed || 0))} 条</span>
            <span>总计 ${escapeHtml(String(state.intentImportPreview.items.length))} 条</span>
        </div>
        <div class="card-list">
            ${state.intentImportPreview.items
                .map((item) => `
                    <article class="record-card compact-card diff-card preview-card ${escapeHtml(item.mode)} ${escapeHtml(item.run_status || "pending")}">
                        <strong>${escapeHtml(item.display_name)}</strong>
                        <p>${escapeHtml(item.description || item.route_target)}</p>
                        <div class="mini-meta">
                            <span class="status-pill">${escapeHtml(item.mode)}</span>
                            <span>${escapeHtml(item.name)}</span>
                            <span>${escapeHtml(`route: ${item.route_target}`)}</span>
                        </div>
                        <div class="mini-meta">
                            <span>${escapeHtml(item.target_name ? `目标: ${item.target_name}` : "新建项")}</span>
                            ${item.changed_fields?.length ? `<span>${escapeHtml(`变更字段: ${item.changed_fields.join("、")}`)}</span>` : "<span>无字段差异</span>"}
                        </div>
                        ${item.validation_errors?.length ? `<p class="error-text">${escapeHtml(item.validation_errors.join("；"))}</p>` : ""}
                        ${item.error_message ? `<p class="error-text">${escapeHtml(item.error_message)}</p>` : ""}
                    </article>
                `)
                .join("")}
        </div>
    `;
}

function diffImportedIntentFields(existing, incoming) {
    const labels = {
        display_name: "展示名",
        route_target: "路由目标",
        description: "描述",
        keywords: "关键词",
        examples: "示例",
        confidence_threshold: "阈值",
        is_active: "启用状态",
        priority: "优先级",
    };

    const existingComparable = {
        display_name: existing.display_name || "",
        route_target: existing.route_target || "",
        description: existing.description || "",
        keywords: normalizeArray(existing.keywords).join("|"),
        examples: normalizeArray(existing.examples).join("|"),
        confidence_threshold: String(existing.confidence_threshold ?? ""),
        is_active: existing.is_active ? "1" : "0",
        priority: String(existing.priority ?? ""),
    };

    const incomingComparable = {
        display_name: incoming.display_name || "",
        route_target: incoming.route_target || "",
        description: incoming.description || "",
        keywords: normalizeArray(incoming.keywords).join("|"),
        examples: normalizeArray(incoming.examples).join("|"),
        confidence_threshold: String(incoming.confidence_threshold ?? ""),
        is_active: incoming.is_active ? "1" : "0",
        priority: String(incoming.priority ?? ""),
    };

    return Object.keys(labels)
        .filter((key) => existingComparable[key] !== incomingComparable[key])
        .map((key) => labels[key]);
}

function normalizeImportedIntent(raw) {
    if (!raw || typeof raw !== "object") {
        throw new Error("导入内容包含非法意图项。");
    }

    const normalized = {
        id: raw.id || null,
        name: String(raw.name || "").trim(),
        display_name: String(raw.display_name || raw.displayName || "").trim(),
        route_target: String(raw.route_target || raw.routeTarget || "").trim(),
        description: raw.description ? String(raw.description).trim() : null,
        keywords: normalizeImportList(raw.keywords, ","),
        examples: normalizeImportList(raw.examples, "\n"),
        confidence_threshold: Number(raw.confidence_threshold ?? raw.confidenceThreshold ?? 0.7),
        is_active: Boolean(raw.is_active ?? raw.isActive ?? true),
        priority: Number(raw.priority ?? 0),
    };

    if (!normalized.name || !normalized.display_name || !normalized.route_target) {
        throw new Error("导入内容缺少必填字段：name / display_name / route_target。");
    }

    return normalized;
}

function normalizeImportList(value, separator) {
    if (Array.isArray(value)) {
        return value.map((item) => String(item).trim()).filter(Boolean);
    }

    if (typeof value === "string") {
        return value
            .split(separator)
            .map((item) => item.trim())
            .filter(Boolean);
    }

    return [];
}

function handleIntentListClick(event) {
    const action = event.target.dataset.action;
    const intentId = event.target.dataset.intentId;
    if (action !== "edit-intent" || !intentId) {
        return;
    }

    const intent = state.intents.find((item) => item.id === intentId);
    if (!intent) {
        return;
    }

    populateIntentForm(intent);
}

function resetIntentForm(options = {}) {
    const { restoreDraft = false } = options;
    el.intentForm.reset();
    el.intentFormTitle.textContent = "新建意图";
    state.intentDraftScope = "new";
    el.intentId.value = "";
    el.intentThreshold.value = 0.7;
    el.intentPriority.value = 0;
    el.intentIsActive.checked = true;
    el.resetIntentFormBtn.classList.add("hidden");
    state.intentFormInitial = createIntentFormSnapshot();
    if (restoreDraft) {
        restoreIntentDraft();
    }
    updateIntentDraftState();
}

async function handleIntentSubmit(event) {
    event.preventDefault();

    if (!isAdminRole()) {
        pushToast("只有管理员可以保存意图配置。", "error");
        return;
    }

    const payload = {
        name: el.intentName.value.trim(),
        display_name: el.intentDisplayName.value.trim(),
        route_target: el.intentRouteTarget.value.trim(),
        description: el.intentDescription.value.trim() || null,
        keywords: splitCsv(el.intentKeywords.value),
        examples: splitLines(el.intentExamples.value),
        confidence_threshold: Number(el.intentThreshold.value),
        is_active: el.intentIsActive.checked,
        priority: Number(el.intentPriority.value),
    };

    if (!payload.display_name || !payload.route_target) {
        pushToast("展示名和路由目标不能为空。", "error");
        return;
    }

    try {
        const draftKey = intentDraftStorageKey();
        if (el.intentId.value) {
            delete payload.name;
            await apiRequest(`/api/v1/admin/intents/${el.intentId.value}`, {
                method: "PUT",
                body: payload,
            });
            pushToast("意图已更新。", "success");
        } else {
            if (!payload.name) {
                pushToast("新建意图时必须填写名称。", "error");
                return;
            }
            await apiRequest("/api/v1/admin/intents", {
                method: "POST",
                body: payload,
            });
            pushToast("意图已创建。", "success");
        }

        localStorage.removeItem(draftKey);
        resetIntentForm({ restoreDraft: false });
        await refreshIntents();
        setStatus("意图配置已保存。");
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`意图保存失败: ${error.message}`);
    }
}

function populateIntentForm(intent) {
    el.intentFormTitle.textContent = "编辑意图";
    el.resetIntentFormBtn.classList.remove("hidden");
    state.intentDraftScope = intent.id;
    el.intentId.value = intent.id;
    el.intentName.value = intent.name;
    el.intentDisplayName.value = intent.display_name;
    el.intentRouteTarget.value = intent.route_target;
    el.intentDescription.value = intent.description || "";
    el.intentKeywords.value = normalizeArray(intent.keywords).join(", ");
    el.intentExamples.value = normalizeArray(intent.examples).join("\n");
    el.intentThreshold.value = intent.confidence_threshold;
    el.intentPriority.value = intent.priority;
    el.intentIsActive.checked = Boolean(intent.is_active);
    state.intentFormInitial = createIntentFormSnapshot();
    restoreIntentDraft();
    updateIntentDraftState();
}

function readIntentFormValues() {
    return {
        intentId: el.intentId.value || "",
        name: el.intentName.value.trim(),
        displayName: el.intentDisplayName.value.trim(),
        routeTarget: el.intentRouteTarget.value.trim(),
        description: el.intentDescription.value.trim(),
        keywords: splitCsv(el.intentKeywords.value).join(","),
        examples: splitLines(el.intentExamples.value).join("\n"),
        threshold: String(el.intentThreshold.value),
        priority: String(el.intentPriority.value),
        isActive: el.intentIsActive.checked ? "1" : "0",
    };
}

function createIntentFormSnapshot() {
    return readIntentFormValues();
}

function getIntentDraftScope() {
    return state.intentDraftScope || el.intentId.value || "new";
}

function intentDraftStorageKey() {
    const userId = state.user?.userId || "guest";
    return `${INTENT_DRAFT_KEY}.${userId}.${getIntentDraftScope()}`;
}

function restoreIntentDraft() {
    const raw = localStorage.getItem(intentDraftStorageKey());
    if (!raw) {
        return;
    }

    try {
        const draft = JSON.parse(raw);
        applyIntentDraft(draft);
        el.intentDraftMeta.textContent = "已从本地恢复草稿。";
    } catch (error) {
        localStorage.removeItem(intentDraftStorageKey());
    }
}

function applyIntentDraft(draft) {
    el.intentName.value = draft.name || "";
    el.intentDisplayName.value = draft.displayName || "";
    el.intentRouteTarget.value = draft.routeTarget || "";
    el.intentDescription.value = draft.description || "";
    el.intentKeywords.value = draft.keywords ? draft.keywords.split(",").join(", ") : "";
    el.intentExamples.value = draft.examples || "";
    el.intentThreshold.value = draft.threshold || "0.7";
    el.intentPriority.value = draft.priority || "0";
    el.intentIsActive.checked = draft.isActive !== "0";
}

function clearIntentDraft() {
    localStorage.removeItem(intentDraftStorageKey());
}

function saveIntentDraft(values) {
    localStorage.setItem(intentDraftStorageKey(), JSON.stringify(values));
}

function diffIntentFields(current, initial) {
    const labels = {
        name: "名称",
        displayName: "展示名",
        routeTarget: "路由目标",
        description: "描述",
        keywords: "关键词",
        examples: "示例",
        threshold: "阈值",
        priority: "优先级",
        isActive: "启用状态",
    };

    return Object.entries(labels)
        .filter(([key]) => current[key] !== initial[key])
        .map(([, label]) => label);
}

function buildIntentDiffEntries(current, initial) {
    const labels = {
        name: "名称",
        displayName: "展示名",
        routeTarget: "路由目标",
        description: "描述",
        keywords: "关键词",
        examples: "示例",
        threshold: "阈值",
        priority: "优先级",
        isActive: "启用状态",
    };

    return Object.entries(labels)
        .filter(([key]) => current[key] !== initial[key])
        .map(([key, label]) => ({
            key,
            label,
            before: formatIntentDiffValue(key, initial[key]),
            after: formatIntentDiffValue(key, current[key]),
        }));
}

function formatIntentDiffValue(key, value) {
    if (key === "isActive") {
        return value === "1" ? "启用" : "停用";
    }

    if (!value) {
        return "空";
    }

    return String(value);
}

function renderIntentDiffPreview(diffEntries) {
    if (!diffEntries.length) {
        el.intentDiffPreview.innerHTML = "";
        el.intentDiffPreview.classList.add("hidden");
        return;
    }

    el.intentDiffPreview.classList.remove("hidden");
    el.intentDiffPreview.innerHTML = diffEntries
        .map((entry) => `
            <article class="record-card compact-card diff-card">
                <strong>${escapeHtml(entry.label)}</strong>
                <div class="mini-meta">
                    <span>原始值</span>
                    <span>${escapeHtml(entry.before)}</span>
                </div>
                <div class="mini-meta">
                    <span>当前值</span>
                    <span>${escapeHtml(entry.after)}</span>
                </div>
            </article>
        `)
        .join("");
}

function updateIntentDraftState() {
    if (!state.intentFormInitial) {
        state.intentFormInitial = createIntentFormSnapshot();
    }

    const current = readIntentFormValues();
    const changedFields = diffIntentFields(current, state.intentFormInitial);
    const diffEntries = buildIntentDiffEntries(current, state.intentFormInitial);

    if (!changedFields.length) {
        el.intentDraftHint.textContent = "尚未修改。";
        el.intentDraftHint.classList.remove("error-text");
        el.intentDraftMeta.textContent = "草稿会自动保存在本地。";
        renderIntentDiffPreview([]);
        clearIntentDraft();
        return;
    }

    saveIntentDraft(current);
    el.intentDraftHint.textContent = `存在未保存修改：${changedFields.join("、")}`;
    el.intentDraftHint.classList.remove("error-text");
    el.intentDraftMeta.textContent = `当前编辑对象：${getIntentDraftScope() === "new" ? "新建意图" : getIntentDraftScope().slice(0, 8)}`;
    renderIntentDiffPreview(diffEntries);
}

function handleIntentFormInput() {
    updateIntentDraftState();
}

async function refreshAnalytics(silent) {
    if (!isStaffRole()) {
        return;
    }

    try {
        const data = await apiRequest("/api/v1/admin/analytics");
        state.analytics = data;
        renderAnalytics();
        if (!silent) {
            setStatus("统计看板已刷新。");
        }
    } catch (error) {
        el.analyticsMetrics.innerHTML = emptyState(error.message);
        el.analyticsSummary.innerHTML = emptyState(error.message);
        el.analyticsRecentConversations.innerHTML = emptyState(error.message);
        el.analyticsRecentTickets.innerHTML = emptyState(error.message);
        el.ticketStatusBars.innerHTML = emptyState(error.message);
        el.intentDistributionBars.innerHTML = emptyState(error.message);
        if (!silent) {
            pushToast(error.message, "error");
            setStatus(`统计加载失败: ${error.message}`);
        }
    }
}

function renderAnalytics() {
    if (!state.analytics) {
        el.analyticsMetrics.innerHTML = emptyState("暂无数据。");
        el.analyticsSummary.innerHTML = emptyState("暂无运营摘要。");
        el.analyticsRecentConversations.innerHTML = emptyState("暂无本地会话摘要。");
        el.analyticsRecentTickets.innerHTML = emptyState("暂无最近工单摘要。");
        return;
    }

    const cards = [
        ["会话总数", state.analytics.total_conversations],
        ["消息总数", state.analytics.total_messages],
        ["工单总数", state.analytics.total_tickets],
        ["文档总数", state.analytics.total_documents],
        ["平均意图置信度", `${(Number(state.analytics.avg_confidence || 0) * 100).toFixed(1)}%`],
    ];

    el.analyticsMetrics.innerHTML = cards
        .map(([label, value]) => `
            <article class="metric-card">
                <span class="subtle-text">${escapeHtml(label)}</span>
                <strong>${escapeHtml(String(value))}</strong>
            </article>
        `)
        .join("");

    renderAnalyticsSummary();
    el.ticketStatusBars.innerHTML = renderBarGroup(state.analytics.tickets_by_status, "暂无工单状态数据。");
    el.intentDistributionBars.innerHTML = renderBarGroup(state.analytics.intent_distribution, "暂无意图分布数据。");
}

function renderAnalyticsSummary() {
    const highPriorityCount = state.tickets.filter((ticket) => ["high", "urgent"].includes(ticket.priority)).length;
    const activeConversationCount = state.conversationId ? 1 : 0;
    const recentConversations = state.conversations.slice(0, 4);
    const filteredTicketCount = getFilteredTickets().length;
    const summaryCards = [
        ["本地缓存会话", state.conversations.length, "基于浏览器本地索引恢复"],
        ["当前激活会话", activeConversationCount, state.conversationId ? state.conversationId.slice(0, 8) : "当前未选择会话"],
        ["已加载工单", state.tickets.length, "当前前端已获取到的工单记录"],
        ["筛选后工单", filteredTicketCount, "按当前搜索条件命中的工单数"],
        ["高优先级工单", highPriorityCount, "priority 为 high 或 urgent"],
    ];

    el.analyticsSummary.innerHTML = `
        <div class="metric-grid analytics-summary-grid">
            ${summaryCards
                .map(([label, value, hint]) => `
                    <article class="metric-card">
                        <span class="subtle-text">${escapeHtml(label)}</span>
                        <strong>${escapeHtml(String(value))}</strong>
                        <div class="mini-meta">
                            <span>${escapeHtml(hint)}</span>
                        </div>
                    </article>
                `)
                .join("")}
        </div>
    `;

    renderAnalyticsRecentTickets();

    if (!recentConversations.length) {
        el.analyticsRecentConversations.innerHTML = emptyState("暂无本地会话摘要。");
        return;
    }

    el.analyticsRecentConversations.innerHTML = recentConversations
        .map((conversation) => `
            <article class="record-card compact-card">
                <strong>${escapeHtml(conversation.title || "未命名会话")}</strong>
                <p>${escapeHtml((conversation.lastMessage || "暂无消息摘要").slice(0, 120))}</p>
                <div class="mini-meta">
                    <span>${escapeHtml(formatRelative(conversation.updatedAt || conversation.createdAt))}</span>
                    <span>${conversation.id === state.conversationId ? "当前激活" : "本地缓存"}</span>
                    <span>${escapeHtml((conversation.id || "").slice(0, 8))}</span>
                </div>
            </article>
        `)
        .join("");
}

function renderAnalyticsRecentTickets() {
    const recentTickets = state.tickets.slice(0, 4);
    if (!recentTickets.length) {
        el.analyticsRecentTickets.innerHTML = emptyState("暂无最近工单摘要。");
        return;
    }

    el.analyticsRecentTickets.innerHTML = recentTickets
        .map((ticket) => `
            <article class="record-card compact-card">
                <strong>${escapeHtml(ticket.title || "未命名工单")}</strong>
                <p>${escapeHtml((ticket.description || "暂无描述").slice(0, 140))}</p>
                <div class="mini-meta">
                    <span class="status-pill">${escapeHtml(ticket.status)}</span>
                    <span>${escapeHtml(ticket.priority || "-")}</span>
                    <span>${escapeHtml(formatRelative(ticket.created_at))}</span>
                    <span>${escapeHtml((ticket.id || "").slice(0, 8))}</span>
                </div>
            </article>
        `)
        .join("");
}

async function handleRagQuery(event) {
    event.preventDefault();

    if (!requireAuth()) {
        return;
    }

    const question = el.ragQuestion.value.trim();
    if (!question) {
        pushToast("请输入问题。", "error");
        return;
    }

    try {
        const data = await apiRequest("/api/v1/rag/query", {
            method: "POST",
            body: {
                question,
                conversation_history: buildConversationHistory(),
                top_k: Number(el.ragTopK.value) || 5,
            },
        });
        el.ragResult.innerHTML = `
            <p><strong>回答</strong></p>
            <p>${escapeHtml(data.answer || "")}</p>
            ${renderSources(data.sources || [])}
        `;
        setStatus("RAG 查询完成。");
    } catch (error) {
        el.ragResult.textContent = error.message;
        pushToast(error.message, "error");
        setStatus(`RAG 查询失败: ${error.message}`);
    }
}

async function handleClassifyIntent(event) {
    event.preventDefault();

    if (!requireAuth()) {
        return;
    }

    const message = el.classifyMessage.value.trim();
    if (!message) {
        pushToast("请输入待分类消息。", "error");
        return;
    }

    try {
        const data = await apiRequest("/api/v1/agent/classify", {
            method: "POST",
            body: {
                message,
                context: buildConversationHistory(),
            },
        });
        el.classifyResult.innerHTML = `
            <p><strong>意图</strong></p>
            <p>${escapeHtml(data.label)}</p>
            <p>置信度: ${escapeHtml((data.confidence * 100).toFixed(2))}%</p>
            <p>需要澄清: ${escapeHtml(String(Boolean(data.needs_clarification)))}</p>
        `;
        setStatus("意图分类完成。");
    } catch (error) {
        el.classifyResult.textContent = error.message;
        pushToast(error.message, "error");
        setStatus(`意图分类失败: ${error.message}`);
    }
}

async function apiRequest(path, options = {}) {
    const config = {
        method: options.method || "GET",
        headers: {},
    };

    if (options.auth !== false) {
        if (!state.token) {
            throw new Error("请先登录。");
        }
        config.headers.Authorization = `Bearer ${state.token}`;
    }

    if (options.isFormData) {
        config.body = options.body;
    } else if (options.body !== undefined) {
        config.headers["Content-Type"] = "application/json";
        config.body = JSON.stringify(options.body);
    }

    const response = await fetch(`${API_BASE}${path}`, config);
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : null;

    if (!response.ok) {
        const message = payload?.error || payload?.detail || `Request failed: ${response.status}`;
        if (response.status === 401) {
            logout();
        }
        throw new Error(message);
    }

    if (payload && payload.success === false) {
        throw new Error(payload.error || "请求失败");
    }

    if (payload && Object.prototype.hasOwnProperty.call(payload, "data")) {
        return payload.data;
    }

    return payload;
}

function requireAuth() {
    if (state.token) {
        return true;
    }
    pushToast("请先登录。", "error");
    return false;
}

function requireStaffRole() {
    if (isStaffRole()) {
        return true;
    }
    pushToast("当前角色无权限执行该操作。", "error");
    return false;
}

function isStaffRole() {
    return state.user && (state.user.role === "admin" || state.user.role === "agent");
}

function isAdminRole() {
    return state.user && state.user.role === "admin";
}

function roleLabel(role) {
    if (role === "user") {
        return "你";
    }
    if (role === "assistant") {
        return "AskFlow";
    }
    return "系统";
}

function mapConversation(item) {
    return {
        id: item.id,
        title: item.title || "未命名会话",
        createdAt: item.created_at,
        updatedAt: item.updated_at,
        status: item.status,
    };
}

function mapHistoryMessage(item) {
    return {
        id: item.id,
        role: item.role,
        content: item.content,
        intent: item.intent || null,
        confidence: item.confidence || null,
        sources: item.sources || [],
        createdAt: item.created_at,
        ticketId: null,
    };
}

function currentConversationTitle() {
    const current = state.conversations.find((item) => item.id === state.conversationId);
    return current?.title || "未命名会话";
}

function deriveConversationTitle(content) {
    return content.replace(/\s+/g, " ").trim().slice(0, 22) || "未命名会话";
}

function renderSources(sources) {
    const normalized = extractSources(sources);
    if (!normalized.length) {
        return "";
    }
    return `
        <div class="source-list">
            ${normalized
                .map((source) => `
                    <span class="source-chip">
                        ${escapeHtml(source.title || source.source || "Unknown")}
                        ${typeof source.score === "number" ? ` · ${(source.score * 100).toFixed(0)}%` : ""}
                    </span>
                `)
                .join("")}
        </div>
    `;
}

function renderBarGroup(group, emptyText) {
    const entries = Object.entries(group || {});
    if (!entries.length) {
        return emptyState(emptyText);
    }

    const maxValue = Math.max(...entries.map(([, value]) => value), 1);
    return entries
        .map(([label, value]) => `
            <div class="bar-row">
                <span>${escapeHtml(label)}</span>
                <div class="bar-track">
                    <div class="bar-fill" style="width: ${(value / maxValue) * 100}%"></div>
                </div>
                <strong>${escapeHtml(String(value))}</strong>
            </div>
        `)
        .join("");
}

function buildConversationHistory() {
    return state.messages
        .slice(-6)
        .map((message) => ({
            role: message.role,
            content: message.content,
        }));
}

function splitCsv(value) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function splitLines(value) {
    return value
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);
}

function normalizeArray(value) {
    if (Array.isArray(value)) {
        return value;
    }
    if (!value || typeof value !== "object") {
        return [];
    }
    return Object.values(value).filter(Boolean);
}

function extractSources(value) {
    if (Array.isArray(value)) {
        return value;
    }
    if (value && Array.isArray(value.sources)) {
        return value.sources;
    }
    return [];
}

function decodeJwtPayload(token) {
    try {
        const payload = token.split(".")[1];
        const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
        return JSON.parse(window.atob(base64));
    } catch (error) {
        return {};
    }
}

function setStatus(text) {
    el.statusText.textContent = text;
}

function pushToast(text, kind = "info") {
    const toast = document.createElement("span");
    toast.className = `toast ${kind}`;
    toast.textContent = text;
    el.toastStack.prepend(toast);
    window.setTimeout(() => {
        toast.remove();
    }, 4500);
}

function emptyState(text) {
    return `<div class="empty-state">${escapeHtml(text)}</div>`;
}

function handleComposerKeydown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function scrollMessagesToEnd() {
    el.messages.scrollTop = el.messages.scrollHeight;
}

function formatRelative(value) {
    if (!value) {
        return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    const diff = Date.now() - date.getTime();
    const minutes = Math.round(diff / 60000);
    if (Math.abs(minutes) < 1) {
        return "刚刚";
    }
    if (Math.abs(minutes) < 60) {
        return `${minutes} 分钟前`;
    }

    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) {
        return `${hours} 小时前`;
    }

    return `${date.getMonth() + 1}/${date.getDate()} ${formatTime(date)}`;
}

function formatTime(date) {
    return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function sortByUpdatedAt(left, right) {
    return new Date(right.updatedAt || right.createdAt || 0).getTime()
        - new Date(left.updatedAt || left.createdAt || 0).getTime();
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
}

async function copyTextToClipboard(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "readonly");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const success = document.execCommand("copy");
    document.body.removeChild(textarea);

    if (!success) {
        throw new Error("浏览器不支持复制到剪贴板。");
    }
}

function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
        return window.CSS.escape(value);
    }
    return String(value).replace(/["\\]/g, "\\$&");
}
