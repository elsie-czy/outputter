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
    } catch (e) {
      showToast("error", "加载失败: " + e.message);
    }
  }

  /* ===== 渲染任务信息 ===== */
  function renderTaskInfo() {
    if (!taskData) return;
    setText("#taskTitle", taskData.work_name || "未知作品");
    setText("#taskPlatform", taskData.platform || "—");
    setText("#taskCategory", taskData.category || "—");
    setText("#taskWordCount", fmtWordCount(taskData.word_count));
    setText("#taskCreated", taskData.created_at || "—");

    // 计算耗时
    if (taskData.processing_start && taskData.completed_at) {
      const start = new Date(taskData.processing_start);
      const end = new Date(taskData.completed_at);
      const duration = Math.round((end - start) / 1000 / 60);
      setText("#taskDuration", duration + "分钟");
    } else if (taskData.processing_start) {
      setText("#taskDuration", "进行中...");
    }

    // 状态标签
    const statusBadge = $("#taskStatus");
    if (statusBadge) {
      const status = taskData.display_status || taskData.status;
      statusBadge.textContent = taskData.stage_label || status;
      statusBadge.className = "td-status-badge";
      if (["deconstructing", "generating_note", "ai_scoring", "human_review", "generating_image"].includes(status)) {
        statusBadge.classList.add("td-status-badge--running");
      } else if (status === "done") {
        statusBadge.classList.add("td-status-badge--success");
      } else if (status === "failed") {
        statusBadge.classList.add("td-status-badge--failed");
      } else {
        statusBadge.classList.add("td-status-badge--waiting");
      }
    }
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
  }

  /* ===== 渲染笔记内容 ===== */
  function renderNote() {
    if (!taskData || !taskData.note_content) {
      // 没有笔记内容
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

    // 标签
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
      // 没有拆文结果
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
    const el = $("#" + id);
    if (el && items) {
      el.querySelector(".td-collapse-content").innerHTML =
        "<ul>" + items.map((item) => "<li>" + esc(item) + "</li>").join("") + "</ul>";
    }
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
    const suggestionsList = $("#suggestionsList");
    if (suggestionsList && score.suggestions) {
      suggestionsList.innerHTML = score.suggestions.map((s) =>
        '<div class="td-suggestion-item">' + esc(s) + "</div>"
      ).join("");
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
      titleInput.addEventListener("input", updateTitleCount);
    }

    const contentArea = $("#noteContent");
    if (contentArea) {
      contentArea.addEventListener("input", updateWordCount);
    }

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
          tagsList.appendChild(tagEl);
        }
      });
    }

    // 删除标签
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
    // 保存草稿
    bindBtn("#btnSaveDraft", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/save-draft", "草稿已保存");
    });

    // 通过审核
    bindBtn("#btnApprove", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/approve", "已通过审核");
      loadTaskDetail(taskData.record_id);
    });

    // 重新生成
    bindBtn("#btnRegenerate", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/regenerate-note", "重新生成中...");
    });

    // 重新生成笔记
    bindBtn("#btnRegenerateNote", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/regenerate-note", "重新生成中...");
    });

    // 重新评分
    bindBtn("#btnRescore", async () => {
      await apiCall("/api/task/" + taskData.record_id + "/rescore", "重新评分中...");
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
})();
