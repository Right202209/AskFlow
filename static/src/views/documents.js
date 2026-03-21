import { state } from "../state.js";
import { apiRequest, requireStaffRole, isStaffRole, isAdminRole } from "../api.js";
import { pushToast, setStatus } from "../toast.js";
import { on } from "../events.js";
import { escapeHtml, emptyState, formatRelative, copyTextToClipboard } from "../dom.js";

const el = {};

export function initDocuments() {
    Object.assign(el, {
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
    });

    el.documentForm.addEventListener("submit", handleUploadDocument);
    el.refreshDocumentsBtn.addEventListener("click", () => refreshDocuments());
    el.documentStatusFilter.addEventListener("change", handleDocumentStatusFilterChange);
    el.documentSearch.addEventListener("input", handleDocumentSearch);
    el.documentLoadMoreBtn.addEventListener("click", handleLoadMoreDocuments);
    el.documentList.addEventListener("click", handleDocumentListClick);
    el.documentDetailDrawer.addEventListener("click", handleDocumentDetailDrawerClick);

    on("app:bootstrap", () => {
        if (isStaffRole()) refreshDocuments(true);
        else renderNoPermission();
    });
    on("app:logout", handleLogout);
    on("auth:roleChanged", updateRoleUI);
    on("view:refresh", (view) => { if (view === "documents") refreshDocuments(); });

    renderEmptyStates();
}

function renderEmptyStates() {
    el.documentList.innerHTML = emptyState("暂无文档。");
    el.documentListMeta.textContent = "默认显示最近 12 条文档。";
    el.documentLoadMoreBtn.disabled = true;
    el.documentDetailDrawer.classList.add("hidden");
    el.documentDetailDrawer.innerHTML = "";
}

function renderNoPermission() {
    el.documentList.innerHTML = emptyState("当前角色无知识库权限。");
    el.documentListMeta.textContent = "当前角色无知识库权限。";
    el.documentLoadMoreBtn.disabled = true;
    el.documentDetailDrawer.classList.add("hidden");
    el.documentDetailDrawer.innerHTML = "";
}

function handleLogout() {
    el.documentSearch.value = "";
    el.documentStatusFilter.value = "";
    renderEmptyStates();
}

function updateRoleUI() {
    const canAccess = isStaffRole();
    el.documentForm.querySelectorAll("input, button").forEach((field) => {
        field.disabled = !canAccess;
    });
}

async function handleUploadDocument(event) {
    event.preventDefault();
    if (!requireStaffRole()) return;

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
        renderNoPermission();
        return;
    }

    const status = el.documentStatusFilter.value;
    const query = status ? `?status=${encodeURIComponent(status)}` : "";

    try {
        const data = await apiRequest(`/api/v1/admin/documents${query}`);
        state.documents = Array.isArray(data) ? data : [];
        renderDocumentList();
        if (!silent) setStatus("文档列表已刷新。");
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
        if (!keyword) return true;
        return [doc.title, doc.source, doc.file_path, doc.id]
            .filter(Boolean).join(" ").toLowerCase().includes(keyword);
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
    if (!action) return;

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
        if (!selected) return;
        const rawEntry = buildDocumentDetailEntries(selected).find((entry) => entry.key === "raw");
        if (!rawEntry) return;
        copyTextToClipboard(rawEntry.value)
            .then(() => pushToast("原始 JSON 已复制。", "success"))
            .catch((error) => pushToast(error.message, "error"));
    }
}

async function handleDocumentListClick(event) {
    const action = event.target.dataset.action;
    const documentId = event.target.dataset.documentId;
    if (!action || !documentId) return;

    if (action === "view-document") {
        state.documentDetailId = documentId;
        state.documentDetailShowRaw = false;
        renderDocumentDetailDrawer();
        return;
    }

    if (!isAdminRole()) return;

    try {
        if (action === "reindex-document") {
            await apiRequest(`/api/v1/embedding/documents/${documentId}/reindex`, { method: "POST", body: {} });
            pushToast("已触发重建索引。", "success");
            setStatus("文档重建索引请求已提交。");
        }

        if (action === "delete-document") {
            await apiRequest(`/api/v1/admin/documents/${documentId}`, { method: "DELETE" });
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
    if (!state.documents.some((doc) => doc.id === state.documentDetailId)) {
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
