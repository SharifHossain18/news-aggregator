/* ===== Search & Filter Engine ===== */
const Search = (() => {
  let debounceTimer = null;
  const MAX_HISTORY = 8;

  function onInput(query) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => performSearch(query), 250);
  }

  function performSearch(query) {
    const container = document.getElementById('searchResults');
    const recentBox = document.getElementById('recentSearches');
    query = (query || '').trim();

    if (!query) {
      container.innerHTML = '';
      showRecent();
      return;
    }

    recentBox.style.display = 'none';
    const articles = News.getAll();
    const q = query.toLowerCase();

    const results = articles.filter(a => {
      const text = ((a.title || '') + ' ' + (a.source || '') + ' ' + (a.summary || '')).toLowerCase();
      return text.includes(q);
    });

    // Save to history
    saveToHistory(query);

    if (results.length === 0) {
      container.innerHTML = `
        <div class="card">
          <div class="empty-state">
            <div class="icon">🔍</div>
            <div class="title">No results for "${News.escapeHtml(query)}"</div>
            <div class="desc">Try different keywords like gas, LNG, coal, Petrobangla</div>
          </div>
        </div>`;
      return;
    }

    container.innerHTML = `
      <div class="card">
        <div class="section-title">
          <span>Search Results</span>
          <span style="font-size:11px;color:var(--primary-light)">${results.length} found</span>
        </div>
        ${results.map((n, i) => `
          <div class="news-item">
            <div class="news-index">${i + 1}</div>
            <div class="news-body">
              <a href="${News.escapeHtml(n.link)}" class="news-title" target="_blank" rel="noopener">${highlightMatch(n.title, query)}</a>
              <div class="news-meta">
                <span class="source-badge">${News.escapeHtml(n.source)}</span>
                <span class="time-badge">🕒 ${News.escapeHtml(n.time || 'Today')}</span>
              </div>
              ${n.summary ? `<div class="news-summary">📝 ${highlightMatch(n.summary, query)}</div>` : ''}
            </div>
          </div>
        `).join('')}
      </div>`;
  }

  function highlightMatch(text, query) {
    if (!text || !query) return News.escapeHtml(text);
    const escaped = News.escapeHtml(text);
    const q = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${q})`, 'gi');
    return escaped.replace(regex, '<mark style="background:var(--primary-glow);color:var(--primary-light);padding:1px 3px;border-radius:3px">$1</mark>');
  }

  function saveToHistory(query) {
    let history = getHistory();
    history = history.filter(h => h.toLowerCase() !== query.toLowerCase());
    history.unshift(query);
    history = history.slice(0, MAX_HISTORY);
    localStorage.setItem('pb_search_history', JSON.stringify(history));
  }

  function getHistory() {
    try {
      return JSON.parse(localStorage.getItem('pb_search_history') || '[]');
    } catch { return []; }
  }

  function showRecent() {
    const history = getHistory();
    const recentBox = document.getElementById('recentSearches');
    const recentList = document.getElementById('recentList');

    if (history.length === 0) {
      recentBox.style.display = 'none';
      // Show suggestions instead
      document.getElementById('searchResults').innerHTML = `
        <div class="card">
          <div class="section-title"><span>Quick Search Topics</span></div>
          <div class="filter-chips" style="flex-wrap:wrap">
            ${['Gas', 'LNG', 'Coal', 'Rock', 'Petrobangla', 'BAPEX', 'Titas', 'Pipeline', 'Barapukuria', 'Maddhapara', 'Energy', 'Mining'].map(t =>
              `<button class="chip" onclick="document.getElementById('searchInput').value='${t}';Search.onInput('${t}')">${t}</button>`
            ).join('')}
          </div>
        </div>`;
      return;
    }

    recentBox.style.display = 'block';
    recentList.innerHTML = history.map(h => `
      <div class="source-item" style="cursor:pointer" onclick="document.getElementById('searchInput').value='${News.escapeHtml(h)}';Search.onInput('${News.escapeHtml(h)}')">
        <span style="font-size:14px">🕑 ${News.escapeHtml(h)}</span>
      </div>
    `).join('');
  }

  function clearHistory() {
    localStorage.removeItem('pb_search_history');
    showRecent();
    App.showToast('Search history cleared');
  }

  return { onInput, performSearch, showRecent, clearHistory };
})();
