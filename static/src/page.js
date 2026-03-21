export const APP_PAGE = document.body.dataset.appPage || "portal";

const PAGE_VIEWS = {
    portal: [],
    user: ["chat", "tickets", "tools"],
    admin: ["chat", "tickets", "documents", "intents", "analytics", "tools"],
};

export function isPortalPage() {
    return APP_PAGE === "portal";
}

export function isWorkspacePage() {
    return APP_PAGE === "user" || APP_PAGE === "admin";
}

export function isUserWorkspacePage() {
    return APP_PAGE === "user";
}

export function isAdminWorkspacePage() {
    return APP_PAGE === "admin";
}

export function getAllowedViews() {
    return PAGE_VIEWS[APP_PAGE] || [];
}

export function getDefaultView() {
    return isAdminWorkspacePage() ? "analytics" : "chat";
}

export function workspaceUrlForRole(role) {
    if (role === "admin" || role === "agent") return "/static/admin.html";
    return "/static/user.html";
}

export function portalUrl() {
    return "/static/index.html";
}
