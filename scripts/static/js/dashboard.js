(function () {
  "use strict";

  const POLL_MS = 30000;
  let timer = null;

  const $ = (selector) => document.querySelector(selector);

  document.addEventListener("DOMContentLoaded", () => {
    if (!$("[data-dashboard-page]")) return;
    setDateRange();
    loadDashboard();
    timer = setInterval(loadDashboard, POLL_MS);
    window.addEventListener("pagehide", stop);
    window.addEventListener("beforeunload", stop);
  });

  async function loadDashboard() {
    try {
      const res = await fetch("/api/dashboard/overview");
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "Dashboard 数据加载失败");
      render(json.data || {});
      showError("");
    } catch (error) {
      showError("数据总览加载失败：" + error.message);
    }
  }

  function render(data) {
    const summary = data.summary || {};
    const status = data.content_status || {};
    setText("#heroSubtitle", "今天是内容创作的第 " + fmt(summary.days_active) + " 天，继续保持创作热情");
    setText("#heroGoal", "今日目标：拆解 " + fmt(summary.today_goal?.deconstruct) + " 本书，生成 " + fmt(summary.today_goal?.notes) + " 篇优质小红书图文笔记");
    setText("#kpiNotes", fmt(summary.notes_total));
    setText("#kpiReads", summary.reads_total == null ? "—" : fmt(summary.reads_total));
    setText("#kpiTasks", fmt(summary.deconstruct_tasks));
    setText("#kpiTasksSub", "已完成 " + fmt(status.completed) + " / 待处理 " + fmt(status.pending));
    setText("#kpiPendingPublish", fmt(summary.pending_publish));
    renderTrend(data.trend || []);
    renderTopics(data.top_topics || []);
    renderAccount(data.account || {}, status);
    renderStatus(status);
    if (typeof lucide !== "undefined") lucide.createIcons();
  }

  function renderTrend(rows) {
    const el = $("#dashboardTrend");
    if (!el) return;
    if (!rows.length || !rows.some((row) => (row.completed || 0) + (row.created || 0) > 0)) {
      el.innerHTML = '<div class="dashboard-empty">近 7 日暂无创建或完成记录</div>';
      return;
    }
    const width = 720;
    const height = 260;
    const pad = { left: 34, right: 18, top: 18, bottom: 32 };
    const max = Math.max(1, ...rows.map((row) => Math.max(row.completed || 0, row.created || 0)));
    const points = (key) => rows.map((row, index) => {
      const x = pad.left + (index * (width - pad.left - pad.right)) / Math.max(1, rows.length - 1);
      const y = height - pad.bottom - ((row[key] || 0) / max) * (height - pad.top - pad.bottom);
      return [x, y];
    });
    const completed = points("completed");
    const created = points("created");
    el.innerHTML =
      '<svg viewBox="0 0 ' + width + " " + height + '" role="img" aria-label="近7日任务趋势">' +
      '<defs><linearGradient id="dashTrendFill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#6C4EFF" stop-opacity="0.24"/><stop offset="1" stop-color="#6C4EFF" stop-opacity="0"/></linearGradient></defs>' +
      grid(width, height, pad, max) +
      area(completed, height - pad.bottom) +
      line(created, "#A7B4D6", 2) +
      line(completed, "#6C4EFF", 3) +
      dots(completed, "#6C4EFF") +
      dots(created, "#A7B4D6") +
      labels(rows, width, height, pad) +
      "</svg>";
  }

  function grid(width, height, pad, max) {
    let html = "";
    for (let i = 0; i <= 4; i += 1) {
      const y = pad.top + (i * (height - pad.top - pad.bottom)) / 4;
      const value = Math.round(max - (i * max) / 4);
      html += '<path d="M' + pad.left + " " + y + "H" + (width - pad.right) + '" stroke="#EEF2F7" />';
      html += '<text x="2" y="' + (y + 4) + '" fill="#94A3B8" font-size="11">' + value + "</text>";
    }
    return html;
  }

  function line(points, color, strokeWidth) {
    return '<polyline fill="none" stroke="' + color + '" stroke-width="' + strokeWidth + '" stroke-linecap="round" stroke-linejoin="round" points="' + points.map((p) => p.join(",")).join(" ") + '" />';
  }

  function area(points, baseline) {
    const first = points[0];
    const last = points[points.length - 1];
    return '<path d="M' + first[0] + " " + baseline + "L" + points.map((p) => p.join(" ")).join("L") + "L" + last[0] + " " + baseline + 'Z" fill="url(#dashTrendFill)" />';
  }

  function dots(points, color) {
    return points.map((p) => '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="3.5" fill="#FFFFFF" stroke="' + color + '" stroke-width="2" />').join("");
  }

  function labels(rows, width, height, pad) {
    return rows.map((row, index) => {
      const x = pad.left + (index * (width - pad.left - pad.right)) / Math.max(1, rows.length - 1);
      return '<text x="' + x + '" y="' + (height - 8) + '" text-anchor="middle" fill="#64748B" font-size="11">' + esc(row.date.slice(5)) + "</text>";
    }).join("");
  }

  function renderTopics(items) {
    const el = $("#dashboardTopTopics");
    if (!el) return;
    if (!items.length) {
      el.innerHTML = '<div class="dashboard-empty">暂无可展示选题，先从选题池同步或提交任务</div>';
      return;
    }
    el.innerHTML = items.map((item, index) =>
      '<div class="dashboard-topic-row">' +
      '<span class="dashboard-rank">' + (index + 1) + "</span>" +
      '<div class="dashboard-topic-main"><strong title="' + esc(item.title) + '">' + esc(item.title) + "</strong>" +
      "<span>" + esc(item.author || "未知作者") + " · " + esc(item.platform || "未标注平台") + "</span></div>" +
      '<span class="dashboard-topic-score">' + scoreText(item) + "</span>" +
      "</div>"
    ).join("");
  }

  function renderAccount(account, status) {
    const el = $("#dashboardAccount");
    if (!el) return;
    const total = Number(status.completed || 0) + Number(status.pending || 0) + Number(status.processing || 0) + Number(status.review || 0) + Number(status.failed || 0);
    const rate = total > 0 ? Math.round((Number(status.completed || 0) / total) * 100) : 0;
    const metrics = account.metrics || [];
    el.innerHTML =
      '<div class="dashboard-donut" style="--p:' + (rate * 3.6) + 'deg"><div class="dashboard-donut-inner"><div><strong>' + rate + '%</strong><div class="dashboard-account-note">完成率</div></div></div></div>' +
      '<div class="dashboard-account-note">粉丝、阅读增长暂未接入真实账号数据</div>' +
      '<div class="dashboard-account-grid">' + metrics.map((m) =>
        '<div class="dashboard-account-metric"><span>' + esc(m.label) + '</span><strong>' + fmt(m.value) + "</strong></div>"
      ).join("") + "</div>";
  }

  function renderStatus(status) {
    const el = $("#dashboardStatus");
    if (!el) return;
    const rows = [
      ["待拆解", status.pending || 0],
      ["生产中", status.processing || 0],
      ["待审核", status.review || 0],
      ["已完成", status.completed || 0],
      ["失败", status.failed || 0],
    ];
    const max = Math.max(1, ...rows.map((row) => row[1]));
    el.innerHTML = rows.map((row) =>
      '<div class="dashboard-status-row"><span>' + row[0] + '</span><div class="dashboard-status-bar"><span style="--w:' + Math.round((row[1] / max) * 100) + '%"></span></div><strong>' + row[1] + "</strong></div>"
    ).join("");
  }

  function setDateRange() {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 6);
    setText("#dashboardDateRange", dateLabel(start) + " ~ " + dateLabel(end));
  }

  function scoreText(item) {
    if (item.quality_score != null) return Math.round(item.quality_score) + "分";
    const hot = Number(item.favorites || 0) + Number(item.likes || 0);
    return hot > 0 ? hot + "热度" : "近期";
  }

  function setText(selector, value) {
    const el = $(selector);
    if (el) el.textContent = value;
  }

  function showError(message) {
    const el = $("#dashboardError");
    if (!el) return;
    el.hidden = !message;
    el.textContent = message;
  }

  function fmt(value) {
    if (value == null || value === "") return "—";
    if (typeof value === "number" && Number.isFinite(value)) return value.toLocaleString("zh-CN");
    return String(value);
  }

  function dateLabel(date) {
    return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }
})();
