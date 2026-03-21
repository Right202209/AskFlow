import { sortByUpdatedAt } from "./dom.js";
import { APP_PAGE } from "./page.js";

export const API_BASE = window.location.origin;
export const SESSION_KEY = "askflow.session";
export const VIEW_KEY = `askflow.view.${APP_PAGE}`;
export const INTENT_DRAFT_KEY = "askflow.intentDraft";

export const VIEW_META = {
    chat: { title: "对话工作台", hint: "登录后可直接通过 WebSocket 发起流式会话。" },
    tickets: { title: "工单中心", hint: "提交问题工单，并追踪当前登录用户的工单状态。" },
    documents: { title: "知识库文档", hint: "上传、筛选和维护向量检索使用的知识文档。" },
    intents: { title: "意图配置", hint: "管理规则化意图定义，校准路由阈值和关键词样本。" },
    analytics: { title: "分析看板", hint: "查看对话量、消息量、工单状态和意图分布。" },
    tools: { title: "接口调试", hint: "直接调用 RAG 查询和意图分类接口，验证服务能力。" },
};

export const state = {
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

export function restoreSession() {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return;
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

export function persistSession() {
    if (!state.token || !state.user) {
        localStorage.removeItem(SESSION_KEY);
        return;
    }
    localStorage.setItem(SESSION_KEY, JSON.stringify({
        token: state.token,
        user: state.user,
        conversationId: state.conversationId,
    }));
}

export function loadStoredConversations() {
    if (!state.user?.userId) return [];
    const raw = localStorage.getItem(conversationStorageKey());
    if (!raw) return [];
    try {
        const list = JSON.parse(raw);
        return Array.isArray(list) ? list.sort(sortByUpdatedAt) : [];
    } catch (error) {
        localStorage.removeItem(conversationStorageKey());
        return [];
    }
}

export function saveStoredConversations() {
    if (!state.user?.userId) return;
    localStorage.setItem(conversationStorageKey(), JSON.stringify(state.conversations));
}

function conversationStorageKey() {
    return `askflow.conversations.${state.user.userId}`;
}
