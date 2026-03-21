import { state, persistSession, saveStoredConversations } from "../state.js";
import { apiRequest, requireAuth, isStaffRole } from "../api.js";
import { pushToast, setStatus } from "../toast.js";
import { connectWS } from "../ws.js";
import { setView } from "../router.js";
import { emit, on } from "../events.js";
import {
    escapeHtml, cssEscape, emptyState, formatRelative, formatTime,
    sortByUpdatedAt, extractSources, roleLabel, mapConversation,
    mapHistoryMessage, deriveConversationTitle, renderSources,
} from "../dom.js";

const el = {};

export function initChat() {
    Object.assign(el, {
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
    });

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
    el.conversationList.addEventListener("click", handleConversationListClick);
    el.conversationSearch.addEventListener("input", handleConversationSearch);
    el.conversationOnlyActive.addEventListener("change", handleConversationSearch);

    on("ws:message", handleServerMessage);
    on("ws:stateChange", syncSendButtonState);
    on("app:bootstrap", handleBootstrap);
    on("app:login", syncSendButtonState);
    on("app:logout", handleLogout);
    on("chat:openConversation", handleOpenConversation);
    on("view:refresh", (view) => {
        if (view !== "chat") return;
        if (state.conversationId) {
            loadConversationMessages(state.conversationId);
        } else {
            renderConversationList();
        }
    });

    renderConversationList();
    renderMessages();
}

async function handleBootstrap() {
    renderConversationList();
    if (state.conversationId) {
        updateConversationHeader();
        await loadConversationMessages(state.conversationId);
    }
    syncSendButtonState();
}

function handleLogout() {
    el.conversationSearch.value = "";
    el.conversationOnlyActive.checked = false;
    renderConversationList();
    renderMessages();
    syncSendButtonState();
}

function syncSendButtonState() {
    const connected = state.ws && state.ws.readyState === WebSocket.OPEN;
    el.sendBtn.disabled = !(state.token && connected && !state.stream);
    el.cancelBtn.classList.toggle("hidden", !state.stream);
}

async function startNewConversation() {
    if (!requireAuth()) return;

    const title = `新会话 ${formatTime(new Date())}`;
    try {
        const data = await apiRequest("/api/v1/chat/conversations", {
            method: "POST",
            body: { title },
        });
        const conversation = mapConversation(data);
        upsertConversation({ ...conversation, title, lastMessage: "" });
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

function upsertConversation(conversation) {
    const idx = state.conversations.findIndex((item) => item.id === conversation.id);
    if (idx >= 0) {
        state.conversations[idx] = { ...state.conversations[idx], ...conversation };
    } else {
        state.conversations.push(conversation);
    }
    state.conversations.sort(sortByUpdatedAt);
    saveStoredConversations();
    renderConversationList();
}

function renderConversationList() {
    if (!state.conversations.length) {
        el.conversationList.innerHTML = emptyState("暂无会话，点击\"新建会话\"或直接发送消息创建。");
        emit("analytics:updateSummary");
        return;
    }

    const conversations = getFilteredConversations();
    if (!conversations.length) {
        el.conversationList.innerHTML = emptyState("没有匹配的会话。");
        return;
    }

    el.conversationList.innerHTML = conversations
        .map((c) => `
            <article class="conversation-card ${c.id === state.conversationId ? "active" : ""}">
                <button class="conversation-item"
                    data-action="select-conversation"
                    data-conversation-id="${escapeHtml(c.id)}" type="button">
                    <strong>${escapeHtml(c.title || "未命名会话")}</strong>
                    <div>${escapeHtml((c.lastMessage || "暂无消息").slice(0, 80))}</div>
                    <div class="mini-meta">
                        <span>${escapeHtml(formatRelative(c.updatedAt || c.createdAt))}</span>
                        <span>${escapeHtml((c.id || "").slice(0, 8))}</span>
                    </div>
                </button>
                <div class="conversation-actions">
                    <button class="icon-btn" data-action="rename-conversation" data-conversation-id="${escapeHtml(c.id)}" type="button">改名</button>
                    <button class="icon-btn" data-action="remove-conversation" data-conversation-id="${escapeHtml(c.id)}" type="button">移除</button>
                </div>
            </article>
        `)
        .join("");

    emit("analytics:updateSummary");
}

function getFilteredConversations() {
    const keyword = state.conversationSearch.trim().toLowerCase();
    return state.conversations.filter((c) => {
        if (state.conversationOnlyActive && c.id !== state.conversationId) return false;
        if (!keyword) return true;
        return [c.title, c.lastMessage, c.id].filter(Boolean).join(" ").toLowerCase().includes(keyword);
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
    if (!requireAuth()) return;

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
    if (!action || !conversationId) return;

    if (action === "select-conversation") {
        await selectConversation(conversationId);
        return;
    }

    if (action === "rename-conversation") {
        const current = state.conversations.find((item) => item.id === conversationId);
        const nextTitle = window.prompt("输入新的本地会话名称", current?.title || "");
        if (nextTitle == null) return;
        const trimmed = nextTitle.trim();
        if (!trimmed) { pushToast("会话名称不能为空。", "error"); return; }
        upsertConversation({ id: conversationId, title: trimmed, updatedAt: new Date().toISOString() });
        if (state.conversationId === conversationId) updateConversationHeader();
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
    if (!requireAuth()) return;

    const content = el.messageInput.value.trim();
    if (!content) return;

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
    if (shouldSyncConversation(message)) {
        state.conversationId = message.conversation_id;
        persistSession();
        upsertConversation({
            id: message.conversation_id,
            title: currentConversationTitle() !== "未命名会话"
                ? currentConversationTitle()
                : (state.pendingConversationTitle || "未命名会话"),
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
            handleTicketWSMessage(message);
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

function shouldSyncConversation(message) {
    if (!message?.conversation_id) return false;
    return ["token", "intent", "source", "message_end", "error"].includes(message.type);
}

function handleTokenMessage(message) {
    if (!state.stream) return;
    const target = state.messages.find((item) => item.id === state.stream.messageId);
    if (!target) return;
    target.content += message.data.content || "";
    target.createdAt = new Date().toISOString();
    patchMessageCard(target);
    scrollMessagesToEnd();
}

function handleIntentMessage(message) {
    if (!state.stream) return;
    const target = state.messages.find((item) => item.id === state.stream.messageId);
    if (!target) return;
    target.intent = message.data.label;
    target.confidence = message.data.confidence;
    patchMessageCard(target);
}

function handleTicketWSMessage(message) {
    const ticketId = message.data.ticket_id;
    if (state.stream) {
        const target = state.messages.find((item) => item.id === state.stream.messageId);
        if (target) {
            target.ticketId = ticketId;
            patchMessageCard(target);
        }
    }
    emit("tickets:refresh", true);
    emit("tickets:fetchDetail", ticketId);
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
    if (!existing) return;
    existing.outerHTML = renderMessageCard(message);
}

function populateTicketDraft() {
    const latestUserMessage = [...state.messages].reverse().find((item) => item.role === "user");
    if (latestUserMessage) {
        emit("tickets:populateDraft", latestUserMessage.content);
    }
}

function currentConversationTitle() {
    const current = state.conversations.find((item) => item.id === state.conversationId);
    return current?.title || "未命名会话";
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

async function handleOpenConversation(conversationId) {
    upsertConversation({
        id: conversationId,
        title: `工单关联会话 ${conversationId.slice(0, 8)}`,
        updatedAt: new Date().toISOString(),
    });
    setView("chat");
    await selectConversation(conversationId);
}

function buildConversationHistory() {
    return state.messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
}

export { buildConversationHistory };
