window.Queue = {
  items: [],
  selectedIds: new Set(),
  currentRid: null,
  interval: null,
  statusFilter: null,

  init() {
    document.getElementById('filterSearch').addEventListener('input', (e) => {
      this.render(this.filterItems(this.items, e.target.value));
    });
    this.buildFilterChips();
    this.fetch();
    this.interval = setInterval(() => this.fetch(), 8000);
  },

  destroy() { clearInterval(this.interval); },

  buildFilterChips() {
    const chips = document.getElementById('filterChips');
    const statuses = [
      { key: 'pending', label: '排队中' },
      { key: 'processing', label: '处理中' },
      { key: 'done', label: '已完成' },
      { key: 'failed', label: '失败' },
    ];
    chips.innerHTML = statuses.map(s =>
      `<span class="dc-chip" data-status="${s.key}">${s.label}</span>`
    ).join('');
    chips.querySelectorAll('.dc-chip').forEach(c => {
      c.addEventListener('click', () => {
        if (c.classList.contains('active')) {
          c.classList.remove('active');
          this.statusFilter = null;
        } else {
          chips.querySelectorAll('.dc-chip').forEach(x => x.classList.remove('active'));
          c.classList.add('active');
          this.statusFilter = c.dataset.status;
        }
        this.render(this.filterItems(this.items, document.getElementById('filterSearch').value));
      });
    });
  },

  async fetch() {
    try {
      const res = await fetch('/api/deconstruct/queue?per_page=100');
      const json = await res.json();
      if (!json.ok) return;
      this.items = json.data.items.reverse();
      this.render(this.filterItems(this.items, document.getElementById('filterSearch').value));
      document.getElementById('queueBadge').textContent = `${json.data.total}`;
    } catch (e) {
      console.error('queue fetch error', e);
    }
  },

  filterItems(items, q) {
    let filtered = items;
    if (this.statusFilter) {
      filtered = filtered.filter(i => i.status === this.statusFilter);
    }
    if (q) {
      const lower = q.toLowerCase();
      filtered = filtered.filter(i => 
        (i.work_name||'').toLowerCase().includes(lower) ||
        (i.author||'').toLowerCase().includes(lower)
      );
    }
    return filtered;
  },

  render(items) {
    const el = document.getElementById('queueList');
    if (!items.length) {
      el.innerHTML = '<div class="dc-empty">暂无任务</div>';
      return;
    }
    el.innerHTML = items.map(item => {
      const sel = this.selectedIds.has(item.record_id) ? ' selected' : '';
      const badge = window.StatusBadge ? StatusBadge.render(item.status) : `<span class="status-badge status-${item.status}"><span class="status-dot"></span>${item.status}</span>`;
      return `<div class="dc-queue-item${sel}" data-rid="${item.record_id}">
        <input type="checkbox" class="qi-check" ${sel ? 'checked' : ''} style="accent-color:var(--color-blue)" />
        ${badge}
        <div class="qi-info">
          <div class="qi-name">${this.esc(item.work_name)}</div>
          <div class="qi-sub">${this.esc(item.author)} · ${this.esc(item.platform)} ${this.esc(item.category)}</div>
        </div>
        ${item.quality_score ? `<span style="font-size:12px;color:var(--color-blue);font-weight:600">${item.quality_score}分</span>` : ''}
      </div>`;
    }).join('');

    el.querySelectorAll('.dc-queue-item').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.tagName === 'INPUT') return;
        const rid = el.dataset.rid;
        this.selectTask(rid);
      });
    });
    el.querySelectorAll('.qi-check').forEach(cb => {
      cb.addEventListener('click', (e) => {
        e.stopPropagation();
        const rid = cb.closest('.dc-queue-item').dataset.rid;
        this.toggleSelect(rid);
      });
    });
  },

  toggleSelect(rid) {
    if (this.selectedIds.has(rid)) this.selectedIds.delete(rid);
    else this.selectedIds.add(rid);
    this.render(this.filterItems(this.items, document.getElementById('filterSearch').value));
    Batch.updateCount(this.selectedIds.size);
  },

  selectTask(rid) {
    this.currentRid = rid;
    this.render(this.filterItems(this.items, document.getElementById('filterSearch').value));
    // 加载详情
    Deconstruct.load(rid);
    Note.load(rid);
  },

  getSelectedIds() { return [...this.selectedIds]; },

  esc(s) {
    const div = document.createElement('div');
    div.textContent = s || '';
    return div.innerHTML;
  }
};
