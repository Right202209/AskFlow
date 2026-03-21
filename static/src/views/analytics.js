import { state } from "../state.js";
import { apiRequest, isStaffRole } from "../api.js";
import { pushToast, setStatus } from "../toast.js";
import { on } from "../events.js";
import { escapeHtml, emptyState, formatRelative, renderBarGroup } from "../dom.js";

const el = {};

export function initAnalytics() {
    Object.assign(el, {
        refreshAnalyticsBtn: document.getElementById("refreshAnalyticsBtn"),
        analyticsMetrics: document.getElementById("analyticsMetrics"),
        analyticsSummary: document.getElementById("analyticsSummary"),
        analyticsRecentConversations: document.getElementById("analyticsRecentConversations"),
        analyticsRecentTickets: document.getElementById("analyticsRecentTickets"),
        ticketStatusBars: document.getElementById("ticketStatusBars"),
        intentDistributionBars: document.getElementById("intentDistributionBars"),
    });

    el.refreshAnalyticsBtn.addEventListener("click", () => refreshAnalytics());

    on("app:bootstrap", () => {
        if (isStaffRole()) refreshAnalytics(true);
        else renderNoPermission();
    });
    on("app:logout", handleLogout);
    on("analytics:updateSummary", () => { if (state.analytics) renderAnalyticsSummary(); });
    on("view:refresh", (view) => { if (view === "analytics") refreshAnalytics(); });

    renderEmptyStates();
}

function renderEmptyStates() {
    el.analyticsMetrics.innerHTML = emptyState("登录后查看指标概览。");
    el.analyticsSummary.innerHTML = emptyState("登录后查看运营摘要。");
    el.analyticsRecentConversations.innerHTML = emptyState("登录后查看本地会话摘要。");
    el.analyticsRecentTickets.innerHTML = emptyState("登录后查看最近工单。");
    el.ticketStatusBars.innerHTML = emptyState("暂无工单状态数据。");
    el.intentDistributionBars.innerHTML = emptyState("暂无意图分布数据。");
}

function renderNoPermission() {
    el.analyticsMetrics.innerHTML = emptyState("当前角色无统计查看权限。");
    el.analyticsSummary.innerHTML = emptyState("当前角色无统计查看权限。");
    el.analyticsRecentConversations.innerHTML = emptyState("当前角色无统计查看权限。");
    el.analyticsRecentTickets.innerHTML = emptyState("当前角色无统计查看权限。");
    el.ticketStatusBars.innerHTML = emptyState("当前角色无统计查看权限。");
    el.intentDistributionBars.innerHTML = emptyState("当前角色无统计查看权限。");
}

function handleLogout() {
    renderEmptyStates();
}

async function refreshAnalytics(silent) {
    if (!isStaffRole()) return;

    try {
        const data = await apiRequest("/api/v1/admin/analytics");
        state.analytics = data;
        renderAnalytics();
        if (!silent) setStatus("统计看板已刷新。");
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

function getFilteredTickets() {
    const keyword = state.ticketSearch.trim().toLowerCase();
    return state.tickets.filter((ticket) => {
        if (state.ticketStatusFilter && ticket.status !== state.ticketStatusFilter) return false;
        if (!keyword) return true;
        return [ticket.title, ticket.description, ticket.id, ticket.conversation_id]
            .filter(Boolean).join(" ").toLowerCase().includes(keyword);
    });
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
                        <div class="mini-meta"><span>${escapeHtml(hint)}</span></div>
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
        .map((c) => `
            <article class="record-card compact-card">
                <strong>${escapeHtml(c.title || "未命名会话")}</strong>
                <p>${escapeHtml((c.lastMessage || "暂无消息摘要").slice(0, 120))}</p>
                <div class="mini-meta">
                    <span>${escapeHtml(formatRelative(c.updatedAt || c.createdAt))}</span>
                    <span>${c.id === state.conversationId ? "当前激活" : "本地缓存"}</span>
                    <span>${escapeHtml((c.id || "").slice(0, 8))}</span>
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
