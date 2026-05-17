/* ===== Search & Filter Engine ===== */
const Search = (() => {
  let debounceTimer = null;
  let searchMode = 'local'; // 'local' or 'web'
  const MAX_HISTORY = 8;

  // BD newspaper domains for Google News search
  const BD_SITES = [
    'prothomalo.com', 'thedailystar.net', 'bdnews24.com', 'banglatribune.com',
    'samakal.com', 'jugantor.com', 'kalerkantho.com', 'dailynayadiganta.com',
    'ittefaq.com.bd', 'amadershomoy.com', 'manobkantha.com.bd', 'jaijaidinbd.com',
    'bssnews.net', 'unb.com.bd', 'dhakatribune.com', 'newagebd.net',
    'tbsnews.net', 'businesspostbd.com', 'thefinancialexpress.com.bd', 'en.prothomalo.com'
  ];

  function setMode(mode) {
    searchMode = mode;
    document.getElementById('modeLocal').classList.toggle('active', mode === 'local');
    document.getElementById('modeWeb').classList.toggle('active', mode === 'web');
    document.getElementById('webSearchHint').style.display = mode === 'web' ? 'block' : 'none';
    document.getElementById('webSearchBtn').style.display = mode === 'web' ? 'block' : 'none';
    document.getElementById('searchInput').placeholder = mode === 'web'
      ? 'Search any topic — sports, politics, culture...'
      : 'Search in saved news...';
    // Re-run search
    const q = document.getElementById('searchInput').value.trim();
    if (q) {
      if (mode === 'local') performSearch(q);
      else document.getElementById('searchResults').innerHTML = '';
    }
  }

  function onInput(query) {
    clearTimeout(debounceTimer);
    if (searchMode === 'local') {
      debounceTimer = setTimeout(() => performSearch(query), 250);
    }
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

    saveToHistory(query);

    if (results.length === 0) {
      container.innerHTML = `
        <div class="card">
          <div class="empty-state">
            <div class="icon">🔍</div>
            <div class="title">No results for "${News.escapeHtml(query)}"</div>
            <div class="desc">Try <b>Web Search</b> to search across all newspapers</div>
          </div>
        </div>`;
      return;
    }

    container.innerHTML = `
      <div class="card">
        <div class="section-title">
          <span>Results in Saved News</span>
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

  async function webSearch() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) {
      App.showToast('Type something to search');
      return;
    }

    // Switch to web mode if not already
    if (searchMode !== 'web') setMode('web');

    saveToHistory(query);
    const container = document.getElementById('searchResults');

    // Show loading
    container.innerHTML = `
      <div class="card">
        <div style="text-align:center;padding:30px">
          <div style="font-size:32px;animation:pulse 1.5s infinite">🌐</div>
          <div style="margin-top:12px;font-size:14px;font-weight:600">Searching newspapers...</div>
          <div style="margin-top:4px;font-size:11px;color:var(--ink-muted)">Scanning 40+ sources for "${News.escapeHtml(query)}"</div>
        </div>
      </div>`;

    try {
      const results = await fetchGoogleNews(query);

      if (results.length === 0) {
        container.innerHTML = `
          <div class="card">
            <div class="empty-state">
              <div class="icon">🔍</div>
              <div class="title">No web results for "${News.escapeHtml(query)}"</div>
              <div class="desc">Try different keywords or check spelling</div>
            </div>
          </div>`;
        return;
      }

      container.innerHTML = `
        <div class="card">
          <div class="section-title">
            <span>🌐 Web Results</span>
            <span style="font-size:11px;color:var(--primary-light)">${results.length} found</span>
          </div>
          ${results.map((n, i) => `
            <div class="news-item">
              <div class="news-index">${i + 1}</div>
              <div class="news-body">
                <a href="${News.escapeHtml(n.link)}" class="news-title" target="_blank" rel="noopener">${highlightMatch(n.title, query)}</a>
                <div class="news-meta">
                  <span class="source-badge">${News.escapeHtml(n.source)}</span>
                  <span class="time-badge">🕒 ${News.escapeHtml(n.time)}</span>
                </div>
                ${n.description ? `<div class="news-summary">📝 ${News.escapeHtml(n.description)}</div>` : ''}
              </div>
            </div>
          `).join('')}
        </div>`;

    } catch (err) {
      console.error('Web search error:', err);
      container.innerHTML = `
        <div class="card">
          <div class="empty-state">
            <div class="icon">⚠️</div>
            <div class="title">Search failed</div>
            <div class="desc">${News.escapeHtml(err.message || 'Network error. Try again.')}</div>
          </div>
        </div>`;
    }
  }

  async function fetchGoogleNews(query) {
    // Build Google News RSS search URL
    const encodedQuery = encodeURIComponent(query + ' Bangladesh');
    const rssUrl = `https://news.google.com/rss/search?q=${encodedQuery}&hl=en-BD&gl=BD&ceid=BD:en`;

    // Try multiple CORS proxies
    const proxies = [
      `https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(rssUrl)}&count=30`,
      `https://api.allorigins.win/raw?url=${encodeURIComponent(rssUrl)}`
    ];

    // Try rss2json first (returns clean JSON)
    try {
      const res = await fetch(proxies[0]);
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'ok' && data.items) {
          return data.items.map(item => ({
            title: stripHtml(item.title),
            link: item.link,
            source: extractSource(item.title) || item.author || 'Google News',
            time: formatDate(item.pubDate),
            description: stripHtml(item.description || '').substring(0, 200)
          }));
        }
      }
    } catch (e) {
      console.warn('rss2json failed:', e);
    }

    // Fallback: allorigins proxy + manual XML parsing
    try {
      const res = await fetch(proxies[1]);
      if (res.ok) {
        const text = await res.text();
        return parseRssXml(text, query);
      }
    } catch (e) {
      console.warn('allorigins failed:', e);
    }

    throw new Error('Could not reach news sources. Check your internet.');
  }

  function parseRssXml(xml, query) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(xml, 'text/xml');
    const items = doc.querySelectorAll('item');
    const results = [];

    items.forEach(item => {
      const title = item.querySelector('title')?.textContent || '';
      const link = item.querySelector('link')?.textContent || '';
      const pubDate = item.querySelector('pubDate')?.textContent || '';
      const desc = item.querySelector('description')?.textContent || '';
      const source = item.querySelector('source')?.textContent || extractSource(title) || 'News';

      results.push({
        title: stripHtml(title),
        link: link,
        source: source,
        time: formatDate(pubDate),
        description: stripHtml(desc).substring(0, 200)
      });
    });

    return results;
  }

  function extractSource(title) {
    // Google News titles often end with " - Source Name"
    const match = title.match(/\s[-–—]\s([^-–—]+)$/);
    return match ? match[1].trim() : '';
  }

  function stripHtml(html) {
    const div = document.createElement('div');
    div.innerHTML = html;
    return div.textContent || div.innerText || '';
  }

  function formatDate(dateStr) {
    if (!dateStr) return 'Recent';
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diffMs = now - d;
      const diffHrs = Math.floor(diffMs / 3600000);
      const diffMins = Math.floor(diffMs / 60000);

      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHrs < 24) return `${diffHrs}h ago`;
      if (diffHrs < 48) return 'Yesterday';
      return d.toLocaleDateString('en-BD', { month: 'short', day: 'numeric' });
    } catch {
      return 'Recent';
    }
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
      document.getElementById('searchResults').innerHTML = `
        <div class="card">
          <div class="section-title"><span>Quick Search Topics</span></div>
          <div class="filter-chips" style="flex-wrap:wrap">
            ${['Cricket', 'Politics', 'Economy', 'Gas', 'Weather', 'Education', 'Sports', 'International', 'Technology', 'Culture', 'Health', 'Entertainment'].map(t =>
              `<button class="chip" onclick="document.getElementById('searchInput').value='${t}';Search.setMode('web');Search.webSearch()">${t}</button>`
            ).join('')}
          </div>
        </div>`;
      return;
    }

    recentBox.style.display = 'block';
    recentList.innerHTML = history.map(h => `
      <div class="source-item" style="cursor:pointer" onclick="document.getElementById('searchInput').value='${News.escapeHtml(h)}';Search.setMode('web');Search.webSearch()">
        <span style="font-size:14px">🕑 ${News.escapeHtml(h)}</span>
      </div>
    `).join('');
  }

  function clearHistory() {
    localStorage.removeItem('pb_search_history');
    showRecent();
    App.showToast('Search history cleared');
  }

  return { onInput, performSearch, webSearch, setMode, showRecent, clearHistory };
})();
