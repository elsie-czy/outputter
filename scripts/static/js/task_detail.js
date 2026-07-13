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
  const AUTO_REFRESH_STORAGE_KEY = "taskDetailAutoRefresh";

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
    bindGenerationWorkflow();
    initAutoRefreshToggle(taskId);
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
      renderGenerationWorkflow();
      renderGenerationStrategy();
      renderImages();
      renderHistory();
      updateRefreshStatus(options.auto ? "自动刷新已更新" : "已刷新");
    } catch (e) {
      updateRefreshStatus("刷新失败");
      showToast("error", "加载失败: " + e.message);
    }
  }

  function startAutoRefresh(taskId) {
    stopAutoRefresh();
    updateRefreshStatus("自动刷新已开启");
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

  function initAutoRefreshToggle(taskId) {
    const toggle = $("#autoRefreshToggle");
    const saved = window.localStorage.getItem(AUTO_REFRESH_STORAGE_KEY);
    const enabled = saved === "1";
    if (toggle) {
      toggle.checked = enabled;
      toggle.addEventListener("change", function() {
        const isEnabled = !!toggle.checked;
        window.localStorage.setItem(AUTO_REFRESH_STORAGE_KEY, isEnabled ? "1" : "0");
        if (isEnabled) {
          startAutoRefresh(taskId);
        } else {
          stopAutoRefresh();
          updateRefreshStatus("自动刷新已关闭");
        }
      });
    }
    if (enabled) {
      startAutoRefresh(taskId);
    } else {
      updateRefreshStatus("自动刷新已关闭");
    }
  }

  function shouldPreserveDraft() {
    return editorHasFocus || isDraftDirty;
  }

  function updateRefreshStatus(text) {
    setText("#autoRefreshStatus", text || "自动刷新已关闭");
    setText("#footerRefreshStatus", text === "刷新失败" ? "异常" : (autoRefreshTimer ? "运行中" : "已暂停"));
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
    setText("#taskPlatformHero", taskData.platform || "—");
    setText("#taskCategory", taskData.category || "—");
    setText("#taskWordCount", fmtWordCount(taskData.word_count));
    setText("#taskModel", "Qwen-Plus");
    setText("#taskSource", taskData.source || "新文 · 小红书笔记");
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
    if (status === "done" || status === "completed") return "已审核";
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
    const steps = ["waiting", "deconstructing", "generating_note", "ai_scoring", "generating_image", "human_review", "done"];
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
    const steps = ["waiting", "deconstructing", "generating_note", "ai_scoring", "generating_image", "human_review", "done"];
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
    var version = _imageVersion();
    var sep = String(path).indexOf("?") >= 0 ? "&" : "?";
    if (path.indexOf("http") === 0) return path + sep + "v=" + version;
    // 直接拼 /_health/images/ + 完整相对路径（支持子目录）
    return "/_health/images/" + encodeURI(path) + "?v=" + version;
  }

  function _imageVersion() {
    if (!taskData) return Date.now();
    var stepTimes = taskData.step_times || {};
    var imageStep = stepTimes.generating_image || {};
    return encodeURIComponent(taskData.updated_at || imageStep.done || taskData.completed_at || Date.now());
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
    renderConversionReview();
  }

  function conversionTextBlock(review) {
    if (!review) return "";
    var replies = review.reply_prompts || [];
    return [
      "评论钩子：\n" + (review.comment_hook || ""),
      "关注理由：\n" + (review.follow_reason || ""),
      "发布后首评：\n" + (review.first_comment || ""),
      "回复话术：\n" + replies.map(function(x, i) { return (i + 1) + ". " + x; }).join("\n")
    ].join("\n\n");
  }

  function renderConversionReview() {
    var card = $("#conversionReviewCard");
    if (!card) return;
    var review = taskData && taskData.conversion_review;
    if (!review) {
      card.innerHTML = '<div class="td-empty-state td-empty-state--compact">暂无互动转化建议，重新生成或评分后会显示</div>';
      return;
    }
    var replies = review.reply_prompts || [];
    var suggestions = review.suggestions || [];
    card.innerHTML =
      '<div class="td-conversion-score">' +
        '<strong>' + esc(review.total || 0) + '/70</strong>' +
        '<span>' + esc(review.grade || "review") + '</span>' +
        (review.comment_hook_type ? '<em>' + esc(review.comment_hook_type) + '</em>' : '') +
      '</div>' +
      conversionItemHtml("评论钩子", review.comment_hook, "copyCommentHook") +
      conversionItemHtml("关注理由", review.follow_reason, "copyFollowReason") +
      conversionItemHtml("发布后首评", review.first_comment, "copyFirstComment") +
      '<div class="td-conversion-item">' +
        '<div class="td-conversion-head"><span>可复用回复</span><button type="button" data-copy-conversion="copyReplies">复制全部</button></div>' +
        '<ol>' + replies.map(function(x) { return '<li>' + esc(x) + '</li>'; }).join("") + '</ol>' +
      '</div>' +
      (suggestions.length ? '<div class="td-conversion-suggestions">' +
        suggestions.map(function(s) {
          return '<div class="td-suggestion-item td-suggestion-item--structured">' +
            '<div class="td-suggestion-head"><strong>' + esc(s.dimension || "转化建议") + '</strong></div>' +
            (s.problem ? '<p><span>问题</span>' + esc(s.problem) + '</p>' : '') +
            (s.action ? '<p><span>动作</span>' + esc(s.action) + '</p>' : '') +
            (s.reason ? '<p><span>依据</span>' + esc(s.reason) + '</p>' : '') +
          '</div>';
        }).join("") +
      '</div>' : '');
  }

  function conversionItemHtml(label, text, key) {
    return '<div class="td-conversion-item">' +
      '<div class="td-conversion-head"><span>' + esc(label) + '</span><button type="button" data-copy-conversion="' + key + '">复制</button></div>' +
      '<p>' + esc(text || "暂无") + '</p>' +
    '</div>';
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

    renderStrategyCollapse();
    setCollapseContent("collapseOpenings", result.openings);
    setCollapseContent("collapseCharacters", result.characters);
    setCollapseContent("collapseConflicts", result.conflicts);
    setCollapseContent("collapseEmotions", result.emotions);
    renderVisualStoryboard(result.visual_storyboard || result.visualStoryboard || []);

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

  function renderVisualStoryboard(items) {
    const el = $("#collapseStoryboard");
    if (!el) return;
    const body = el.querySelector(".td-collapse-content");
    if (!body) return;
    if (!Array.isArray(items) || !items.length) {
      body.innerHTML = '<div class="td-empty-state td-empty-state--compact">暂无视觉分镜，新任务生成后会显示图片依据</div>';
      return;
    }
    body.innerHTML = '<div class="td-storyboard-list">' + items.slice(0, 5).map(function(item, idx) {
      if (typeof item === "string") {
        return '<div class="td-storyboard-item"><strong>第' + (idx + 1) + '页</strong><p>' + esc(item) + '</p></div>';
      }
      item = item || {};
      const role = item["作用"] || item.role || "分镜";
      const basis = item["剧情依据"] || item.basis || "";
      const subject = item["画面主体"] || item.subject || "";
      const scene = item["场景"] || item.scene || "";
      const action = item["动作"] || item.action || "";
      const mood = item["情绪"] || item.mood || "";
      return '<div class="td-storyboard-item">' +
        '<strong>第' + (idx + 1) + '页 · ' + esc(role) + '</strong>' +
        '<p><span>剧情依据</span>' + esc(basis || "未填写") + '</p>' +
        '<p><span>画面</span>' + esc([subject, scene, action, mood].filter(Boolean).join(" · ") || "未填写") + '</p>' +
        '</div>';
    }).join("") + '</div>';
  }

  function renderGenerationStrategy() {
    const el = $("#generationStrategyCard");
    if (!el) return;
    const strategy = taskData && taskData.generation_strategy ? taskData.generation_strategy : null;
    if (!strategy || !strategy.id) {
      el.innerHTML = '<div class="td-empty-state td-empty-state--compact">暂无生成策略信息</div>';
      return;
    }
    el.innerHTML =
      '<div class="td-strategy-card-head">' +
      '<strong>' + esc(strategy.name || strategy.id) + "</strong>" +
      '<span>' + esc(strategy.id || "") + "</span>" +
      "</div>" +
      '<p>' + esc(strategy.positioning || "未填写账号定位") + "</p>" +
      workflowSummary(strategy.generation_params || (taskData && taskData.generation_params) || {}) +
      strategyPills(strategy.quality_focus || [], "质量关注");
  }

  function renderGenerationWorkflow() {
    if (!taskData) return;
    var params = taskData.generation_params || {};
    setSelectValue("#workflowNoteType", params.note_type || "normal_recommendation");
    setSelectValue("#workflowOpeningType", params.opening_type || "auto");
    setSelectValue("#workflowReadStatus", params.read_status || "synopsis_only");
    setSelectValue("#workflowCoverTemplate", params.cover_template || params.note_type || "normal_recommendation");
    var brief = $("#workflowManualBrief");
    if (brief && document.activeElement !== brief) {
      brief.value = params.manual_generation_brief || "";
    }
  }

  function workflowSummary(params) {
    if (!params) return "";
    var labels = {
      normal_recommendation: "正常推荐",
      comment_experiment: "求投喂",
      warning_review: "避雷判断",
      booklist: "书单合集",
      auto: "自动",
      strong_recommend: "强安利",
      warning_reversal: "避雷反转",
      book_shortage_rescue: "书荒急救",
      audience_filter: "人群筛选",
      rant_entry: "吐槽带入",
      synopsis_only: "只看简介",
      read_to_chapter: "读到前 N 章",
      full_read: "已读全文"
    };
    var items = [
      "笔记类型: " + (labels[params.note_type] || params.note_type || "正常推荐"),
      "前三行: " + (labels[params.opening_type] || params.opening_type || "自动"),
      "资料边界: " + (labels[params.read_status] || params.read_status || "只看简介")
    ];
    return '<div class="td-workflow-summary">' + items.map(function(item) {
      return '<em>' + esc(item) + '</em>';
    }).join("") + "</div>";
  }

  function setSelectValue(sel, value) {
    var el = $(sel);
    if (el) el.value = value;
  }

  function renderStrategyCollapse() {
    const el = $("#collapseStrategy");
    if (!el) return;
    const strategy = taskData && taskData.generation_strategy ? taskData.generation_strategy : null;
    if (!strategy || !strategy.id) {
      el.querySelector(".td-collapse-content").innerHTML = '<div class="td-empty-state td-empty-state--compact">暂无生成依据</div>';
      return;
    }
    el.querySelector(".td-collapse-content").innerHTML =
      '<div class="td-strategy-trace">' +
      '<div class="td-strategy-trace-main"><span>账号策略</span><strong>' + esc(strategy.name || strategy.id) + '</strong><p>' + esc(strategy.positioning || "") + "</p></div>" +
      strategyPills(strategy.platform_rules || [], "平台规则") +
      strategyPills(strategy.quality_focus || [], "质量关注") +
      strategyPills(strategy.benchmark_accounts || [], "对标账号") +
      '<div class="td-strategy-note">' + (strategy.content_fact_first ? "内容事实优先：标题、正文和封面钩子必须能被作品信息支撑。" : "内容事实优先未开启。") + "</div>" +
      "</div>";
  }

  function strategyPills(items, label) {
    const values = (items || []).filter(Boolean).slice(0, 8);
    if (!values.length) return "";
    return '<div class="td-strategy-pills"><span>' + esc(label) + '</span><div>' +
      values.map(function(item) { return '<em>' + esc(item) + "</em>"; }).join("") +
      "</div></div>";
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
      setText("#heroTotalScore", "—");
      setText("#heroScoreBadge", "待评分");
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
    setText("#heroTotalScore", score.total || 0);
    setText("#heroScoreBadge", (score.total || 0) >= 80 ? "优秀" : ((score.total || 0) >= 60 ? "待优化" : "需重写"));
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
      if (s && typeof s === "object") {
        return '<div class="td-suggestion-item td-suggestion-item--structured">' +
          '<div class="td-suggestion-head"><strong>' + esc(s.dimension || "编辑建议") + '</strong></div>' +
          (s.problem ? '<p><span>问题</span>' + esc(s.problem) + "</p>" : "") +
          (s.action ? '<p><span>动作</span>' + esc(s.action) + "</p>" : "") +
          (s.reason ? '<p><span>依据</span>' + esc(s.reason) + "</p>" : "") +
          "</div>";
      }
      return '<div class="td-suggestion-item">' + esc(s) + "</div>";
    }).join("");
  }

  async function copyText(text, successMessage) {
    if (!String(text || "").trim()) {
      showToast("error", "暂无可复制内容");
      return;
    }
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      showToast("success", successMessage || "已复制");
    } catch (e) {
      showToast("error", "复制失败: " + e.message);
    }
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

  function bindGenerationWorkflow() {
    [
      "#workflowNoteType",
      "#workflowOpeningType",
      "#workflowReadStatus",
      "#workflowCoverTemplate",
      "#workflowManualBrief"
    ].forEach(function(sel) {
      var el = $(sel);
      if (!el) return;
      el.addEventListener("change", function() { isDraftDirty = true; });
      el.addEventListener("input", function() { isDraftDirty = true; });
    });
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
      if (!confirm("确认通过审核？通过后任务将标记为「已审核」")) return;
      const result = await apiCall("/api/task/" + taskData.record_id + "/approve", "已通过审核并回写飞书", getDraftPayload());
      if (result && result.ok) {
        isDraftDirty = false;
        if (result.warning) showToast("error", result.warning);
        await loadTaskDetail(taskData.record_id);
      }
    });

    bindBtn("#btnCopyNote", async () => {
      const payload = getDraftPayload();
      const text = composeCopyText(payload);
      if (!text.trim()) {
        showToast("error", "暂无可复制内容");
        return;
      }
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
        } else {
          const ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.focus();
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
        }
        showToast("success", "笔记已复制");
      } catch (e) {
        showToast("error", "复制失败: " + e.message);
      }
    });

    document.addEventListener("click", async function(event) {
      var btn = event.target.closest("[data-copy-conversion]");
      if (!btn) return;
      var review = taskData && taskData.conversion_review;
      if (!review) {
        showToast("error", "暂无互动转化建议");
        return;
      }
      var key = btn.getAttribute("data-copy-conversion");
      var text = "";
      if (key === "copyCommentHook") text = review.comment_hook || "";
      if (key === "copyFollowReason") text = review.follow_reason || "";
      if (key === "copyFirstComment") text = review.first_comment || "";
      if (key === "copyReplies") text = (review.reply_prompts || []).join("\n");
      if (key === "copyAll") text = conversionTextBlock(review);
      await copyText(text, "已复制互动建议");
    });

    // 重新生成
    bindBtn("#btnRegenerate", async (event) => regenerateNote(event.currentTarget));

    // 重新生成笔记
    bindBtn("#btnRegenerateNote", async (event) => regenerateNote(event.currentTarget));

    // 重新生成配图
    bindBtn("#btnRegenerateImages", async (event) => regenerateImages(event.currentTarget));

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

  function composeCopyText(payload) {
    const parts = [];
    if (payload.title) parts.push(payload.title.trim());
    if (payload.content) parts.push(payload.content.trim());
    if (payload.tags && payload.tags.length) {
      parts.push(payload.tags.map(function(tag) {
        tag = String(tag || "").trim();
        return tag ? (tag.charAt(0) === "#" ? tag : "#" + tag) : "";
      }).filter(Boolean).join(" "));
    }
    return parts.filter(Boolean).join("\n\n");
  }

  async function regenerateNote(button) {
    if (!taskData || !taskData.record_id) return;
    setButtonBusy(button, true, "生成中...");
    showToast("success", "正在重新生成笔记，模型返回前请稍等");
    const result = await apiCall(
      "/api/task/" + taskData.record_id + "/regenerate-note",
      "笔记已重新生成",
      getGenerationPayload()
    );
    setButtonBusy(button, false);
    if (result) {
      isDraftDirty = false;
      await loadTaskDetail(taskData.record_id);
    }
  }

  function getGenerationPayload() {
    var noteType = ($("#workflowNoteType") || {}).value || "normal_recommendation";
    var readStatus = ($("#workflowReadStatus") || {}).value || "synopsis_only";
    return {
      note_type: noteType,
      opening_type: ($("#workflowOpeningType") || {}).value || "auto",
      read_status: readStatus,
      cover_template: ($("#workflowCoverTemplate") || {}).value || noteType,
      source_confidence: readStatus === "full_read" ? "full_read" : (readStatus === "read_to_chapter" ? "partial_read" : "synopsis"),
      manual_generation_brief: ($("#workflowManualBrief") || {}).value || ""
    };
  }

  async function regenerateImages(button) {
    if (!taskData || !taskData.record_id) return;
    if (!confirm("确认重新生成配图？当前封面和配图会被新结果替换。")) return;
    setButtonBusy(button, true, "生图中...");
    showToast("success", "正在重新生成配图，图片服务返回前请稍等");
    const result = await apiCall("/api/task/" + taskData.record_id + "/regenerate-images", "配图已重新生成");
    setButtonBusy(button, false);
    if (result) {
      await loadTaskDetail(taskData.record_id);
    }
  }

  function setButtonBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.classList.add("is-loading");
      const icon = button.querySelector("i") ? '<i data-lucide="loader-circle"></i>' : "";
      button.innerHTML = icon + "<span>" + esc(label || "处理中...") + "</span>";
      if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
      return;
    }
    button.disabled = false;
    button.classList.remove("is-loading");
    if (button.dataset.originalHtml) {
      button.innerHTML = button.dataset.originalHtml;
      delete button.dataset.originalHtml;
      if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    }
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
  let currentProvider = 'jimeng';

  async function loadImageStrategy() {
    try {
      const res = await fetch('/api/config/image_strategy');
      const data = await res.json();
      currentStrategy = data.strategy || 'ai';
      currentStyle = data.style || 'warm';
      currentProvider = data.provider || 'jimeng';
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
        '<option value="ai"' + (currentStrategy==='ai'?' selected':'') + '>AI 生图</option>' +
        '<option value="html_card"' + (currentStrategy==='html_card'?' selected':'') + '>HTML 卡片截图</option>' +
        '<option value="auto"' + (currentStrategy==='auto'?' selected':'') + '>🤖 自动匹配</option>' +
      '</select>' +
      '<select id="imageProvider" style="padding:4px 8px;border-radius:6px;font-size:13px;border:1px solid var(--border,#e0e0e0);background:var(--bg-surface,#fff);' + (currentStrategy==='ai'?'':'display:none;') + '">' +
        '<option value="liblib"' + (currentProvider==='liblib'?' selected':'') + '>LiblibAI 星流</option>' +
        '<option value="doubao_seedream_5_lite"' + (currentProvider==='doubao_seedream_5_lite'?' selected':'') + '>豆包 Seedream 5.0</option>' +
        '<option value="doubao_seedream_4_5"' + (currentProvider==='doubao_seedream_4_5'?' selected':'') + '>豆包 Seedream 4.5</option>' +
        '<option value="doubao_seedream_4_0"' + (currentProvider==='doubao_seedream_4_0'?' selected':'') + '>豆包 Seedream 4.0</option>' +
        '<option value="jimeng"' + (currentProvider==='jimeng'?' selected':'') + '>即梦 / 火山</option>' +
        '<option value="siliconflow"' + (currentProvider==='siliconflow'?' selected':'') + '>SiliconFlow</option>' +
        '<option value="mock"' + (currentProvider==='mock'?' selected':'') + '>Mock</option>' +
      '</select>' +
      '<select id="imageStyle" style="padding:4px 8px;border-radius:6px;font-size:13px;border:1px solid var(--border,#e0e0e0);background:var(--bg-surface,#fff);' + (currentStrategy==='html_card'?'':'display:none;') + '">' +
        '<option value="warm"' + (currentStyle==='warm'?' selected':'') + '>暖色生活(Warm)</option>' +
        '<option value="anthropic"' + (currentStyle==='anthropic'?' selected':'') + '>杂志风(Anthropic)</option>' +
        '<option value="notion"' + (currentStyle==='notion'?' selected':'') + '>笔记风(Notion)</option>' +
        '<option value="minimal"' + (currentStyle==='minimal'?' selected':'') + '>极简(Minimal)</option>' +
        '<option value="morandi"' + (currentStyle==='morandi'?' selected':'') + '>莫兰迪(Morandi)</option>' +
        '<option value="auto"' + (currentStyle==='auto'?' selected':'') + '>🤖 自动匹配</option>' +
      '</select>' +
      '<span id="strategyStatus" style="font-size:12px;color:var(--text-muted,#999);"></span>';
    document.getElementById('imageStrategy').addEventListener('change', onStrategyChange);
    document.getElementById('imageProvider').addEventListener('change', onStrategyChange);
    document.getElementById('imageStyle').addEventListener('change', onStrategyChange);
  }

  async function onStrategyChange() {
    const strategy = document.getElementById('imageStrategy').value;
    const provider = document.getElementById('imageProvider').value;
    const style = document.getElementById('imageStyle').value;
    const providerEl = document.getElementById('imageProvider');
    const styleEl = document.getElementById('imageStyle');
    providerEl.style.display = (strategy === 'ai') ? '' : 'none';
    styleEl.style.display = (strategy === 'html_card') ? '' : 'none';
    const status = document.getElementById('strategyStatus');
    status.textContent = '保存中...';
    const body = { strategy };
    if (strategy === 'ai') body.provider = provider;
    if (strategy === 'html_card') body.style = style;
    try {
      const res = await fetch('/api/config/image_strategy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
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
