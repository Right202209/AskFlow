let statusEl = null;
let toastStackEl = null;

export function initToast() {
    statusEl = document.getElementById("statusText");
    toastStackEl = document.getElementById("toastStack");
}

export function setStatus(text) {
    statusEl.textContent = text;
}

export function pushToast(text, kind = "info") {
    const toast = document.createElement("span");
    toast.className = `toast ${kind}`;
    toast.textContent = text;
    toastStackEl.prepend(toast);
    window.setTimeout(() => toast.remove(), 4500);
}
