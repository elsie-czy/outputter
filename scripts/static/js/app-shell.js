/**
 * AppShell 交互模块
 * - Sidebar 折叠/展开
 * - 移动端抽屉模式
 * - Lucide icon 初始化
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
  });
})();
