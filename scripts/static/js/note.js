window.Note = {
  async load(rid) {
    const body = document.getElementById('rightPanel').querySelector('.dc-panel-body');
    body.innerHTML = '<div class="dc-empty">加载中...</div>';

    try {
      const res = await fetch(`/api/note/${rid}`);
      const json = await res.json();
      if (!json.ok) { body.innerHTML = `<div class="dc-empty">笔记数据未找到</div>`; return; }

      const d = json.data;
      const note = d.note_content || '';
      const score = d.quality_score;

      let html = '';
      // Score
      if (score) {
        html += this._renderScore(score);
      }

      // Note content
      html += `<div class="dc-r-section">
        <h3>笔记内容</h3>
        <div class="dc-note-field">
          <label>标题</label>
          <input type="text" id="noteTitle" value="${this._extractTitle(note)}" />
        </div>
        <div class="dc-note-field">
          <label>正文</label>
          <textarea id="noteBody" rows="8">${this.esc(this._extractBody(note))}</textarea>
        </div>
        <div class="dc-note-field">
          <label>标签</label>
          <input type="text" id="noteTags" value="${this._extractTags(note)}" />
        </div>
        <div class="dc-note-actions">
          <button class="dc-btn primary" onclick="Note.save('${rid}')">保存修改</button>
          <button class="dc-btn" onclick="Note.regen('${rid}')">重新生成</button>
          <button class="dc-btn" onclick="Note.copy()">复制全文</button>
        </div>
      </div>`;

      // Reference notes
      html += `<div class="dc-r-section">
        <h3>参考笔记</h3>
        <div id="refNotes"><span class="text-muted" style="font-size:12px">加载中...</span></div>
        <button class="dc-btn" onclick="Note.regenWithRef('${rid}')" style="margin-top:8px">以选中参考重新生成</button>
      </div>`;

      body.innerHTML = html;
      this._loadRefNotes();
    } catch (e) {
      body.innerHTML = `<div class="dc-empty">加载失败: ${e.message}</div>`;
    }
  },

  _renderScore(score) {
    if (typeof score === 'object') return this._renderScoreObj(score);
    return `<div class="dc-r-section"><div class="dc-score-header"><div class="dc-score-total" style="color:var(--color-blue)">${score}分</div></div></div>`;
  },

  _renderScoreObj(s) {
    const grade = s.grade || (s.total >= 85 ? 'good' : s.total >= 75 ? 'review' : 'retry');
    return `<div class="dc-r-section">
      <div class="dc-score-header">
        <div class="dc-score-total ${grade}">${s.total || 0}</div>
        <div class="text-muted" style="font-size:11px">${s.suggestion || ''}</div>
      </div>
      ${this._scoreBar('标题吸引力', s.title_appeal || 0, 20)}
      ${this._scoreBar('情绪浓度', s.emotion_density || 0, 20)}
      ${this._scoreBar('收藏价值', s.collection_value || 0, 20)}
      ${this._scoreBar('互动引导', s.interaction_guide || 0, 15)}
      ${this._scoreBar('风格匹配', s.xhs_style_match || 0, 15)}
      ${this._scoreBar('AI痕迹(低=好)', s.ai_trace || 0, 10)}
      <button class="dc-btn" onclick="Note.rescore('${this._currentRid}')" style="margin-top:8px;width:100%">重新评分</button>
    </div>`;
  },

  _scoreBar(label, score, max) {
    const pct = max > 0 ? Math.round(score / max * 100) : 0;
    const grade = pct >= 85 ? 'high' : pct >= 75 ? 'medium' : 'low';
    return `<div class="score-row" style="margin-bottom:2px">
      <span class="score-label" style="width:80px;font-size:11px">${label}</span>
      <div class="score-track"><div class="score-fill ${grade}" style="width:${pct}%"></div></div>
      <span class="score-value" style="width:40px;font-size:11px">${score}</span>
    </div>`;
  },

  async _loadRefNotes() {
    try {
      const res = await fetch('/api/reference/top-notes');
      const json = await res.json();
      if (!json.ok) return;
      const notes = json.data.notes || [];
      const el = document.getElementById('refNotes');
      el.innerHTML = notes.map((n, i) => `
        <div class="dc-ref-item">
          <input type="checkbox" value="${i}" style="accent-color:var(--color-blue)" />
          <span>#${i+1} 👍${n['点赞']} ⭐${n['收藏']} ${this.esc(n['标题'])}</span>
        </div>
      `).join('') || '<span class="text-muted" style="font-size:12px">暂无历史数据</span>';
    } catch (e) {}
  },

  async save(rid) {
    const title = document.getElementById('noteTitle').value;
    const body = document.getElementById('noteBody').value;
    const tags = document.getElementById('noteTags').value;
    try {
      const res = await fetch(`/api/note/${rid}/save`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ title, body, tags, diff_log: '人工修改' })
      });
      const j = await res.json();
      alert(j.ok ? '保存成功' : '保存失败: ' + (j.error || ''));
    } catch (e) { alert('保存失败: ' + e.message); }
  },

  async regen(rid) {
    if (!confirm('将重新调用模型生成笔记，确认？')) return;
    try {
      const res = await fetch(`/api/note/${rid}/regenerate`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ fields: ['title','body','tags','cta'] })
      });
      const j = await res.json();
      if (j.ok) Note.load(rid);
      else alert('生成失败: ' + (j.error || ''));
    } catch (e) { alert('生成失败: ' + e.message); }
  },

  async regenWithRef(rid) {
    const checked = [...document.querySelectorAll('#refNotes input:checked')].map(c => c.value);
    if (!confirm('将以选中的参考笔记为风格重新生成？')) return;
    try {
      const res = await fetch(`/api/note/${rid}/regenerate`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ fields: ['title','body','tags','cta'], reference_ids: checked })
      });
      const j = await res.json();
      if (j.ok) Note.load(rid);
      else alert('生成失败');
    } catch (e) { alert('生成失败: ' + e.message); }
  },

  async rescore(rid) {
    try {
      const res = await fetch(`/api/note/${rid}/score`, { method: 'POST' });
      const j = await res.json();
      if (j.ok) Note.load(rid);
      else alert('评分失败');
    } catch (e) { alert('评分失败: ' + e.message); }
  },

  copy() {
    const el = document.getElementById('noteBody');
    if (el) { navigator.clipboard.writeText(el.value); alert('已复制'); }
  },

  _extractTitle(note) {
    const m = note.match(/标题[：:]\s*(.+)/);
    return m ? m[1] : '';
  },
  _extractBody(note) { return note || ''; },
  _extractTags(note) {
    const m = note.match(/(#\S+)/g);
    return m ? m.join(' ') : '';
  },

  esc(s) {
    if (!s) return '';
    const div = document.createElement('div');
    div.textContent = String(s);
    return div.innerHTML;
  }
};
