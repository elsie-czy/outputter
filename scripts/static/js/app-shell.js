/**
 * AppShell 交互模块
 * - Sidebar 折叠/展开
 * - 移动端抽屉模式
 * - Lucide icon 初始化
 * - Worker 状态检查
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    // 初始化 lucide icon
    if (typeof lucide !== "undefined") {
      lucide.createIcons();
    } else {
      createFallbackIcons();
    }

    const sidebar = document.getElementById("appSidebar");
    const toggleBtn = document.getElementById("sidebarToggle");

    if (sidebar && toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        if (window.innerWidth < 768) {
          sidebar.classList.toggle("mobile-open");
        } else {
          sidebar.classList.toggle("collapsed");
        }
      });

      // 点击遮罩关闭移动端菜单
      document.addEventListener("click", (e) => {
        if (window.innerWidth < 768 && sidebar.classList.contains("mobile-open")) {
          if (!sidebar.contains(e.target) && e.target !== toggleBtn && !toggleBtn.contains(e.target)) {
            sidebar.classList.remove("mobile-open");
          }
        }
      });
    }

    // Worker 状态检查
    checkWorkerStatus();
    setInterval(checkWorkerStatus, 10000); // 每10秒检查一次

    // Worker 重启按钮
    const restartBtn = document.getElementById("workerRestartBtn");
    if (restartBtn) {
      restartBtn.addEventListener("click", restartWorker);
    }
  });

  function createFallbackIcons(root) {
    const scope = root || document;
    const icons = {
      "archive": '<path d="M3 7h18"/><path d="M5 7v12h14V7"/><path d="M8 3h8l2 4H6z"/><path d="M10 12h4"/>',
      "arrow-left": '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
      "badge-check": '<path d="M3.9 12a2 2 0 0 1 .6-1.4l1.1-1.1V7.9a2 2 0 0 1 2-2h1.6l1.1-1.1a2 2 0 0 1 2.8 0l1.1 1.1h1.6a2 2 0 0 1 2 2v1.6l1.1 1.1a2 2 0 0 1 0 2.8l-1.1 1.1v1.6a2 2 0 0 1-2 2h-1.6l-1.1 1.1a2 2 0 0 1-2.8 0l-1.1-1.1H7.6a2 2 0 0 1-2-2v-1.6l-1.1-1.1A2 2 0 0 1 3.9 12Z"/><path d="m9 12 2 2 4-4"/>',
      "bar-chart-3": '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
      "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 6 3 8H3c0-2 3-1 3-8"/><path d="M10.3 20a2 2 0 0 0 3.4 0"/>',
      "book-open": '<path d="M12 7v14"/><path d="M3 18a2 2 0 0 1 2-2h7V5H5a2 2 0 0 0-2 2z"/><path d="M21 18a2 2 0 0 0-2-2h-7V5h7a2 2 0 0 1 2 2z"/>',
      "book-open-check": '<path d="M12 21V5"/><path d="M3 18a2 2 0 0 1 2-2h7V5H5a2 2 0 0 0-2 2z"/><path d="M21 10V7a2 2 0 0 0-2-2h-7v16"/><path d="m16 18 2 2 4-4"/>',
      "box": '<path d="m21 8-9-5-9 5 9 5 9-5Z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/>',
      "check-circle-2": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
      "circle-help": '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 1 1 5.8 1c-.6 1-1.9 1.4-2.4 2.3"/><path d="M12 17h.01"/>',
      "clipboard-check": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
      "clipboard-list": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M8 12h.01"/><path d="M12 12h4"/><path d="M8 16h.01"/><path d="M12 16h4"/>',
      "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
      "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>',
      "external-link": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
      "file-pen-line": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M10 18H8"/><path d="m16 13-3.5 3.5L11 17l.5-1.5L15 12z"/>',
      "file-plus-2": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M12 18v-6"/><path d="M9 15h6"/>',
      "file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
      "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
      "image-off": '<path d="m2 2 20 20"/><path d="M10.4 10.4A2 2 0 0 1 9 9"/><path d="M13.5 5H19a2 2 0 0 1 2 2v9.5"/><path d="M3 3.5V19a2 2 0 0 0 2 2h15.5"/><path d="m21 15-3.1-3.1"/><path d="M10.6 17.4 8 15l-5 5"/>',
      "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
      "layout-dashboard": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
      "library": '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>',
      "loader": '<path d="M12 2v4"/><path d="M12 18v4"/><path d="m4.93 4.93 2.83 2.83"/><path d="m16.24 16.24 2.83 2.83"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="m4.93 19.07 2.83-2.83"/><path d="m16.24 7.76 2.83-2.83"/>',
      "more-horizontal": '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
      "octagon-x": '<path d="M7.9 2h8.2L22 7.9v8.2L16.1 22H7.9L2 16.1V7.9z"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
      "panel-left": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
      "pause": '<path d="M10 4H6v16h4z"/><path d="M18 4h-4v16h4z"/>',
      "plus-square": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 8v8"/><path d="M8 12h8"/>',
      "refresh-cw": '<path d="M21 12a9 9 0 0 0-15-6.7L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 15 6.7L21 16"/><path d="M16 16h5v5"/>',
      "rotate-cw": '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>',
      "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
      "send": '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
      "settings": '<path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.6 1Z"/>',
      "sparkles": '<path d="m12 3-1.9 5.8L4 11l6.1 2.2L12 19l1.9-5.8L20 11l-6.1-2.2z"/><path d="M5 3v4"/><path d="M3 5h4"/><path d="M19 17v4"/><path d="M17 19h4"/>',
      "trending-up": '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
      "user": '<path d="M19 21a7 7 0 0 0-14 0"/><circle cx="12" cy="7" r="4"/>',
      "workflow": '<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M9 6h4a3 3 0 0 1 3 3v6"/><path d="M12 12H9a3 3 0 0 0-3 3v0"/>',
      "x-circle": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
      "zap": '<path d="M13 2 3 14h8l-1 8 10-12h-8z"/>'
    };

    scope.querySelectorAll("i[data-lucide]").forEach((el) => {
      if (el.querySelector("svg")) return;
      const name = el.getAttribute("data-lucide") || "";
      const data = icons[name] || icons["circle-help"];
      el.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + data + "</svg>";
      el.classList.add("lucide-fallback");
    });
  }

  window.createAppFallbackIcons = createFallbackIcons;

  async function checkWorkerStatus() {
    const el = document.getElementById("workerStatus");
    if (!el) return;

    try {
      const res = await fetch("/_health/worker-status");
      const json = await res.json();
      if (!json.ok) return;

      const data = json.data;
      const dot = el.querySelector(".worker-dot");
      const name = el.querySelector(".worker-name");

      if (dot) {
        dot.className = "worker-dot";
        if (data.healthy) {
          dot.classList.add("worker-dot--running");
          el.title = "Worker 运行中";
        } else {
          dot.classList.add("worker-dot--stopped");
          el.title = "Worker 已停止";
        }
      }

      if (name) {
        name.textContent = data.name || "Worker";
      }
    } catch (_) {
      // 请求失败，显示未知状态
      const dot = el.querySelector(".worker-dot");
      if (dot) {
        dot.className = "worker-dot worker-dot--unknown";
      }
    }
  }

  async function restartWorker() {
    const btn = document.getElementById("workerRestartBtn");
    if (!btn || btn.classList.contains("spinning")) return;

    btn.classList.add("spinning");
    btn.disabled = true;

    try {
      const res = await fetch("/_health/worker-restart", { method: "POST" });
      const json = await res.json();

      if (json.ok) {
        showToast("success", json.data.message || "Worker 已重启");
        // 延迟检查状态
        setTimeout(checkWorkerStatus, 3000);
      } else {
        showToast("error", "重启失败: " + (json.error || "未知错误"));
      }
    } catch (e) {
      showToast("error", "重启失败: " + e.message);
    } finally {
      setTimeout(() => {
        btn.classList.remove("spinning");
        btn.disabled = false;
      }, 2000);
    }
  }

  function showToast(type, message) {
    let toast = document.querySelector(".app-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "app-toast";
      document.body.appendChild(toast);
    }

    toast.className = "app-toast app-toast--" + type;
    toast.textContent = message;
    toast.style.cssText = "position:fixed;top:72px;right:24px;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:500;z-index:1000;opacity:0;transform:translateX(100%);transition:all 0.3s;";

    if (type === "success") {
      toast.style.background = "#ECFDF5";
      toast.style.color = "#065F46";
      toast.style.border = "1px solid #A7F3D0";
    } else {
      toast.style.background = "#FEF2F2";
      toast.style.color = "#991B1B";
      toast.style.border = "1px solid #FECACA";
    }

    requestAnimationFrame(() => {
      toast.style.opacity = "1";
      toast.style.transform = "translateX(0)";
    });

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
    }, 3000);
  }
})();
