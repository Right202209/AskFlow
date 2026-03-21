import { state } from "../state.js";
import { apiRequest, requireAuth, isStaffRole, isAdminRole } from "../api.js";
import { pushToast, setStatus } from "../toast.js";
import { emit, on } from "../events.js";
import { escapeHtml, cssEscape, emptyState, formatRelative, deriveConversationTitle } from "../dom.js";

const el = {};

export function initTickets() {
    Object.assign(el, {
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
    });

    el.ticketForm.addEventListener("submit", handleCreateTicket);
    el.refreshTicketsBtn.addEventListener("click", () => refreshTickets());
    el.ticketList.addEventListener("click", handleTicketListClick);
    el.ticketLoadMoreBtn.addEventListener("click", handleLoadMoreTickets);
    el.ticketLookupForm.addEventListener("submit", handleTicketLookupSubmit);
    el.ticketDetailResetBtn.addEventListener("click", resetTicketDetail);
    el.ticketDetailContainer.addEventListener("click", handleTicketDetailClick);
    el.ticketDetailContainer.addEventListener("input", handleTicketDetailInput);
    el.ticketDetailContainer.addEventListener("change", handleTicketDetailInput);
    el.ticketSearch.addEventListener("input", handleTicketFilterChange);
    el.ticketStatusFilter.addEventListener("change", handleTicketFilterChange);

    on("tickets:refresh", (silent) => refreshTickets(silent));
    on("tickets:fetchDetail", (ticketId) => {
        if (state.ticketDetail && state.ticketDetail.id === ticketId) {
            fetchTicketDetail(ticketId, true);
        }
    });
    on("tickets:populateDraft", (content) => {
        if (!el.ticketTitle.value.trim()) {
            el.ticketTitle.value = deriveConversationTitle(content);
        }
        if (!el.ticketDescription.value.trim()) {
            el.ticketDescription.value = content;
        }
    });
    on("app:bootstrap", () => refreshTickets(true));
    on("app:logout", handleLogout);
    on("auth:roleChanged", updateRoleUI);
    on("view:refresh", (view) => { if (view === "tickets") refreshTickets(); });

    renderEmptyStates();
}

function renderEmptyStates() {
    el.ticketList.innerHTML = emptyState("暂无工单。");
    el.ticketListMeta.textContent = "默认加载最近 20 条工单。";
    el.ticketLoadMoreBtn.disabled = true;
    el.ticketDetailContainer.innerHTML = emptyState("输入工单 ID 查看详情。");
}

function handleLogout() {
    el.ticketSearch.value = "";
    el.ticketStatusFilter.value = "";
    renderEmptyStates();
    resetTicketDetail();
}

function updateRoleUI() {
    const canAccessStaffViews = isStaffRole();
    el.ticketListHint.textContent = canAccessStaffViews
        ? "列表接口当前只返回当前登录用户的工单；可在下方通过工单 ID 查看并处理指定工单。"
        : "当前接口返回当前登录用户的工单列表；你只能关闭自己的工单。";
}

async function handleCreateTicket(event) {
    event.preventDefault();
    if (!requireAuth()) return;

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
                content: { source: "web-console", message_count: state.messages.length },
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
        if (!silent) setStatus("工单列表已刷新。");
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
        emit("analytics:updateSummary");
        return;
    }

    const tickets = getFilteredTickets();
    if (!tickets.length) {
        el.ticketList.innerHTML = emptyState("没有匹配的工单。");
        updateTicketListMeta();
        emit("analytics:updateSummary");
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
    emit("analytics:updateSummary");
}

function getFilteredTickets() {
    const keyword = state.ticketSearch.trim().toLowerCase();
    return state.tickets.filter((ticket) => {
        if (state.ticketStatusFilter && ticket.status !== state.ticketStatusFilter) return false;
        if (!keyword) return true;
        return [ticket.title, ticket.description, ticket.id, ticket.conversation_id]
            .filter(Boolean).join(" ").toLowerCase().includes(keyword);
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
    if (!requireAuth()) return;
    if (state.ticketReachedEnd) { pushToast("当前没有更多工单。", "info"); return; }
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
                    .map((s) => `<option value="${s}" ${ticket.status === s ? "selected" : ""}>${s}</option>`)
                    .join("")}
            </select>
        `);
        actions.push(`<button class="secondary-btn small" data-action="update-ticket" data-ticket-id="${escapeHtml(ticket.id)}" data-select-id="${escapeHtml(selectId)}" type="button">更新状态</button>`);
    } else if (ticket.status !== "closed") {
        actions.push(`<button class="secondary-btn small" data-action="close-ticket" data-ticket-id="${escapeHtml(ticket.id)}" type="button">关闭工单</button>`);
    }

    actions.push(`<button class="ghost-btn small" data-action="load-ticket-detail" data-ticket-id="${escapeHtml(ticket.id)}" type="button">查看详情</button>`);

    if (ticket.conversation_id) {
        actions.push(`<button class="ghost-btn small" data-action="open-ticket-conversation" data-conversation-id="${escapeHtml(ticket.conversation_id)}" type="button">打开会话</button>`);
    }

    return actions.join("");
}

async function handleTicketListClick(event) {
    const action = event.target.dataset.action;
    if (!action) return;

    if (action === "open-ticket-conversation") {
        const conversationId = event.target.dataset.conversationId;
        if (conversationId) emit("chat:openConversation", conversationId);
        return;
    }

    if (action === "update-ticket") {
        const ticketId = event.target.dataset.ticketId;
        const selectId = event.target.dataset.selectId;
        const select = el.ticketList.querySelector(`[data-ticket-select="${cssEscape(selectId)}"]`);
        if (ticketId && select) await updateTicket(ticketId, { status: select.value }, `工单状态已更新为 ${select.value}。`);
        return;
    }

    if (action === "close-ticket") {
        const ticketId = event.target.dataset.ticketId;
        if (ticketId) await updateTicket(ticketId, { status: "closed" }, "工单已关闭。");
        return;
    }

    if (action === "load-ticket-detail") {
        const ticketId = event.target.dataset.ticketId;
        if (ticketId) {
            el.ticketLookupId.value = ticketId;
            await fetchTicketDetail(ticketId);
        }
    }
}

async function handleTicketLookupSubmit(event) {
    event.preventDefault();
    if (!requireAuth()) return;
    const ticketId = el.ticketLookupId.value.trim();
    if (!ticketId) { pushToast("请输入工单 ID。", "error"); return; }
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
        if (!silent) setStatus("工单详情已加载。");
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
                                .map((p) => `<option value="${p}" ${ticket.priority === p ? "selected" : ""}>${p}</option>`)
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
    return allowed.map((s) => `<option value="${s}" ${currentStatus === s ? "selected" : ""}>${s}</option>`).join("");
}

function formatTicketContent(content) {
    if (!content) return "";
    try { return JSON.stringify(content, null, 2); } catch (error) { return ""; }
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
    if (!statusNode || !priorityNode || !assigneeNode || !contentNode) return null;

    const contentRaw = contentNode.value.trim();
    let parsedContent = null;
    let contentError = "";
    if (contentRaw) {
        try { parsedContent = JSON.parse(contentRaw); }
        catch (error) { contentError = "扩展内容不是合法 JSON。"; }
    }

    return { status: statusNode.value, priority: priorityNode.value, assignee: assigneeNode.value.trim(), contentRaw, content: parsedContent, contentError };
}

function updateTicketDetailDirtyState() {
    const hint = document.getElementById("ticketDetailDirtyHint");
    const saveBtn = document.getElementById("ticketDetailSaveBtn");
    if (!hint || !state.ticketDetailInitial) return;

    const draft = readTicketDetailDraft();
    if (!draft) return;

    if (draft.contentError) {
        hint.textContent = draft.contentError;
        hint.classList.add("error-text");
        if (saveBtn) saveBtn.disabled = true;
        return;
    }

    const dirty = draft.status !== state.ticketDetailInitial.status
        || draft.priority !== state.ticketDetailInitial.priority
        || draft.assignee !== state.ticketDetailInitial.assignee
        || draft.contentRaw !== state.ticketDetailInitial.contentRaw;

    hint.textContent = dirty ? "存在未保存修改。" : "尚未修改。";
    hint.classList.toggle("error-text", false);
    if (saveBtn) saveBtn.disabled = !dirty;
}

function handleTicketDetailInput() {
    updateTicketDetailDirtyState();
}

async function handleTicketDetailClick(event) {
    const action = event.target.dataset.action;
    if (!action) return;

    if (action === "open-ticket-conversation") {
        const conversationId = event.target.dataset.conversationId;
        if (conversationId) emit("chat:openConversation", conversationId);
        return;
    }

    const ticketId = event.target.dataset.ticketId;
    if (!ticketId) return;

    if (action === "close-ticket-detail") {
        await updateTicket(ticketId, { status: "closed" }, "工单已关闭。");
        return;
    }

    if (action === "save-ticket-detail") {
        const draft = readTicketDetailDraft();
        if (!draft) return;
        if (draft.contentError) { pushToast(draft.contentError, "error"); return; }

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
        await apiRequest(`/api/v1/tickets/${ticketId}`, { method: "PUT", body: payload });
        await refreshTickets(true);
        if (refreshDetail || (state.ticketDetail && state.ticketDetail.id === ticketId)) {
            await fetchTicketDetail(ticketId, true);
        }
        pushToast(successMessage, "success");
        setStatus(successMessage);
    } catch (error) {
        pushToast(error.message, "error");
        setStatus(`工单更新失败: ${error.message}`);
    }
}

export { getFilteredTickets };
