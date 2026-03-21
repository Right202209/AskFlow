import { state, INTENT_DRAFT_KEY } from "../state.js";
import { apiRequest, requireStaffRole, isStaffRole, isAdminRole } from "../api.js";
import { pushToast, setStatus } from "../toast.js";
import { on } from "../events.js";
import { escapeHtml, emptyState, normalizeArray, splitCsv, splitLines } from "../dom.js";

const el = {};

export function initIntents() {
    Object.assign(el, {
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
    });

    el.intentForm.addEventListener("submit", handleIntentSubmit);
    el.intentForm.addEventListener("input", handleIntentFormInput);
    el.intentForm.addEventListener("change", handleIntentFormInput);
    el.resetIntentFormBtn.addEventListener("click", () => resetIntentForm());
    el.intentSearch.addEventListener("input", handleIntentSearch);
    el.exportIntentsBtn.addEventListener("click", handleExportIntents);
    el.importIntentsBtn.addEventListener("click", () => el.importIntentsFile.click());
    el.importIntentsFile.addEventListener("change", handleImportIntentsFile);
    el.intentImportPreview.addEventListener("click", handleIntentImportPreviewClick);
    el.refreshIntentsBtn.addEventListener("click", () => refreshIntents());
    el.intentList.addEventListener("click", handleIntentListClick);

    on("app:bootstrap", () => {
        if (isStaffRole()) refreshIntents(true);
        else el.intentList.innerHTML = emptyState("当前角色无意图管理权限。");
    });
    on("app:login", () => resetIntentForm({ restoreDraft: true }));
    on("app:logout", handleLogout);
    on("auth:roleChanged", updateRoleUI);
    on("view:refresh", (view) => { if (view === "intents") refreshIntents(); });

    renderEmptyStates();
    resetIntentForm({ restoreDraft: Boolean(state.user) });
}

function renderEmptyStates() {
    el.intentList.innerHTML = emptyState("暂无意图配置。");
    el.intentImportPreview.classList.add("hidden");
    el.intentImportPreview.innerHTML = "";
    el.intentDraftHint.textContent = "尚未修改。";
    el.intentDraftHint.classList.remove("error-text");
    el.intentDraftMeta.textContent = "草稿会自动保存在本地。";
    el.intentDiffPreview.innerHTML = "";
    el.intentDiffPreview.classList.add("hidden");
}

function handleLogout() {
    el.intentSearch.value = "";
    el.importIntentsFile.value = "";
    renderEmptyStates();
    resetIntentForm({ restoreDraft: false });
}

function updateRoleUI() {
    const adminEditable = isAdminRole();
    const canAccess = isStaffRole();
    Array.from(el.intentForm.elements).forEach((field) => {
        if (field.id === "intentId") return;
        field.disabled = !adminEditable;
    });
    el.exportIntentsBtn.disabled = !canAccess;
    el.importIntentsBtn.disabled = !adminEditable;
    el.importIntentsFile.disabled = !adminEditable;
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
        if (!silent) setStatus("意图列表已刷新。");
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
        if (!keyword) return true;
        return [intent.display_name, intent.name, intent.route_target, intent.description, normalizeArray(intent.keywords).join(" ")]
            .filter(Boolean).join(" ").toLowerCase().includes(keyword);
    });
}

function handleIntentSearch() {
    state.intentSearch = el.intentSearch.value.trim();
    renderIntentList();
}

function handleExportIntents() {
    if (!requireStaffRole()) return;

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
    if (!file) return;

    try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        const intents = Array.isArray(parsed) ? parsed : parsed.intents;
        if (!Array.isArray(intents) || !intents.length) throw new Error("JSON 中未找到 intents 数组。");
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
        if (item.id) duplicateIdCounts.set(item.id, (duplicateIdCounts.get(item.id) || 0) + 1);
        duplicateNameCounts.set(item.name, (duplicateNameCounts.get(item.name) || 0) + 1);
    });

    const existingById = new Map(state.intents.map((i) => [i.id, i]));
    const existingByName = new Map(state.intents.map((i) => [i.name, i]));
    const previewItems = normalizedItems.map((normalized) => {
        const existing = (normalized.id && existingById.get(normalized.id)) || existingByName.get(normalized.name);
        const validationErrors = [];
        if (normalized.id && duplicateIdCounts.get(normalized.id) > 1) validationErrors.push("导入文件中存在重复 id");
        if (duplicateNameCounts.get(normalized.name) > 1) validationErrors.push("导入文件中存在重复 name");
        const changedFields = existing ? diffImportedIntentFields(existing, normalized) : [];
        const mode = validationErrors.length ? "invalid"
            : !existing ? "create"
            : changedFields.length ? "update"
            : "noop";
        return { ...normalized, mode, target_id: existing?.id || null, target_name: existing?.name || null, changed_fields: changedFields, validation_errors: validationErrors, run_status: "pending", error_message: "" };
    });

    state.intentImportPreview = {
        filename,
        created: previewItems.filter((i) => i.mode === "create").length,
        updated: previewItems.filter((i) => i.mode === "update").length,
        noop: previewItems.filter((i) => i.mode === "noop").length,
        invalid: previewItems.filter((i) => i.mode === "invalid").length,
        failed: 0,
        items: previewItems,
    };
    renderIntentImportPreview();
    pushToast(`导入预览已生成：${filename}`, "success");
}

async function applyIntentImportPreview() {
    if (!isAdminRole()) throw new Error("只有管理员可以导入意图配置。");
    if (!state.intentImportPreview?.items?.length) return;
    if (state.intentImportPreview.invalid) throw new Error("导入预览中存在重复项，请先修正 JSON 文件。");

    let created = 0, updated = 0, noop = 0;

    for (const normalized of state.intentImportPreview.items) {
        if (normalized.run_status === "success" || normalized.run_status === "skipped") continue;
        if (normalized.mode === "noop") { normalized.run_status = "skipped"; noop += 1; continue; }

        try {
            if (normalized.mode === "update" && normalized.target_id) {
                await apiRequest(`/api/v1/admin/intents/${normalized.target_id}`, {
                    method: "PUT",
                    body: { display_name: normalized.display_name, route_target: normalized.route_target, description: normalized.description, keywords: normalized.keywords, examples: normalized.examples, confidence_threshold: normalized.confidence_threshold, is_active: normalized.is_active, priority: normalized.priority },
                });
                normalized.run_status = "success";
                normalized.error_message = "";
                updated += 1;
                continue;
            }
            await apiRequest("/api/v1/admin/intents", {
                method: "POST",
                body: { name: normalized.name, display_name: normalized.display_name, route_target: normalized.route_target, description: normalized.description, keywords: normalized.keywords, examples: normalized.examples, confidence_threshold: normalized.confidence_threshold, is_active: normalized.is_active, priority: normalized.priority },
            });
            normalized.run_status = "success";
            normalized.error_message = "";
            created += 1;
        } catch (error) {
            normalized.run_status = "failed";
            normalized.error_message = error.message || "未知错误";
        }
    }

    state.intentImportPreview.created = state.intentImportPreview.items.filter((i) => i.mode === "create").length;
    state.intentImportPreview.updated = state.intentImportPreview.items.filter((i) => i.mode === "update").length;
    state.intentImportPreview.noop = state.intentImportPreview.items.filter((i) => i.mode === "noop").length;
    state.intentImportPreview.failed = state.intentImportPreview.items.filter((i) => i.run_status === "failed").length;

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
    if (!action) return;
    if (action === "cancel-intent-import-preview") { clearIntentImportPreview(); return; }
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
    const labels = { display_name: "展示名", route_target: "路由目标", description: "描述", keywords: "关键词", examples: "示例", confidence_threshold: "阈值", is_active: "启用状态", priority: "优先级" };
    const toComparable = (obj) => ({
        display_name: obj.display_name || "", route_target: obj.route_target || "", description: obj.description || "",
        keywords: normalizeArray(obj.keywords).join("|"), examples: normalizeArray(obj.examples).join("|"),
        confidence_threshold: String(obj.confidence_threshold ?? ""), is_active: obj.is_active ? "1" : "0", priority: String(obj.priority ?? ""),
    });
    const a = toComparable(existing), b = toComparable(incoming);
    return Object.keys(labels).filter((key) => a[key] !== b[key]).map((key) => labels[key]);
}

function normalizeImportedIntent(raw) {
    if (!raw || typeof raw !== "object") throw new Error("导入内容包含非法意图项。");
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
    if (!normalized.name || !normalized.display_name || !normalized.route_target) throw new Error("导入内容缺少必填字段：name / display_name / route_target。");
    return normalized;
}

function normalizeImportList(value, separator) {
    if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
    if (typeof value === "string") return value.split(separator).map((item) => item.trim()).filter(Boolean);
    return [];
}

function handleIntentListClick(event) {
    const action = event.target.dataset.action;
    const intentId = event.target.dataset.intentId;
    if (action !== "edit-intent" || !intentId) return;
    const intent = state.intents.find((item) => item.id === intentId);
    if (intent) populateIntentForm(intent);
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
    if (restoreDraft) restoreIntentDraft();
    updateIntentDraftState();
}

async function handleIntentSubmit(event) {
    event.preventDefault();
    if (!isAdminRole()) { pushToast("只有管理员可以保存意图配置。", "error"); return; }

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

    if (!payload.display_name || !payload.route_target) { pushToast("展示名和路由目标不能为空。", "error"); return; }

    try {
        const draftKey = intentDraftStorageKey();
        if (el.intentId.value) {
            delete payload.name;
            await apiRequest(`/api/v1/admin/intents/${el.intentId.value}`, { method: "PUT", body: payload });
            pushToast("意图已更新。", "success");
        } else {
            if (!payload.name) { pushToast("新建意图时必须填写名称。", "error"); return; }
            await apiRequest("/api/v1/admin/intents", { method: "POST", body: payload });
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

function createIntentFormSnapshot() { return readIntentFormValues(); }
function getIntentDraftScope() { return state.intentDraftScope || el.intentId.value || "new"; }
function intentDraftStorageKey() { return `${INTENT_DRAFT_KEY}.${state.user?.userId || "guest"}.${getIntentDraftScope()}`; }

function restoreIntentDraft() {
    const raw = localStorage.getItem(intentDraftStorageKey());
    if (!raw) return;
    try {
        applyIntentDraft(JSON.parse(raw));
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

function updateIntentDraftState() {
    if (!state.intentFormInitial) state.intentFormInitial = createIntentFormSnapshot();

    const current = readIntentFormValues();
    const changedFields = diffIntentFields(current, state.intentFormInitial);
    const diffEntries = buildIntentDiffEntries(current, state.intentFormInitial);

    if (!changedFields.length) {
        el.intentDraftHint.textContent = "尚未修改。";
        el.intentDraftHint.classList.remove("error-text");
        el.intentDraftMeta.textContent = "草稿会自动保存在本地。";
        renderIntentDiffPreview([]);
        localStorage.removeItem(intentDraftStorageKey());
        return;
    }

    localStorage.setItem(intentDraftStorageKey(), JSON.stringify(current));
    el.intentDraftHint.textContent = `存在未保存修改：${changedFields.join("、")}`;
    el.intentDraftHint.classList.remove("error-text");
    el.intentDraftMeta.textContent = `当前编辑对象：${getIntentDraftScope() === "new" ? "新建意图" : getIntentDraftScope().slice(0, 8)}`;
    renderIntentDiffPreview(diffEntries);
}

function handleIntentFormInput() { updateIntentDraftState(); }

function diffIntentFields(current, initial) {
    const labels = { name: "名称", displayName: "展示名", routeTarget: "路由目标", description: "描述", keywords: "关键词", examples: "示例", threshold: "阈值", priority: "优先级", isActive: "启用状态" };
    return Object.entries(labels).filter(([key]) => current[key] !== initial[key]).map(([, label]) => label);
}

function buildIntentDiffEntries(current, initial) {
    const labels = { name: "名称", displayName: "展示名", routeTarget: "路由目标", description: "描述", keywords: "关键词", examples: "示例", threshold: "阈值", priority: "优先级", isActive: "启用状态" };
    return Object.entries(labels)
        .filter(([key]) => current[key] !== initial[key])
        .map(([key, label]) => ({ key, label, before: formatIntentDiffValue(key, initial[key]), after: formatIntentDiffValue(key, current[key]) }));
}

function formatIntentDiffValue(key, value) {
    if (key === "isActive") return value === "1" ? "启用" : "停用";
    return value || "空";
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
                <div class="mini-meta"><span>原始值</span><span>${escapeHtml(entry.before)}</span></div>
                <div class="mini-meta"><span>当前值</span><span>${escapeHtml(entry.after)}</span></div>
            </article>
        `)
        .join("");
}
