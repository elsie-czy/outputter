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
  const PAGE_SIZE = 10;

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
    const grid = $("#tpGrid");
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
    const wordCount = $("#tpWordCount")?.value || "";
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
    if (wordCount) {
      list = list.filter((i) => {
        const wc = i.word_count || 0;
        if (wordCount === "0-50") return wc < 500000;
        if (wordCount === "50-100") return wc >= 500000 && wc < 1000000;
        if (wordCount === "100-200") return wc >= 1000000 && wc < 2000000;
        if (wordCount === "200+") return wc >= 2000000;
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
    const grid = $("#tpGrid");
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
      const catClass = getCategoryClass(item.category);
      const catIcon = getCategoryIcon(item.category);

      html +=
        '<div class="tp-card' + sel + '" data-rid="' + esc(rid) + '">' +
        '<div class="tp-card-checkbox">' + (sel ? "✓" : "") + "</div>" +
        '<div class="tp-card-cover">' + catIcon + '</div>' +
        '<div class="tp-card-content">' +
        '<div class="tp-card-name">' + esc(item.work_name || "未知作品") + "</div>" +
        '<div class="tp-card-author">' + esc(item.author || "未知作者") + "</div>" +
        '<div class="tp-card-meta">' +
        '<span class="tp-card-tag">' + esc(item.platform || "-") + "</span>" +
        '<span class="tp-card-tag ' + catClass + '">' + esc(item.category || "-") + "</span>" +
        (item.word_count ? '<span class="tp-card-tag">' + fmtWordCount(item.word_count) + "</span>" : "") +
        "</div>" +
        '<div class="tp-card-metrics">' +
        '<div class="tp-card-metric"><span class="tp-card-metric-value">' + fmtNum(item.favorites) + '</span><span class="tp-card-metric-label">收藏</span></div>' +
        '<div class="tp-card-metric"><span class="tp-card-metric-value">' + fmtNum(item.likes) + '</span><span class="tp-card-metric-label">点赞</span></div>' +
        '<div class="tp-card-metric"><span class="tp-card-metric-value">' + fmtNum(item.monthly_votes) + '</span><span class="tp-card-metric-label">月票</span></div>' +
        '<div class="tp-card-metric"><span class="tp-card-metric-value">' + fmtNum(item.recommend_votes) + '</span><span class="tp-card-metric-label">推荐</span></div>' +
        '<div class="tp-card-metric"><span class="tp-card-metric-value">' + fmtNum(item.comments) + '</span><span class="tp-card-metric-label">评论</span></div>' +
        '<div class="tp-card-metric"><span class="tp-card-metric-value">' + (item.rank ? "#" + item.rank : "暂无") + '</span><span class="tp-card-metric-label">排名</span></div>' +
        "</div>" +
        "</div>" +
        '<div class="tp-card-score tp-score-' + scoreInfo.level + '">' +
        '<div class="tp-card-score-label">综合评分</div>' +
        '<div class="tp-card-score-value">' + (score || "暂无") + "</div>" +
        '<div class="tp-card-score-level">' + (scoreInfo.label || "待评分") + "</div>" +
        '<div class="tp-card-score-stars">' + scoreInfo.stars + "</div>" +
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
      });
    });

    updateSidebar();
  }

  function getScoreInfo(score) {
    if (!score) return { cls: "tp-score-c", label: "", level: "c", stars: "" };
    if (score >= 90) return { cls: "tp-score-s", label: "极高", level: "s", stars: "★★★★★" };
    if (score >= 80) return { cls: "tp-score-a", label: "很高", level: "a", stars: "★★★★☆" };
    if (score >= 70) return { cls: "tp-score-b", label: "较高", level: "b", stars: "★★★☆☆" };
    if (score >= 60) return { cls: "tp-score-c", label: "一般", level: "c", stars: "★★☆☆☆" };
    return { cls: "tp-score-d", label: "较低", level: "d", stars: "★☆☆☆☆" };
  }

  function getCategoryClass(category) {
    const map = { "玄幻": "tp-card-tag--fantasy", "科幻": "tp-card-tag--scifi" };
    return map[category] || "";
  }

  function getCategoryIcon(category) {
    const map = {
      "都市": "🏙️",
      "玄幻": "⚔️",
      "科幻": "🚀",
      "言情": "💕",
      "幻言": "💕",
      "古言": "🏯",
      "悬疑": "🔍"
    };
    return map[category] || "📖";
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

    ["#tpPlatform", "#tpCategory", "#tpWordCount", "#tpScoreLevel"].forEach((sel) => {
      const el = $(sel);
      if (el) el.addEventListener("change", () => { currentPage = 1; renderGrid(); });
    });

    const sortSelect = $("#tpSort");
    if (sortSelect) {
      sortSelect.addEventListener("change", () => {
        currentSort = sortSelect.value;
        currentPage = 1;
        renderGrid();
      });
    }

    // 重置按钮
    bindBtn("#tpResetBtn", () => {
      $("#tpSearch").value = "";
      $("#tpPlatform").value = "";
      $("#tpCategory").value = "";
      $("#tpWordCount").value = "";
      $("#tpScoreLevel").value = "";
      $("#tpSort").value = "score";
      currentSort = "score";
      currentPage = 1;
      renderGrid();
    });

    // 批量操作
    bindBtn("#tpSelectAll", () => {
      const filtered = getFiltered();
      filtered.forEach((i) => selectedIds.add(i.record_id));
      renderGrid();
    });

    bindBtn("#tpDeselectAll", () => {
      const filtered = getFiltered();
      filtered.forEach((i) => selectedIds.delete(i.record_id));
      renderGrid();
    });

    bindBtn("#tpSelectHighPot", () => {
      selectedIds.clear();
      allItems.forEach((i) => { if ((i.quality_score || 0) >= 80) selectedIds.add(i.record_id); });
      currentPage = 1;
      renderGrid();
    });

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
    setText("#tpBatchCount", count);

    // 分类分布
    const catMap = {};
    selected.forEach((i) => { const c = i.category || "未知"; catMap[c] = (catMap[c] || 0) + 1; });
    const catEl = $("#tpCategoryDist");
    if (catEl) {
      if (count === 0) {
        catEl.innerHTML = '<span class="text-muted">—</span>';
      } else {
        const maxCat = Math.max(...Object.values(catMap));
        catEl.innerHTML = Object.entries(catMap)
          .map(([k, v]) =>
            '<div class="tp-distribution-item">' +
            '<span class="tp-distribution-label">' + esc(k) + "</span>" +
            '<div class="tp-distribution-bar"><div class="tp-distribution-fill" style="width:' + (v / maxCat * 100) + '%"></div></div>' +
            '<span class="tp-distribution-count">' + v + "篇</span>" +
            "</div>"
          ).join("");
      }
    }

    // 平台分布
    const platMap = {};
    selected.forEach((i) => { const p = i.platform || "未知"; platMap[p] = (platMap[p] || 0) + 1; });
    const platEl = $("#tpPlatformDist");
    if (platEl) {
      if (count === 0) {
        platEl.innerHTML = '<span class="text-muted">—</span>';
      } else {
        const maxPlat = Math.max(...Object.values(platMap));
        platEl.innerHTML = Object.entries(platMap)
          .map(([k, v]) =>
            '<div class="tp-distribution-item">' +
            '<span class="tp-distribution-label">' + esc(k) + "</span>" +
            '<div class="tp-distribution-bar"><div class="tp-distribution-fill" style="width:' + (v / maxPlat * 100) + '%"></div></div>' +
            '<span class="tp-distribution-count">' + v + "篇</span>" +
            "</div>"
          ).join("");
      }
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
    setMetric("#tpAvgRecommend", "recommend_votes");
    setMetric("#tpAvgComments", "comments");
    setMetric("#tpAvgRank", "rank");

    // 预计资源消耗
    setText("#tpEstToken", count > 0 ? "≈ " + (count * 3000).toLocaleString() + " Token" : "—");
    setText("#tpEstTime", count > 0 ? "≈ " + Math.ceil(count * 0.5) + "分钟" : "—");

    // 预计产出
    setText("#tpOutReport", "×" + count);
    setText("#tpOutNote", "×" + count);
    setText("#tpOutScore", "×" + count);

    // KPI 已选作品 & 预计耗时
    setText("#kpiSelected", count);
    setText("#kpiDuration", count > 0 ? Math.ceil(count * 0.5) : "—");

    // 提交按钮
    const submitBtn = $("#tpSubmitBtn");
    if (submitBtn) {
      submitBtn.disabled = count === 0;
      submitBtn.textContent = "提交生产（" + count + "篇）";
    }
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
    if (n == null || n === 0) return "暂无";
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
