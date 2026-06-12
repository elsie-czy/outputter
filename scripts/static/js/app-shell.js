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
})();
