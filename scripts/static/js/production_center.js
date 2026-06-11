/**
 * 生产中心页面交互模块
 * - Tab 状态筛选
 * - 搜索 / 筛选
 * - 多选任务
 * - 批量操作（暂停/重试/终止）
 * - 单任务操作（暂停/重试/终止/查看详情）
 * - 分页
 * - 统计轮询
 */
(function () {
  "use strict";

  /* ===== 状态 ===== */
  let currentPage = 1;
  let currentStatus = "";
  let pollInterval = null;
  let selectedIds = new Set();
  let pendingAction = null;
  const PAGE_SIZE = 20;

  /* ===== DOM 缓存 ===== */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  /* ===== 初始化 ===== */
  document.addEventListener("DOMContentLoaded", () => {
    loadStats();
    loadList();
    bindToolbar();
    bindTabs();
    bindBatchMenu();
    bindModal();
    pollInterval = setInterval(loadStats, 30000);
  });

  /* ===== 数据加载 ===== */
  async function loadStats() {
    try {
      const res = await fetch("/api/production/stats");
      const json = await res.json();
      if (!json.ok) return;
      const d = json.data;
      setText("#statProcessing", d.processing);
      setText("#statPending", d.pending);
      setText("#statCompleted", d.today_completed);
      setText("#statFailed", d.today_failed);
      setText("#statDuration", d.avg_duration);
      setText("#statResource", d.resource_usage + "%");
      setText("#tokenUsed", (d.token_used / 10000).toFixed(0) + "万");
      setText("#todayOutput", d.today_completed);
      
      // 预计剩余时间
      const estRemain = d.pending > 0 ? Math.ceil(d.pending * d.avg_duration) : 0;
      setText("#estRemain", estRemain > 0 ? estRemain + "分钟" : "—");
    } catch (_) {}
  }

  async function loadList() {
    const tbody = $("#pcTableBody");
    if (!tbody) return;
    tbody.innerHTML = '<tr class="pc-loading"><td colspan="8">加载中...</td></tr>';

    try {
      const q = ($("#pcSearch")?.value || "").trim();
      const params = new URLSearchParams({
        page: currentPage,
        per_page: PAGE_SIZE,
      });
      if (currentStatus) params.set("status", currentStatus);
      if (q) params.set("q", q);

      const res = await fetch("/api/production/list?" + params.toString());
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);

      const items = json.data.items || [];
      const total = json.data.total || 0;

      if (items.length === 0) {
        tbody.innerHTML = 
          '<tr class="pc-empty-row"><td colspan="8">' +
          '<div class="pc-empty">' +
          '<div class="pc-empty-icon">📭</div>' +
          '<div class="pc-empty-title">暂无任务</div>' +
          '<div class="pc-empty-desc">请从选题池提交作品开始生产</div>' +
          '<a href="/topic-pool" class="pc-empty-btn">前往选题池</a>' +
          '</div>' +
          '</td></tr>';
        renderPagination(0);
        return;
      }

      renderTable(items);
      renderPagination(Math.ceil(total / PAGE_SIZE));
    } catch (e) {
      tbody.innerHTML = '<tr class="pc-empty"><td colspan="8">加载失败: ' + esc(e.message) + '</td></tr>';
    }
  }

  function renderTable(items) {
    const tbody = $("#pcTableBody");
    if (!tbody) return;

    let html = "";
    for (const item of items) {
      const rid = item.record_id || "";
      const checked = selectedIds.has(rid) ? " checked" : "";
      const progress = item.progress_percent || 0;
      const stageLabel = item.stage_label || "等待中";
      const stageStatus = item.display_status || item.status || "waiting";
      const error = item.error || "";

      html +=
        "<tr>" +
        '<td><input type="checkbox" class="pc-checkbox" data-rid="' + esc(rid) + '"' + checked + " /></td>" +
        '<td><div class="pc-cover">📖</div></td>' +
        "<td>" +
        '<div class="pc-info-name">' + esc(item.work_name || "未知作品") + "</div>" +
        '<div class="pc-info-meta">' +
        "<span>" + esc(item.author || "未知") + "</span>" +
        "<span>" + esc(item.platform || "-") + "</span>" +
        "<span>" + esc(item.category || "-") + "</span>" +
        "</div>" +
        (error ? '<div class="pc-error">' + esc(error) + '</div>' : "") +
        "</td>" +
        "<td>" +
        '<div class="pc-progress">' +
        '<div class="pc-progress-bar"><div class="pc-progress-fill" style="width:' + progress + '%"></div></div>' +
        '<span class="pc-progress-text">' + progress + "%</span>" +
        "</div>" +
        "</td>" +
        "<td><span class='pc-stage pc-stage--" + stageStatus + "'>" + esc(stageLabel) + "</span></td>" +
        "<td>" +
        '<div class="pc-model-list">' +
        '<span class="pc-model-tag">拆文:GLM4</span>' +
        '<span class="pc-model-tag">笔记:Qwen</span>' +
        "</div>" +
        "</td>" +
        '<td><span class="pc-time">' + esc(item.created_at || "-") + "</span></td>" +
        "<td>" +
        '<div class="pc-actions">' +
        '<a class="pc-action-link" data-action="view" data-rid="' + esc(rid) + '">查看</a>' +
        (stageStatus !== "done" && stageStatus !== "cancelled" && stageStatus !== "failed" ? 
          '<a class="pc-action-link" data-action="pause" data-rid="' + esc(rid) + '">暂停</a>' : "") +
        (stageStatus === "failed" ? 
          '<a class="pc-action-link" data-action="retry" data-rid="' + esc(rid) + '">重试</a>' : "") +
        (stageStatus !== "done" ? 
          '<a class="pc-action-link pc-action-link--danger" data-action="cancel" data-rid="' + esc(rid) + '">终止</a>' : "") +
        "</div>" +
        "</td>" +
        "</tr>";
    }

    tbody.innerHTML = html;

    // 绑定 checkbox 事件
    tbody.querySelectorAll(".pc-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        const rid = cb.dataset.rid;
        if (cb.checked) {
          selectedIds.add(rid);
        } else {
          selectedIds.delete(rid);
        }
        updateBatchBtn();
      });
    });

    // 绑定操作按钮
    tbody.querySelectorAll(".pc-action-link").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const action = link.dataset.action;
        const rid = link.dataset.rid;
        handleAction(action, [rid]);
      });
    });
  }

  /* ===== 操作处理 ===== */
  function handleAction(action, recordIds) {
    const count = recordIds.length;
    let title = "";
    let body = "";

    if (action === "pause") {
      title = "暂停任务";
      body = "确定暂停 " + count + " 个任务？暂停后任务将停止执行。";
    } else if (action === "retry") {
      title = "重试任务";
      body = "确定重试 " + count + " 个失败任务？任务将重新进入队列。";
    } else if (action === "cancel") {
      title = "终止任务";
      body = "确定终止 " + count + " 个任务？终止后无法恢复。";
    } else if (action === "view") {
      // 查看详情跳转
      if (recordIds.length === 1) {
        window.open("/notes/" + recordIds[0], "_blank");
      }
      return;
    }

    pendingAction = { action, recordIds };
    $("#pcModalTitle").textContent = title;
    $("#pcModalBody").textContent = body;
    $("#pcModalOverlay").classList.add("visible");
  }

  async function executeAction() {
    if (!pendingAction) return;
    const { action, recordIds } = pendingAction;
    const confirmBtn = $("#pcModalConfirm");
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = "执行中...";
    }

    try {
      let url = "";
      let body = {};
      if (action === "pause") {
        url = recordIds.length === 1 ? "/api/production/pause" : "/api/production/batch-pause";
        body = recordIds.length === 1 ? { record_id: recordIds[0] } : { record_ids: recordIds };
      } else if (action === "retry") {
        url = recordIds.length === 1 ? "/api/production/retry" : "/api/production/batch-retry";
        body = recordIds.length === 1 ? { record_id: recordIds[0] } : { record_ids: recordIds };
      } else if (action === "cancel") {
        url = recordIds.length === 1 ? "/api/production/cancel" : "/api/production/batch-cancel";
        body = recordIds.length === 1 ? { record_id: recordIds[0] } : { record_ids: recordIds };
      }

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const json = await res.json();
      if (!json.ok) throw new Error(json.error);

      closeModal();
      showToast("success", "操作成功");
      selectedIds.clear();
      loadList();
      loadStats();
    } catch (e) {
      showToast("error", "操作失败: " + e.message);
    } finally {
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = "确认";
      }
    }
  }

  /* ===== 分页 ===== */
  function renderPagination(totalPages) {
    const el = $("#pcPagination");
    if (!el) return;
    if (totalPages <= 1) {
      el.innerHTML = "";
      return;
    }

    let html = "";
    html += '<button class="pc-page-btn" data-page="prev"' + (currentPage === 1 ? " disabled" : "") + ">«</button>";

    for (let p = 1; p <= totalPages; p++) {
      if (p === 1 || p === totalPages || (p >= currentPage - 2 && p <= currentPage + 2)) {
        html += '<button class="pc-page-btn' + (p === currentPage ? " active" : "") + '" data-page="' + p + '">' + p + "</button>";
      } else if (p === currentPage - 3 || p === currentPage + 3) {
        html += '<span style="color: #999;">...</span>';
      }
    }

    html += '<button class="pc-page-btn" data-page="next"' + (currentPage === totalPages ? " disabled" : "") + ">»</button>";

    el.innerHTML = html;

    el.querySelectorAll(".pc-page-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const page = btn.dataset.page;
        if (page === "prev") {
          if (currentPage > 1) currentPage--;
        } else if (page === "next") {
          if (currentPage < totalPages) currentPage++;
        } else {
          currentPage = parseInt(page, 10);
        }
        loadList();
      });
    });
  }

  /* ===== Tab 筛选 ===== */
  function bindTabs() {
    $$(".pc-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$(".pc-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        currentStatus = tab.dataset.status;
        currentPage = 1;
        loadList();
      });
    });
  }

  /* ===== 工具栏绑定 ===== */
  function bindToolbar() {
    const search = $("#pcSearch");
    if (search) {
      let timer;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => { currentPage = 1; loadList(); }, 300);
      });
    }

    // 重置按钮
    const resetBtn = $("#pcResetBtn");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        $("#pcSearch").value = "";
        $("#pcModel").value = "";
        $("#pcCategory").value = "";
        currentStatus = "";
        currentPage = 1;
        $$(".pc-tab").forEach((t) => t.classList.remove("active"));
        $$(".pc-tab")[0].classList.add("active");
        loadList();
      });
    }

    // 全选
    const selectAll = $("#pcSelectAll");
    if (selectAll) {
      selectAll.addEventListener("change", () => {
        const checkboxes = $$(".pc-checkbox");
        checkboxes.forEach((cb) => {
          cb.checked = selectAll.checked;
          const rid = cb.dataset.rid;
          if (selectAll.checked) {
            selectedIds.add(rid);
          } else {
            selectedIds.delete(rid);
          }
        });
        updateBatchBtn();
      });
    }
  }

  /* ===== 批量操作菜单 ===== */
  function bindBatchMenu() {
    const btn = $("#pcBatchBtn");
    const menu = $("#pcBatchMenu");
    if (btn && menu) {
      btn.addEventListener("click", () => {
        menu.classList.toggle("visible");
      });

      // 点击外部关闭
      document.addEventListener("click", (e) => {
        if (!btn.contains(e.target) && !menu.contains(e.target)) {
          menu.classList.remove("visible");
        }
      });

      // 菜单项点击
      menu.querySelectorAll(".pc-batch-menu-item").forEach((item) => {
        item.addEventListener("click", () => {
          const action = item.dataset.action;
          const recordIds = Array.from(selectedIds);
          if (recordIds.length > 0) {
            handleAction(action, recordIds);
          }
          menu.classList.remove("visible");
        });
      });
    }
  }

  /* ===== 弹窗 ===== */
  function bindModal() {
    const overlay = $("#pcModalOverlay");
    if (!overlay) return;

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeModal();
    });

    const cancelBtn = $("#pcModalCancel");
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

    const confirmBtn = $("#pcModalConfirm");
    if (confirmBtn) confirmBtn.addEventListener("click", executeAction);
  }

  function closeModal() {
    const overlay = $("#pcModalOverlay");
    if (overlay) overlay.classList.remove("visible");
    pendingAction = null;
  }

  function updateBatchBtn() {
    const btn = $("#pcBatchBtn");
    if (btn) {
      btn.disabled = selectedIds.size === 0;
      btn.innerHTML = '<i data-lucide="more-horizontal"></i> 批量操作 (' + selectedIds.size + ")";
      if (typeof lucide !== "undefined") lucide.createIcons();
    }
  }

  /* ===== Toast ===== */
  function showToast(type, message) {
    let toast = $(".pc-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "pc-toast";
      document.body.appendChild(toast);
    }
    toast.className = "pc-toast pc-toast-" + type;
    toast.textContent = message;
    toast.classList.add("visible");
    setTimeout(() => toast.classList.remove("visible"), 3000);
  }

  /* ===== 工具函数 ===== */
  function setText(sel, val) {
    const el = $(sel);
    if (el) el.textContent = val != null ? val : "0";
  }

  function esc(str) {
    if (str == null) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
})();
