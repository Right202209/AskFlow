import { state } from "./state.js";
import { pushToast, setStatus } from "./toast.js";
import { emit } from "./events.js";

let connectionDotEl = null;
let connectionTextEl = null;

export function initWS() {
    connectionDotEl = document.getElementById("connectionDot");
    connectionTextEl = document.getElementById("connectionText");
}

export async function connectWS() {
    if (!state.token) return;

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
            emit("ws:stateChange");
            if (!settled) { settled = true; resolve(); }
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            emit("ws:message", message);
        };

        ws.onerror = () => {
            setConnectionState("error", "连接异常");
            emit("ws:stateChange");
            if (!settled) { settled = true; reject(new Error("WebSocket error")); }
        };

        ws.onclose = () => {
            clearHeartbeatTimer();
            emit("ws:stateChange");

            if (!settled) { settled = true; reject(new Error("WebSocket closed")); }

            if (state.manualDisconnect || !state.token) {
                setConnectionState("idle", "未连接");
                return;
            }

            if (ws.code === 4001) {
                pushToast("登录已失效，请重新登录。", "error");
                emit("auth:expired");
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

export function clearWS() {
    clearReconnectTimer();
    clearHeartbeatTimer();
    if (state.ws) {
        state.manualDisconnect = true;
        state.ws.close();
        state.ws = null;
    }
    setConnectionState("idle", "未连接");
    emit("ws:stateChange");
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
    connectionDotEl.classList.remove("connected", "connecting", "error");
    if (kind === "connected") connectionDotEl.classList.add("connected");
    else if (kind === "connecting") connectionDotEl.classList.add("connecting");
    else if (kind === "error") connectionDotEl.classList.add("error");
    connectionTextEl.textContent = text;
}
