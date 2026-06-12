/**
 * 任务详情页交互模块
 * - 加载任务详情
 * - Tab 切换
 * - 笔记编辑
 * - 拆文结果展示
 * - AI 评分展示
 * - 修改记录
 * - 操作按钮
 */
(function () {
  "use strict";

  /* ===== 状态 ===== */
  let taskData = null;
  let currentTab = "note";

  /* ===== DOM 缓存 ===== */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  /* ===== 初始化 ===== */
  document.addEventListener("DOMContentLoaded", () => {
    const container = $(".td-container");
    if (!container) return;
    const taskId = container.dataset.taskId;
    loadTaskDetail(taskId);
    bindTabs();
    bindActions();
    bindCollapses();
    bindEditor();
  });

  /* ===== 数据加载 ===== */
  async function loadTaskDetail(taskId) {
    try {
      const res = await fetch("/api/task/" + taskId);
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);
      taskData = json.data;
      renderTaskInfo();
      renderProgress();
      renderNote();
      renderDeconstruct();
      renderScore();
      renderHistory();
    } catch (e) {
      showToast("error", "加载失败: " + e.message);
    }
  }

  /* ===== 渲染任务信息 ===== */
  function renderTaskInfo() {
    if (!taskData) return;
    
    // 第一层：标题
    setText("#taskTitle", taskData.work_name || "未知作品");
    
    // 第二层：标签
    setText("#taskPlatform", taskData.platform || "—");
    setText("#taskCategory", taskData.category || "—");
    setText("#taskWordCount", fmtWordCount(taskData.word_count));
    
    // 第三层：辅助信息
    setText("#taskId", taskData.record_id || "—");
    setText("#taskCreated", taskData.created_at || "—");
    setText("#taskStarted", taskData.processing_start || "—");
    
    // 计算耗时
    if (taskData.processing_start && taskData.completed_at) {
      const start = new Date(taskData.processing_start);
      const end = new Date(taskData.completed_at);
      const duration = Math.round((end - start) / 1000);
      setText("#taskDuration", fmtDuration(duration));
      setText("#taskTotalTime", fmtDuration(duration));
    } else if (taskData.processing_start) {
      const start = new Date(taskData.processing_start);
      const now = new Date();
      const elapsed = Math.round((now - start) / 1000);
      setText("#taskDuration", fmtDuration(elapsed) + " (进行中)");
      setText("#taskTotalTime", fmtDuration(elapsed));
    }

    // 进度统计
    const progress = taskData.progress_percent || 0;
    setText("#taskPercent", progress + "%");
    
    const progressBar = $("#taskProgressBar");
    if (progressBar) progressBar.style.width = progress + "%";
    
    // 状态文本
    const statusText = taskData.stage_label || "等待中";
    setText("#taskStatusText", statusText);
    
    // 统计详情
    setText("#taskToken", taskData.token_used ? taskData.token_used.toLocaleString() : "—");
    setText("#taskModel", taskData.model || "GLM-4");
    setText("#taskWordCount2", taskData.note_content ? (taskData.note_content.length || "—") + "字" : "—");
  }

  /* ===== 渲染进度轴 ===== */
  function renderProgress() {
    if (!taskData) return;
    const status = taskData.display_status || taskData.status;
    const steps = ["waiting", "deconstructing", "generating_note", "ai_scoring", "human_review", "generating_image", "done"];
    const currentIdx = steps.indexOf(status);

    $$(".td-step").forEach((step, idx) => {
      step.classList.remove("completed", "active");
      if (idx < currentIdx) {
        step.classList.add("completed");
      } else if (idx === currentIdx) {
        step.classList.add("active");
      }
    });

    // 显示时间信息
    const createdAt = taskData.created_at;
    const processingStart = taskData.processing_start;
    const completedAt = taskData.completed_at;

    if (createdAt) {
      setText("#stepTimeWaiting", formatTime(createdAt));
    }

    if (processingStart) {
      setText("#stepTimeDeconstructing", formatTime(processingStart));
      if (createdAt) {
        const waitSeconds = Math.round((new Date(processingStart) - new Date(createdAt)) / 1000);
        setText("#stepDurationWaiting", "耗时" + fmtDuration(waitSeconds));
      }
    }

    if (completedAt && processingStart) {
      setText("#stepTimeDone", formatTime(completedAt));
      const totalSeconds = Math.round((new Date(completedAt) - new Date(processingStart)) / 1000);
      setText("#stepDurationDone", "总耗时" + fmtDuration(totalSeconds));
    }

    // 当前步骤显示进行中
    if (status === "processing" || status === "deconstructing") {
      const activeStep = $(".td-step.active");
      if (activeStep) {
        const durationEl = activeStep.querySelector(".td-step-duration");
        if (durationEl && processingStart) {
          const elapsed = Math.round((new Date() - new Date(processingStart)) / 1000);
          durationEl.textContent = "已耗时" + fmtDuration(elapsed);
        }
      }
    }
  }

  /* ===== 渲染笔记内容 ===== */
  function renderNote() {
    if (!taskData || !taskData.note_content) {
      const titleInput = $("#noteTitle");
      if (titleInput) titleInput.value = "";
      const contentArea = $("#noteContent");
      if (contentArea) contentArea.value = "";
      const tagsList = $("#tagsList");
      if (tagsList) tagsList.innerHTML = "";
      updateTitleCount();
      updateWordCount();
      return;
    }
    
    const note = taskData.note_content;

    const titleInput = $("#noteTitle");
    if (titleInput) {
      titleInput.value = note.title || "";
      updateTitleCount();
    }

    const contentArea = $("#noteContent");
    if (contentArea) {
      contentArea.value = note.content || "";
      updateWordCount();
    }

    const tagsList = $("#tagsList");
    if (tagsList && note.tags) {
      tagsList.innerHTML = note.tags.map((tag) =>
        '<span class="td-tag">' + esc(tag) + '<span class="td-tag-remove" data-tag="' + esc(tag) + '">×</span></span>'
      ).join("");
    }
  }

  /* ===== 渲染拆文结果 ===== */
  function renderDeconstruct() {
    if (!taskData || !taskData.deconstruct_result) {
      $$(".td-collapse-content").forEach(el => {
        el.innerHTML = '<div style="color:#999; padding:20px; text-align:center;">暂无拆文结果，请先运行拆文任务</div>';
      });
      return;
    }
    const result = taskData.deconstruct_result;

    setCollapseContent("collapseOpenings", result.openings);
    setCollapseContent("collapseCharacters", result.characters);
    setCollapseContent("collapseConflicts", result.conflicts);
    setCollapseContent("collapseEmotions", result.emotions);

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
    const el = $("#" + id);
    if (el && items) {
      el.querySelector(".td-collapse-content").innerHTML =
        "<ul>" + items.map((item) => "<li>" + esc(item) + "</li>").join("") + "</ul>";
    }
  }

  /* ===== 渲染AI评分 ===== */
  function renderScore() {
    if (!taskData || !taskData.note_content || !taskData.note_content.score) {
      setText("#totalScore", "—");
      setText("#scoreTitle", "—");
      setText("#scoreEmotion", "—");
      setText("#scoreCollect", "—");
      setText("#scoreInteraction", "—");
      setText("#scoreStyle", "—");
      setText("#scoreAi", "—");
      const suggestionsList = $("#suggestionsList");
      if (suggestionsList) {
        suggestionsList.innerHTML = '<div style="color:#999; padding:20px; text-align:center;">暂无评分数据</div>';
      }
      return;
    }
    
    const score = taskData.note_content.score;

    setText("#totalScore", score.total || 0);
    setText("#scoreTitle", (score.title_attract || 0) + "/30");
    setText("#scoreEmotion", (score.emotion || 0) + "/20");
    setText("#scoreCollect", (score.collect_value || 0) + "/20");
    setText("#scoreInteraction", (score.interaction || 0) + "/15");
    setText("#scoreStyle", (score.style_match || 0) + "/10");
    setText("#scoreAi", (score.ai_trace || 0) + "/5");

    const ring = $("#scoreRing");
    if (ring) {
      const circumference = 2 * Math.PI * 54;
      const offset = circumference - (score.total / 100) * circumference;
      ring.style.strokeDashoffset = offset;
    }

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

    const suggestionsList = $("#suggestionsList");
    if (suggestionsList && score.suggestions) {
      suggestionsList.innerHTML = score.suggestions.map((s) =>
        '<div class="td-suggestion-item">' + esc(s) + "</div>"
      ).join("");
    }
  }

  /* ===== 渲染修改记录 ===== */
  function renderHistory() {
    const timeline = $("#historyTimeline");
    if (!timeline) return;

    // 示例数据（实际应从 API 获取）
    const history = [
      {
        time: "2026-06-13 10:24",
        user: "运营小明",
        action: "标题修改",
        detail: '<span class="old">重生后我逆袭豪门</span> → <span class="new">重生后我打脸豪门所有人</span>'
      },
      {
        time: "2026-06-13 10:20",
        user: "AI生成",
        action: "笔记生成",
        detail: "生成笔记初稿，共812字"
      },
      {
        time: "2026-06-13 10:18",
        user: "系统",
        action: "拆文完成",
        detail: "拆文分析完成，提取5个开篇套路、3个人物设定"
      }
    ];

    if (history.length === 0) {
      timeline.innerHTML = '<div class="td-history-empty">暂无修改记录</div>';
      return;
    }

    timeline.innerHTML = history.map(item =>
      '<div class="td-history-item">' +
      '<div class="td-history-time">' + esc(item.time) + '</div>' +
      '<div class="td-history-content">' +
      '<div class="td-history-title">' + esc(item.action) + ' · ' + esc(item.user) + '</div>' +
      '<div class="td-history-detail">' + item.detail + '</div>' +
      '</div>' +
      '</div>'
    ).join("");
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
      titleInput.addEventListener("input", updateTitleCount);
    }

    const contentArea = $("#noteContent");
    if (contentArea) {
      contentArea.addEventListener("input", updateWordCount);
    }

    const addTagBtn = $("#addTagBtn");
    if (addTagBtn) {
      addTagBtn.addEventListener("click", () => {
        const tag = prompt("输入标签:");
        if (tag && tag.trim()) {
          const tagsList = $("#tagsList");
          const tagEl = document.createElement("span");
          tagEl.className = "td-tag";
          tagEl.innerHTML = esc(tag.trim()) + '<span class="td-tag-remove" data-tag="' + esc(tag.trim()) + '">×</span>';
          tagsList.appendChild(tagEl);
        }
      });
    }

    document.addEventListener("click", (e) => {
      if (e.target.classList.contains("td-tag-remove")) {
        e.target.parentElement.remove();
      }
    });
  }

  function updateTitleCount() {
    const input = $("#noteTitle");
    const counter = $("#titleCount");
    if (input && counter) {
      counter.textContent = input.value.length;
    }
  }

  function updateWordCount() {
    const textarea = $("#noteContent");
    const counter = $("#wordCount");
    if (textarea && counter) {
      counter.textContent = textarea.value.length;
    }
  }

  /* ===== 操作按钮 ===== */
  function bindActions() {
    bindBtn("#btnSaveDraft", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/save-draft", "草稿已保存");
    });

    bindBtn("#btnApprove", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/approve", "已通过审核");
      loadTaskDetail(taskData.record_id);
    });

    bindBtn("#btnRegenerate", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/regenerate-note", "重新生成中...");
    });
  }

  async function apiCall(url, successMsg) {
    try {
      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" } });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error);
      showToast("success", successMsg || "操作成功");
    } catch (e) {
      showToast("error", "操作失败: " + e.message);
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

  function fmtWordCount(n) {
    if (n == null) return "—";
    if (n >= 10000) return (n / 10000).toFixed(1) + "万字";
    return n + "字";
  }

  function fmtDuration(seconds) {
    if (seconds < 60) return seconds + "秒";
    if (seconds < 3600) return Math.floor(seconds / 60) + "分" + (seconds % 60) + "秒";
    return Math.floor(seconds / 3600) + "时" + Math.floor((seconds % 3600) / 60) + "分";
  }

  function formatTime(timeStr) {
    if (!timeStr) return "—";
    const date = new Date(timeStr);
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
})();
