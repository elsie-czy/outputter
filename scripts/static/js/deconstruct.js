window.Deconstruct = {
  async load(rid) {
    const body = document.getElementById('mainBody');
    body.innerHTML = '<div class="dc-empty">加载中...</div>';

    try {
      const res = await fetch(`/api/deconstruct/${rid}/result`);
      const json = await res.json();
      if (!json.ok) { body.innerHTML = `<div class="dc-empty">任务未找到</div>`; return; }

      const item = json.data;
      const r = item.deconstruct_result;
      if (!r || r['缓存']) {
        body.innerHTML = `<div class="dc-empty"><div style="font-size:32px">💾</div><div>缓存命中，从飞书主表复用</div></div>`;
        return;
      }

      const sections = [
        { title: '开篇套路', key: '开篇套路', items: r['开篇套路'] || [] },
        { title: '人物设定', key: '人物设定', items: null, obj: r['人物设定'] },
        { title: '冲突设计', key: '冲突设计', items: null, obj: r['冲突设计'] },
        { title: '情绪触发', key: '情绪触发', items: r['情绪触发'] || [] },
        { title: '金句', key: '金句', items: r['金句'] || [] },
      ];

      let html = '';
      for (const sec of sections) {
        html += `<div class="dc-section">
          <div class="dc-section-head" data-section="${sec.key}">
            <span>${sec.title}</span><span class="text-muted">▼</span>
          </div>
          <div class="dc-section-body">`;
        if (sec.obj) {
          for (const [k, v] of Object.entries(sec.obj)) {
            html += `<div style="margin-bottom:4px"><strong>${k}:</strong> ${this.esc(v)}</div>`;
          }
        } else if (sec.items) {
          html += '<ol>' + sec.items.map(i => `<li>${this.esc(i)}</li>`).join('') + '</ol>';
        }
        html += '</div></div>';
      }
      body.innerHTML = html;

      body.querySelectorAll('.dc-section-head').forEach(h => {
        h.addEventListener('click', () => {
          const b = h.nextElementSibling;
          const open = b.classList.toggle('open');
          h.querySelector('span:last-child').textContent = open ? '▲' : '▼';
        });
      });

      // Load assets
      this.loadAssets(rid);
    } catch (e) {
      body.innerHTML = `<div class="dc-empty">加载失败: ${e.message}</div>`;
    }
  },

  async loadAssets(rid) {
    try {
      const res = await fetch(`/api/deconstruct/${rid}/assets`);
      const json = await res.json();
      if (!json.ok) return;
      const d = json.data;
      const s = `图片: ${d.image_status.done}/${d.image_status.total || 0} | 视频: ${d.video_status}`;
      document.getElementById('statsBar').innerHTML += `<span class="text-muted" style="margin-left:12px">${s}</span>`;
    } catch (e) {}
  },

  esc(s) {
    if (!s) return '';
    const div = document.createElement('div');
    div.textContent = String(s);
    return div.innerHTML;
  }
};
