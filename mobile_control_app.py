import os
import subprocess
import threading
import datetime
import json
import urllib.request
from collections import deque

from flask import Flask, jsonify, request, Response

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(BASE_DIR, "news_aggregator.py")
HOST = os.environ.get("MOBILE_APP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MOBILE_APP_PORT", "5055"))
AUTH_TOKEN = os.environ.get("MOBILE_APP_TOKEN", "").strip()

# GitHub Config for Cloud Trigger
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip() # Format: owner/repo
GITHUB_WORKFLOW = "scrape.yml"

app = Flask(__name__)

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return Response(status=204)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-App-Token'
    return response

process_lock = threading.Lock()
active_process = None
run_logs = deque(maxlen=2000)

def append_log(line):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    run_logs.append(f"[{ts}] {line}")

def is_authorized(req):
    if not AUTH_TOKEN:
        return True
    token = req.headers.get("X-App-Token", "").strip()
    return token == AUTH_TOKEN

def run_command(args, extra_env=None):
    global active_process
    with process_lock:
        if active_process is not None and active_process.poll() is None:
            return False, "A run is already in progress."

        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)

        cmd = ["py", RUNNER] + args
        append_log(f"Starting command: {' '.join(cmd)}")
        active_process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        thread = threading.Thread(target=stream_output, args=(active_process,), daemon=True)
        thread.start()
        return True, "Started Locally"

def stream_output(proc):
    global active_process
    try:
        for line in iter(proc.stdout.readline, ""):
            clean = line.rstrip()
            if clean:
                append_log(clean)
        return_code = proc.wait()
        append_log(f"Process finished with exit code {return_code}")
    except Exception as e:
        append_log(f"Output stream error: {e}")
    finally:
        with process_lock:
            active_process = None

@app.route("/")
def index():
    return Response(MOBILE_HTML, mimetype="text/html")

@app.route("/manifest.json")
def manifest():
    with open(os.path.join(BASE_DIR, "docs", "manifest.json"), "r") as f:
        return Response(f.read(), mimetype="application/json")

@app.route("/sw.js")
def service_worker():
    with open(os.path.join(BASE_DIR, "sw.js"), "r") as f:
        return Response(f.read(), mimetype="application/javascript")

@app.route("/api/status")
def status():
    if not is_authorized(request):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    running = False
    with process_lock:
        running = active_process is not None and active_process.poll() is None
    return jsonify({
        "ok": True,
        "running": running,
        "log_count": len(run_logs),
        "ai_enabled": os.environ.get("GEMINI_API_KEY") is not None
    })

@app.route("/api/run", methods=["POST"])
def run_now():
    if not is_authorized(request):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or "trigger").strip().lower()
    location = (payload.get("location") or "local").strip().lower()

    if location == "cloud":
        return trigger_github_action(mode)

    if mode == "trigger":
        ok, msg = run_command(["trigger"])
    elif mode == "digest":
        ok, msg = run_command([], extra_env={"FORCE_DIGEST": "true"})
    elif mode == "stats":
        ok, msg = run_command(["stats"])
    else:
        return jsonify({"ok": False, "error": "Invalid mode"}), 400

    code = 200 if ok else 409
    return jsonify({"ok": ok, "message": msg}), code

@app.route("/api/search", methods=["POST"])
def search_news():
    if not is_authorized(request):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"ok": False, "error": "No search query provided"}), 400
    
    append_log(f"Starting deep search for: {query}")
    ok, msg = run_command(["trigger"], extra_env={"SEARCH_QUERY": query})
    code = 200 if ok else 409
    return jsonify({"ok": ok, "message": msg, "query": query}), code

@app.route("/api/search/results")
def search_results():
    search_file = os.path.join(BASE_DIR, "docs", "search_results.json")
    if not os.path.exists(search_file):
        return jsonify({"query": "", "count": 0, "results": []})
    try:
        with open(search_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"query": "", "count": 0, "results": [], "error": str(e)})

def trigger_github_action(mode):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return jsonify({"ok": False, "error": "GitHub Token or Repo not configured in .env"}), 400
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"
    data = json.dumps({
        "ref": "main",
        "inputs": {"mode": mode}
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "NewsAggregator-MobileApp")
    
    try:
        urllib.request.urlopen(req)
        append_log(f"Cloud Scraper triggered successfully (Mode: {mode})")
        return jsonify({"ok": True, "message": "Cloud Scraper Triggered! News will update in 1-2 mins."})
    except Exception as e:
        append_log(f"GitHub Trigger Error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/logs")
def logs():
    if not is_authorized(request):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    try:
        limit = int(request.args.get("limit", "250"))
    except ValueError:
        limit = 250
    limit = max(20, min(limit, 2000))
    lines = list(run_logs)[-limit:]
    return jsonify({"ok": True, "lines": lines})

# --- PREMIUM MOBILE UI ---
MOBILE_HTML = """<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no'/>
  <meta name='apple-mobile-web-app-capable' content='yes'/>
  <meta name='apple-mobile-web-app-status-bar-style' content='black-translucent'/>
  <link rel='manifest' href='/manifest.json'/>
  <title>News Aggregator Pro</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0f172a;
      --card: rgba(30, 41, 59, 0.7);
      --ink: #f8fafc;
      --muted: #94a3b8;
      --primary: #10b981;
      --primary-glow: rgba(16, 185, 129, 0.3);
      --accent: #f59e0b;
      --danger: #ef4444;
      --glass: rgba(255, 255, 255, 0.03);
    }
    
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
    
    body {
      margin: 0;
      font-family: 'Outfit', sans-serif;
      background: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(16, 185, 129, 0.1) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(245, 158, 11, 0.1) 0px, transparent 50%);
      color: var(--ink);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .header {
      padding: 30px 20px 20px;
      text-align: center;
    }

    .header h1 {
      margin: 0;
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.5px;
      background: linear-gradient(to right, #10b981, #34d399);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .header p {
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 14px;
      font-weight: 300;
    }

    .wrap {
      max-width: 500px;
      width: 100%;
      margin: 0 auto;
      padding: 0 16px 40px;
      flex: 1;
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      margin-bottom: 20px;
      background: var(--glass);
      border: 1px solid rgba(255,255,255,0.1);
    }

    .status-badge.idle .dot { background: var(--muted); }
    .status-badge.running .dot { 
      background: var(--primary);
      box-shadow: 0 0 10px var(--primary);
      animation: pulse 1.5s infinite;
    }
    
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-right: 8px;
    }

    @keyframes pulse {
      0% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.3); opacity: 0.5; }
      100% { transform: scale(1); opacity: 1; }
    }

    .card {
      background: var(--card);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 24px;
      padding: 24px;
      margin-bottom: 20px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.2);
    }

    .section-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
    }

    .ai-badge {
      font-size: 10px;
      background: var(--primary);
      color: white;
      padding: 2px 6px;
      border-radius: 4px;
      vertical-align: middle;
    }

    .btn-group {
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }

    button {
      outline: none;
      border: none;
      border-radius: 16px;
      padding: 16px;
      font-size: 16px;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      position: relative;
      overflow: hidden;
    }

    button:active { transform: scale(0.97); }

    .btn-primary {
      background: var(--primary);
      color: white;
      box-shadow: 0 8px 16px var(--primary-glow);
    }

    .btn-cloud {
      background: linear-gradient(135deg, #6366f1, #4f46e5);
      color: white;
      box-shadow: 0 8px 16px rgba(99, 102, 241, 0.3);
    }

    .btn-outline {
      background: var(--glass);
      border: 1px solid rgba(255,255,255,0.1);
      color: var(--ink);
    }

    .btn-outline:hover {
      background: rgba(255,255,255,0.08);
    }

    .input-group {
      margin-bottom: 20px;
    }

    input {
      width: 100%;
      background: rgba(0,0,0,0.2);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 12px;
      padding: 12px 16px;
      color: white;
      font-family: inherit;
      font-size: 14px;
    }

    input:focus {
      border-color: var(--primary);
      outline: none;
    }

    .logs-container {
      background: #000;
      border-radius: 16px;
      padding: 12px;
      font-family: 'Courier New', monospace;
      font-size: 12px;
      color: #10b981;
      height: 300px;
      overflow-y: auto;
      border: 1px solid rgba(255,255,255,0.05);
    }

    .log-line { margin-bottom: 4px; line-height: 1.4; }
    .log-ts { color: #4b5563; margin-right: 6px; }

    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }

    .tabs {
      display: flex;
      background: var(--glass);
      padding: 4px;
      border-radius: 12px;
      margin-bottom: 20px;
    }

    .tab {
      flex: 1;
      text-align: center;
      padding: 8px;
      font-size: 14px;
      font-weight: 600;
      color: var(--muted);
      cursor: pointer;
      border-radius: 8px;
    }

    .tab.active {
      background: var(--primary);
      color: white;
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>News Aggregator Pro</h1>
    <p>Bangladesh Energy Sector Intelligence</p>
  </div>

  <div class="wrap">
    <div id="statusBadge" class="status-badge idle">
      <div class="dot"></div>
      <span id="statusText">Checking Status...</span>
    </div>

    <div class="tabs">
      <div id="localTab" class="tab active" onclick="setTab('local')">Local Server</div>
      <div id="cloudTab" class="tab" onclick="setTab('cloud')">Cloud Runner</div>
    </div>

    <div class="card">
      <div class="section-title">
        <span>Quick Actions</span>
        <span id="aiBadge" class="ai-badge" style="display:none">AI ACTIVE</span>
      </div>
      
      <div class="input-group">
        <input id="token" type="password" placeholder="App Token (X-App-Token)" oninput="saveToken()"/>
      </div>
      <div id="serverInfo" style="font-size:11px;color:var(--muted);margin-top:-12px;margin-bottom:16px;text-align:center"></div>

      <div class="btn-group">
        <button id="mainBtn" class="btn-primary" onclick="runMode('trigger')">
          <span>🚀</span> <span id="mainBtnText">Run Alerts Scan</span>
        </button>
        <button class="btn-outline" onclick="runMode('digest')">
          <span>📋</span> Run Daily Digest
        </button>
        <button class="btn-outline" onclick="runMode('stats')">
          <span>📊</span> Send Analytics
        </button>
      </div>
    </div>

    <div class="card">
      <div class="section-title">Terminal Logs</div>
      <div id="logs" class="logs-container">
        <div class="log-line">Connecting to server...</div>
      </div>
      <button class="btn-outline" style="margin-top:12px; width:100%; font-size:12px; padding:8px" onclick="clearLogs()">
        Clear Console
      </button>
    </div>
  </div>

  <script>
    let currentTab = 'local';

    function setTab(tab) {
      currentTab = tab;
      document.getElementById('localTab').classList.toggle('active', tab === 'local');
      document.getElementById('cloudTab').classList.toggle('active', tab === 'cloud');
      
      const mainBtn = document.getElementById('mainBtn');
      const mainBtnText = document.getElementById('mainBtnText');
      
      if (tab === 'cloud') {
        mainBtn.className = 'btn-cloud';
        mainBtnText.textContent = 'Launch Cloud Scraper';
      } else {
        mainBtn.className = 'btn-primary';
        mainBtnText.textContent = 'Run Alerts Scan';
      }
    }

    function headers() {
      const token = document.getElementById('token').value.trim();
      const h = {'Content-Type': 'application/json'};
      if (token) h['X-App-Token'] = token;
      return h;
    }

    async function refreshStatus() {
      try {
        const res = await fetch('/api/status', {headers: headers()});
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'status failed');
        
        const badge = document.getElementById('statusBadge');
        const text = document.getElementById('statusText');
        
        if (data.running) {
          badge.className = 'status-badge running';
          text.textContent = 'SCRAPING IN PROGRESS';
        } else {
          badge.className = 'status-badge idle';
          text.textContent = 'SYSTEM IDLE';
        }

        if (data.ai_enabled) {
          document.getElementById('aiBadge').style.display = 'inline-block';
        }
      } catch (e) {
        document.getElementById('statusText').textContent = 'CONNECTION ERROR';
      }
    }

    async function refreshLogs() {
      try {
        const res = await fetch('/api/logs?limit=350', {headers: headers()});
        const data = await res.json();
        if (!data.ok) return;
        
        const box = document.getElementById('logs');
        const scrollAtBottom = box.scrollHeight - box.scrollTop <= box.clientHeight + 50;
        
        box.innerHTML = data.lines.map(line => {
          if (line.startsWith('[')) {
            const idx = line.indexOf(']');
            if (idx > 0) {
              const ts = line.substring(1, idx);
              const msg = line.substring(idx + 1).trim();
              return `<div class="log-line"><span class="log-ts">${ts}</span>${msg}</div>`;
            }
          }
          return `<div class="log-line">${line}</div>`;
        }).join('');

        if (scrollAtBottom) {
          box.scrollTop = box.scrollHeight;
        }
      } catch (e) {}
    }

    async function runMode(mode) {
      try {
        const mainBtn = document.getElementById('mainBtn');
        mainBtn.style.opacity = '0.5';
        mainBtn.disabled = true;

        const res = await fetch('/api/run', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify({mode, location: currentTab})
        });
        const data = await res.json();
        
        if (!data.ok) throw new Error(data.error || data.message || 'run failed');
        
        if (currentTab === 'cloud') {
          alert("Cloud Request Sent! The scraper will run on GitHub and update your news feed.");
        }
        
        await refreshStatus();
        await refreshLogs();
      } catch (e) {
        alert(e.message);
      } finally {
        const mainBtn = document.getElementById('mainBtn');
        mainBtn.style.opacity = '1';
        mainBtn.disabled = false;
      }
    }

    function clearLogs() {
      document.getElementById('logs').innerHTML = '';
    }

    function saveToken() {
      const token = document.getElementById('token').value;
      if (token) localStorage.setItem('app_token', token);
      else localStorage.removeItem('app_token');
    }

    function loadToken() {
      const saved = localStorage.getItem('app_token');
      if (saved) document.getElementById('token').value = saved;
    }

    function showServerInfo() {
      const el = document.getElementById('serverInfo');
      const host = location.hostname;
      const port = location.port;
      el.textContent = host !== 'localhost' && host !== '127.0.0.1'
        ? 'Connected to ' + host + (port ? ':' + port : '')
        : 'Open your mobile browser to http://YOUR_PC_IP:' + port + ' from your phone';
    }

    // Register Service Worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js');
    }

    loadToken();
    showServerInfo();
    setInterval(refreshStatus, 3000);
    setInterval(refreshLogs, 2000);
    refreshStatus();
    refreshLogs();
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    append_log("Mobile Pro App started")
    app.run(host=HOST, port=PORT)
