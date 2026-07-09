(function () {
  "use strict";

  const PAGE_SIZE = 20;
  let mode = "rank";
  let allItems = [];
  let currentPage = 1;
  let pollTimer = null;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  document.addEventListener("DOMContentLoaded", () => {
    const batch = $("#psBatch");
    if (batch && !batch.value) batch.value = new Date().toISOString().slice(0, 10);
    bindMode();
    bindFetch();
    bindFilters();
    bindMaintain();
    $("#psRefreshBtn")?.addEventListener("click", refreshAll);
    $("#psToggleFilters")?.addEventListener("click", toggleFilters);
    $("#psPrevPage")?.addEventListener("click", () => movePage(-1));
    $("#psNextPage")?.addEventListener("click", () => movePage(1));
    refreshAll();
    pollTimer = setInterval(loadOverview, 15000);
  });

  window.addEventListener("beforeunload", () => {
    if (pollTimer) clearInterval(pollTimer);
  });

  function bindMode() {
    $$(".ps-segment button").forEach((btn) => {
      btn.addEventListener("click", () => {
        mode = btn.dataset.mode || "rank";
        $$(".ps-segment button").forEach((b) => b.classList.toggle("active", b === btn));
        const q = $("#psQuery");
        if (!q) return;
        q.disabled = mode === "rank";
        q.placeholder = mode === "rank" ? "排行榜模式无需关键词" : "请输入关键词";
        if (mode === "rank") q.value = "";
      });
    });
  }

  function bindFetch() {
    $("#psFetchForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const btn = event.submitter || $(".ps-primary-btn");
      const sources = $$(".ps-source-box input:checked").map((i) => i.value);
      const payload = {
        mode,
        sources,
        limit: Number($("#psLimit")?.value || 60),
        batch: $("#psBatch")?.value || "",
        query: $("#psQuery")?.value || "",
      };
      if (!sources.length) {
        showError("请至少选择一个来源");
        return;
      }
      if (mode === "search" && !payload.query.trim()) {
        showError("关键词抓取需要填写关键词");
        return;
      }
      await postJob("/api/prescreen/fetch", payload, btn, "已提交抓取任务");
      loadOverview();
    });
  }

  function bindFilters() {
    [
      "#psFilterPlatform",
      "#psFilterSource",
      "#psFilterBatch",
      "#psFilterIn",
      "#psFilterFinish",
      "#psFilterDimension",
      "#psFilterRankSource",
      "#psFilterScore",
    ].forEach((sel) => {
      $(sel)?.addEventListener("change", () => {
        currentPage = 1;
        renderTable();
      });
    });
    $("#psResetFilters")?.addEventListener("click", () => {
      $$("#psFilters select").forEach((s) => {
        s.value = "";
      });
      currentPage = 1;
      renderTable();
    });
  }

  function bindMaintain() {
    $$("[data-maintain-limit]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const limit = Number(btn.dataset.maintainLimit || 128);
        await postJob("/api/prescreen/maintain", { limit }, btn, "已提交维护任务");
      });
    });
  }

  async function refreshAll() {
    await Promise.all([loadOverview(), loadList()]);
  }

  async function loadOverview() {
    try {
      const res = await fetch("/api/prescreen/overview");
      const json = await res.json();
      const err = $("#psOverviewError");
      if (!json.ok && json.error) {
        if (err) {
          err.hidden = false;
          err.textContent = "读取初筛表失败：" + json.error;
        }
      } else if (err) {
        err.hidden = true;
      }

      const counts = json.status?.counts || {};
      setText("#psFetched", counts.fetched || 0);
      setText("#psCreated", counts.created || 0);
      setText("#psUpdated", counts.updated || 0);
      setText("#psSkipped", counts.skipped || 0);
      setText("#psErrors", counts.errors || 0);
      setText("#psCommand", json.status?.command || "—");
      const latest = json.status?.latest_result || {};
      setText("#psLatestTime", latest.ts ? "完成于 " + formatTime(latest.ts) : "暂无完成时间");

      const stats = json.stats || {};
      setText("#psTotal", stats.total ?? "—");
      setText("#psYes", stats.yes ?? "—");
      setText("#psNo", stats.no ?? "—");
      setText("#psUnscored", stats.unscored ?? "—");
      setText("#psStatsTime", "统计于 " + new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }));
      fillSelect("#psMaintainBatch", stats.batch_options || [], "选择批次");
    } catch (e) {
      showError(e.message || "状态读取失败");
    }
  }

  async function loadList() {
    const body = $("#psTableBody");
    if (body) body.innerHTML = '<tr><td colspan="15" class="ps-empty">加载中...</td></tr>';
    try {
      const res = await fetch("/api/prescreen/list?limit=1200");
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "读取失败");
      allItems = json.data?.items || [];
      populateFilters();
      currentPage = 1;
      renderTable();
    } catch (e) {
      if (body) body.innerHTML = '<tr><td colspan="15" class="ps-empty">读取失败：' + esc(e.message) + "</td></tr>";
    }
  }

  function populateFilters() {
    fillSelect("#psFilterPlatform", unique("platform"), "全部");
    fillSelect("#psFilterSource", unique("rank_source"), "全部");
    fillSelect("#psFilterBatch", unique("batch"), "全部");
    fillSelect("#psFilterFinish", unique("finished"), "全部");
    fillSelect("#psFilterDimension", unique("dimension"), "全部");
    fillSelect("#psFilterRankSource", unique("rank_source"), "全部");
  }

  function unique(key) {
    return Array.from(new Set(allItems.map((i) => (i[key] || "").trim()).filter(Boolean))).slice(0, 80);
  }

  function fillSelect(sel, values, firstLabel) {
    const el = $(sel);
    if (!el) return;
    const old = el.value;
    el.innerHTML = '<option value="">' + esc(firstLabel || "全部") + "</option>" + values.map((v) => '<option value="' + esc(v) + '">' + esc(v) + "</option>").join("");
    if (values.includes(old)) el.value = old;
  }

  function getFiltered() {
    const platform = $("#psFilterPlatform")?.value || "";
    const source = $("#psFilterSource")?.value || "";
    const batch = $("#psFilterBatch")?.value || "";
    const inLib = $("#psFilterIn")?.value || "";
    const finish = $("#psFilterFinish")?.value || "";
    const dim = $("#psFilterDimension")?.value || "";
    const rankSource = $("#psFilterRankSource")?.value || "";
    const score = $("#psFilterScore")?.value || "";
    let items = allItems.slice();
    if (platform) items = items.filter((i) => i.platform === platform);
    if (source) items = items.filter((i) => i.rank_source === source);
    if (batch) items = items.filter((i) => i.batch === batch);
    if (inLib) items = items.filter((i) => normalizeYesNo(i.in_library) === inLib);
    if (finish) items = items.filter((i) => i.finished === finish);
    if (dim) items = items.filter((i) => i.dimension === dim);
    if (rankSource) items = items.filter((i) => i.rank_source === rankSource);
    if (score === "90") items = items.filter((i) => Number(i.score || 0) >= 90);
    if (score === "80") items = items.filter((i) => Number(i.score || 0) >= 80 && Number(i.score || 0) < 90);
    if (score === "0") items = items.filter((i) => Number(i.score || 0) < 80);
    items.sort((a, b) => Number(b.score || 0) - Number(a.score || 0) || Number(b.updated_ts || 0) - Number(a.updated_ts || 0));
    return items;
  }

  function renderTable() {
    const body = $("#psTableBody");
    if (!body) return;
    const items = getFiltered();
    setText("#psTotalRows", "共 " + items.length + " 条");
    setText("#psCurrentCount", items.length);

    if (!items.length) {
      body.innerHTML = '<tr><td colspan="15" class="ps-empty">暂无匹配记录</td></tr>';
      updatePageInfo(0);
      return;
    }

    const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
    if (currentPage > totalPages) currentPage = totalPages;
    const pageItems = items.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
    body.innerHTML = pageItems.map(rowHtml).join("");
    updatePageInfo(totalPages);
    bindRowActions();
    if (window.lucide) window.lucide.createIcons();
  }

  function rowHtml(item) {
    const inText = normalizeYesNo(item.in_library);
    const link = item.link ? '<a class="ps-link" href="' + esc(item.link) + '" target="_blank" rel="noreferrer">' + esc(item.title || "未知作品") + "</a>" : esc(item.title || "未知作品");
    const promoteBtn =
      inText === "是"
        ? '<button type="button" title="已入库" disabled><i data-lucide="check"></i></button>'
        : '<button type="button" title="入库到选题库" data-action="promote" data-rid="' + esc(item.record_id || "") + '"><i data-lucide="archive"></i></button>';
    return (
      "<tr>" +
      "<td>" + link + "</td>" +
      "<td>" + esc(item.author || "-") + "</td>" +
      "<td>" + esc(item.platform || "-") + "</td>" +
      "<td>" + esc(item.type || "-") + "</td>" +
      '<td><span class="ps-badge ' + (inText === "是" ? "yes" : "no") + '">' + esc(inText) + "</span></td>" +
      "<td>" + fmtScore(item.score) + "</td>" +
      "<td>" + esc(item.dimension || "-") + "</td>" +
      "<td>" + esc(item.rank_source || "-") + "</td>" +
      "<td>" + (item.rank_pos || "-") + "</td>" +
      "<td>" + fmtNum(item.collect_num) + "</td>" +
      "<td>" + fmtNum(item.review_num) + "</td>" +
      "<td>" + fmtScore(item.platform_score) + "</td>" +
      "<td>" + esc(item.batch || "-") + "</td>" +
      "<td>" + esc(item.updated_at || "-") + "</td>" +
      '<td><div class="ps-row-actions">' +
      (item.link ? '<a href="' + esc(item.link) + '" target="_blank" rel="noreferrer" title="查看作品"><i data-lucide="eye"></i></a>' : "") +
      promoteBtn +
      '<button type="button" title="编辑备注"><i data-lucide="pencil"></i></button>' +
      "</div></td>" +
      "</tr>"
    );
  }

  function bindRowActions() {
    $$('[data-action="promote"]').forEach((btn) => {
      btn.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        const rid = btn.dataset.rid || "";
        if (!rid) return;
        const old = btn.innerHTML;
        try {
          btn.disabled = true;
          btn.textContent = "...";
          const res = await fetch("/api/prescreen/promote", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ record_id: rid }),
          });
          const json = await res.json();
          if (!json.ok) throw new Error(json.error || "入库失败");
          showError(json.action === "updated" ? "已更新到选题库" : "已入库到选题库", true);
          await refreshAll();
        } catch (e) {
          btn.disabled = false;
          btn.innerHTML = old;
          showError(e.message || "入库失败");
          if (window.lucide) window.lucide.createIcons();
        }
      });
    });
  }

  function movePage(delta) {
    const total = Math.max(1, Math.ceil(getFiltered().length / PAGE_SIZE));
    currentPage = Math.max(1, Math.min(total, currentPage + delta));
    renderTable();
  }

  function updatePageInfo(totalPages) {
    const total = totalPages || 1;
    setText("#psPageInfo", currentPage + " / " + total);
    const prev = $("#psPrevPage");
    const next = $("#psNextPage");
    if (prev) prev.disabled = currentPage <= 1;
    if (next) next.disabled = currentPage >= total;
  }

  async function postJob(url, payload, btn, okText) {
    const original = btn?.textContent || "";
    try {
      if (btn) {
        btn.disabled = true;
        btn.textContent = "提交中...";
      }
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "提交失败");
      showError(okText + "：" + (json.job_id || ""), true);
    } catch (e) {
      showError(e.message || "提交失败");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = original;
      }
    }
  }

  function toggleFilters() {
    const filters = $("#psFilters");
    const btn = $("#psToggleFilters");
    if (!filters || !btn) return;
    const hidden = filters.style.display === "none";
    filters.style.display = hidden ? "grid" : "none";
    btn.textContent = hidden ? "收起" : "展开";
  }

  function setText(sel, val) {
    const el = $(sel);
    if (el) el.textContent = val == null || val === "" ? "—" : String(val);
  }

  function showError(msg, ok) {
    const err = $("#psOverviewError");
    if (!err) return;
    err.hidden = false;
    err.textContent = msg;
    err.style.background = ok ? "#ecfdf5" : "#fef2f2";
    err.style.color = ok ? "#065f46" : "#991b1b";
    setTimeout(() => {
      err.hidden = true;
    }, ok ? 3500 : 6000);
  }

  function normalizeYesNo(v) {
    const s = String(v || "").trim().toLowerCase();
    return ["是", "yes", "true", "1", "已入库"].includes(s) ? "是" : "否";
  }

  function fmtNum(v) {
    const n = Number(v || 0);
    if (!n) return "-";
    if (n >= 100000000) return trim(n / 100000000) + "亿";
    if (n >= 10000) return trim(n / 10000) + "万";
    return String(Math.round(n));
  }

  function fmtScore(v) {
    const n = Number(v || 0);
    return n ? trim(n) : "-";
  }

  function trim(n) {
    return Number(n).toFixed(1).replace(/\.0$/, "");
  }

  function formatTime(ts) {
    const d = new Date(Number(ts) * 1000);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
