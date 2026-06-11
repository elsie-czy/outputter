/**
 * 选题池页面交互模块
 * - 加载选题列表
 * - 搜索 / 筛选 / 排序
 * - 多选卡片
 * - 右侧面板统计
 * - KPI 轮询
 * - 弹窗确认提交
 * - 分页
 */
(function () {
  "use strict";

  /* ===== 状态 ===== */
  let allItems = [];
  let selectedIds = new Set();
  let currentSort = "score";
  let pollInterval = null;
  let currentPage = 1;
  const PAGE_SIZE = 12;

  /* ===== DOM 缓存 ===== */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  /* ===== 初始化 ===== */
  document.addEventListener("DOMContentLoaded", () => {
    loadTopics();
    loadKPI();
    bindToolbar();
    bindSubmit();
    bindModal();
    pollInterval = setInterval(loadKPI, 30000);
  });

  /* ===== 数据加载 ===== */
  async function loadTopics() {
    const grid = $(".tp-grid");
    if (!grid) return;
    grid.innerHTML = '<div class="tp-loading">加载中...</div>';

    try {
      const res = await fetch("/api/deconstruct/queue?per_page=500&status=pending");
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);
      allItems = json.data.items || [];
      currentPage = 1;
      renderGrid();
    } catch (e) {
      grid.innerHTML =
        '<div class="tp-empty"><div class="tp-empty-icon">✕</div><div class="tp-empty-title">加载失败</div><div class="tp-empty-desc">' +
        esc(e.message) +
        "</div></div>";
    }
  }

  async function loadKPI() {
    try {
      const res = await fetch("/api/topic-pool/stats");
      const json = await res.json();
      if (!json.ok) return;
      const d = json.data;
      setText("#kpiPending", d.pending_topics);
      setText("#kpiToday", d.today_added);
      setText("#kpiHighPot", d.high_potential);
    } catch (_) {}
  }

  function setText(sel, val) {
    const el = $(sel);
    if (el) el.textContent = val != null ? val : "—";
  }

  /* ===== 筛选 / 排序 ===== */
  function getFiltered() {
    const q = ($("#tpSearch")?.value || "").trim().toLowerCase();
    const platform = $("#tpPlatform")?.value || "";
    const category = $("#tpCategory")?.value || "";
    const scoreLevel = $("#tpScoreLevel")?.value || "";

    let list = allItems.slice();

    if (q) {
      list = list.filter(
        (i) =>
          (i.work_name || "").toLowerCase().includes(q) ||
          (i.author || "").toLowerCase().includes(q)
      );
    }
    if (platform) list = list.filter((i) => i.platform === platform);
    if (category) list = list.filter((i) => i.category === category);
    if (scoreLevel) {
      list = list.filter((i) => {
        const s = i.quality_score || 0;
        if (scoreLevel === "s") return s >= 90;
        if (scoreLevel === "a") return s >= 80 && s < 90;
        if (scoreLevel === "b") return s >= 70 && s < 80;
        if (scoreLevel === "c") return s < 70;
        return true;
      });
    }

    const sortFns = {
      score: (a, b) => (b.quality_score || 0) - (a.quality_score || 0),
      favorites: (a, b) => (b.favorites || 0) - (a.favorites || 0),
      likes: (a, b) => (b.likes || 0) - (a.likes || 0),
      comments: (a, b) => (b.comments || 0) - (a.comments || 0),
      created_at: (a, b) => (b.created_at || "").localeCompare(a.created_at || ""),
    };
    list.sort(sortFns[currentSort] || sortFns.score);

    return list;
  }

  function renderGrid() {
    const grid = $(".tp-grid");
    if (!grid) return;
    const filtered = getFiltered();

    if (filtered.length === 0) {
      grid.innerHTML =
        '<div class="tp-empty">' +
        '<div class="tp-empty-icon">📚</div>' +
        '<div class="tp-empty-title">暂无待处理作品</div>' +
        '<div class="tp-empty-desc">请先同步飞书选题库或调整筛选条件</div>' +
        '<button class="tp-empty-btn" onclick="location.reload()">刷新</button>' +
        "</div>";
      renderPagination(0);
      updateSidebar();
      return;
    }

    const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
    if (currentPage > totalPages) currentPage = totalPages;
    const start = (currentPage - 1) * PAGE_SIZE;
    const pageItems = filtered.slice(start, start + PAGE_SIZE);

    let html = "";
    for (const item of pageItems) {
      const rid = item.record_id || "";
      const sel = selectedIds.has(rid) ? " selected" : "";
      const score = item.quality_score;
      const scoreInfo = getScoreInfo(score);

      html +=
        '<div class="tp-card' + sel + '" data-rid="' + esc(rid) + '">' +
        '<div class="tp-card-checkbox">' + (sel ? "✓" : "") + "</div>" +
        '<div class="tp-card-cover">📖</div>' +
        '<div class="tp-card-body">' +
        '<div class="tp-card-name">' + esc(item.work_name || "未知作品") + "</div>" +
        '<div class="tp-card-author">' + esc(item.author || "未知作者") + "</div>" +
        '<div class="tp-card-meta">' +
        '<span class="tp-card-meta-tag">' + esc(item.platform || "-") + "</span>" +
        '<span class="tp-card-meta-tag">' + esc(item.category || "-") + "</span>" +
        (item.word_count ? '<span class="tp-card-meta-tag">' + fmtWordCount(item.word_count) + "</span>" : "") +
        "</div>" +
        '<div class="tp-card-metrics">' +
        "<span>收藏 " + fmtNum(item.favorites) + "</span>" +
        "<span>点赞 " + fmtNum(item.likes) + "</span>" +
        (item.monthly_votes ? "<span>月票 " + fmtNum(item.monthly_votes) + "</span>" : "") +
        (item.recommend_votes ? "<span>推荐 " + fmtNum(item.recommend_votes) + "</span>" : "") +
        "<span>评论 " + fmtNum(item.comments) + "</span>" +
        (item.rank ? "<span>排名 #" + item.rank + "</span>" : "") +
        "</div>" +
        '<div class="tp-card-score-row">' +
        (score
          ? '<span class="tp-card-score ' + scoreInfo.cls + '">综合评分 ' + score + scoreInfo.label + "</span>" +
            '<span class="tp-ai-tag tp-ai-tag--' + scoreInfo.level + '">AI ' + scoreInfo.level.toUpperCase() + "</span>"
          : '<span class="tp-card-score tp-score-c">暂无评分</span>') +
        "</div>" +
        "</div>" +
        "</div>";
    }

    grid.innerHTML = html;
    renderPagination(totalPages);

    grid.querySelectorAll(".tp-card").forEach((card) => {
      card.addEventListener("click", () => {
        const rid = card.dataset.rid;
        if (!rid) return;
        if (selectedIds.has(rid)) {
          selectedIds.delete(rid);
          card.classList.remove("selected");
          card.querySelector(".tp-card-checkbox").innerHTML = "";
        } else {
          selectedIds.add(rid);
          card.classList.add("selected");
          card.querySelector(".tp-card-checkbox").innerHTML = "✓";
        }
        updateSidebar();
        updateKpiSelected();
      });
    });

    updateSidebar();
  }

  function getScoreInfo(score) {
    if (!score) return { cls: "tp-score-c", label: "", level: "c" };
    if (score >= 90) return { cls: "tp-score-s", label: " S级", level: "s" };
    if (score >= 80) return { cls: "tp-score-a", label: " A级", level: "a" };
    if (score >= 70) return { cls: "tp-score-b", label: " B级", level: "b" };
    return { cls: "tp-score-c", label: " C级", level: "c" };
  }

  /* ===== 分页 ===== */
  function renderPagination(totalPages) {
    const el = $("#tpPagination");
    if (!el) return;
    if (totalPages <= 1) {
      el.innerHTML = "";
      return;
    }

    let html = "";
    html += '<button class="tp-page-btn" data-page="prev"' + (currentPage === 1 ? " disabled" : "") + ">«</button>";

    for (let p = 1; p <= totalPages; p++) {
      if (p === 1 || p === totalPages || (p >= currentPage - 2 && p <= currentPage + 2)) {
        html += '<button class="tp-page-btn' + (p === currentPage ? " active" : "") + '" data-page="' + p + '">' + p + "</button>";
      } else if (p === currentPage - 3 || p === currentPage + 3) {
        html += '<span class="tp-page-ellipsis">...</span>';
      }
    }

    html += '<button class="tp-page-btn" data-page="next"' + (currentPage === totalPages ? " disabled" : "") + ">»</button>";

    el.innerHTML = html;

    el.querySelectorAll(".tp-page-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const page = btn.dataset.page;
        if (page === "prev") {
          if (currentPage > 1) currentPage--;
        } else if (page === "next") {
          if (currentPage < totalPages) currentPage++;
        } else {
          currentPage = parseInt(page, 10);
        }
        renderGrid();
      });
    });
  }

  /* ===== 工具栏绑定 ===== */
  function bindToolbar() {
    const search = $("#tpSearch");
    if (search) {
      let timer;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => { currentPage = 1; renderGrid(); }, 300);
      });
    }

    const platform = $("#tpPlatform");
    if (platform) platform.addEventListener("change", () => { currentPage = 1; renderGrid(); });

    const category = $("#tpCategory");
    if (category) category.addEventListener("change", () => { currentPage = 1; renderGrid(); });

    const scoreLevel = $("#tpScoreLevel");
    if (scoreLevel) scoreLevel.addEventListener("change", () => { currentPage = 1; renderGrid(); });

    // 排序按钮
    $$(".tp-sort-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".tp-sort-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentSort = btn.dataset.sort || "score";
        currentPage = 1;
        renderGrid();
      });
    });

    // 全选
    bindBtn("#tpSelectAll", () => {
      const filtered = getFiltered();
      filtered.forEach((i) => selectedIds.add(i.record_id));
      renderGrid();
    });

    // 取消全选
    bindBtn("#tpDeselectAll", () => {
      const filtered = getFiltered();
      filtered.forEach((i) => selectedIds.delete(i.record_id));
      renderGrid();
    });

    // 仅高潜
    bindBtn("#tpSelectHighPot", () => {
      selectedIds.clear();
      allItems.forEach((i) => {
        if ((i.quality_score || 0) >= 80) selectedIds.add(i.record_id);
      });
      currentPage = 1;
      renderGrid();
    });

    // 清空
    bindBtn("#tpClearSelect", () => {
      selectedIds.clear();
      renderGrid();
    });
  }

  function bindBtn(sel, fn) {
    const el = $(sel);
    if (el) el.addEventListener("click", fn);
  }

  /* ===== 右侧面板 ===== */
  function updateSidebar() {
    const selected = allItems.filter((i) => selectedIds.has(i.record_id));
    const count = selected.length;

    setText("#tpSelectedCount", count + "篇");

    // 分类分布
    const catMap = {};
    selected.forEach((i) => { const c = i.category || "未知"; catMap[c] = (catMap[c] || 0) + 1; });
    const catEl = $("#tpCategoryDist");
    if (catEl) {
      catEl.innerHTML = Object.entries(catMap)
        .map(([k, v]) => '<span class="tp-distribution-tag">' + esc(k) + " " + v + "</span>")
        .join("") || '<span class="text-muted">—</span>';
    }

    // 平台分布
    const platMap = {};
    selected.forEach((i) => { const p = i.platform || "未知"; platMap[p] = (platMap[p] || 0) + 1; });
    const platEl = $("#tpPlatformDist");
    if (platEl) {
      platEl.innerHTML = Object.entries(platMap)
        .map(([k, v]) => '<span class="tp-distribution-tag">' + esc(k) + " " + v + "</span>")
        .join("") || '<span class="text-muted">—</span>';
    }

    // 核心指标均值
    const avgMetric = (key) => {
      const vals = selected.map((i) => i[key]).filter((v) => v != null && v > 0);
      return vals.length > 0 ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null;
    };
    const setMetric = (id, key) => {
      const el = $(id);
      if (el) { const v = avgMetric(key); el.textContent = v != null ? fmtNum(v) : "—"; }
    };
    setMetric("#tpAvgFav", "favorites");
    setMetric("#tpAvgLikes", "likes");
    setMetric("#tpAvgMonthly", "monthly_votes");
    setMetric("#tpAvgComments", "comments");
    setMetric("#tpAvgRank", "rank");

    // 预计产出
    setText("#tpOutReport", "×" + count);
    setText("#tpOutNote", "×" + count);
    setText("#tpOutScore", "×" + count);

    // KPI 已选作品 & 预计耗时
    setText("#kpiSelected", count);
    setText("#kpiDuration", count > 0 ? Math.ceil(count * 0.5) + "分钟" : "—");

    // 提交按钮
    const submitBtn = $("#tpSubmitBtn");
    if (submitBtn) {
      submitBtn.disabled = count === 0;
      submitBtn.textContent = "提交生产（" + count + "篇）";
    }
  }

  function updateKpiSelected() {
    setText("#kpiSelected", selectedIds.size);
  }

  /* ===== 提交生产 ===== */
  function bindSubmit() {
    const btn = $("#tpSubmitBtn");
    if (!btn) return;
    btn.addEventListener("click", () => {
      if (selectedIds.size === 0) return;
      openModal();
    });
  }

  function openModal() {
    const overlay = $("#tpModalOverlay");
    if (!overlay) return;

    const selected = allItems.filter((i) => selectedIds.has(i.record_id));

    const listEl = $("#tpModalList");
    if (listEl) {
      listEl.innerHTML = selected
        .map((i) => "<li>" + esc(i.work_name || "未知") + " — " + esc(i.author || "未知") + "</li>")
        .join("");
    }

    const infoEl = $("#tpModalInfo");
    if (infoEl) {
      infoEl.innerHTML =
        "执行流程：<span>✓ 拆文分析</span> <span>✓ 笔记生成</span> <span>✓ AI评分</span><br>" +
        "预计耗时：<span>~" + Math.ceil(selected.length * 0.5) + "分钟</span>";
    }

    overlay.classList.add("visible");
  }

  function bindModal() {
    const overlay = $("#tpModalOverlay");
    if (!overlay) return;

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeModal();
    });

    const cancelBtn = $("#tpModalCancel");
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

    const confirmBtn = $("#tpModalConfirm");
    if (confirmBtn) confirmBtn.addEventListener("click", submitProduction);
  }

  function closeModal() {
    const overlay = $("#tpModalOverlay");
    if (overlay) overlay.classList.remove("visible");
  }

  async function submitProduction() {
    const selected = allItems.filter((i) => selectedIds.has(i.record_id));
    if (selected.length === 0) return;

    const confirmBtn = $("#tpModalConfirm");
    if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.textContent = "提交中..."; }

    try {
      const works = selected.map((i) => ({
        record_id: i.record_id,
        作品名称: i.work_name,
        作者: i.author,
        平台: i.platform,
        分类: i.category,
      }));

      const res = await fetch("/api/deconstruct/batch-enqueue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ works: works }),
      });

      const json = await res.json();
      if (!json.ok) throw new Error(json.error);

      closeModal();
      showToast("success", "✓ 成功提交 " + json.data.enqueued + " 篇作品");
      selectedIds.clear();
      loadTopics();
      loadKPI();
    } catch (e) {
      showToast("error", "✕ 提交失败：" + e.message);
    } finally {
      if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = "确认提交"; }
    }
  }

  /* ===== Toast ===== */
  function showToast(type, message) {
    let toast = $(".tp-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "tp-toast";
      document.body.appendChild(toast);
    }
    toast.className = "tp-toast tp-toast-" + type;
    toast.innerHTML = message;
    toast.classList.add("visible");
    setTimeout(() => toast.classList.remove("visible"), 3000);
  }

  /* ===== 工具函数 ===== */
  function esc(str) {
    if (str == null) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function fmtNum(n) {
    if (n == null) return "—";
    if (n >= 10000) return (n / 10000).toFixed(1) + "万";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  function fmtWordCount(n) {
    if (n == null) return "—";
    if (n >= 10000) return (n / 10000).toFixed(1) + "万字";
    return n + "字";
  }
})();
