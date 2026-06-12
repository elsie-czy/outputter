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
