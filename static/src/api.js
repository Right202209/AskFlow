import { state, API_BASE } from "./state.js";
import { pushToast } from "./toast.js";
import { emit } from "./events.js";

export async function apiRequest(path, options = {}) {
    const config = {
        method: options.method || "GET",
        headers: {},
    };

    if (options.auth !== false) {
        if (!state.token) throw new Error("请先登录。");
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
            emit("auth:expired");
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

export function requireAuth() {
    if (state.token) return true;
    pushToast("请先登录。", "error");
    return false;
}

export function requireStaffRole() {
    if (isStaffRole()) return true;
    pushToast("当前角色无权限执行该操作。", "error");
    return false;
}

export function isStaffRole() {
    return state.user && (state.user.role === "admin" || state.user.role === "agent");
}

export function isAdminRole() {
    return state.user && state.user.role === "admin";
}
