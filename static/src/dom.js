export function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
}

export function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
        return window.CSS.escape(value);
    }
    return String(value).replace(/["\\]/g, "\\$&");
}

export async function copyTextToClipboard(text) {
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

export function emptyState(text) {
    return `<div class="empty-state">${escapeHtml(text)}</div>`;
}

export function formatRelative(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    const diff = Date.now() - date.getTime();
    const minutes = Math.round(diff / 60000);
    if (Math.abs(minutes) < 1) return "刚刚";
    if (Math.abs(minutes) < 60) return `${minutes} 分钟前`;
    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) return `${hours} 小时前`;
    return `${date.getMonth() + 1}/${date.getDate()} ${formatTime(date)}`;
}

export function formatTime(date) {
    return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function sortByUpdatedAt(left, right) {
    return new Date(right.updatedAt || right.createdAt || 0).getTime()
        - new Date(left.updatedAt || left.createdAt || 0).getTime();
}

export function splitCsv(value) {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function splitLines(value) {
    return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

export function normalizeArray(value) {
    if (Array.isArray(value)) return value;
    if (!value || typeof value !== "object") return [];
    return Object.values(value).filter(Boolean);
}

export function extractSources(value) {
    if (Array.isArray(value)) return value;
    if (value && Array.isArray(value.sources)) return value.sources;
    return [];
}

export function decodeJwtPayload(token) {
    try {
        const payload = token.split(".")[1];
        const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
        return JSON.parse(window.atob(base64));
    } catch (error) {
        return {};
    }
}

export function roleLabel(role) {
    if (role === "user") return "你";
    if (role === "assistant") return "AskFlow";
    return "系统";
}

export function mapConversation(item) {
    return {
        id: item.id,
        title: item.title || "未命名会话",
        createdAt: item.created_at,
        updatedAt: item.updated_at,
        status: item.status,
    };
}

export function mapHistoryMessage(item) {
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

export function deriveConversationTitle(content) {
    return content.replace(/\s+/g, " ").trim().slice(0, 22) || "未命名会话";
}

export function renderSources(sources) {
    const normalized = extractSources(sources);
    if (!normalized.length) return "";
    return `
        <div class="source-list">
            ${normalized.map((source) => `
                <span class="source-chip">
                    ${escapeHtml(source.title || source.source || "Unknown")}
                    ${typeof source.score === "number" ? ` · ${(source.score * 100).toFixed(0)}%` : ""}
                </span>
            `).join("")}
        </div>
    `;
}

export function renderBarGroup(group, emptyText) {
    const entries = Object.entries(group || {});
    if (!entries.length) return emptyState(emptyText);
    const maxValue = Math.max(...entries.map(([, value]) => value), 1);
    return entries.map(([label, value]) => `
        <div class="bar-row">
            <span>${escapeHtml(label)}</span>
            <div class="bar-track">
                <div class="bar-fill" style="width: ${(value / maxValue) * 100}%"></div>
            </div>
            <strong>${escapeHtml(String(value))}</strong>
        </div>
    `).join("");
}
