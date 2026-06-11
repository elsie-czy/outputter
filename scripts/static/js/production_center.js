/**
 * 生产中心页面交互模块
 * - 加载任务列表
 * - 搜索 / 筛选
 * - 多选任务
 * - 分页
 * - 统计轮询
 */
(function () {
  "use strict";

  /* ===== 状态 ===== */
  let currentPage = 1;
  let currentStatus = "";
  let currentSort = "created_at";
  let pollInterval = null;
  let selectedIds = new Set();
  const PAGE_SIZE = 20;

  /* ===== DOM 缓存 ===== */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  /* ===== 初始化 ===== */
  document.addEventListener("DOMContentLoaded", () => {
    loadStats();
    loadList();
    bindToolbar();
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
        sort: currentSort,
      });
      if (currentStatus) params.set("status", currentStatus);
      if (q) params.set("q", q);

      const res = await fetch("/api/production/list?" + params.toString());
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);

      const items = json.data.items || [];
      const total = json.data.total || 0;

      if (items.length === 0) {
        tbody.innerHTML = '<tr class="pc-empty"><td colspan="8">暂无任务</td></tr>';
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
      const progress = getProgress(item);
      const stage = getStage(item);
      const model = getModel(item);

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
        (item.word_count ? "<span>" + fmtWordCount(item.word_count) + "</span>" : "") +
        "</div>" +
        "</td>" +
        "<td>" +
        '<div class="pc-progress">' +
        '<div class="pc-progress-bar"><div class="pc-progress-fill" style="width:' + progress.value + '%"></div></div>' +
        '<span class="pc-progress-text">' + progress.value + "%</span>" +
        "</div>" +
        "</td>" +
        "<td><span class="pc-stage pc-stage--" + stage.cls + ">" + stage.label + "</span></td>" +
        "<td><span class='pc-model-tag'>" + esc(model) + "</span></td>" +
        '<td><span class="pc-time">' + esc(item.created_at || "-") + "</span></td>" +
        "<td>" +
        '<div class="pc-actions">' +
        '<a class="pc-action-link" data-action="view" data-rid="' + esc(rid) + '">查看</a>' +
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
  }

  function getProgress(item) {
    const status = item.status;
    if (status === "completed") return { value: 100 };
    if (status === "failed") return { value: 0 };
    if (status === "processing") return { value: 50 };
    return { value: 0 };
  }

  function getStage(item) {
    const status = item.status;
    if (status === "completed") return { cls: "completed", label: "已完成" };
    if (status === "failed") return { cls: "failed", label: "已失败" };
    if (status === "processing") return { cls: "processing", label: "生产中" };
    return { cls: "waiting", label: "等待中" };
  }

  function getModel(item) {
    return "GLM-4";
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
    html += '<span class="pc-page-info">共 ' + totalPages + ' 页</span>';

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

    const statusSelect = $("#pcStatus");
    if (statusSelect) {
      statusSelect.addEventListener("change", () => {
        currentStatus = statusSelect.value;
        currentPage = 1;
        loadList();
      });
    }

    const sortSelect = $("#pcSort");
    if (sortSelect) {
      sortSelect.addEventListener("change", () => {
        currentSort = sortSelect.value;
        currentPage = 1;
        loadList();
      });
    }

    // 重置按钮
    const resetBtn = $("#pcResetBtn");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        $("#pcSearch").value = "";
        $("#pcStatus").value = "";
        $("#pcSort").value = "created_at";
        currentStatus = "";
        currentSort = "created_at";
        currentPage = 1;
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

  function updateBatchBtn() {
    const btn = $("#pcBatchBtn");
    if (btn) {
      btn.disabled = selectedIds.size === 0;
      btn.innerHTML = '<i data-lucide="more-horizontal"></i> 批量操作 (' + selectedIds.size + ")";
      if (typeof lucide !== "undefined") lucide.createIcons();
    }
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

  function fmtWordCount(n) {
    if (n == null) return "";
    if (n >= 10000) return (n / 10000).toFixed(1) + "万字";
    return n + "字";
  }
})();
