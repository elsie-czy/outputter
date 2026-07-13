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
let currentQuickFilter = null;
let pollInterval = null;
let currentPage = 1;
let workMode = "client";
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
    bindSyncAndArchive();
    pollInterval = setInterval(loadKPI, 30000);
  });

  /* ===== 数据加载 ===== */
  async function loadTopics() {
    const grid = $("#tpGrid");
    if (!grid) return;
    grid.innerHTML = '<div class="tp-loading">加载中...</div>';

    try {
      // 优先从飞书选题库读取
      const res = await fetch("/api/topic-pool/list");
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);
      allItems = json.data.items || [];
      selectedIds = new Set(Array.from(selectedIds).filter((rid) => {
        const item = allItems.find((i) => i.record_id === rid);
        return item && isSubmittable(item);
      }));
      currentPage = 1;
      renderGrid();
      updatePoolStats();
      // 更新待拆作品 KPI（基于选题库实际拆解状态）
      setText("#kpiPending", allItems.filter(i => isSubmittable(i)).length);
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
      // kpiPending 由 loadTopics() 根据选题库实际状态更新，此处不再覆盖
      setText("#kpiToday", d.today_added);
      setText("#kpiHighPot", d.high_potential);
      
      // 更新工作模式和待归档
      workMode = d.work_mode || "client";
      const syncBtn = $("#tpSyncBtn");
      const archiveBtn = $("#tpArchiveBtn");
      if (syncBtn) syncBtn.style.display = "inline-flex";
      
      if (workMode === "owner") {
        if (archiveBtn && d.pending_archive > 0) {
          archiveBtn.style.display = "flex";
          setText("#archiveCount", d.pending_archive);
        } else if (archiveBtn) {
          archiveBtn.style.display = "none";
        }
      } else {
        if (archiveBtn) archiveBtn.style.display = "none";
      }
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
    const decStatus = $("#tpDeconstructStatus")?.value || "pending";

    let list = allItems.slice();

    if (decStatus === "pending") {
      list = list.filter((i) => !i.is_deconstructed);
    } else if (decStatus === "done") {
      list = list.filter((i) => i.is_deconstructed);
    }
    // "all" 不过滤

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

    // 快捷筛选
    if (currentQuickFilter) {
      if (currentQuickFilter === "high-favorites") {
        list = list.filter((i) => (i.favorites || 0) >= 50000);
      } else if (currentQuickFilter === "high-score") {
        list = list.filter((i) => (i.quality_score || 0) >= 80);
      } else if (currentQuickFilter === "high-interaction") {
        list = list.filter((i) => (i.comments || 0) >= 5000);
      } else if (currentQuickFilter === "potential") {
        list = list.filter((i) => (i.quality_score || 0) >= 70 && (i.quality_score || 0) < 85);
      }
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
      const disabled = !isSubmittable(item);
      const disabledClass = disabled ? " is-disabled" : "";
      const score = item.quality_score;
      const scoreInfo = getScoreInfo(score);
      const catClass = getCategoryClass(item.category);
      const catIcon = getCategoryIcon(item.category);
      const potential = getPotentialInfo(item);
      const statusBadge = getTopicStatusBadge(item);

      html +=
        '<div class="tp-row' + sel + disabledClass + '" data-rid="' + esc(rid) + '">' +
        '<div class="tp-cell tp-cell-select"><div class="tp-card-checkbox" aria-hidden="true">' + (sel ? "✓" : "") + "</div></div>" +
        '<div class="tp-cell tp-cell-work">' +
          '<div class="tp-card-cover">' + catIcon + '</div>' +
          '<div class="tp-card-content">' +
            '<div class="tp-card-name">' + esc(item.work_name || "未知作品") + "</div>" +
            '<div class="tp-card-author">' + esc(item.author || "未知作者") + "</div>" +
            '<div class="tp-card-meta">' +
              '<span class="tp-card-tag tp-card-tag--platform">' + esc(item.platform || "-") + "</span>" +
              '<span class="tp-card-tag ' + catClass + '">' + esc(item.category || "-") + "</span>" +
              (item.word_count ? '<span class="tp-card-tag">' + fmtWordCount(item.word_count) + "</span>" : "") +
            "</div>" +
          "</div>" +
        "</div>" +
        '<div class="tp-cell tp-cell-score">' +
          '<div class="tp-score-pill tp-score-' + scoreInfo.level + '">' +
            '<strong>' + (score || "—") + "</strong>" +
            '<span>' + (scoreInfo.label || "待评分") + "</span>" +
          "</div>" +
          '<div class="tp-card-score-stars">' + scoreInfo.stars + "</div>" +
        "</div>" +
        '<div class="tp-cell tp-cell-source">' +
          '<span class="tp-platform-chip tp-platform-' + getPlatformClass(item.platform) + '">' + esc(item.platform || "未知") + "</span>" +
          '<span class="tp-source-sub">' + esc(item.category || "内容类型") + "</span>" +
        "</div>" +
        '<div class="tp-cell tp-cell-status">' +
          statusBadge +
          '<span class="tp-potential-badge tp-potential-' + potential.level + '">' + potential.label + "</span>" +
        "</div>" +
        '<div class="tp-cell tp-cell-action">' +
          '<button class="tp-icon-action" type="button" title="收藏"><i data-lucide="star"></i></button>' +
          '<button class="tp-icon-action" type="button" title="查看链接"><i data-lucide="link"></i></button>' +
          '<button class="tp-icon-action" type="button" title="' + (disabled ? "已入队" : (sel ? "移出" : "加入生产")) + '" data-action="toggle"' + (disabled ? " disabled" : "") + '><i data-lucide="more-horizontal"></i></button>' +
        "</div>" +
        "</div>";
    }

    grid.innerHTML = html;
    renderPagination(totalPages);

    grid.querySelectorAll(".tp-row").forEach((card) => {
      card.addEventListener("click", () => {
        const rid = card.dataset.rid;
        if (!rid) return;
        const item = allItems.find((i) => i.record_id === rid);
        if (!isSubmittable(item)) {
          showToast("warning", "该作品已在生产中心，请到生产中心查看或重试");
          return;
        }
        if (selectedIds.has(rid)) {
          selectedIds.delete(rid);
          card.classList.remove("selected");
        } else {
          selectedIds.add(rid);
        }
        renderGrid();
      });
    });

    updateSidebar();
    refreshIcons();
  }

  function isSubmittable(item) {
    return !!item && !item.is_deconstructed && !item.is_in_queue;
  }

  function getTopicStatusBadge(item) {
    if (item && item.is_in_queue) {
      const label = queueStatusLabel(item.queue_status);
      return '<span class="tp-badge tp-badge--queued">已在生产中心' + (label ? " · " + esc(label) : "") + "</span>";
    }
    if (item && item.is_deconstructed) {
      return '<span class="tp-badge tp-badge--muted">已拆解</span>';
    }
    return '<span class="tp-badge tp-badge--green">待评估</span>';
  }

  function queueStatusLabel(status) {
    const map = {
      pending: "等待中",
      waiting: "等待中",
      processing: "生产中",
      deconstructing: "拆文中",
      generating_note: "生成笔记",
      ai_scoring: "AI评分",
      human_review: "待审核",
      generating_image: "生成图片",
      done: "已完成",
      failed: "失败",
      cancelled: "已取消",
      paused: "已暂停",
    };
    return map[status] || status || "";
  }

  function getScoreInfo(score) {
    if (!score) return { cls: "tp-score-c", label: "", level: "c", stars: "" };
    if (score >= 90) return { cls: "tp-score-s", label: "极高", level: "s", stars: "★★★★★" };
    if (score >= 80) return { cls: "tp-score-a", label: "很高", level: "a", stars: "★★★★☆" };
    if (score >= 70) return { cls: "tp-score-b", label: "较高", level: "b", stars: "★★★☆☆" };
    if (score >= 60) return { cls: "tp-score-c", label: "一般", level: "c", stars: "★★☆☆☆" };
    return { cls: "tp-score-d", label: "较低", level: "d", stars: "★☆☆☆☆" };
  }

  function getPotentialInfo(item) {
    const score = item.quality_score || 0;
    const favorites = item.favorites || 0;
    const comments = item.comments || 0;
    if (score >= 90 || favorites >= 80000) {
      return { level: "hot", label: "优先生产", desc: "高分或高收藏" };
    }
    if (score >= 80 || comments >= 5000) {
      return { level: "good", label: "建议生产", desc: "互动基础较好" };
    }
    if (score >= 70) {
      return { level: "watch", label: "观察", desc: "可补充评估" };
    }
    return { level: "low", label: "低优先", desc: "等待复核" };
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

  function getPlatformClass(platform) {
    const p = String(platform || "");
    if (p.includes("番茄")) return "fanqie";
    if (p.includes("晋江")) return "jinjiang";
    if (p.includes("起点")) return "qidian";
    return "other";
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

    ["#tpPlatform", "#tpCategory", "#tpWordCount", "#tpScoreLevel", "#tpDeconstructStatus"].forEach((sel) => {
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

    // 快捷筛选
    $$(".tp-quick-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const filter = btn.dataset.filter;
        if (currentQuickFilter === filter) {
          currentQuickFilter = null;
          btn.classList.remove("active");
        } else {
          $$(".tp-quick-btn").forEach((b) => b.classList.remove("active"));
          currentQuickFilter = filter;
          btn.classList.add("active");
        }
        currentPage = 1;
        renderGrid();
      });
    });
  }

  function bindBtn(sel, fn) {
    const el = $(sel);
    if (el) el.addEventListener("click", fn);
  }

  /* ===== 同步和归档 ===== */
  function bindSyncAndArchive() {
    // 同步选题
    const syncBtn = $("#tpSyncBtn");
    if (syncBtn) {
      syncBtn.addEventListener("click", async () => {
        syncBtn.disabled = true;
        syncBtn.innerHTML = '<i data-lucide="loader"></i> 同步中...';
        try {
          const res = await fetch("/api/topic-pool/sync", { method: "POST" });
          const json = await res.json();
          if (json.ok) {
            showToast("success", "✓ 同步成功，共 " + json.count + " 条");
            loadTopics();
            loadKPI();
          } else {
            showToast("error", "同步失败: " + json.error);
          }
        } catch (e) {
          showToast("error", "同步失败: " + e.message);
        } finally {
          syncBtn.disabled = false;
          syncBtn.innerHTML = '<i data-lucide="refresh-cw"></i> 同步';
          refreshIcons();
        }
      });
    }

    // 归档到飞书
    const archiveBtn = $("#tpArchiveBtn");
    if (archiveBtn) {
      archiveBtn.addEventListener("click", async () => {
        if (!confirm("确定要将待归档记录同步到飞书吗？")) return;
        archiveBtn.disabled = true;
        archiveBtn.innerHTML = '<i data-lucide="loader"></i> 归档中...';
        try {
          const res = await fetch("/api/topic-pool/archive", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
          });
          const json = await res.json();
          if (json.ok) {
            showToast("success", "✓ 归档成功，共 " + json.archived + " 条");
            loadKPI();
          } else {
            showToast("error", "归档失败: " + json.error);
          }
        } catch (e) {
          showToast("error", "归档失败: " + e.message);
        } finally {
          archiveBtn.disabled = false;
          archiveBtn.innerHTML = '<i data-lucide="archive"></i> 归档 <span id="archiveCount">0</span>';
          refreshIcons();
        }
      });
    }
  }

  function updatePoolStats() {
    const total = allItems.length;
    const pending = allItems.filter((i) => isSubmittable(i)).length;
    const high = allItems.filter((i) => (i.quality_score || 0) >= 80).length;
    const working = allItems.filter((i) => i.is_in_queue).length;
    const done = allItems.filter((i) => i.is_deconstructed).length;

    setText("#kpiTotalTopics", total);
    setText("#kpiPending", pending);
    setText("#kpiHighPot", high);
    setText("#heroTotalTopics", total);
    setText("#heroPendingTopics", pending);
    setText("#heroHighPotential", high);
    setText("#heroPendingProduction", working || pending);
    setText("#tpDonutTotal", total);
    setText("#tpLegendPending", pending);
    setText("#tpLegendDone", done || high);
    setText("#tpLegendWorking", working);

    const donut = $("#tpDonut");
    if (donut) {
      const p1 = total ? Math.round((pending / total) * 100) : 0;
      const p2 = total ? Math.round(((done || high) / total) * 100) : 0;
      const p3 = total ? Math.round((working / total) * 100) : 0;
      donut.style.setProperty("--p1", p1);
      donut.style.setProperty("--p2", p2);
      donut.style.setProperty("--p3", p3);
    }
  }

  /* ===== 右侧面板 ===== */
  function updateSidebar() {
    const selected = allItems.filter((i) => selectedIds.has(i.record_id));
    const count = selected.length;

    setText("#tpSelectedCount", count + "篇");
    setText("#tpBatchCount", count);
    updatePoolStats();

    // 分类分布
    const catMap = {};
    (count ? selected : allItems).forEach((i) => { const c = i.category || "未知"; catMap[c] = (catMap[c] || 0) + 1; });
    const catEl = $("#tpCategoryDist");
    if (catEl) {
      if (Object.keys(catMap).length === 0) {
        catEl.innerHTML = '<span class="text-muted">—</span>';
      } else {
        const maxCat = Math.max(...Object.values(catMap));
        catEl.innerHTML = Object.entries(catMap).sort((a, b) => b[1] - a[1]).slice(0, 5)
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
    (count ? selected : allItems).forEach((i) => { const p = i.platform || "未知"; platMap[p] = (platMap[p] || 0) + 1; });
    const platEl = $("#tpPlatformDist");
    if (platEl) {
      if (Object.keys(platMap).length === 0) {
        platEl.innerHTML = '<span class="text-muted">—</span>';
      } else {
        const maxPlat = Math.max(...Object.values(platMap));
        platEl.innerHTML = Object.entries(platMap).sort((a, b) => b[1] - a[1])
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
    setText("#tpEstCost", count > 0 ? "≈ " + (count * 0.04).toFixed(2) + "元" : "—");

    // 推荐理由
    const reasonsEl = $("#tpRecommendReasons");
    if (reasonsEl) {
      if (count === 0) {
        reasonsEl.innerHTML = '<span class="text-muted">请先选择作品</span>';
      } else {
        const avgScore = avgMetric("quality_score");
        const avgFav = avgMetric("favorites");
        const catPercent = Math.round((Object.values(catMap).reduce((a, b) => a + b, 0) / count) * 100);
        const platPercent = Math.round((Object.values(platMap).reduce((a, b) => a + b, 0) / count) * 100);
        
        let reasonsHtml = "";
        if (avgScore) reasonsHtml += '<div class="tp-recommend-item"><span class="tp-recommend-icon">✓</span><span>平均评分 ' + avgScore + '</span></div>';
        if (avgFav) reasonsHtml += '<div class="tp-recommend-item"><span class="tp-recommend-icon">✓</span><span>收藏均值 ' + fmtNum(avgFav) + '</span></div>';
        if (catMap[Object.keys(catMap)[0]]) reasonsHtml += '<div class="tp-recommend-item"><span class="tp-recommend-icon">✓</span><span>' + Object.keys(catMap)[0] + '占比 ' + Math.round((catMap[Object.keys(catMap)[0]] / count) * 100) + '%</span></div>';
        if (platMap[Object.keys(platMap)[0]]) reasonsHtml += '<div class="tp-recommend-item"><span class="tp-recommend-icon">✓</span><span>' + Object.keys(platMap)[0] + '占比 ' + Math.round((platMap[Object.keys(platMap)[0]] / count) * 100) + '%</span></div>';
        
        reasonsEl.innerHTML = reasonsHtml || '<span class="text-muted">选择作品后显示推荐理由</span>';
      }
    }

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

    // 读取全局策略默认值
    const strategySelect = $("#tpModalStrategy");
    const providerSelect = $("#tpModalProvider");
    const strategyHint = $("#tpModalStrategyHint");
    if (strategySelect) {
      fetch("/api/config/image_strategy")
        .then(r => r.json())
        .then(json => {
          if (json.ok && json.data && json.data.strategy) {
            strategySelect.value = json.data.strategy;
          }
          if (providerSelect && json.ok && json.data && json.data.provider) {
            providerSelect.value = json.data.provider;
          }
        })
        .catch(() => {})
        .finally(() => {
          updateStrategyHint(strategySelect, providerSelect, strategyHint);
        });
      strategySelect.addEventListener("change", () => {
        updateStrategyHint(strategySelect, providerSelect, strategyHint);
      });
      if (providerSelect) {
        providerSelect.addEventListener("change", () => {
          updateStrategyHint(strategySelect, providerSelect, strategyHint);
        });
      }
    }

    overlay.classList.add("visible");
  }

  function updateStrategyHint(selectEl, providerEl, hintEl) {
    if (!selectEl || !hintEl) return;
    const v = selectEl.value;
    const provider = providerEl ? providerEl.value : "";
    const providerField = $("#tpModalProviderField");
    if (providerEl) providerEl.style.display = v === "ai" ? "" : "none";
    if (providerField) providerField.style.display = v === "ai" ? "" : "none";
    const providerHints = {
      "liblib": "LiblibAI 星流，适合新图文模型",
      "doubao_seedream_5_lite": "豆包 Seedream 5.0，火山方舟 OpenAI 兼容接口",
      "doubao_seedream_4_5": "豆包 Seedream 4.5，火山方舟 OpenAI 兼容接口",
      "doubao_seedream_4_0": "豆包 Seedream 4.0，火山方舟 OpenAI 兼容接口",
      "jimeng": "即梦 / 火山，使用既有链路",
      "siliconflow": "SiliconFlow，需已配置密钥",
      "mock": "Mock，本地无成本联调",
    };
    const hints = {
      "ai": providerHints[provider] || "AI 生图，适合需要真实图片的场景",
      "html_card": "HTML 卡片截图，文字 100% 可控，适合小红书图文笔记",
      "auto": "根据笔记内容自动匹配最佳风格",
    };
    hintEl.textContent = hints[v] || "";
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
    const selectedAll = allItems.filter((i) => selectedIds.has(i.record_id));
    const selected = selectedAll.filter((i) => isSubmittable(i));
    if (selected.length === 0) {
      selectedIds.clear();
      renderGrid();
      showToast("warning", "所选作品已在生产中心，没有可新增的拆解任务");
      return;
    }

    const confirmBtn = $("#tpModalConfirm");
    const cancelBtn = $("#tpModalCancel");
    if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.textContent = "提交中..."; }
    if (cancelBtn) cancelBtn.disabled = true;

    // 显示 loading 浮层
    var overlay = document.createElement("div");
    overlay.className = "tp-submit-loading";
    overlay.innerHTML = '<div class="tp-spinner"></div><div style="margin-top:12px;font-size:14px">正在提交生产队列...</div>';
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.3);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;color:#fff";
    document.body.appendChild(overlay);

    try {
      const works = selected.map((i) => ({
        record_id: i.record_id,
        作品名称: i.work_name,
        作者: i.author,
        平台: i.platform,
        分类: i.category,
        简介: i.synopsis || "",
        取向: i.orientation || "",
      }));

      const strategySelect = $("#tpModalStrategy");
      const imageStrategy = (strategySelect ? strategySelect.value : "") || "";
      const providerSelect = $("#tpModalProvider");
      const imageProvider = (providerSelect ? providerSelect.value : "") || "";

      const res = await fetch("/api/deconstruct/batch-enqueue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          works: works,
          image_strategy: imageStrategy || undefined,
          image_provider: imageStrategy === "ai" ? (imageProvider || undefined) : undefined,
        }),
      });

      const json = await res.json();
      if (!json.ok) throw new Error(json.error);

      if (!json.data || !json.data.enqueued) {
        if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
        if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = "确认提交"; }
        if (cancelBtn) cancelBtn.disabled = false;
        showToast("warning", "没有新增任务，所选作品可能已在生产中心");
        return;
      }

      closeModal();
      const skippedText = json.data.skipped ? "，跳过 " + json.data.skipped + " 篇已存在作品" : "";
      showToast("success", "✓ 成功提交 " + json.data.enqueued + " 篇作品" + skippedText);
      selectedIds.clear();
      
      // 保持 loading 过渡直到跳转，避免提交成功后页面突然静止。
      overlay.querySelector("div:last-child").textContent = "提交成功，正在进入生产中心...";
      setTimeout(() => {
        window.location.href = "/production-center";
      }, 1500);
    } catch (e) {
      showToast("error", "✕ 提交失败：" + e.message);
      if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
      if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = "确认提交"; }
      if (cancelBtn) cancelBtn.disabled = false;
    } finally {
      // 成功路径会跳转，不在这里移除遮罩；失败路径已恢复按钮。
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
  function refreshIcons() {
    if (typeof lucide !== "undefined") {
      lucide.createIcons();
    } else if (typeof window.createAppFallbackIcons === "function") {
      window.createAppFallbackIcons();
    }
  }

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
