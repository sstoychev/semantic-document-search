import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.routers import documents, auth
from app.database import verify_ready
from app.services.indexing_service import preload_models as preload_indexing_models
from app.services.search_service import preload_models as preload_search_models

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Check-only: app startup must never create/initialize infrastructure.
    verify_ready()

    # Eager-load models once so requests do not pay first-hit load cost.
    preload_indexing_models()
    preload_search_models()
    yield

app = FastAPI(
    title="Semantic Document Search",
    description="Store and semantically search text documents",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


@app.get("/demo", response_class=HTMLResponse, tags=["demo"])
def demo_page() -> str:
        return """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Semantic Search Demo</title>
    <style>
        :root {
            --bg: #f7f7f2;
            --panel: #fffef8;
            --ink: #22201b;
            --muted: #6b665b;
            --brand: #0b6e4f;
            --brand-2: #0a4f59;
            --line: #e5dfd1;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 10%, #f4efe0 0, transparent 45%),
                radial-gradient(circle at 90% 0%, #e5f3ee 0, transparent 50%),
                var(--bg);
        }
        .wrap { max-width: 980px; margin: 28px auto; padding: 0 16px 24px; }
        .header { margin-bottom: 14px; }
        h1 { margin: 0; font-family: "IBM Plex Serif", Georgia, serif; font-size: 1.8rem; }
        .sub { color: var(--muted); margin-top: 4px; }
        .auth-bar {
            display: flex; align-items: center; gap: 12px;
            background: var(--panel); border: 1px solid var(--line);
            border-radius: 10px; padding: 8px 14px; margin-bottom: 12px;
            font-size: .92rem;
        }
        .auth-bar .spacer { flex: 1; }
        .tabs { display: flex; gap: 8px; margin: 16px 0; }
        .tab {
            border: 1px solid var(--line); background: #fff; color: var(--ink);
            padding: 10px 14px; border-radius: 10px; cursor: pointer; font-weight: 600;
        }
        .tab.active {
            background: linear-gradient(90deg, var(--brand), var(--brand-2));
            color: #fff; border-color: transparent;
        }
        .panel {
            border: 1px solid var(--line); background: var(--panel);
            border-radius: 14px; padding: 16px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.05);
        }
        .hidden { display: none; }
        .row { display: flex; gap: 10px; flex-wrap: wrap; }
        input[type="text"], input[type="password"], input[type="number"] {
            flex: 1; min-width: 220px; border: 1px solid var(--line);
            background: white; color: var(--ink); border-radius: 10px;
            padding: 10px 12px; font-size: 0.98rem;
        }
        input[type="file"] {
            border: 1px dashed var(--line); border-radius: 10px;
            padding: 10px; width: 100%; background: #fff;
        }
        button {
            border: 0; border-radius: 10px; padding: 10px 14px; color: #fff;
            background: linear-gradient(90deg, var(--brand), var(--brand-2));
            cursor: pointer; font-weight: 700;
        }
        button.secondary {
            background: #e8e4da; color: var(--ink);
        }
        button:disabled { opacity: .6; cursor: not-allowed; }
        .hint { color: var(--muted); font-size: .9rem; margin-top: 8px; }
        .status { margin-top: 10px; font-weight: 600; }
        .ok { color: #127a38; }
        .err { color: #a62222; }
        .warn { color: #8b6200; }
        .results { margin-top: 14px; display: grid; gap: 10px; }
        .item {
            border: 1px solid var(--line); border-radius: 10px;
            background: #fff; padding: 12px;
        }
        .meta { color: var(--muted); font-size: .9rem; margin-bottom: 6px; }
        .login-form { max-width: 360px; display: grid; gap: 10px; }
        @media (max-width: 640px) { .wrap { margin-top: 14px; } h1 { font-size: 1.5rem; } }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="header">
            <h1>Semantic Document Search</h1>
            <div class="sub">Search indexed chunks and add new documents.</div>
        </div>

        <div class="auth-bar">
            <span id="auth-user-label">Not logged in</span>
            <span class="spacer"></span>
            <button id="btn-logout" class="secondary hidden" type="button">Logout</button>
        </div>

        <div class="tabs">
            <button id="tab-search" class="tab" type="button">Search</button>
            <button id="tab-add" class="tab" type="button">Add</button>
            <button id="tab-login" class="tab active" type="button">Login</button>
        </div>

        <section id="panel-login" class="panel">
            <div class="login-form">
                <div class="row">
                    <input id="login-user" type="text" placeholder="Username" autocomplete="username" />
                </div>
                <div class="row">
                    <input id="login-pass" type="password" placeholder="Password" autocomplete="current-password" />
                </div>
                <button id="btn-login" type="button">Log in</button>
            </div>
            <div id="login-status" class="status"></div>
        </section>

        <section id="panel-search" class="panel hidden">
            <div class="row">
                <input id="query" type="text" placeholder="Enter query..." />
                <input id="limit" type="number" min="1" max="50" value="10" />
                <button id="btn-search" type="button">Run Search</button>
            </div>
            <div id="search-status" class="status"></div>
            <div id="results" class="results"></div>
        </section>

        <section id="panel-add" class="panel hidden">
            <input id="file" type="file" accept=".txt,.md,.docx,.pdf,.html,.htm" multiple />
            <div class="hint">Allowed: txt, md, docx, pdf, html, htm. Max size: 200 KB each. Up to 10 files.</div>
            <div style="margin-top:10px;">
                <button id="btn-add" type="button">Upload &amp; Index</button>
            </div>
            <div id="add-status" class="status"></div>
        </section>
    </div>

    <script>
        // ── Auth state ───────────────────────────────────────────────────────
        let authToken = localStorage.getItem('authToken') || '';
        let currentUser = localStorage.getItem('currentUser') || '';

        function authHeaders(extra) {
            const h = Object.assign({}, extra || {});
            if (authToken) h['Authorization'] = 'Bearer ' + authToken;
            return h;
        }

        // ── Tab management ───────────────────────────────────────────────────
        const tabSearch = document.getElementById('tab-search');
        const tabAdd    = document.getElementById('tab-add');
        const tabLogin  = document.getElementById('tab-login');
        const panelSearch = document.getElementById('panel-search');
        const panelAdd    = document.getElementById('panel-add');
        const panelLogin  = document.getElementById('panel-login');
        const authUserLabel = document.getElementById('auth-user-label');
        const btnLogout = document.getElementById('btn-logout');

        function openTab(name) {
            tabSearch.classList.toggle('active', name === 'search');
            tabAdd.classList.toggle('active', name === 'add');
            tabLogin.classList.toggle('active', name === 'login');
            panelSearch.classList.toggle('hidden', name !== 'search');
            panelAdd.classList.toggle('hidden', name !== 'add');
            panelLogin.classList.toggle('hidden', name !== 'login');
        }

        function updateAuthUI() {
            if (authToken) {
                authUserLabel.textContent = 'Logged in as: ' + currentUser;
                authUserLabel.className = 'ok';
                btnLogout.classList.remove('hidden');
                tabLogin.classList.add('hidden');
                openTab('search');
            } else {
                authUserLabel.textContent = 'Not logged in';
                authUserLabel.className = '';
                btnLogout.classList.add('hidden');
                tabLogin.classList.remove('hidden');
                openTab('login');
            }
        }

        tabSearch.addEventListener('click', () => openTab('search'));
        tabAdd.addEventListener('click', () => openTab('add'));
        tabLogin.addEventListener('click', () => openTab('login'));

        // ── Login ────────────────────────────────────────────────────────────
        const loginUserEl = document.getElementById('login-user');
        const loginPassEl = document.getElementById('login-pass');
        const loginBtn    = document.getElementById('btn-login');
        const loginStatus = document.getElementById('login-status');

        async function doLogin() {
            const username = loginUserEl.value.trim();
            const password = loginPassEl.value;
            if (!username || !password) {
                loginStatus.textContent = 'Please enter username and password.';
                loginStatus.className = 'status err';
                return;
            }
            loginBtn.disabled = true;
            loginStatus.textContent = 'Logging in...';
            loginStatus.className = 'status';
            try {
                const res = await fetch('/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password}),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Login failed');
                authToken = data.access_token;
                currentUser = username;
                localStorage.setItem('authToken', authToken);
                localStorage.setItem('currentUser', currentUser);
                loginPassEl.value = '';
                loginStatus.textContent = '';
                updateAuthUI();
            } catch (err) {
                loginStatus.textContent = err.message;
                loginStatus.className = 'status err';
            } finally {
                loginBtn.disabled = false;
            }
        }

        loginBtn.addEventListener('click', doLogin);
        loginPassEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });

        // ── Logout ───────────────────────────────────────────────────────────
        function doLogout() {
            authToken = '';
            currentUser = '';
            localStorage.removeItem('authToken');
            localStorage.removeItem('currentUser');
            updateAuthUI();
        }
        btnLogout.addEventListener('click', doLogout);

        // ── Handle 401 from any API call ─────────────────────────────────────
        function handleUnauthorized() {
            authToken = '';
            currentUser = '';
            localStorage.removeItem('authToken');
            localStorage.removeItem('currentUser');
            updateAuthUI();
        }

        // ── Search ───────────────────────────────────────────────────────────
        const qInput     = document.getElementById('query');
        const limitInput = document.getElementById('limit');
        const searchBtn  = document.getElementById('btn-search');
        const searchStatus = document.getElementById('search-status');
        const resultsEl  = document.getElementById('results');

        async function runSearch() {
            const query = qInput.value.trim();
            if (!query) return;
            const limit = Math.max(1, Math.min(50, Number(limitInput.value || 10)));
            searchBtn.disabled = true;
            searchStatus.textContent = 'Searching...';
            searchStatus.className = 'status';
            resultsEl.innerHTML = '';
            const startedAt = performance.now();
            try {
                const res = await fetch('/documents/search', {
                    method: 'POST',
                    headers: authHeaders({'Content-Type': 'application/json'}),
                    body: JSON.stringify({query, limit, debug: true}),
                });
                if (res.status === 401) { handleUnauthorized(); return; }
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Search failed');
                const elapsedMs = performance.now() - startedAt;
                const vectorGenMs   = Number(res.headers.get('X-Debug-Vector-Generation-Ms') || '0');
                const lancedbMs     = Number(res.headers.get('X-Debug-Lancedb-Search-Ms') || '0');
                const sqliteMs      = Number(res.headers.get('X-Debug-Sqlite-Search-Ms') || '0');
                const rrfMs         = Number(res.headers.get('X-Debug-Rrf-Ms') || '0');
                const fetchChunksMs = Number(res.headers.get('X-Debug-Fetch-Chunks-Ms') || '0');
                const rerankMs      = Number(res.headers.get('X-Debug-Rerank-Ms') || '0');
                const buildResultsMs = Number(res.headers.get('X-Debug-Build-Results-Ms') || '0');
                searchStatus.textContent =
                    `Found ${data.length} result(s) in ${elapsedMs.toFixed(1)} ms ` +
                    `| vector: ${vectorGenMs.toFixed(1)} ms ` +
                    `| lancedb: ${lancedbMs.toFixed(1)} ms ` +
                    `| sqlite: ${sqliteMs.toFixed(1)} ms ` +
                    `| rrf: ${rrfMs.toFixed(1)} ms ` +
                    `| fetch_chunks: ${fetchChunksMs.toFixed(1)} ms ` +
                    `| rerank: ${rerankMs.toFixed(1)} ms ` +
                    `| build_results: ${buildResultsMs.toFixed(1)} ms`;
                searchStatus.className = 'status ok';
                resultsEl.innerHTML = data.map((r, i) => {
                    const crumbs = (r.breadcrumbs || []).join(' > ');
                    const viewUrl = `/documents/${r.document_id}/view?token=${encodeURIComponent(authToken)}`;
                    return `
                        <article class="item">
                            <div><strong>${i + 1}. <a href="${viewUrl}" target="_blank" rel="noopener noreferrer">${r.document_name}</a></strong> <span class="meta">score ${Number(r.score).toFixed(3)}</span></div>
                            <div class="meta">${crumbs || '(no headings)'}</div>
                            <div>${(r.snippet || '').slice(0, 320)}</div>
                        </article>
                    `;
                }).join('');
            } catch (err) {
                searchStatus.textContent = err.message;
                searchStatus.className = 'status err';
            } finally {
                searchBtn.disabled = false;
            }
        }

        searchBtn.addEventListener('click', runSearch);
        qInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') runSearch(); });

        // ── Upload ───────────────────────────────────────────────────────────
        const fileInput = document.getElementById('file');
        const addBtn    = document.getElementById('btn-add');
        const addStatus = document.getElementById('add-status');
        const maxBytes = 200 * 1024;
        const allowed  = ['txt', 'md', 'docx', 'pdf', 'html', 'htm'];

        async function uploadFile() {
            const files = Array.from(fileInput.files || []);
            if (!files.length) { addStatus.textContent = 'Please choose one or more files.'; addStatus.className = 'status err'; return; }
            if (files.length > 10) { addStatus.textContent = 'You can upload at most 10 files at once.'; addStatus.className = 'status err'; return; }
            for (const file of files) {
                const ext = (file.name.split('.').pop() || '').toLowerCase();
                if (!allowed.includes(ext)) { addStatus.textContent = 'Unsupported type. Allowed: ' + allowed.join(', '); addStatus.className = 'status err'; return; }
                if (file.size > maxBytes) { addStatus.textContent = `File too large (${file.name}: ${file.size} bytes). Max is ${maxBytes} bytes.`; addStatus.className = 'status err'; return; }
            }
            addBtn.disabled = true;
            addStatus.textContent = `Uploading and indexing ${files.length} file(s)...`;
            addStatus.className = 'status';
            const startedAt = performance.now();
            try {
                const form = new FormData();
                for (const file of files) form.append('files', file);
                const res = await fetch('/documents/upload', {
                    method: 'POST',
                    headers: authHeaders(),
                    body: form,
                });
                if (res.status === 401) { handleUnauthorized(); return; }
                if (res.status === 403) { addStatus.textContent = 'Permission denied: you need Create permission to upload.'; addStatus.className = 'status err'; return; }
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Upload failed');
                const elapsedMs = performance.now() - startedAt;
                const validateMs  = Number(res.headers.get('X-Debug-Upload-Validate-Ms') || '0');
                const readMs      = Number(res.headers.get('X-Debug-Upload-Read-Ms') || '0');
                const saveMs      = Number(res.headers.get('X-Debug-Upload-Save-Ms') || '0');
                const indexMs     = Number(res.headers.get('X-Debug-Upload-Index-Ms') || '0');
                const reindexMs   = Number(res.headers.get('X-Debug-Upload-Reindex-Ms') || '0');
                const totalMs     = Number(res.headers.get('X-Debug-Upload-Total-Ms') || '0');
                const indexedNow  = (res.headers.get('X-Debug-Upload-Indexed-Now') || 'false') === 'true';
                const pendingBefore = Number(res.headers.get('X-Debug-Upload-Pending-Before') || '0');
                const pendingAfter  = Number(res.headers.get('X-Debug-Upload-Pending-After') || '0');
                const threshold     = Number(res.headers.get('X-Debug-Upload-Threshold') || '0');
                const reindexedCount = Number(res.headers.get('X-Debug-Upload-Reindexed-Count') || '0');
                const fileSummary = (data.files || []).map((item) => item.name).join(', ');
                addStatus.textContent =
                    `${indexedNow ? 'Reindexed now' : 'Queued for reindex'}: ${fileSummary} ` +
                    `| files: ${(data.files || []).length} ` +
                    `| pending: ${pendingBefore} → ${pendingAfter} (threshold ${threshold}) ` +
                    `| reindexed docs: ${reindexedCount} ` +
                    `| elapsed: ${elapsedMs.toFixed(1)} ms ` +
                    `| server total: ${totalMs.toFixed(1)} ms ` +
                    `| validate: ${validateMs.toFixed(1)} ms ` +
                    `| read: ${readMs.toFixed(1)} ms ` +
                    `| save: ${saveMs.toFixed(1)} ms ` +
                    `| pending-index: ${indexMs.toFixed(1)} ms ` +
                    `| reindex: ${reindexMs.toFixed(1)} ms`;
                addStatus.className = 'status ok';
                fileInput.value = '';
            } catch (err) {
                addStatus.textContent = err.message;
                addStatus.className = 'status err';
            } finally {
                addBtn.disabled = false;
            }
        }

        addBtn.addEventListener('click', uploadFile);

        // ── Init ─────────────────────────────────────────────────────────────
        updateAuthUI();
    </script>
</body>
</html>
"""
