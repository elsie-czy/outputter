window.StatusBadge = {
  labels: { pending: '排队中', processing: '处理中', done: '已完成', failed: '失败', retry: '重试中' },
  render(status) {
    const label = this.labels[status] || status;
    return `<span class="status-badge status-${status}"><span class="status-dot"></span>${label}</span>`;
  }
};
