/**
 * 选题池页面交互模块
 * - 加载选题列表
 * - 搜索 / 筛选 / 排序
 * - 多选卡片
 * - 右侧面板统计
 * - KPI 轮询
 * - 弹窗确认提交
 */
(function () {
  "use strict";

  /* ===== 状态 ===== */
  let allItems = [];
  let selectedIds = new Set();
  let currentSort = "created_at";
  let pollInterval = null;

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
      const res = await fetch("/api/deconstruct/queue?per_page=200&status=pending");
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);
      allItems = json.data.items || [];
      renderGrid();
    } catch (e) {
      grid.innerHTML =
        '<div class="tp-empty"><div class="tp-empty-icon">&#x1F6AB;</div><div class="tp-empty-title">加载失败</div><div class="tp-empty-desc">' +
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
      const kpiValues = $$(".tp-kpi-value");
      if (kpiValues[0]) kpiValues[0].textContent = d.pending_topics;
      if (kpiValues[1]) kpiValues[1].textContent = d.today_added;
      if (kpiValues[2]) kpiValues[2].textContent = d.high_potential;
      if (kpiValues[3]) kpiValues[3].textContent = selectedIds.size;
    } catch (_) {}
  }

  /* ===== 筛选 / 排序 ===== */
  function getFiltered() {
    const q = ($("#tpSearch")?.value || "").trim().toLowerCase();
    const platform = $("#tpPlatform")?.value || "";
    const category = $("#tpCategory")?.value || "";

    let list = allItems.slice();

    if (q) {
      list = list.filter(
        (i) =>
          (i.work_name || "").toLowerCase().includes(q) ||
          (i.author || "").toLowerCase().includes(q)
      );
    }
    if (platform) {
      list = list.filter((i) => i.platform === platform);
    }
    if (category) {
      list = list.filter((i) => i.category === category);
    }

    if (currentSort === "score") {
      list.sort(
        (a, b) => (b.quality_score || 0) - (a.quality_score || 0)
      );
    } else {
      list.sort(
        (a, b) =>
          (b.created_at || "").localeCompare(a.created_at || "")
      );
    }

    return list;
  }

  function renderGrid() {
    const grid = $(".tp-grid");
    if (!grid) return;
    const list = getFiltered();

    if (list.length === 0) {
      grid.innerHTML =
        '<div class="tp-empty">' +
        '<div class="tp-empty-icon">&#x1F4D6;</div>' +
        '<div class="tp-empty-title">暂无待处理作品</div>' +
        '<div class="tp-empty-desc">请先同步飞书选题库或调整筛选条件</div>' +
        '<button class="tp-empty-btn" onclick="location.reload()">&#x1F504; 刷新</button>' +
        "</div>";
      updateSidebar();
      return;
    }

    let html = "";
    for (const item of list) {
      const rid = item.record_id || "";
      const sel = selectedIds.has(rid) ? " selected" : "";
      const score = item.quality_score;
      const scoreClass = score
        ? score >= 90
          ? "tp-score-s"
          : score >= 80
            ? "tp-score-a"
            : score >= 70
              ? "tp-score-b"
              : "tp-score-c"
        : "";
      const scoreLabel = score
        ? score >= 90
          ? " S级"
          : score >= 80
            ? " A级"
            : score >= 70
              ? " B级"
              : " C级"
        : "";

      html +=
        '<div class="tp-card' + sel + '" data-rid="' + esc(rid) + '">' +
        '<div class="tp-card-checkbox">' + (sel ? "&#x2713;" : "") + "</div>" +
        '<div class="tp-card-name">' + esc(item.work_name || "未知作品") + "</div>" +
        '<div class="tp-card-author">' + esc(item.author || "未知作者") + "</div>" +
        '<div class="tp-card-platform">' +
        esc(item.platform || "-") + " · " + esc(item.category || "-") +
        "</div>" +
        '<div class="tp-card-metrics">' +
        "<span>收藏 " + fmtNum(item.favorites) + "</span>" +
        "<span>点赞 " + fmtNum(item.likes) + "</span>" +
        "<span>评论 " + fmtNum(item.comments) + "</span>" +
        "</div>" +
        (score
          ? '<div class="tp-card-score ' + scoreClass + '">' +
            "综合评分 " + score + scoreLabel +
            "</div>"
          : "") +
        "</div>";
    }

    grid.innerHTML = html;

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
          card.querySelector(".tp-card-checkbox").innerHTML = "&#x2713;";
        }
        updateSidebar();
        updateKpiSelected();
      });
    });

    updateSidebar();
  }

  /* ===== 工具栏绑定 ===== */
  function bindToolbar() {
    const search = $("#tpSearch");
    if (search) {
      let timer;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(renderGrid, 300);
      });
    }

    const platform = $("#tpPlatform");
    if (platform) platform.addEventListener("change", renderGrid);

    const category = $("#tpCategory");
    if (category) category.addEventListener("change", renderGrid);

    $$(".tp-sort-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".tp-sort-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentSort = btn.dataset.sort || "created_at";
        renderGrid();
      });
    });

    const selectAll = $("#tpSelectAll");
    if (selectAll) {
      selectAll.addEventListener("click", () => {
        const filtered = getFiltered();
        const allSelected = filtered.every((i) =>
          selectedIds.has(i.record_id)
        );
        if (allSelected) {
          filtered.forEach((i) => selectedIds.delete(i.record_id));
        } else {
          filtered.forEach((i) => selectedIds.add(i.record_id));
        }
        renderGrid();
      });
    }
  }

  /* ===== 右侧面板 ===== */
  function updateSidebar() {
    const selected = allItems.filter((i) =>
      selectedIds.has(i.record_id)
    );
    const count = selected.length;

    const countEl = $("#tpSelectedCount");
    if (countEl) countEl.textContent = count + "篇";

    /* 分类分布 */
    const catMap = {};
    selected.forEach((i) => {
      const c = i.category || "未知";
      catMap[c] = (catMap[c] || 0) + 1;
    });
    const catEl = $("#tpCategoryDist");
    if (catEl) {
      catEl.innerHTML = Object.entries(catMap)
        .map(
          ([k, v]) =>
            '<span class="tp-distribution-tag">' + esc(k) + " " + v + "</span>"
        )
        .join("") || '<span class="text-muted">—</span>';
    }

    /* 平台分布 */
    const platMap = {};
    selected.forEach((i) => {
      const p = i.platform || "未知";
      platMap[p] = (platMap[p] || 0) + 1;
    });
    const platEl = $("#tpPlatformDist");
    if (platEl) {
      platEl.innerHTML = Object.entries(platMap)
        .map(
          ([k, v]) =>
            '<span class="tp-distribution-tag">' + esc(k) + " " + v + "</span>"
        )
        .join("") || '<span class="text-muted">—</span>';
    }

    /* 平均评分 */
    const scores = selected
      .map((i) => i.quality_score)
      .filter((s) => s != null);
    const avgScore =
      scores.length > 0
        ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
        : null;
    const scoreEl = $("#tpAvgScore");
    if (scoreEl) scoreEl.textContent = avgScore != null ? avgScore + "分" : "—";

    /* 预估 */
    const tokenEl = $("#tpEstToken");
    if (tokenEl)
      tokenEl.textContent = count > 0 ? "~" + count * 3000 + " tokens" : "—";
    const timeEl = $("#tpEstTime");
    if (timeEl)
      timeEl.textContent = count > 0 ? "~" + Math.ceil(count * 0.5) + "分钟" : "—";
    const outputEl = $("#tpEstOutput");
    if (outputEl)
      outputEl.textContent =
        count > 0
          ? "拆文报告" + count + "份 / 笔记初稿" + count + "份 / 评分报告" + count + "份"
          : "—";

    /* 提交按钮 */
    const submitBtn = $("#tpSubmitBtn");
    if (submitBtn) submitBtn.disabled = count === 0;
  }

  function updateKpiSelected() {
    const kpiValues = $$(".tp-kpi-value");
    if (kpiValues[3]) kpiValues[3].textContent = selectedIds.size;
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

    const selected = allItems.filter((i) =>
      selectedIds.has(i.record_id)
    );

    const listEl = $("#tpModalList");
    if (listEl) {
      listEl.innerHTML = selected
        .map((i) => "<li>" + esc(i.work_name || "未知") + "</li>")
        .join("");
    }

    const infoEl = $("#tpModalInfo");
    if (infoEl) {
      infoEl.innerHTML =
        "执行流程：<span>&#x2713; 拆文分析</span> <span>&#x2713; 笔记生成</span> <span>&#x2713; AI评分</span><br>" +
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
    const selected = allItems.filter((i) =>
      selectedIds.has(i.record_id)
    );

    if (selected.length === 0) return;

    const confirmBtn = $("#tpModalConfirm");
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = "提交中...";
    }

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
      showToast("success", "&#x2713; 成功提交 " + json.data.enqueued + " 篇作品");
      selectedIds.clear();
      loadTopics();
      loadKPI();
    } catch (e) {
      showToast("error", "&#x2717; 提交失败：" + e.message);
    } finally {
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = "确认提交";
      }
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
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(n) {
    if (n == null) return "—";
    if (n >= 10000) return (n / 10000).toFixed(1) + "w";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }
})();
