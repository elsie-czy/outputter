/**
 * 生产中心页面交互模块
 * - Tab 状态筛选
 * - 搜索 / 前端筛选
 * - 多选任务与批量操作
 * - 单任务查看 / 暂停 / 重试 / 终止
 * - 5 秒静默刷新
 */
(function () {
  "use strict";

  let currentPage = 1;
  let currentStatus = "";
  let pollInterval = null;
  let selectedIds = new Set();
  let pendingAction = null;
  let lastTableHtml = "";
  let lastItems = [];
  let lastTotal = 0;
  const PAGE_SIZE = 20;
  const POLL_MS = 5000;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  document.addEventListener("DOMContentLoaded", () => {
    loadStats();
    loadList();
    bindToolbar();
    bindTabs();
    bindBatchMenu();
    bindModal();
    pollInterval = setInterval(refreshVisibleData, POLL_MS);
    window.addEventListener("pagehide", stopPolling);
    window.addEventListener("beforeunload", stopPolling);
  });

  async function loadStats() {
    try {
      const [statsRes, totalDoneRes, allRes, reviewRes, failedRes] = await Promise.all([
        fetch("/api/production/stats"),
        fetch("/api/production/list?status=done&page=1&per_page=1"),
        fetch("/api/production/list?page=1&per_page=1"),
        fetch("/api/production/list?status=human_review&page=1&per_page=1"),
        fetch("/api/production/list?status=failed,cancelled&page=1&per_page=1"),
      ]);
      const statsJson = await statsRes.json();
      const totalDoneJson = await totalDoneRes.json();
      const allJson = await allRes.json();
      const reviewJson = await reviewRes.json();
      const failedJson = await failedRes.json();
      if (!statsJson.ok) return;

      const d = statsJson.data || {};
      const doneTotal = totalDoneJson?.data?.total || 0;
      const allTotal = allJson?.data?.total || 0;
      const reviewTotal = reviewJson?.data?.total || 0;
      const failedTotal = failedJson?.data?.total || d.today_failed || 0;

      setText("#statTotalDone", doneTotal);
      setText("#statProcessing", d.processing || 0);
      setText("#statReview", reviewTotal);
      setText("#statPending", d.pending || 0);
      setText("#statFailed", failedTotal);
      setText("#tabAllCount", allTotal);
      setText("#tabProcessingCount", d.processing || 0);
      setText("#tabPendingCount", d.pending || 0);
      setText("#tabReviewCount", reviewTotal);
      setText("#tabDoneCount", doneTotal);
      setText("#tabFailedCount", failedTotal);
      setText("#tokenUsed", ((d.token_used || 0) / 10000).toFixed(0) + "万");
      setText("#todayOutput", d.today_completed || 0);

      const estRemain = d.pending > 0 ? Math.ceil(d.pending * (d.avg_duration || 0)) : 0;
      setText("#estRemain", estRemain > 0 ? estRemain + "分钟" : "-");
    } catch (_) {}
  }

  async function loadList(options) {
    options = options || {};
    const tbody = $("#pcTableBody");
    if (!tbody) return;
    if (!options.silent) {
      tbody.innerHTML = '<tr class="pc-loading"><td colspan="8">加载中...</td></tr>';
      lastTableHtml = "";
    }

    try {
      const q = ($("#pcSearch")?.value || "").trim();
      const params = new URLSearchParams({ page: currentPage, per_page: PAGE_SIZE });
      if (currentStatus) params.set("status", currentStatus);
      if (q) params.set("q", q);

      const res = await fetch("/api/production/list?" + params.toString());
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "列表加载失败");

      lastItems = json.data.items || [];
      lastTotal = json.data.total || 0;
      renderCurrentItems(lastTotal, options.silent);
    } catch (e) {
      tbody.innerHTML = '<tr class="pc-error-row"><td colspan="8">加载失败: ' + esc(e.message) + "</td></tr>";
      lastTableHtml = "";
    }
  }

  function renderCurrentItems(total, silent) {
    const tbody = $("#pcTableBody");
    const items = applyLocalFilters(lastItems);
    if (!items.length) {
      const html =
        '<tr class="pc-empty-row"><td colspan="8">' +
        '<div class="pc-empty">' +
        '<div class="pc-empty-icon"><i data-lucide="inbox"></i></div>' +
        '<div class="pc-empty-title">暂无匹配任务</div>' +
        '<div class="pc-empty-desc">调整状态、分类或搜索关键词后再查看</div>' +
        '<a href="/topic-pool" class="pc-empty-btn">前往选题池</a>' +
        "</div></td></tr>";
      setTableHtml(tbody, html, silent);
      renderPagination(total ? Math.ceil(total / PAGE_SIZE) : 0);
      return;
    }

    const html = items.map(renderRow).join("");
    setTableHtml(tbody, html, silent);
    renderPagination(Math.ceil(total / PAGE_SIZE));
    syncSelectionState();
  }

  function setTableHtml(tbody, html, silent) {
    if (silent && html === lastTableHtml) return;
    tbody.innerHTML = html;
    lastTableHtml = html;
    bindRowEvents(tbody);
    refreshIcons();
  }

  function applyLocalFilters(items) {
    const category = ($("#pcCategory")?.value || "").trim();
    const model = ($("#pcModel")?.value || "").trim();
    const stage = ($("#pcStage")?.value || "").trim();
    return items.filter((item) => {
      const status = normalizedStatus(item);
      const categoryText = String(item.category || "");
      if (category && categoryText.indexOf(category) === -1) return false;
      if (stage && status !== stage) return false;
      if (model === "glm" || model === "qwen") return true;
      return true;
    });
  }

  function renderRow(item) {
    const rid = item.record_id || "";
    const checked = selectedIds.has(rid) ? " checked" : "";
    const selectedClass = selectedIds.has(rid) ? " is-selected" : "";
    const progress = clamp(item.progress_percent || 0, 0, 100);
    const status = normalizedStatus(item);
    const label = item.stage_label || statusLabel(status);
    const error = item.error || "";
    const coverUrl = imgUrl(item.images);
    const categoryTags = splitCategory(item.category).slice(0, 4);

    return (
      '<tr class="pc-task-row' + selectedClass + '" data-rid="' + esc(rid) + '">' +
      '<td><input type="checkbox" class="pc-checkbox" data-rid="' + esc(rid) + '"' + checked + " /></td>" +
      '<td><div class="pc-cover">' + renderCover(coverUrl) + "</div></td>" +
      "<td>" +
      '<div class="pc-info-name" title="' + esc(item.work_name || "未知作品") + '">' + esc(item.work_name || "未知作品") + "</div>" +
      '<div class="pc-info-meta">' +
      "<span title=\"作者\">" + esc(item.author || "未知作者") + "</span>" +
      "<span title=\"平台\">" + esc(item.platform || "-") + "</span>" +
      categoryTags.map((tag) => '<span title="分类">' + esc(tag) + "</span>").join("") +
      "</div>" +
      (error ? '<div class="pc-error" title="' + esc(error) + '">' + esc(error) + "</div>" : "") +
      "</td>" +
      "<td>" +
      '<div class="pc-progress" title="进度 ' + progress + '%">' +
      '<div class="pc-progress-bar"><div class="pc-progress-fill" style="width:' + progress + '%"></div></div>' +
      '<span class="pc-progress-text">' + progress + "%</span>" +
      "</div>" +
      "</td>" +
      '<td><span class="pc-stage pc-stage--' + esc(status) + '">' + esc(label) + "</span></td>" +
      "<td><div class=\"pc-model-list\">" +
      '<span class="pc-model-tag">拆文-GLM4</span>' +
      '<span class="pc-model-tag">笔记-Qwen</span>' +
      "</div></td>" +
      '<td><span class="pc-time">' + esc(formatTime(item.created_at)) + "</span></td>" +
      '<td><div class="pc-actions">' + renderActions(status, rid) + "</div></td>" +
      "</tr>"
    );
  }

  function renderCover(url) {
    if (url) return '<img src="' + esc(url) + '" alt="" loading="lazy" onerror="this.closest(\'.pc-cover\').classList.add(\'pc-cover--missing\');this.remove();" />';
    return '<i data-lucide="image-off"></i>';
  }

  function renderActions(status, rid) {
    const safeRid = esc(rid);
    let html = "";
    if (!["done", "cancelled", "failed"].includes(status)) {
      html += '<a class="pc-action-link" data-action="pause" data-rid="' + safeRid + '" data-tooltip="暂停任务"><i data-lucide="pause"></i></a>';
    }
    if (status === "failed") {
      html += '<a class="pc-action-link" data-action="retry" data-rid="' + safeRid + '" data-tooltip="重试任务"><i data-lucide="rotate-cw"></i></a>';
    }
    if (status !== "done") {
      html += '<a class="pc-action-link pc-action-link--danger" data-action="cancel" data-rid="' + safeRid + '" data-tooltip="终止任务"><i data-lucide="octagon-x"></i></a>';
    }
    html += '<a class="pc-action-link pc-action-link--primary" href="/task/' + safeRid + '" target="_blank" rel="noopener" data-action="view" data-rid="' + safeRid + '" data-tooltip="查看详情"><i data-lucide="external-link"></i><span>查看</span></a>';
    return html;
  }

  function bindRowEvents(tbody) {
    tbody.querySelectorAll(".pc-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        const rid = cb.dataset.rid;
        if (cb.checked) selectedIds.add(rid);
        else selectedIds.delete(rid);
        syncSelectionState();
      });
    });

    tbody.querySelectorAll(".pc-action-link").forEach((link) => {
      link.addEventListener("click", (e) => {
        if (link.dataset.action === "view") return;
        e.preventDefault();
        handleAction(link.dataset.action, [link.dataset.rid]);
      });
    });
  }

  function refreshVisibleData() {
    loadStats();
    loadList({ silent: true });
  }

  function stopPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = null;
  }

  function imgUrl(imgs) {
    if (!imgs) return null;
    const cover = imgs.cover || imgs[Object.keys(imgs)[0]];
    if (!cover) return null;
    if (cover.indexOf("http") === 0) return cover;
    const p = cover.replace(/^temp\/(jimeng_cache|generated_images)\//, "");
    return "/_health/images/" + encodeURI(p);
  }

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
      if (recordIds.length === 1) window.open("/task/" + recordIds[0], "_blank");
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
      const map = {
        pause: ["/api/production/pause", "/api/production/batch-pause", "record_id", "record_ids"],
        retry: ["/api/production/retry", "/api/production/batch-retry", "record_id", "record_ids"],
        cancel: ["/api/production/cancel", "/api/production/batch-cancel", "record_id", "record_ids"],
      };
      const cfg = map[action];
      const isSingle = recordIds.length === 1;
      const res = await fetch(isSingle ? cfg[0] : cfg[1], {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(isSingle ? { [cfg[2]]: recordIds[0] } : { [cfg[3]]: recordIds }),
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "接口返回失败");
      closeModal();
      showToast("success", "操作成功");
      selectedIds.clear();
      await loadList();
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

  function renderPagination(totalPages) {
    const el = $("#pcPagination");
    if (!el) return;
    if (totalPages <= 1) {
      el.innerHTML = "";
      return;
    }
    let html = '<button class="pc-page-btn" data-page="prev"' + (currentPage === 1 ? " disabled" : "") + ">‹</button>";
    for (let p = 1; p <= totalPages; p++) {
      if (p === 1 || p === totalPages || (p >= currentPage - 2 && p <= currentPage + 2)) {
        html += '<button class="pc-page-btn' + (p === currentPage ? " active" : "") + '" data-page="' + p + '">' + p + "</button>";
      } else if (p === currentPage - 3 || p === currentPage + 3) {
        html += '<span style="color:#94A3B8;padding:0 4px;">...</span>';
      }
    }
    html += '<button class="pc-page-btn" data-page="next"' + (currentPage === totalPages ? " disabled" : "") + ">›</button>";
    el.innerHTML = html;
    el.querySelectorAll(".pc-page-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const page = btn.dataset.page;
        if (page === "prev" && currentPage > 1) currentPage--;
        else if (page === "next" && currentPage < totalPages) currentPage++;
        else if (!Number.isNaN(parseInt(page, 10))) currentPage = parseInt(page, 10);
        loadList();
      });
    });
  }

  function bindTabs() {
    $$(".pc-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$(".pc-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        currentStatus = tab.dataset.status || "";
        currentPage = 1;
        selectedIds.clear();
        loadList();
      });
    });
  }

  function bindToolbar() {
    const search = $("#pcSearch");
    if (search) {
      let timer;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          currentPage = 1;
          selectedIds.clear();
          loadList();
        }, 300);
      });
    }
    ["#pcModel", "#pcCategory", "#pcStage"].forEach((sel) => {
      const el = $(sel);
      if (el) el.addEventListener("change", () => renderCurrentItems(lastTotal, false));
    });
    const resetBtn = $("#pcResetBtn");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        $("#pcSearch").value = "";
        $("#pcModel").value = "";
        $("#pcCategory").value = "";
        $("#pcStage").value = "";
        currentStatus = "";
        currentPage = 1;
        selectedIds.clear();
        $$(".pc-tab").forEach((t) => t.classList.remove("active"));
        $$(".pc-tab")[0].classList.add("active");
        loadList();
      });
    }
    const selectAll = $("#pcSelectAll");
    if (selectAll) {
      selectAll.addEventListener("change", () => {
        $$(".pc-checkbox").forEach((cb) => {
          cb.checked = selectAll.checked;
          if (selectAll.checked) selectedIds.add(cb.dataset.rid);
          else selectedIds.delete(cb.dataset.rid);
        });
        syncSelectionState();
      });
    }
  }

  function bindBatchMenu() {
    const btn = $("#pcBatchBtn");
    const menu = $("#pcBatchMenu");
    if (!btn || !menu) return;
    btn.addEventListener("click", () => {
      if (!btn.disabled) menu.classList.toggle("visible");
    });
    document.addEventListener("click", (e) => {
      if (!btn.contains(e.target) && !menu.contains(e.target)) menu.classList.remove("visible");
    });
    menu.querySelectorAll(".pc-batch-menu-item").forEach((item) => {
      item.addEventListener("click", () => {
        const recordIds = Array.from(selectedIds);
        if (recordIds.length) handleAction(item.dataset.action, recordIds);
        menu.classList.remove("visible");
      });
    });
  }

  function bindModal() {
    const overlay = $("#pcModalOverlay");
    if (!overlay) return;
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeModal();
    });
    $("#pcModalCancel")?.addEventListener("click", closeModal);
    $("#pcModalConfirm")?.addEventListener("click", executeAction);
  }

  function closeModal() {
    $("#pcModalOverlay")?.classList.remove("visible");
    pendingAction = null;
  }

  function syncSelectionState() {
    $$(".pc-task-row").forEach((tr) => tr.classList.toggle("is-selected", selectedIds.has(tr.dataset.rid)));
    $$(".pc-checkbox").forEach((cb) => { cb.checked = selectedIds.has(cb.dataset.rid); });
    const visibleBoxes = Array.from($$(".pc-checkbox"));
    const checked = visibleBoxes.filter((cb) => cb.checked).length;
    const selectAll = $("#pcSelectAll");
    if (selectAll) {
      selectAll.checked = visibleBoxes.length > 0 && checked === visibleBoxes.length;
      selectAll.indeterminate = checked > 0 && checked < visibleBoxes.length;
    }
    const btn = $("#pcBatchBtn");
    if (btn) {
      btn.disabled = selectedIds.size === 0;
      btn.innerHTML = '<i data-lucide="more-horizontal"></i> 批量操作' + (selectedIds.size ? " (" + selectedIds.size + ")" : "");
    }
    refreshIcons();
  }

  function refreshIcons() {
    if (typeof lucide !== "undefined") {
      lucide.createIcons();
    } else if (typeof window.createAppFallbackIcons === "function") {
      window.createAppFallbackIcons();
    }
  }

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

  function normalizedStatus(item) {
    const raw = item.display_status || item.status || "waiting";
    if (raw === "pending") return "waiting";
    if (raw === "completed") return "done";
    return raw;
  }

  function statusLabel(status) {
    const labels = {
      waiting: "等待中",
      paused: "已暂停",
      deconstructing: "拆文中",
      generating_note: "生成笔记",
      ai_scoring: "AI评分",
      human_review: "待审核",
      generating_image: "生成图片",
      done: "已完成",
      failed: "失败",
      cancelled: "已终止",
    };
    return labels[status] || status || "未知";
  }

  function splitCategory(value) {
    return String(value || "-")
      .split(/[、/，,\s]+/)
      .map((v) => v.trim())
      .filter(Boolean);
  }

  function formatTime(value) {
    if (!value) return "-";
    return String(value).replace("T", " ").slice(0, 19);
  }

  function clamp(num, min, max) {
    return Math.max(min, Math.min(max, Number(num) || 0));
  }

  function setText(sel, val) {
    const el = $(sel);
    if (el) el.textContent = val != null ? val : "0";
  }

  function esc(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
