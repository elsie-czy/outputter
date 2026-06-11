window.Batch = {
  init() {
    document.querySelectorAll('#batchBar .dc-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const ids = Queue.getSelectedIds();
        if (!ids.length) return alert('请先选择任务');
        const action = btn.dataset.action;
        if (action === 'start') await this.start(ids);
        else if (action === 'complete') await this.complete(ids);
        else if (action === 'generate') await this.generate(ids);
        else if (action === 'image') await this.imageGen(ids);
      });
    });
  },

  updateCount(n) {
    const el = document.getElementById('batchCount');
    el.style.display = n > 0 ? 'inline' : 'none';
    el.textContent = `已选${n}项`;
  },

  async start(ids) {
    const res = await fetch('/api/deconstruct/batch-start', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({record_ids: ids})
    });
    const j = await res.json();
    if (j.ok) Queue.fetch();
    else alert('操作失败: ' + (j.error || ''));
  },

  async complete(ids) {
    if (!confirm(`确认标记 ${ids.length} 个任务为完成？`)) return;
    const res = await fetch('/api/deconstruct/batch-complete', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({record_ids: ids})
    });
    const j = await res.json();
    if (j.ok) Queue.fetch();
    else alert('操作失败');
  },

  async generate(ids) {
    const res = await fetch('/api/note/batch-generate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({record_ids: ids})
    });
    const j = await res.json();
    if (j.ok) alert(`已获取 ${j.data.generated} 篇笔记`);
    else alert('操作失败');
  },

  async imageGen(ids) {
    const res = await fetch('/api/image/batch-generate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({record_ids: ids})
    });
    const j = await res.json();
    alert(j.ok ? `已入队 ${j.data.enqueued} 个图片任务` : '操作失败');
  }
};
