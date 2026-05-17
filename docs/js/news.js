/* ===== News Feed Engine ===== */
const News = (() => {
  let allArticles = [];
  let filteredArticles = [];
  let currentFilter = 'all';
  let showAISummaries = true;
  let editMode = false;

  // Topic keywords for filtering
  const TOPICS = {
    gas: ['gas', 'গ্যাস', 'গ্যাসের', 'গ্যাসহীন', 'গ্যাস সংকট', 'gas field', 'gasfield', 'gas well', 'গ্যাস কূপ'],
    lng: ['lng', 'এলএনজি', 'liquefied natural gas', 'cargo', 'spot lng'],
    coal: ['coal', 'কয়লা', 'কয়লা খনি', 'coal mine', 'barapukuria', 'বড়পুকুরিয়া'],
    rock: ['rock', 'পাথর', 'পাথর খনি', 'maddhapara', 'মধ্যপাড়া', 'mining', 'খনি', 'extraction', 'উত্তোলন'],
    petrobangla: ['petrobangla', 'পেট্রোবাংলা', 'bgfcl', 'sgfl', 'gtcl', 'rpgcl', 'bcmcl', 'mgmcl', 'জিটিসিএল', 'আরপিজিসিএল'],
    titas: ['titas', 'তিতাস', 'bakhrabad', 'বাখরাবাদ', 'jalalabad', 'জালালাবাদ', 'pashchimanchal'],
    bapex: ['bapex', 'বাপেক্স', 'drilling', 'কূপ খনন', 'well drilling', 'exploration']
  };

  // Priority/breaking keywords
  const BREAKING_KEYWORDS = [
    'explosion', 'blast', 'fire', 'emergency', 'crisis', 'accident', 'death', 'killed',
    'বিস্ফোরণ', 'আগুন', 'জরুরি', 'সংকট', 'দুর্ঘটনা', 'মৃত্যু', 'হতাহত', 'দগ্ধ'
  ];

  // Default & fallback data URL
  function getDataUrl() {
    const saved = localStorage.getItem('pb_data_url');
    if (saved) return saved;
    // Try relative path first (for local/GitHub Pages serving)
    return './news_data.json';
  }

  function getStatsUrl() {
    const dataUrl = getDataUrl();
    return dataUrl.replace('news_data.json', 'source_stats.json');
  }

  async function fetchNews() {
    try {
      const url = getDataUrl();
      const res = await fetch(url + '?t=' + Date.now());
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      allArticles = data || [];
      editMode = false;
      // Cache for offline
      localStorage.setItem('pb_news_cache', JSON.stringify(allArticles));
      localStorage.setItem('pb_news_cache_time', Date.now().toString());
      return allArticles;
    } catch (e) {
      console.warn('Fetch failed, using cache:', e);
      const cached = localStorage.getItem('pb_news_cache');
      if (cached) {
        allArticles = JSON.parse(cached);
        return allArticles;
      }
      return [];
    }
  }

  async function fetchStats() {
    try {
      const url = getStatsUrl();
      const res = await fetch(url + '?t=' + Date.now());
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      localStorage.setItem('pb_stats_cache', JSON.stringify(data));
      return data;
    } catch (e) {
      const cached = localStorage.getItem('pb_stats_cache');
      return cached ? JSON.parse(cached) : {};
    }
  }

  function isBreaking(article) {
    const text = (article.title || '').toLowerCase();
    return BREAKING_KEYWORDS.some(kw => text.includes(kw.toLowerCase()));
  }

  function matchesTopic(article, topic) {
    if (topic === 'all') return true;
    const keywords = TOPICS[topic] || [];
    const text = ((article.title || '') + ' ' + (article.summary || '')).toLowerCase();
    return keywords.some(kw => text.includes(kw.toLowerCase()));
  }

  function filter(topic) {
    currentFilter = topic;
    // Update chip UI
    document.querySelectorAll('.chip').forEach(c => {
      c.classList.toggle('active', c.dataset.filter === topic);
    });
    filteredArticles = topic === 'all' ? [...allArticles] : allArticles.filter(a => matchesTopic(a, topic));
    render(filteredArticles);
  }

  function render(articles) {
    const container = document.getElementById('newsList');
    const countEl = document.getElementById('newsCount');

    if (!articles || articles.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="icon">📭</div>
          <div class="title">No news found</div>
          <div class="desc">Tap Scan Now to fetch fresh articles</div>
        </div>`;
      countEl.textContent = '0 articles';
      return;
    }

    countEl.textContent = `${articles.length} article${articles.length !== 1 ? 's' : ''}`;

    const toolbarHtml = `
      <div class="news-toolbar">
        <button class="edit-toggle ${editMode ? 'active' : ''}" onclick="News.toggleEdit()">
          ${editMode ? '✅ Done' : '✏\ufe0f Edit'}
        </button>
        <button class="clear-all-btn ${editMode ? 'visible' : ''}" onclick="News.clearAll()">
          \ud83d\uddd1\ufe0f Clear All
        </button>
      </div>`;

    container.innerHTML = toolbarHtml + articles.map((n, i) => `
      <div class="news-item" id="news-${i}">
        <div class="news-index">${i + 1}</div>
        <div class="news-body">
          <a href="${escapeHtml(n.link)}" class="news-title" target="_blank" rel="noopener">${escapeHtml(n.title)}</a>
          <div class="news-meta">
            <span class="source-badge">${escapeHtml(n.source)}</span>
            <span class="time-badge">\ud83d\udd52 ${escapeHtml(n.time || 'Today')}</span>
          </div>
          ${(showAISummaries && n.summary) ? `<div class="news-summary">\ud83d\udcdd ${escapeHtml(n.summary)}</div>` : ''}
        </div>
        ${editMode ? `<div class="news-actions"><button class="news-delete-btn" onclick="News.deleteArticle(${i})" title="Delete">\u2716</button></div>` : ''}
      </div>
    `).join('');
  }

  function toggleEdit() {
    editMode = !editMode;
    filter(currentFilter);
  }

  function deleteArticle(index) {
    const visible = currentFilter === 'all' ? allArticles : allArticles.filter(a => matchesTopic(a, currentFilter));
    const article = visible[index];
    if (!article) return;

    // Animate out
    const el = document.getElementById('news-' + index);
    if (el) el.classList.add('deleting');

    setTimeout(() => {
      // Permanently remove from array
      allArticles = allArticles.filter(a => a.link !== article.link);
      // Update cache
      localStorage.setItem('pb_news_cache', JSON.stringify(allArticles));
      filter(currentFilter);
      if (typeof App !== 'undefined') App.showToast('Article deleted');
    }, 300);
  }

  function clearAll() {
    if (!confirm('Permanently delete all visible articles?')) return;
    if (currentFilter === 'all') {
      allArticles = [];
    } else {
      allArticles = allArticles.filter(a => !matchesTopic(a, currentFilter));
    }
    localStorage.setItem('pb_news_cache', JSON.stringify(allArticles));
    editMode = false;
    filter(currentFilter);
    if (typeof App !== 'undefined') App.showToast('All articles deleted');
  }

  function renderBreaking() {
    const container = document.getElementById('breakingNews');
    const breaking = allArticles.filter(a => isBreaking(a));
    if (breaking.length === 0) {
      container.style.display = 'none';
      return;
    }
    const first = breaking[0];
    container.style.display = 'block';
    container.innerHTML = `
      <div class="breaking-banner" onclick="window.open('${escapeHtml(first.link)}','_blank')">
        <span class="icon">🚨</span>
        <span class="text">${escapeHtml(first.title)}</span>
      </div>`;
  }

  function renderScanStatus(stats) {
    const box = document.getElementById('scanStatus');
    const meta = stats._meta;
    if (!meta) { box.style.display = 'none'; return; }
    box.style.display = 'flex';
    document.getElementById('scanDuration').textContent = meta.duration || '--';
    document.getElementById('scanHealth').textContent = `${meta.successful_sources || 0} OK / ${meta.failed_sources || 0} Fail`;
  }

  function setShowSummaries(val) {
    showAISummaries = val;
    filter(currentFilter);
  }

  function getAll() { return allArticles; }
  function getFiltered() { return filteredArticles; }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  return { fetchNews, fetchStats, filter, render, renderBreaking, renderScanStatus, isBreaking, matchesTopic, setShowSummaries, toggleEdit, deleteArticle, clearAll, getAll, getFiltered, getDataUrl, getStatsUrl, TOPICS, escapeHtml };
})();
