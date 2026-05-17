/* ===== Main App Controller ===== */
const App = (() => {
  let autoRefreshInterval = null;
  let statsData = {};
  let scanMode = 'cloud'; // 'cloud' or 'local'
  let localPollTimer = null;
  let deferredInstallPrompt = null;

  // Capture PWA install prompt
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    const banner = document.getElementById('installBanner');
    if (banner) banner.style.display = 'block';
  });

  window.addEventListener('appinstalled', () => {
    deferredInstallPrompt = null;
    const banner = document.getElementById('installBanner');
    if (banner) banner.style.display = 'none';
    showToast('✅ App installed!');
  });

  // --- Initialize ---
  async function init() {
    loadSettings();
    setupOfflineDetection();
    setupPullToRefresh();

    // Load data
    await loadAll();

    // Auto refresh
    if (localStorage.getItem('pb_auto_refresh') !== 'false') {
      startAutoRefresh();
    }

    // Register SW
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('./sw.js').catch(e => console.warn('SW failed:', e));
    }
  }

  async function loadAll() {
    const [articles, stats] = await Promise.all([
      News.fetchNews(),
      News.fetchStats()
    ]);
    statsData = stats;

    // Render Home
    News.filter('all');
    News.renderBreaking();
    News.renderScanStatus(stats);

    // Render Sources
    renderSources(stats);

    // Render Analytics
    Charts.renderStats(articles, stats);
    Charts.renderSourceChart(stats);
    Charts.renderTopicChart(articles);
  }

  // --- Tab Navigation ---
  function switchTab(tabName) {
    document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    const view = document.getElementById('view' + tabName);
    if (view) view.classList.add('active');

    const nav = document.querySelector(`.nav-item[data-tab="${tabName}"]`);
    if (nav) nav.classList.add('active');

    if (tabName === 'Search') {
      Search.showRecent();
      setTimeout(() => document.getElementById('searchInput')?.focus(), 300);
    }
  }

  // --- Theme ---
  function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') !== 'light';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    document.getElementById('themeToggle').textContent = isDark ? '☀️' : '🌙';
    document.getElementById('darkModeToggle').checked = !isDark;
    document.querySelector('meta[name="theme-color"]').content = isDark ? '#f0fdfa' : '#030b0f';
    localStorage.setItem('pb_theme', isDark ? 'light' : 'dark');
  }

  // --- Refresh ---
  async function refresh() {
    const btn = document.getElementById('refreshBtn');
    btn.classList.add('spinning');
    btn.disabled = true;
    try {
      await loadAll();
      showToast('✅ News updated');
    } catch (e) {
      showToast('❌ Refresh failed');
    }
    btn.classList.remove('spinning');
    btn.disabled = false;
  }

  // --- Auto Refresh ---
  function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshInterval = setInterval(() => { loadAll(); }, 5 * 60 * 1000);
  }

  function stopAutoRefresh() {
    if (autoRefreshInterval) clearInterval(autoRefreshInterval);
  }

  function toggleAutoRefresh() {
    const on = document.getElementById('autoRefreshToggle').checked;
    localStorage.setItem('pb_auto_refresh', on ? 'true' : 'false');
    if (on) startAutoRefresh(); else stopAutoRefresh();
    showToast(on ? 'Auto-refresh enabled' : 'Auto-refresh disabled');
  }

  // --- AI Summary Toggle ---
  function toggleAISummary() {
    const on = document.getElementById('aiSummaryToggle').checked;
    localStorage.setItem('pb_show_ai', on ? 'true' : 'false');
    News.setShowSummaries(on);
    showToast(on ? 'AI summaries shown' : 'AI summaries hidden');
  }

  // =============================================
  // ===== SCAN MODE SYSTEM (Cloud + Local) =====
  // =============================================

  function setScanMode(mode) {
    scanMode = mode;
    localStorage.setItem('pb_scan_mode', mode);

    // Update UI chips
    document.getElementById('modeCloud').classList.toggle('active', mode === 'cloud');
    document.getElementById('modeLocal').classList.toggle('active', mode === 'local');

    // Show/hide config panels
    document.getElementById('cloudConfig').style.display = mode === 'cloud' ? 'block' : 'none';
    document.getElementById('localConfig').style.display = mode === 'local' ? 'block' : 'none';

    // Update label
    const label = document.getElementById('scanModeLabel');
    if (mode === 'cloud') {
      label.textContent = '☁️ CLOUD';
      label.style.background = 'rgba(99,102,241,0.15)';
      label.style.color = '#818cf8';
    } else {
      label.textContent = '💻 LOCAL';
      label.style.background = 'rgba(16,185,129,0.15)';
      label.style.color = '#34d399';
    }
  }

  // --- Quick Scan from Home tab ---
  let homeProgressTimer = null;

  async function quickScan() {
    const btn = document.getElementById('homeScanBtn');
    const statusEl = document.getElementById('homeScanStatus');
    const card = document.getElementById('homeScanCard');
    const progressWrapper = document.getElementById('homeProgress');
    const progressFill = document.getElementById('homeProgressFill');
    const progressLabel = document.getElementById('homeProgressLabel');
    const progressPct = document.getElementById('homeProgressPct');

    btn.disabled = true;
    btn.innerHTML = '⏳ Scanning...';
    card.classList.add('scanning');
    statusEl.textContent = 'SCANNING';
    statusEl.style.background = 'rgba(59,130,246,0.15)';
    statusEl.style.color = '#60a5fa';
    statusEl.style.borderColor = 'rgba(59,130,246,0.3)';

    // Show & animate home progress bar
    progressWrapper.style.display = 'block';
    progressFill.classList.add('active');
    animateHomeProgress(progressFill, progressLabel, progressPct);

    try {
      await executeScan('trigger');
      statusEl.textContent = 'TRIGGERED';
      statusEl.style.background = 'rgba(16,185,129,0.15)';
      statusEl.style.color = '#34d399';
      statusEl.style.borderColor = 'rgba(16,185,129,0.3)';

      // Let progress finish gracefully
      const delay = scanMode === 'local' ? 30000 : 120000;
      setTimeout(async () => {
        await loadAll();
        // Reset UI
        clearInterval(homeProgressTimer);
        progressFill.style.width = '100%';
        progressLabel.textContent = 'Complete!';
        progressPct.textContent = '100%';
        progressFill.classList.remove('active');
        setTimeout(() => {
          progressWrapper.style.display = 'none';
          progressFill.style.width = '0%';
          card.classList.remove('scanning');
          statusEl.textContent = 'IDLE';
          statusEl.style.background = 'var(--bg-glass)';
          statusEl.style.color = 'var(--ink-muted)';
          statusEl.style.borderColor = 'var(--border)';
        }, 2000);
      }, delay);

    } catch (e) {
      clearInterval(homeProgressTimer);
      progressFill.classList.remove('active');
      progressLabel.textContent = 'Failed';
      progressFill.style.width = '0%';
      card.classList.remove('scanning');
      statusEl.textContent = 'ERROR';
      statusEl.style.background = 'rgba(239,68,68,0.15)';
      statusEl.style.color = '#fca5a5';
      setTimeout(() => { progressWrapper.style.display = 'none'; }, 3000);
    }

    btn.disabled = false;
    btn.innerHTML = '\ud83d\ude80 Scan Now';
  }

  // Newspaper names to show in progress
  const NEWSPAPER_NAMES = [
    'Prothom Alo', 'Daily Star', 'Dhaka Tribune', 'TBS News', 'Kaler Kantho',
    'Samakal', 'Jugantor', 'Bangla Tribune', 'Jago News', 'Ittefaq',
    'Bonik Barta', 'Naya Diganta', 'Daily Inqilab', 'BD Pratidin',
    'Manab Zamin', 'Alokito Bangladesh', 'Desh Rupantor', 'Sangbad',
    'Ajker Patrika', 'Kalbela', 'Protidiner Bangladesh', 'Jai Jai Din',
    'Financial Express', 'New Age', 'Daily Sun', 'Observer',
    'Amader Shomoy', 'Daily Sangram', 'Dinkal', 'Manobkantha',
    'Rupali Bangladesh', 'Google News', 'Just Energy News'
  ];

  function animateHomeProgress(fill, label, pct) {
    let progress = 0;
    let paperIdx = 0;
    homeProgressTimer = setInterval(() => {
      progress += Math.random() * 2 + 0.3;
      if (progress > 95) progress = 95;
      fill.style.width = progress.toFixed(1) + '%';
      pct.textContent = Math.round(progress) + '%';
      // Cycle through newspaper names
      const paper = NEWSPAPER_NAMES[paperIdx % NEWSPAPER_NAMES.length];
      if (progress < 10) {
        label.textContent = 'Connecting...';
      } else if (progress < 90) {
        label.textContent = '📰 ' + paper;
      } else {
        label.textContent = 'Filtering results...';
      }
      paperIdx++;
    }, 800);
  }

  // --- Main Scan Trigger (from Scan tab) ---
  let scanProgressTimer = null;

  async function triggerScan(mode) {
    const btn = document.getElementById('scanTriggerBtn');
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Starting...';

    // Show progress bar
    const progressWrapper = document.getElementById('scanProgress');
    progressWrapper.style.display = 'block';
    setScanProgress('running', 'Connecting...', 'Establishing connection');
    setProgressBar(0, 'Connecting...', true);
    setStage(0, 'active');

    try {
      await executeScan(mode);
      btn.textContent = '✅ Scan Started!';

      // Animate through stages
      setStage(0, 'completed');
      setStage(1, 'active');
      setScanProgress('running', 'Scan in progress', scanMode === 'cloud' ? 'Results will appear shortly' : 'Scraping newspapers...');

      // Start animated progress
      startScanProgressAnimation();

      if (scanMode === 'local') {
        startLocalPolling();
      }

      setTimeout(() => {
        btn.textContent = oldText;
        btn.disabled = false;
      }, 4000);

    } catch (e) {
      btn.textContent = oldText;
      btn.disabled = false;
      setScanProgress('error', 'Scan failed', e.message || 'Check your configuration');
      setProgressBar(0, 'Failed', false);
      setStage(0, 'error');
      setTimeout(() => { progressWrapper.style.display = 'none'; }, 5000);
    }
  }

  function startScanProgressAnimation() {
    let progress = 10;
    let paperIdx = 0;

    clearInterval(scanProgressTimer);
    scanProgressTimer = setInterval(() => {
      progress += Math.random() * 1.5 + 0.2;
      if (progress > 95) progress = 95;

      const paper = NEWSPAPER_NAMES[paperIdx % NEWSPAPER_NAMES.length];
      let stageNum, label;

      if (progress < 15) {
        stageNum = 0; label = '🔗 Connecting to sources...';
      } else if (progress < 70) {
        stageNum = 1; label = '📰 Scanning: ' + paper;
      } else if (progress < 88) {
        stageNum = 2; label = '🔍 Filtering: ' + paper;
      } else {
        stageNum = 3; label = '✅ Finalizing results...';
      }

      setProgressBar(progress, label, true);
      for (let i = 0; i < stageNum; i++) setStage(i, 'completed');
      setStage(stageNum, 'active');
      paperIdx++;
    }, 1200);
  }

  function completeScanProgress() {
    clearInterval(scanProgressTimer);
    setProgressBar(100, 'Complete!', false);
    for (let i = 0; i < 4; i++) setStage(i, 'completed');
    setScanProgress('done', 'Scan complete!', 'Refresh to see new articles');
    setTimeout(() => {
      document.getElementById('scanProgress').style.display = 'none';
      setProgressBar(0, 'Initializing...', false);
      for (let i = 0; i < 4; i++) setStage(i, '');
    }, 4000);
  }

  // --- Progress Bar Helpers ---
  function setProgressBar(percent, label, active) {
    const fill = document.getElementById('scanProgressFill');
    const pctEl = document.getElementById('scanProgressPct');
    const labelEl = document.getElementById('scanProgressLabel');
    if (fill) {
      fill.style.width = percent.toFixed(1) + '%';
      fill.classList.toggle('active', !!active);
    }
    if (pctEl) pctEl.textContent = Math.round(percent) + '%';
    if (label && labelEl) labelEl.textContent = label;
  }

  function setStage(index, status) {
    const dot = document.getElementById('stage' + index);
    const label = document.getElementById('stageLabel' + index);
    if (!dot) return;
    dot.className = 'stage-dot' + (status ? ' ' + status : '');
    if (label) label.className = 'stage-label' + (status ? ' ' + status : '');
  }

  // --- Execute the actual scan ---
  async function executeScan(mode) {
    if (scanMode === 'cloud') {
      return executeCloudScan(mode);
    } else {
      return executeLocalScan(mode);
    }
  }

  // Cloud scan via GitHub Actions
  async function executeCloudScan(mode) {
    const token = (document.getElementById('scanGhToken')?.value || document.getElementById('ghToken')?.value || '').trim();
    if (!token) {
      showToast('⚠️ Enter GitHub token in Scan tab');
      switchTab('Scan');
      throw new Error('No GitHub token');
    }

    const repo = localStorage.getItem('pb_github_repo') || 'SharifHossain18/news-aggregator';
    const url = `https://api.github.com/repos/${repo}/actions/workflows/scrape.yml/dispatches`;

    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ref: 'main', inputs: { mode: mode } })
    });

    if (res.ok || res.status === 204) {
      showToast('🚀 Cloud scan triggered! News will update in 1-2 mins.');
      return true;
    } else {
      const err = await res.json().catch(() => ({}));
      showToast('❌ ' + (err.message || 'Failed. Check token.'));
      throw new Error(err.message || 'GitHub API error');
    }
  }

  // Local scan via mobile_control_app.py Flask server
  async function executeLocalScan(mode) {
    const serverUrl = (document.getElementById('localServerUrl')?.value || '').trim();
    if (!serverUrl) {
      showToast('⚠️ Enter local server URL in Scan tab');
      switchTab('Scan');
      throw new Error('No local server URL');
    }

    const appToken = (document.getElementById('localAppToken')?.value || '').trim();
    const headers = { 'Content-Type': 'application/json' };
    if (appToken) headers['X-App-Token'] = appToken;

    const res = await fetch(serverUrl.replace(/\/$/, '') + '/api/run', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ mode: mode, location: 'local' })
    });

    const data = await res.json();
    if (!data.ok) {
      showToast('❌ ' + (data.error || data.message || 'Run failed'));
      throw new Error(data.error || 'Local scan failed');
    }

    showToast('🚀 Local scan started! ' + (data.message || ''));
    return true;
  }

  // --- Local Server Status Polling ---
  function startLocalPolling() {
    stopLocalPolling();
    localPollTimer = setInterval(async () => {
      try {
        const serverUrl = (document.getElementById('localServerUrl')?.value || '').trim();
        if (!serverUrl) return;

        const appToken = (document.getElementById('localAppToken')?.value || '').trim();
        const headers = {};
        if (appToken) headers['X-App-Token'] = appToken;

        const res = await fetch(serverUrl.replace(/\/$/, '') + '/api/status', { headers });
        const data = await res.json();

        if (data.ok) {
          if (data.running) {
            setScanProgress('running', 'Scraping in progress...', 'Checking newspapers');
          } else {
            setScanProgress('done', 'Scan complete!', 'Refresh to see new articles');
            completeScanProgress();
            stopLocalPolling();
            // Auto refresh after done
            setTimeout(() => loadAll(), 3000);
          }
        }
      } catch (e) {
        // Silent fail — server might be busy
      }
    }, 3000);
  }

  function stopLocalPolling() {
    if (localPollTimer) { clearInterval(localPollTimer); localPollTimer = null; }
  }

  // --- Scan Progress UI ---
  function setScanProgress(status, text, sub) {
    const dot = document.getElementById('scanProgressDot');
    const textEl = document.getElementById('scanProgressText');
    const subEl = document.getElementById('scanProgressSub');

    textEl.textContent = text || '';
    subEl.textContent = sub || '';

    if (status === 'running') {
      dot.style.background = '#3b82f6';
      dot.style.boxShadow = '0 0 10px rgba(59,130,246,0.5)';
      dot.style.animation = 'pulse 1.5s infinite';
    } else if (status === 'done') {
      dot.style.background = '#10b981';
      dot.style.boxShadow = '0 0 10px rgba(16,185,129,0.5)';
      dot.style.animation = 'none';
    } else if (status === 'error') {
      dot.style.background = '#ef4444';
      dot.style.boxShadow = '0 0 10px rgba(239,68,68,0.5)';
      dot.style.animation = 'none';
    } else {
      dot.style.background = 'var(--ink-muted)';
      dot.style.boxShadow = 'none';
      dot.style.animation = 'none';
    }
  }

  // --- Sources Rendering ---
  let allSourceEntries = [];

  function renderSources(stats) {
    const container = document.getElementById('sourceList');
    const countEl = document.getElementById('sourceCount');

    if (!stats || Object.keys(stats).length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="icon">📡</div><div class="title">No source data</div><div class="desc">Run a scan to populate source stats</div></div>';
      return;
    }

    allSourceEntries = Object.entries(stats)
      .filter(([k]) => k !== '_meta')
      .sort(([a], [b]) => a.localeCompare(b));

    countEl.textContent = `${allSourceEntries.length} sources`;
    renderSourceList(allSourceEntries);
  }

  function renderSourceList(entries) {
    const container = document.getElementById('sourceList');
    container.innerHTML = entries.map(([name, s]) => {
      const failStreak = s.last_fail_streak || 0;
      const status = failStreak >= 5 ? 'fail' : failStreak >= 1 ? 'unknown' : 'ok';
      const articles = s.articles || 0;
      const lastCheck = s.last_check || 'Never';
      return `
        <div class="source-item">
          <div class="source-info">
            <div class="source-dot ${status}"></div>
            <div>
              <div class="source-name">${News.escapeHtml(name)}</div>
              <div style="font-size:10px;color:var(--ink-muted)">Last: ${News.escapeHtml(lastCheck)}</div>
            </div>
          </div>
          <div class="source-stat">${articles} articles</div>
        </div>`;
    }).join('');
  }

  // --- Source Filter ---
  window.Sources = {
    filter(query) {
      const q = (query || '').toLowerCase();
      const filtered = q ? allSourceEntries.filter(([name]) => name.toLowerCase().includes(q)) : allSourceEntries;
      renderSourceList(filtered);
    }
  };

  // --- Settings Persistence ---
  function loadSettings() {
    // Theme
    const theme = localStorage.getItem('pb_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    document.getElementById('themeToggle').textContent = theme === 'light' ? '☀️' : '🌙';
    document.getElementById('darkModeToggle').checked = theme === 'dark';
    document.querySelector('meta[name="theme-color"]').content = theme === 'light' ? '#f0fdfa' : '#030b0f';

    // Auto refresh
    const autoRefresh = localStorage.getItem('pb_auto_refresh') !== 'false';
    document.getElementById('autoRefreshToggle').checked = autoRefresh;

    // AI summaries
    const showAI = localStorage.getItem('pb_show_ai') !== 'false';
    document.getElementById('aiSummaryToggle').checked = showAI;
    News.setShowSummaries(showAI);

    // GitHub token (sync both fields)
    const ghToken = localStorage.getItem('pb_gh_token') || '';
    const ghEl = document.getElementById('ghToken');
    const scanGhEl = document.getElementById('scanGhToken');
    if (ghEl) ghEl.value = ghToken;
    if (scanGhEl) scanGhEl.value = ghToken;

    // Data URL
    const dataUrl = localStorage.getItem('pb_data_url') || '';
    document.getElementById('dataUrl').value = dataUrl;

    // Scan mode
    const savedMode = localStorage.getItem('pb_scan_mode') || 'cloud';
    setScanMode(savedMode);

    // Local server settings
    const localUrl = localStorage.getItem('pb_local_url') || '';
    const localToken = localStorage.getItem('pb_local_token') || '';
    const localUrlEl = document.getElementById('localServerUrl');
    const localTokenEl = document.getElementById('localAppToken');
    if (localUrlEl) localUrlEl.value = localUrl;
    if (localTokenEl) localTokenEl.value = localToken;
  }

  function saveToken() {
    const val = (document.getElementById('scanGhToken')?.value || document.getElementById('ghToken')?.value || '').trim();
    localStorage.setItem('pb_gh_token', val);
    // Sync both inputs
    const ghEl = document.getElementById('ghToken');
    const scanGhEl = document.getElementById('scanGhToken');
    if (ghEl) ghEl.value = val;
    if (scanGhEl) scanGhEl.value = val;
    showToast('Token saved');
  }

  function saveLocalUrl() {
    localStorage.setItem('pb_local_url', (document.getElementById('localServerUrl')?.value || '').trim());
    showToast('Local server URL saved');
  }

  function saveLocalToken() {
    localStorage.setItem('pb_local_token', (document.getElementById('localAppToken')?.value || '').trim());
    showToast('App token saved');
  }

  function saveDataUrl() {
    localStorage.setItem('pb_data_url', document.getElementById('dataUrl').value.trim());
    showToast('Data URL saved — refreshing...');
    setTimeout(() => refresh(), 500);
  }

  // --- Offline Detection ---
  function setupOfflineDetection() {
    const banner = document.getElementById('offlineBanner');
    const update = () => { banner.classList.toggle('visible', !navigator.onLine); };
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    update();
  }

  // --- Pull to Refresh ---
  function setupPullToRefresh() {
    let startY = 0;
    let pulling = false;
    const indicator = document.getElementById('pullIndicator');
    const content = document.querySelector('.app-content');

    content.addEventListener('touchstart', (e) => {
      if (window.scrollY === 0) { startY = e.touches[0].clientY; pulling = true; }
    }, { passive: true });

    content.addEventListener('touchmove', (e) => {
      if (!pulling) return;
      if (e.touches[0].clientY - startY > 60) indicator.classList.add('visible');
    }, { passive: true });

    content.addEventListener('touchend', () => {
      if (indicator.classList.contains('visible')) { refresh(); indicator.classList.remove('visible'); }
      pulling = false;
    }, { passive: true });
  }

  // --- Toast ---
  function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2500);
  }

  async function installApp() {
    if (!deferredInstallPrompt) {
      showToast('Open in Chrome browser to install');
      return;
    }
    deferredInstallPrompt.prompt();
    const result = await deferredInstallPrompt.userChoice;
    if (result.outcome === 'accepted') {
      showToast('✅ Installing...');
    }
    deferredInstallPrompt = null;
    const banner = document.getElementById('installBanner');
    if (banner) banner.style.display = 'none';
  }

  return {
    init, switchTab, toggleTheme, refresh, toggleAutoRefresh,
    toggleAISummary, triggerScan, quickScan, setScanMode,
    saveToken, saveLocalUrl, saveLocalToken, saveDataUrl, showToast, installApp
  };
})();

// Boot
document.addEventListener('DOMContentLoaded', App.init);
