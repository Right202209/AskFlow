import { restoreSession } from "./state.js";
import { initToast, setStatus } from "./toast.js";
import { initAuth, applyAuthMode, updateAuthUI, syncPageAccess } from "./auth.js";

document.addEventListener("DOMContentLoaded", () => {
    initToast();
    initAuth();

    restoreSession();
    if (!syncPageAccess()) return;

    applyAuthMode();
    updateAuthUI();
    setStatus("请选择身份并登录。");
});
