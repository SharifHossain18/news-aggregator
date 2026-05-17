/* ===== Search & Filter Engine ===== */
const Search = (() => {
  let debounceTimer = null;
  let searchMode = 'web'; // 'local', 'web', or 'deep'
  let deepPollTimer = null;
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
    const deepBtn = document.getElementById('modeDeep');
    if (deepBtn) deepBtn.classList.toggle('active', mode === 'deep');
    document.getElementById('webSearchHint').style.display = (mode === 'web' || mode === 'deep') ? 'block' : 'none';
    document.getElementById('webSearchBtn').style.display = mode !== 'local' ? 'block' : 'none';
    
    // Update button text
    const btn = document.querySelector('#webSearchBtn button');
    if (btn) {
      btn.textContent = mode === 'deep' ? '🔍 Deep Search (5-7 min)' : '🌐 Search Web';
    }
    
    document.getElementById('searchInput').placeholder = mode === 'local'
      ? 'Search in saved news...'
      : mode === 'deep' ? 'Search any topic across 44 newspapers...'
      : 'Search any topic...';
    // Re-run search
    const q = document.getElementById('searchInput').value.trim();
    if (q && mode === 'local') performSearch(q);
    else if (!q) document.getElementById('searchResults').innerHTML = '';
  }

  function onInput(query) {
    clearTimeout(debounceTimer);
    if (searchMode === 'local') {
      debounceTimer = setTimeout(() => performSearch(query), 250);
    }
    // In web mode, just wait for Enter or button tap
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

    // If deep mode, use local server
    if (searchMode === 'deep') {
      return deepSearch(query);
    }

    // Switch to web mode if not already
    if (searchMode === 'local') setMode('web');

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

  async function deepSearch(query) {
    if (!query) query = document.getElementById('searchInput').value.trim();
    if (!query) { App.showToast('Type something to search'); return; }

    saveToHistory(query);
    const container = document.getElementById('searchResults');
    const localUrl = localStorage.getItem('pb_local_url') || 'http://192.168.11.25:5055';
    const localToken = localStorage.getItem('pb_local_token') || '';

    // Show progress
    container.innerHTML = `
      <div class="card">
        <div style="text-align:center;padding:30px">
          <div style="font-size:32px;animation:pulse 1.5s infinite">\ud83d\udd0d</div>
          <div style="margin-top:12px;font-size:14px;font-weight:600">Deep Searching: "${News.escapeHtml(query)}"</div>
          <div style="margin-top:4px;font-size:11px;color:var(--ink-muted)">Scraping 44 newspaper websites... (5-7 minutes)</div>
          <div style="margin-top:16px;height:4px;background:var(--bg-glass);border-radius:4px;overflow:hidden">
            <div id="deepProgress" style="height:100%;width:0%;background:linear-gradient(90deg,var(--primary),#3b82f6);border-radius:4px;transition:width 1s ease"></div>
          </div>
          <div id="deepStatus" style="margin-top:8px;font-size:11px;color:var(--ink-muted)">Starting scan...</div>
        </div>
      </div>`;

    // Trigger search via local server
    try {
      const headers = {'Content-Type': 'application/json'};
      if (localToken) headers['X-App-Token'] = localToken;

      const res = await fetch(localUrl + '/api/search', {
        method: 'POST',
        headers,
        body: JSON.stringify({query})
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Server error');
      }

      // Start polling for results
      let elapsed = 0;
      const maxWait = 600; // 10 minutes max
      clearInterval(deepPollTimer);

      deepPollTimer = setInterval(async () => {
        elapsed += 5;
        const pct = Math.min(95, (elapsed / 420) * 100); // ~7 min estimate
        const bar = document.getElementById('deepProgress');
        const status = document.getElementById('deepStatus');
        if (bar) bar.style.width = pct + '%';
        if (status) status.textContent = `Scanning... ${Math.floor(elapsed/60)}m ${elapsed%60}s elapsed`;

        // Check if scan is done
        try {
          const statusRes = await fetch(localUrl + '/api/status', {headers: localToken ? {'X-App-Token': localToken} : {}});
          const statusData = await statusRes.json();

          if (!statusData.running) {
            clearInterval(deepPollTimer);
            // Fetch results
            const resRes = await fetch(localUrl + '/api/search/results', {headers: localToken ? {'X-App-Token': localToken} : {}});
            const data = await resRes.json();

            if (data.results && data.results.length > 0) {
              container.innerHTML = `
                <div class="card">
                  <div class="section-title">
                    <span>\ud83d\udd0d Deep Search: "${News.escapeHtml(query)}"</span>
                    <span style="font-size:11px;color:var(--primary-light)">${data.results.length} found</span>
                  </div>
                  ${data.results.map((n, i) => `
                    <div class="news-item">
                      <div class="news-index">${i + 1}</div>
                      <div class="news-body">
                        <a href="${News.escapeHtml(n.link)}" class="news-title" target="_blank" rel="noopener">${highlightMatch(n.title, query)}</a>
                        <div class="news-meta">
                          <span class="source-badge">${News.escapeHtml(n.source)}</span>
                          <span class="time-badge">\ud83d\udd52 ${News.escapeHtml(n.time || 'Today')}</span>
                        </div>
                        ${n.summary ? `<div class="news-summary">\ud83d\udcdd ${News.escapeHtml(n.summary)}</div>` : ''}
                      </div>
                    </div>
                  `).join('')}
                </div>`;
              App.showToast(`Found ${data.results.length} articles!`);
            } else {
              container.innerHTML = `
                <div class="card">
                  <div class="empty-state">
                    <div class="icon">\ud83d\udd0d</div>
                    <div class="title">No results for "${News.escapeHtml(query)}"</div>
                    <div class="desc">No matching articles found across 44 newspapers. Try different keywords.</div>
                  </div>
                </div>`;
            }
          }
        } catch (pollErr) {
          console.warn('Poll error:', pollErr);
        }

        if (elapsed >= maxWait) {
          clearInterval(deepPollTimer);
          container.innerHTML = `
            <div class="card"><div class="empty-state">
              <div class="icon">\u23f0</div>
              <div class="title">Search timed out</div>
              <div class="desc">The scan took too long. Try again.</div>
            </div></div>`;
        }
      }, 5000);

    } catch (err) {
      container.innerHTML = `
        <div class="card"><div class="empty-state">
          <div class="icon">\u26a0\ufe0f</div>
          <div class="title">Could not start deep search</div>
          <div class="desc">${News.escapeHtml(err.message)}. Make sure the local server is running.</div>
        </div></div>`;
    }
  }

  return { onInput, performSearch, webSearch, deepSearch, setMode, showRecent, clearHistory };
})();
