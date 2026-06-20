/**
 * 任务详情页交互模块
 * - 加载任务详情
 * - Tab 切换
 * - 笔记编辑
 * - 拆文结果展示
 * - AI 评分展示
 * - 操作按钮
 */
(function () {
  "use strict";

  /* ===== 状态 ===== */
  let taskData = null;
  let currentTab = "note";
  let autoRefreshTimer = null;
  let isDraftDirty = false;
  let editorHasFocus = false;
  let currentTaskId = null;
  const AUTO_REFRESH_MS = 5000;

  /* ===== DOM 缓存 ===== */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  /* ===== 初始化 ===== */
  document.addEventListener("DOMContentLoaded", () => {
    const container = $(".td-container");
    if (!container) return;
    const taskId = container.dataset.taskId;
    currentTaskId = taskId;
    loadTaskDetail(taskId);
    loadImageStrategy();
    bindTabs();
    bindActions();
    bindCollapses();
    bindEditor();
    startAutoRefresh(taskId);
    window.addEventListener("pagehide", stopAutoRefresh);
    window.addEventListener("beforeunload", stopAutoRefresh);
    renderHistory();
  });

  /* ===== 数据加载 ===== */
  async function loadTaskDetail(taskId, options) {
    options = options || {};
    try {
      const res = await fetch("/api/task/" + taskId);
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);
      taskData = json.data;
      const preserveDraft = options.preserveDraft || shouldPreserveDraft();
      renderTaskInfo();
      renderProgress();
      if (!preserveDraft) {
        renderNote();
      } else {
        updateTitleCount();
        updateWordCount();
        updateSideStats();
      }
      renderDeconstruct();
      renderScore();
      renderImages();
      renderHistory();
      updateRefreshStatus(options.auto ? "自动刷新中" : "已刷新");
    } catch (e) {
      updateRefreshStatus("刷新失败");
      showToast("error", "加载失败: " + e.message);
    }
  }

  function startAutoRefresh(taskId) {
    stopAutoRefresh();
    updateRefreshStatus("自动刷新中");
    autoRefreshTimer = window.setInterval(function() {
      if (document.hidden) return;
      loadTaskDetail(taskId, { auto: true, preserveDraft: shouldPreserveDraft() });
    }, AUTO_REFRESH_MS);
  }

  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      window.clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }

  function shouldPreserveDraft() {
    return editorHasFocus || isDraftDirty;
  }

  function updateRefreshStatus(text) {
    setText("#autoRefreshStatus", text || "自动刷新中");
    setText("#footerRefreshStatus", text === "刷新失败" ? "异常" : "运行中");
    const last = $("#lastRefresh");
    if (last) last.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  }

  /* ===== 渲染修改记录 ===== */
  function renderHistory() {
    const timeline = $("#historyTimeline");
    if (!timeline) return;
    
    var logText = taskData && taskData.modification_log ? String(taskData.modification_log) : "";
    var history = logText.split("\n").filter(Boolean);
    
    if (history.length === 0) {
      timeline.innerHTML = '<div class="td-history-empty">暂无修改记录，完成修改后自动生成</div>';
      return;
    }
    
    timeline.innerHTML = history.slice().reverse().map(function(item) {
      return '<div class="td-history-item">' +
        '<div class="td-history-time">' + esc(item.split("|")[0] || "") + '</div>' +
        '<div class="td-history-content">' +
        '<div class="td-history-type">' + esc(item) + '</div>' +
      '</div></div>';
    }).join("");
  }

  /* ===== 渲染任务信息 ===== */
  function renderTaskInfo() {
    if (!taskData) return;
    setText("#taskTitle", taskData.work_name || "未知作品");
    setText("#taskAuthor", taskData.author || "作者未知");
    setText("#taskPlatform", taskData.platform || "—");
    setText("#taskCategory", taskData.category || "—");
    setText("#taskWordCount", fmtWordCount(taskData.word_count));
    setText("#taskModel", "Qwen-Plus");
    setText("#taskCreated", taskData.created_at || "—");
    setText("#taskId", taskData.record_id || "—");
    var progress = taskData.progress_percent != null ? Number(taskData.progress_percent) : 0;
    if (!Number.isFinite(progress)) progress = 0;
    progress = Math.max(0, Math.min(100, Math.round(progress)));
    setText("#summaryProgress", progress);
    setText("#summaryRemaining", estimateRemaining(progress, taskData));
    var progressBar = $("#summaryProgressBar");
    if (progressBar) progressBar.style.width = progress + "%";
    setText("#summaryStage", taskData.stage_label || "—");

    // 生产摘要卡
    var status = normalizeDisplayStatus(taskData.display_status || taskData.status || "pending");
    var statusLabel = getStatusLabel(status, taskData.stage_label);
    var statusEl = $("#summaryStatus");
    if (statusEl) {
      statusEl.textContent = statusLabel;
      statusEl.className = "td-summary-status status-" + status;
    }
    setText("#summaryRetries", taskData.retry_count || 0);

    if (taskData.processing_start && taskData.completed_at) {
      var start = new Date(taskData.processing_start);
      var end = new Date(taskData.completed_at);
      var duration = Math.round((end - start) / 1000);
      setText("#taskDuration", formatDuration(duration));
      setText("#summaryDuration", formatDuration(duration));
      var noteLen = (taskData.note_content && taskData.note_content.content) ? taskData.note_content.content.length : 0;
      var speedPerMin = duration > 0 ? Math.round(noteLen / (duration / 60)) : 0;
      setText("#summarySpeed", speedPerMin > 0 ? speedPerMin + "字/分" : "—");
    } else if (taskData.processing_start) {
      var start2 = new Date(taskData.processing_start);
      var elapsed = Math.round((new Date() - start2) / 1000);
      setText("#taskDuration", formatDuration(elapsed));
      setText("#summaryDuration", formatDuration(elapsed));
      setText("#summarySpeed", "—");
    }
  }

  function getStatusLabel(status, fallback) {
    if (status === "done" || status === "completed") return "已完成";
    if (status === "failed") return "失败";
    if (status === "cancelled" || status === "terminated") return "已终止";
    if (status === "human_review") return "待审核";
    if (status === "processing") return "生产中";
    if (status === "waiting" || status === "pending") return "待处理";
    return fallback || "生产中";
  }

  function normalizeDisplayStatus(status) {
    if (status === "completed") return "done";
    if (status === "review") return "human_review";
    if (status === "terminated") return "cancelled";
    return status || "pending";
  }

  function formatDuration(seconds) {
    if (seconds < 60) return seconds + "秒";
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return minutes + "分" + secs + "秒";
  }

  function estimateRemaining(progress, task) {
    if (progress >= 100 || (task && normalizeDisplayStatus(task.display_status || task.status) === "done")) return "0 分钟";
    if (!task || !task.processing_start || progress <= 0) return "—";
    var start = new Date(task.processing_start);
    var elapsed = Math.max(0, Math.round((new Date() - start) / 1000));
    if (!Number.isFinite(elapsed) || elapsed <= 0) return "—";
    var total = elapsed / (progress / 100);
    var remaining = Math.max(0, Math.round(total - elapsed));
    if (!Number.isFinite(remaining)) return "—";
    if (remaining < 60) return "1 分钟内";
    return Math.ceil(remaining / 60) + " 分钟";
  }

  /* ===== 渲染进度轴 ===== */
  function renderProgress() {
    if (!taskData) return;
    const rawStatus = normalizeDisplayStatus(taskData.display_status || taskData.status);
    const status = resolveStepStatus(rawStatus, taskData);
    const steps = ["waiting", "deconstructing", "generating_note", "ai_scoring", "human_review", "generating_image", "done"];
    const failed = rawStatus === "failed" || rawStatus === "cancelled";
    const currentIdx = failed ? Math.max(0, getTaskProgressIndex(taskData)) : Math.max(0, steps.indexOf(status));
    const stepTimes = taskData.step_times || {};

    $$(".td-step").forEach((step, idx) => {
      step.classList.remove("completed", "active", "failed", "cancelled", "waiting");
      const stepName = step.dataset.step;
      const timeEl = step.querySelector(".td-step-time");
      const outputEl = step.querySelector(".td-step-output");
      
      if (failed && idx === currentIdx) {
        step.classList.add(rawStatus === "cancelled" ? "cancelled" : "failed");
        if (timeEl) timeEl.textContent = rawStatus === "failed" ? "失败" : "已终止";
        if (outputEl) outputEl.textContent = taskData.error || "任务未完成";
      } else if (idx < currentIdx || rawStatus === "done") {
        step.classList.add("completed");
        if (timeEl) {
          const stepData = stepTimes[stepName];
          if (stepData) {
            timeEl.textContent = stepData.done + " (耗时" + stepData.duration + "秒)";
          } else {
            timeEl.textContent = "已完成";
          }
        }
      } else if (idx === currentIdx) {
        step.classList.add("active");
        if (timeEl) {
          if (status === "done") {
            const stepData = stepTimes[stepName];
            if (stepData) {
              timeEl.textContent = stepData.done + " (耗时" + stepData.duration + "秒)";
            } else {
              timeEl.textContent = "已完成";
            }
          } else {
            timeEl.textContent = "进行中...";
          }
        }
      } else {
        step.classList.add("waiting");
        if (timeEl) {
          timeEl.textContent = "等待中";
        }
      }
    });
  }

  function getTaskProgressIndex(task) {
    var progress = Number(task && task.stage_progress);
    if (!Number.isFinite(progress)) return 0;
    return Math.max(0, Math.min(6, Math.floor(progress)));
  }

  function resolveStepStatus(status, task) {
    const steps = ["waiting", "deconstructing", "generating_note", "ai_scoring", "human_review", "generating_image", "done"];
    if (steps.indexOf(status) >= 0) return status;
    if (status === "pending") return "waiting";
    if (status === "processing") {
      return steps[Math.max(1, Math.min(5, getTaskProgressIndex(task)))] || "deconstructing";
    }
    return steps[Math.max(0, Math.min(6, getTaskProgressIndex(task)))] || "waiting";
  }

  /* ===== 渲染笔记内容 ===== */
  /* ===== 渲染笔记 ===== */
  function openLightbox(url) {
    var lb = document.createElement("div");
    lb.className = "td-cover-lightbox";
    lb.innerHTML = '<img src="' + url + '" />';
    lb.onclick = function() { document.body.removeChild(lb); };
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape" && lb.parentNode) { document.body.removeChild(lb); }
    });
    document.body.appendChild(lb);
  }

  function renderImages() {
    var coverEl = document.querySelector(".td-cover-img");
    var previewEl = document.querySelector(".td-cover-preview");
    if (!taskData || !taskData.images || !Object.keys(taskData.images).length) {
      if (coverEl) coverEl.innerHTML = '<span aria-hidden="true">📖</span>';
      if (previewEl) {
        previewEl.innerHTML = '<div class="td-empty-state">暂无图片<br>封面和配图生成后会显示在这里</div>';
      }
      return;
    }
    var imgs = taskData.images;
    var keys = Object.keys(imgs);
    var coverUrl = _toImageUrl(imgs.cover || imgs[keys[0]]);
    if (!coverUrl) {
      if (previewEl) previewEl.innerHTML = '<div class="td-empty-state">暂无可预览图片</div>';
      return;
    }

    if (coverEl) {
      coverEl.textContent = "";
      coverEl.style.position = "relative";
      var img = document.createElement("img");
      img.src = coverUrl;
      img.style.cssText = "width:100%;height:100%;object-fit:cover;border-radius:12px";
      img.onerror = function() { this.parentElement.textContent = "📖"; };
      img.onclick = function() { openLightbox(this.src); };
      coverEl.appendChild(img);
      var hover = document.createElement("div");
      hover.className = "td-cover-hover-layer";
      hover.innerHTML = '<button type="button">查看大图</button>';
      hover.querySelector("button").onclick = function(event) {
        event.stopPropagation();
        openLightbox(coverUrl);
      };
      coverEl.appendChild(hover);
    }
    if (previewEl) {
      previewEl.textContent = "";
      var mainImg = document.createElement("img");
      mainImg.src = coverUrl;
      mainImg.style.cssText = "width:100%;height:360px;object-fit:cover;border-radius:8px;flex-shrink:0;cursor:pointer";
      mainImg.onclick = function() { openLightbox(this.src); };
      previewEl.appendChild(mainImg);
      var thumbRow = document.createElement("div");
      thumbRow.className = "td-thumb-row";
      keys.forEach(function(k, i) {
        var thumbUrl = _toImageUrl(imgs[k]);
        if (!thumbUrl) return;
        var thumb = document.createElement("img");
        thumb.src = thumbUrl;
        thumb.className = "td-thumb" + (i === 0 ? " active" : "");
        thumb.onclick = function() {
          mainImg.src = this.src;
          $$(".td-thumb").forEach(function(el) { el.classList.remove("active"); });
          this.classList.add("active");
        };
        thumb.onerror = function() { this.style.display = "none"; };
        thumbRow.appendChild(thumb);
      });
      previewEl.appendChild(thumbRow);
    }
  }

  function _toImageUrl(path) {
    if (!path) return null;
    if (path.indexOf("http") === 0) return path;
    var p = path.replace(/^temp\/(jimeng_cache|generated_images)\//, "");
    return "/_health/images/" + encodeURI(p);
  }

  function renderNote() {
    var titleInput = document.getElementById("noteTitle");
    var contentArea = document.getElementById("noteContent");
    if (!taskData || !taskData.note_content) {
      if (titleInput) titleInput.value = "";
      if (contentArea) contentArea.value = "";
      renderTitleOptions();
      return;
    }

    var note = taskData.note_content;
    if (titleInput) {
      titleInput.value = note.title || "";
      updateTitleCount();
    }
    if (contentArea) {
      contentArea.value = note.content || "";
      updateWordCount();
    }
    var tagsList = document.getElementById("tagsList");
    if (tagsList) {
      tagsList.textContent = "";
      if (note.tags && note.tags.length) {
        for (var i = 0; i < note.tags.length; i++) {
          var span = document.createElement("span");
          span.className = "td-tag";
          span.innerHTML = esc(note.tags[i]) + '<span class="td-tag-remove" data-tag="' + esc(note.tags[i]) + '">×</span>';
          tagsList.appendChild(span);
        }
      } else {
        tagsList.innerHTML = '<span class="td-empty-inline">暂无标签</span>';
      }
    }
    renderTitleOptions();
    updateSideStats();
  }

  /* ===== 备选标题选择器 ===== */
  function renderTitleOptions() {
    var box = document.getElementById("titleOptionsBox");
    var list = document.getElementById("titleOptionsList");
    if (!box || !list) return;

    var titles = [];
    if (taskData && taskData.note_content && taskData.note_content.title_options) {
      titles = taskData.note_content.title_options;
    }

    if (!titles || !titles.length) {
      box.style.display = "none";
      return;
    }

    box.style.display = "block";
    list.textContent = "";

    var currentTitle = (document.getElementById("noteTitle") || {}).value || "";
    titles.forEach(function(t) {
      var chip = document.createElement("span");
      chip.className = "td-option-chip";
      if (t === currentTitle) {
        chip.classList.add("td-option-active");
      }
      chip.textContent = t;
      chip.title = t;
      chip.addEventListener("click", function() {
        var titleInput = document.getElementById("noteTitle");
        if (titleInput) {
          titleInput.value = t;
          updateTitleCount();
          isDraftDirty = true;
          // 更新 active 状态
          var allChips = list.querySelectorAll(".td-option-chip");
          allChips.forEach(function(c) { c.classList.remove("td-option-active"); });
          chip.classList.add("td-option-active");
        }
      });
      list.appendChild(chip);
    });
  }

  /* ===== 渲染拆文结果 ===== */
  function renderDeconstruct() {
    if (!taskData || !taskData.deconstruct_result) {
      // 没有拆文结果
      $$(".td-collapse-content").forEach(el => {
        el.innerHTML = '<div class="td-empty-state td-empty-state--compact">暂无拆文结果，请先运行拆文任务</div>';
      });
      return;
    }
    const result = taskData.deconstruct_result;

    setCollapseContent("collapseOpenings", result.openings);
    setCollapseContent("collapseCharacters", result.characters);
    setCollapseContent("collapseConflicts", result.conflicts);
    setCollapseContent("collapseEmotions", result.emotions);

    // 金句特殊处理
    const quotesEl = $("#collapseQuotes");
    if (quotesEl && result.quotes) {
      quotesEl.querySelector(".td-collapse-content").innerHTML =
        '<div class="td-quote-list">' +
        result.quotes.map((q, i) =>
          '<div class="td-quote-item"><span class="td-quote-number">' + (i + 1) + ".</span>" + esc(q) + "</div>"
        ).join("") +
        "</div>";
    }
  }

  function setCollapseContent(id, items) {
    var el = document.getElementById(id);
    if (!el || !items || !items.length) {
      if (el) {
        el.querySelector(".td-collapse-content").innerHTML = '<div class="td-empty-state td-empty-state--compact">内容为空，可点击重试获得完整结果</div>';
      }
      return;
    }
    el.querySelector(".td-collapse-content").innerHTML =
      "<ul>" + items.map(function(item) { return "<li>" + esc(item) + "</li>"; }).join("") + "</ul>";
  }

  /* ===== 渲染AI评分 ===== */
  function renderScore() {
    if (!taskData || !taskData.note_content || !taskData.note_content.score) {
      // 没有评分数据
      setText("#totalScore", "—");
      setText("#scoreTitle", "—");
      setText("#scoreEmotion", "—");
      setText("#scoreCollect", "—");
      setText("#scoreInteraction", "—");
      setText("#scoreStyle", "—");
      setText("#scoreAi", "—");
      const empty = $("#scoreEmptyState");
      if (empty) empty.style.display = "flex";
      
      renderAdvice([]);
      return;
    }
    
    const score = taskData.note_content.score;
    const empty = $("#scoreEmptyState");
    if (empty) empty.style.display = "none";

    setText("#totalScore", score.total || 0);
    setText("#scoreTitle", (score.title_attract || 0) + "/30");
    setText("#scoreEmotion", (score.emotion || 0) + "/20");
    setText("#scoreCollect", (score.collect_value || 0) + "/20");
    setText("#scoreInteraction", (score.interaction || 0) + "/15");
    setText("#scoreStyle", (score.style_match || 0) + "/10");
    setText("#scoreAi", (score.ai_trace || 0) + "/5");

    // 更新环形进度
    const ring = $("#scoreRing");
    if (ring) {
      const circumference = 2 * Math.PI * 54;
      const offset = circumference - (score.total / 100) * circumference;
      ring.style.strokeDashoffset = offset;
    }

    // 更新进度条
    const items = $$(".td-score-item");
    const values = [
      (score.title_attract || 0) / 30,
      (score.emotion || 0) / 20,
      (score.collect_value || 0) / 20,
      (score.interaction || 0) / 15,
      (score.style_match || 0) / 10,
      (score.ai_trace || 0) / 5,
    ];
    items.forEach((item, idx) => {
      const fill = item.querySelector(".td-score-item-fill");
      if (fill) fill.style.width = (values[idx] * 100) + "%";
    });

    // AI建议
    renderAdvice(score.suggestions || []);
  }

  function renderAdvice(suggestions) {
    const adviceList = $("#aiAdviceList");
    if (!adviceList) return;
    if (!suggestions || !suggestions.length) {
      adviceList.innerHTML = '<div class="td-empty-state td-empty-state--compact">暂无 AI 建议，重新评分后会显示改进方向</div>';
      return;
    }
    adviceList.innerHTML = suggestions.map(function(s) {
      return '<div class="td-suggestion-item">' + esc(s) + "</div>";
    }).join("");
  }

  /* ===== Tab切换 ===== */
  function bindTabs() {
    $$(".td-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$(".td-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const tabName = tab.dataset.tab;
        $$(".td-tab-pane").forEach((pane) => pane.classList.remove("active"));
        $("#tab" + capitalize(tabName)).classList.add("active");
        currentTab = tabName;
      });
    });
  }

  function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  /* ===== 折叠面板 ===== */
  function bindCollapses() {
    $$(".td-collapse-header").forEach((header) => {
      header.addEventListener("click", () => {
        const item = header.closest(".td-collapse-item");
        item.classList.toggle("collapsed");
      });
    });
  }

  /* ===== 编辑器 ===== */
  function bindEditor() {
    const titleInput = $("#noteTitle");
    if (titleInput) {
      titleInput.addEventListener("input", function() {
        isDraftDirty = true;
        updateTitleCount();
      });
    }

    const contentArea = $("#noteContent");
    if (contentArea) {
      contentArea.addEventListener("input", function() {
        isDraftDirty = true;
        updateWordCount();
      });
    }

    ["#noteTitle", "#noteContent", "#tagsList"].forEach(function(sel) {
      const el = $(sel);
      if (!el) return;
      el.addEventListener("focusin", function() { editorHasFocus = true; });
      el.addEventListener("focusout", function() {
        window.setTimeout(function() {
          editorHasFocus = !!document.activeElement && !!document.activeElement.closest("#noteTitle, #noteContent, #tagsList");
        }, 0);
      });
    });

    // 添加标签
    const addTagBtn = $("#addTagBtn");
    if (addTagBtn) {
      addTagBtn.addEventListener("click", () => {
        const tag = prompt("输入标签:");
        if (tag && tag.trim()) {
          const tagsList = $("#tagsList");
          const tagEl = document.createElement("span");
          tagEl.className = "td-tag";
          tagEl.innerHTML = esc(tag.trim()) + '<span class="td-tag-remove" data-tag="' + esc(tag.trim()) + '">×</span>';
          const empty = tagsList.querySelector(".td-empty-inline");
          if (empty) empty.remove();
          tagsList.appendChild(tagEl);
          isDraftDirty = true;
          updateSideStats();
        }
      });
    }

    // 删除标签
    document.addEventListener("click", (e) => {
      if (e.target.classList.contains("td-tag-remove")) {
        e.target.parentElement.remove();
        isDraftDirty = true;
        updateSideStats();
      }
    });
  }

  function updateTitleCount() {
    const input = $("#noteTitle");
    const counter = $("#titleCount");
    if (input && counter) {
      counter.textContent = input.value.length;
    }
    updateSideStats();
  }

  function updateWordCount() {
    const textarea = $("#noteContent");
    const counter = $("#wordCount");
    if (textarea && counter) {
      counter.textContent = textarea.value.length;
    }
    updateSideStats();
  }

  function updateSideStats() {
    const content = $("#noteContent");
    const tags = $$("#tagsList .td-tag");
    setText("#sideWordCount", content ? content.value.length : 0);
    setText("#sideTagCount", tags.length);
  }

  /* ===== 操作按钮 ===== */
  function bindActions() {
    // 保存草稿
    bindBtn("#btnSaveDraft", async () => {
      const result = await apiCall("/api/task/" + taskData.record_id + "/save-draft", "草稿已保存", getDraftPayload());
      if (result) {
        isDraftDirty = false;
        setText("#saveStatus", "已保存 " + new Date().toLocaleTimeString("zh-CN", { hour12: false }));
      }
      loadTaskDetail(taskData.record_id);
    });

    // 通过审核
    bindBtn("#btnApprove", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/approve", "已通过审核");
      loadTaskDetail(taskData.record_id);
    });

    // 重新生成
    bindBtn("#btnRegenerate", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/regenerate-note", "重新生成中...");
      loadTaskDetail(taskData.record_id);
    });

    // 重新生成笔记
    bindBtn("#btnRegenerateNote", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/regenerate-note", "重新生成中...");
      loadTaskDetail(taskData.record_id);
    });

    // 重新评分
    bindBtn("#btnRescore", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/rescore", "重新评分完成", {
        note_content: ($("#noteContent") || {}).value || ""
      });
      loadTaskDetail(taskData.record_id);
    });

    bindBtn("#btnRefresh", async () => {
      await loadTaskDetail((taskData && taskData.record_id) || currentTaskId, { preserveDraft: shouldPreserveDraft() });
    });
  }

  function getDraftPayload() {
    return {
      title: ($("#noteTitle") || {}).value || "",
      content: ($("#noteContent") || {}).value || "",
      tags: Array.from(document.querySelectorAll("#tagsList .td-tag")).map(function(el) {
        return (el.childNodes[0] ? el.childNodes[0].textContent : el.textContent).replace("×", "").trim();
      }).filter(Boolean)
    };
  }

  async function apiCall(url, successMsg, payload) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);
      showToast("success", successMsg || "操作成功");
      return json;
    } catch (e) {
      showToast("error", "操作失败: " + e.message);
      return null;
    }
  }

  function bindBtn(sel, fn) {
    const el = $(sel);
    if (el) el.addEventListener("click", fn);
  }

  /* ===== Toast ===== */
  function showToast(type, message) {
    let toast = $(".td-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "td-toast";
      document.body.appendChild(toast);
    }
    toast.className = "td-toast td-toast-" + type;
    toast.textContent = message;
    toast.style.cssText = "position:fixed;top:72px;right:24px;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:500;z-index:1000;opacity:0;transform:translateX(100%);transition:all 0.3s;";
    if (type === "success") {
      toast.style.background = "#ECFDF5";
      toast.style.color = "#065F46";
      toast.style.border = "1px solid #A7F3D0";
    } else {
      toast.style.background = "#FEF2F2";
      toast.style.color = "#991B1B";
      toast.style.border = "1px solid #FECACA";
    }
    toast.style.opacity = "1";
    toast.style.transform = "translateX(0)";
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
    }, 3000);
  }

  /* ===== 工具函数 ===== */
  function setText(sel, val) {
    const el = $(sel);
    if (el) el.textContent = val != null ? val : "—";
  }

  function esc(str) {
    if (str == null) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  /* ===== 图片生成策略切换 ===== */
  let currentStrategy = 'ai';
  let currentStyle = 'warm';

  async function loadImageStrategy() {
    try {
      const res = await fetch('/api/config/image_strategy');
      const data = await res.json();
      currentStrategy = data.strategy || 'ai';
      currentStyle = data.style || 'warm';
      renderStrategySelector();
    } catch (e) {
      console.warn('加载策略失败:', e);
    }
  }

  function renderStrategySelector() {
    let container = document.getElementById('strategySelector');
    if (!container) {
      container = document.createElement('div');
      container.id = 'strategySelector';
      container.style.cssText = 'margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;';
      const right = document.querySelector('.td-header-right .td-summary-actions');
      if (right && right.parentElement) {
        right.parentElement.appendChild(container);
      }
    }
    const safe = (s) => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    container.innerHTML =
      '<label style="font-size:13px;color:var(--text-secondary,#666);">生图策略:</label>' +
      '<select id="imageStrategy" style="padding:4px 8px;border-radius:6px;font-size:13px;border:1px solid var(--border,#e0e0e0);background:var(--bg-surface,#fff);">' +
        '<option value="ai"' + (currentStrategy==='ai'?' selected':'') + '>AI 即梦生图</option>' +
        '<option value="html_card"' + (currentStrategy==='html_card'?' selected':'') + '>HTML 卡片截图</option>' +
      '</select>' +
      '<select id="imageStyle" style="padding:4px 8px;border-radius:6px;font-size:13px;border:1px solid var(--border,#e0e0e0);background:var(--bg-surface,#fff);' + (currentStrategy==='html_card'?'':'display:none;') + '">' +
        '<option value="warm"' + (currentStyle==='warm'?' selected':'') + '>暖色生活(Warm)</option>' +
        '<option value="anthropic"' + (currentStyle==='anthropic'?' selected':'') + '>杂志风(Anthropic)</option>' +
        '<option value="notion"' + (currentStyle==='notion'?' selected':'') + '>笔记风(Notion)</option>' +
        '<option value="minimal"' + (currentStyle==='minimal'?' selected':'') + '>极简(Minimal)</option>' +
        '<option value="morandi"' + (currentStyle==='morandi'?' selected':'') + '>莫兰迪(Morandi)</option>' +
      '</select>' +
      '<span id="strategyStatus" style="font-size:12px;color:var(--text-muted,#999);"></span>';
    document.getElementById('imageStrategy').addEventListener('change', onStrategyChange);
    document.getElementById('imageStyle').addEventListener('change', onStrategyChange);
  }

  async function onStrategyChange() {
    const strategy = document.getElementById('imageStrategy').value;
    const style = document.getElementById('imageStyle').value;
    document.getElementById('imageStyle').style.display = strategy === 'html_card' ? '' : 'none';
    const status = document.getElementById('strategyStatus');
    status.textContent = '保存中...';
    try {
      const res = await fetch('/api/config/image_strategy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({strategy, style})
      });
      const data = await res.json();
      if (data.ok) {
        status.textContent = '已保存，重启 worker 后生效';
        setTimeout(function(){ status.textContent = ''; }, 3000);
      } else {
        status.textContent = '保存失败: ' + (data.error || '');
      }
    } catch (e) {
      status.textContent = '保存失败: ' + e.message;
    }
  }

  function fmtWordCount(n) {
    if (n == null) return "—";
    if (n >= 10000) return (n / 10000).toFixed(1) + "万字";
    return n + "字";
  }
})();
