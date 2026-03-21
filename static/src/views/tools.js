import { state } from "../state.js";
import { apiRequest, requireAuth } from "../api.js";
import { pushToast, setStatus } from "../toast.js";
import { on } from "../events.js";
import { escapeHtml, renderSources } from "../dom.js";

const el = {};

export function initTools() {
    Object.assign(el, {
        ragForm: document.getElementById("ragForm"),
        ragQuestion: document.getElementById("ragQuestion"),
        ragTopK: document.getElementById("ragTopK"),
        ragResult: document.getElementById("ragResult"),
        classifyForm: document.getElementById("classifyForm"),
        classifyMessage: document.getElementById("classifyMessage"),
        classifyResult: document.getElementById("classifyResult"),
    });

    el.ragForm.addEventListener("submit", handleRagQuery);
    el.classifyForm.addEventListener("submit", handleClassifyIntent);

    on("app:logout", () => {
        el.ragResult.textContent = "暂无结果";
        el.classifyResult.textContent = "暂无结果";
    });

    el.ragResult.textContent = "暂无结果";
    el.classifyResult.textContent = "暂无结果";
}

function buildConversationHistory() {
    return state.messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
}

async function handleRagQuery(event) {
    event.preventDefault();
    if (!requireAuth()) return;

    const question = el.ragQuestion.value.trim();
    if (!question) { pushToast("请输入问题。", "error"); return; }

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
    if (!requireAuth()) return;

    const message = el.classifyMessage.value.trim();
    if (!message) { pushToast("请输入待分类消息。", "error"); return; }

    try {
        const data = await apiRequest("/api/v1/agent/classify", {
            method: "POST",
            body: { message, context: buildConversationHistory() },
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
