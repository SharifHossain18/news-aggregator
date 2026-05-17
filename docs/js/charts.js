/* ===== Analytics Charts ===== */
const Charts = (() => {

  function renderSourceChart(stats) {
    const container = document.getElementById('sourceChart');
    if (!stats || Object.keys(stats).length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="desc">No source data available</div></div>';
      return;
    }

    // Build sorted list (exclude _meta)
    const sources = Object.entries(stats)
      .filter(([k]) => k !== '_meta')
      .map(([name, s]) => ({ name, articles: s.articles || 0 }))
      .sort((a, b) => b.articles - a.articles)
      .slice(0, 12);

    const maxVal = Math.max(...sources.map(s => s.articles), 1);

    container.innerHTML = sources.map(s => `
      <div class="chart-bar-item">
        <div class="chart-bar-label" title="${News.escapeHtml(s.name)}">${News.escapeHtml(s.name)}</div>
        <div class="chart-bar-track">
          <div class="chart-bar-fill" style="width:${(s.articles / maxVal * 100).toFixed(1)}%"></div>
        </div>
        <div class="chart-bar-value">${s.articles}</div>
      </div>
    `).join('');
  }

  function renderTopicChart(articles) {
    const container = document.getElementById('topicChart');
    if (!articles || articles.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="desc">No article data available</div></div>';
      return;
    }

    const topics = [
      { key: 'gas', label: '⛽ Gas', color: '#10b981' },
      { key: 'lng', label: '🚢 LNG', color: '#3b82f6' },
      { key: 'coal', label: '⚫ Coal', color: '#6b7280' },
      { key: 'rock', label: '🪨 Rock/Mining', color: '#f59e0b' },
      { key: 'petrobangla', label: '🏢 Petrobangla', color: '#8b5cf6' },
      { key: 'titas', label: '🔥 Titas/Distribution', color: '#ef4444' },
      { key: 'bapex', label: '🛢️ BAPEX/Exploration', color: '#14b8a6' }
    ];

    const counts = topics.map(t => ({
      ...t,
      count: articles.filter(a => News.matchesTopic(a, t.key)).length
    })).sort((a, b) => b.count - a.count);

    const maxVal = Math.max(...counts.map(c => c.count), 1);

    container.innerHTML = counts.map(t => `
      <div class="chart-bar-item">
        <div class="chart-bar-label">${t.label}</div>
        <div class="chart-bar-track">
          <div class="chart-bar-fill" style="width:${(t.count / maxVal * 100).toFixed(1)}%;background:${t.color}"></div>
        </div>
        <div class="chart-bar-value">${t.count}</div>
      </div>
    `).join('');
  }

  function renderStats(articles, stats) {
    const totalArticles = articles ? articles.length : 0;
    document.getElementById('totalArticles').textContent = totalArticles;

    if (stats && typeof stats === 'object') {
      const sourceEntries = Object.entries(stats).filter(([k]) => k !== '_meta');
      const totalSources = sourceEntries.length;
      const healthy = sourceEntries.filter(([, s]) => (s.last_fail_streak || 0) < 3).length;
      const failed = totalSources - healthy;

      document.getElementById('totalSources').textContent = totalSources;
      document.getElementById('healthyCount').textContent = healthy;
      document.getElementById('failedCount').textContent = failed;
    }
  }

  return { renderSourceChart, renderTopicChart, renderStats };
})();
