// PR Review Agent - Frontend Logic
const API = '/api';
let refreshInterval = null;
let currentFindings = [];
let selectedRepoPath = '';
let selectedFile = '';
let sourceViewerRepo = '';

// ============================================================
// Navigation
// ============================================================
function showPage(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));
    const el = document.getElementById('page-' + page);
    if (el) el.classList.add('active');
    const nav = document.getElementById('nav-' + page);
    if (nav) nav.classList.add('active');
    if (page === 'dashboard') loadDashboard();
    if (page === 'config') loadConfig();
    if (page === 'new-task') initCreateForm();
    clearInterval(refreshInterval);
}

// ============================================================
// Dashboard
// ============================================================
async function loadDashboard() {
    try {
        const res = await fetch(API + '/tasks');
        const data = await res.json();
        renderStats(data.stats);
        renderTaskList(data.tasks);
    } catch (e) {
        console.error('Failed to load dashboard:', e);
    }
}

function renderStats(stats) {
    const items = [
        { label: '\u603b\u4efb\u52a1\u6570', value: stats.total, icon: '\ud83d\udccb', color: 'var(--primary)' },
        { label: '\u8fd0\u884c\u4e2d', value: stats.running, icon: '\u26a1', color: 'var(--info)' },
        { label: '\u5df2\u5b8c\u6210', value: stats.completed, icon: '\u2705', color: 'var(--success)' },
        { label: '\u5931\u8d25', value: stats.failed, icon: '\u274c', color: 'var(--danger)' },
    ];
    document.getElementById('stats-bar').innerHTML = items.map(s =>
        '<div class="stat-card">' +
            '<div class="stat-icon" style="background:' + s.color + '15;color:' + s.color + '">' + s.icon + '</div>' +
            '<div class="stat-value" style="color:' + s.color + '">' + s.value + '</div>' +
            '<div class="stat-label">' + s.label + '</div>' +
        '</div>'
    ).join('');
    startCardTimers();
}

function formatTime(isoStr) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        const pad = n => String(n).padStart(2, '0');
        return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()) + ' ' +
               pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
    } catch(e) { return isoStr; }
}

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '\u8ba1\u7b97\u4e2d...';
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return min > 0 ? min + 'm ' + sec + 's' : sec + 's';
}

function renderTaskList(tasks) {
    const list = document.getElementById('task-list');
    if (!tasks.length) {
        list.innerHTML = '<div class="empty-state">' +
            '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>' +
            '<h3>\u6682\u65e0\u4efb\u52a1</h3><p>\u521b\u5efa\u4e00\u4e2a\u65b0\u4efb\u52a1\u5f00\u59cb AI \u4ee3\u7801\u5ba1\u67e5</p></div>';
        return;
    }
    const modeLabels = { simple: '\ud83d\udfe2 \u7b80\u5355', council: '\ud83d\udfe3 \u59d4\u5458\u4f1a', debate: '\ud83d\udfe0 \u8fa9\u8bba', agentic: '\ud83d\udd34 \u4ee3\u7406' };
    list.innerHTML = tasks.map(t =>
        '<div class="task-card" onclick="showTaskDetail(\'' + t.task_id + '\')">' +
            '<div class="task-info">' +
                '<h3>' + escapeHtml(t.task_id) + '</h3>' +
                '<div class="task-meta">' +
                    '<span>' + (modeLabels[t.mode] || t.mode) + '</span>' +
                    '<span>\ud83d\udcdd ' + escapeHtml(t.repo_path || 'N/A') + '</span>' +
                '</div>' +
            '</div>' +
            '<div class="task-status">' +
                (t.findings_count ? '<span class="findings-count">' + t.findings_count + ' \u4e2a\u53d1\u73b0</span>' : '') +
                '<span class="task-time">\u23f1 ' + (t.status === 'running' && t.started_at ? '<span class="card-timer" data-start="' + escapeAttr(t.started_at) + '" style="color:var(--primary);font-weight:600">0s</span>' : formatTime(t.created_at)) + '</span>' +
                '<span class="badge badge-' + t.status + '">' + statusLabel(t.status) + '</span>' +
                '<button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteTask(\'' + t.task_id + '\')">&#215;</button>' +
            '</div>' +
        '</div>'
    ).join('');
}

// Live timer for dashboard running tasks
let _cardTimerInterval = null;
function startCardTimers() {
    clearInterval(_cardTimerInterval);
    _cardTimerInterval = setInterval(() => {
        document.querySelectorAll('.card-timer').forEach(el => {
            const start = new Date(el.dataset.start).getTime();
            const elapsed = Math.floor((Date.now() - start) / 1000);
            const min = Math.floor(elapsed / 60);
            const sec = elapsed % 60;
            el.textContent = (min > 0 ? min + 'm ' : '') + sec + 's';
        });
    }, 1000);
}

function statusLabel(s) {
    return { pending: '\u5f85\u6267\u884c', running: '\u8fd0\u884c\u4e2d', completed: '\u5df2\u5b8c\u6210', failed: '\u5931\u8d25' }[s] || s;
}

// ============================================================
// Create Task - File Browser + Commit Dropdown
// ============================================================
async function initCreateForm() {
    await loadRepoList();
}

async function loadRepoList() {
    const browser = document.getElementById('file-browser');
    browser.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
        const res = await fetch(API + '/repos');
        const data = await res.json();
        const repos = data.repos || [];
        if (!repos.length) {
            browser.innerHTML = '<div style="padding:12px;color:var(--text-muted)">\u65e0\u53ef\u7528\u4ed3\u5e93</div>';
            return;
        }
        browser.innerHTML = repos.map(r =>
            '<div class="file-browser-item" data-path="' + escapeAttr(r.path) + '" data-name="' + escapeAttr(r.name) + '" onclick="selectRepo(this)">' +
                '<span class="fb-icon">\ud83d\udc22</span>' +
                '<span>' + escapeHtml(r.name) + '</span>' +
                '<span style="margin-left:auto;font-size:11px;color:var(--text-muted)">' + r.file_count + ' files</span>' +
            '</div>'
        ).join('');
        // Auto-select first repo
        if (repos.length) selectRepo(document.querySelector('#file-browser .file-browser-item'));
    } catch(e) {
        browser.innerHTML = '<div style="padding:12px;color:var(--danger)">\u52a0\u8f7d\u5931\u8d25</div>';
    }
}

async function selectRepo(el) {
    const repoPath = el.dataset.path;
    const repoName = el.dataset.name;
    selectedRepoPath = repoPath;
    document.getElementById('repo-path').value = repoPath;

    // Highlight selected
    document.querySelectorAll('#file-browser .file-browser-item').forEach(item => item.classList.remove('selected'));
    el.classList.add('selected');

    // Load commits for this repo
    await loadCommits(repoPath);
}

async function loadCommits(repoPath) {
    const baseSelect = document.getElementById('base-commit');
    const targetSelect = document.getElementById('target-commit');
    baseSelect.innerHTML = '<option>\u52a0\u8f7d\u4e2d...</option>';
    targetSelect.innerHTML = '<option>\u52a0\u8f7d\u4e2d...</option>';

    try {
        const res = await fetch(API + '/repos/commits?repo=' + encodeURIComponent(repoPath));
        const data = await res.json();
        const commits = data.commits || [];

        if (!commits.length) {
            baseSelect.innerHTML = '<option value="HEAD~1">HEAD~1</option>';
            targetSelect.innerHTML = '<option value="HEAD">HEAD</option>';
            // Show hint that this is a single-commit repo
            baseSelect.title = '\u8be5\u4ed3\u5e93\u53ea\u6709 1 \u4e2a\u63d0\u4ea4\uff0c\u65e0\u6cd5\u9009\u62e9\u57fa\u51c6';
            targetSelect.title = '\u8be5\u4ed3\u5e93\u53ea\u6709 1 \u4e2a\u63d0\u4ea4';
            return;
        }

        const options = commits.map((c, i) => {
            const idx = i;
            const prefix = idx === 0 ? '\u2705 \u6700\u65b0\u7248\u672c - ' : (idx === commits.length - 1 ? '\u23ea \u6700\u65e9\u7248\u672c - ' : '');
            const label = prefix + escapeHtml(c.message) + '  (' + escapeHtml(c.date.substring(0, 10)) + ')';
            return '<option value="' + escapeAttr(c.full_hash) + '">' + label + '</option>';
        }).join('');

        baseSelect.innerHTML = options;
        targetSelect.innerHTML = options;
        // Default: target = first (latest), base = second
        if (commits.length > 1) baseSelect.selectedIndex = 1;
        targetSelect.selectedIndex = 0;
    } catch(e) {
        baseSelect.innerHTML = '<option value="HEAD~1">HEAD~1</option>';
        targetSelect.innerHTML = '<option value="HEAD">HEAD</option>';
    }
}

async function loadFileTree(repoPath) {
    // Optional: could show file tree in a section
}

async function createTask(e) {
    e.preventDefault();
    const body = {
        mode: document.getElementById('flow-mode').value,
        repo_path: document.getElementById('repo-path').value,
        base_commit: document.getElementById('base-commit').value,
        target_commit: document.getElementById('target-commit').value,
        pr_description: document.getElementById('pr-desc').value,
        rag_enabled: document.getElementById('rag-enabled').checked,
        max_rounds: parseInt(document.getElementById('max-rounds').value),
    };
    try {
        const res = await fetch(API + '/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const data = await res.json();
        showPage('dashboard');
        showTaskDetail(data.task_id);
    } catch (e) {
        alert('\u521b\u5efa\u4efb\u52a1\u5931\u8d25: ' + e.message);
    }
}

// ============================================================
// Task Detail
// ============================================================
async function showTaskDetail(taskId) {
    sourceViewerRepo = '';  // reset
    clearInterval(refreshInterval);
    showPage('task-detail');
    const container = document.getElementById('task-detail-content');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>\u52a0\u8f7d\u4e2d...</div>';

    async function refresh() {
        try {
            const res = await fetch(API + '/tasks/' + taskId);
            const task = await res.json();
            sourceViewerRepo = task.repo_path || '';

            let html = '<div class="detail-header">' +
                '<div class="page-header"><div>' +
                    '<h1>' + escapeHtml(task.task_id) + ' <span class="badge badge-' + task.status + '">' + statusLabel(task.status) + '</span></h1>' +
                    '<div class="detail-meta">' +
                        '<div class="detail-meta-item">\ud83d\udd04 \u6a21\u5f0f: ' + escapeHtml(task.mode) + '</div>' +
                        '<div class="detail-meta-item">\ud83d\udcdd \u4ed3\u5e93: ' + escapeHtml(task.repo_path || 'N/A') + '</div>' +
                        '<div class="detail-meta-item">\u23f1 \u8017\u65f6: ' + (task.status === 'running' ? '<span id="detail-timer" style="color:var(--primary);font-weight:600">0s</span>' : formatDuration(task.duration_seconds)) + '</div>' +
                        '<div class="detail-meta-item">\ud83d\udd52 \u63d0\u4ea4\u65f6\u95f4: ' + formatTime(task.created_at) + '</div>' +
                    '</div>' +
                '</div>' +
                '<div style="display:flex;gap:8px">' +
                    '<button class="btn btn-outline" onclick="openSourceViewerByPath(sourceViewerRepo)">\ud83d\udc41 \u67e5\u770b\u6e90\u6587\u4ef6</button>' +
                    '<button class="btn btn-ghost" onclick="showPage(\'dashboard\')">\u2190 \u8fd4\u56de</button>' +
                '</div>' +
                '</div></div>';

            if (task.status === 'running') {
                html += '<div class="detail-section"><div class="loading"><div class="spinner"></div>\u5ba1\u67e5\u8fdb\u884c\u4e2d... <span id="live-timer" style="font-weight:600;color:var(--primary)"></span></div></div>';
                if (task.started_at) {
                    const startTime = new Date(task.started_at).getTime();
                    const timerEl = document.getElementById('live-timer');
                    function updateTimer() {
                        const elapsed = Math.floor((Date.now() - startTime) / 1000);
                        const min = Math.floor(elapsed / 60);
                        const sec = elapsed % 60;
                        const txt = (min > 0 ? min + 'm ' : '') + sec + 's';
                        if (timerEl) timerEl.textContent = txt;
                        const dtEl = document.getElementById('detail-timer');
                        if (dtEl) dtEl.textContent = txt;
                    }
                    updateTimer();
                    setInterval(updateTimer, 1000);
                }
            }

            if (task.status === 'completed' || task.status === 'failed') {
                try {
                    const fRes = await fetch(API + '/tasks/' + taskId + '/findings');
                    if (fRes.ok) html += renderFindings(await fRes.json());
                } catch(e) {}

                try {
                    const rRes = await fetch(API + '/tasks/' + taskId + '/report');
                    if (rRes.ok) html += renderReport(await rRes.text(), task);
                } catch(e) {}

                if (task.judge_result) html += renderJudge(task.judge_result);
            }

            container.innerHTML = html;
            if (task.judge_result && task.judge_result.scores) {
                setTimeout(() => initJudgeChart(task.judge_result.scores), 100);
            }
            if (task.status === 'running') {
                // Clear old timer if exists, keep polling
                setTimeout(refresh, 2000);
            } else {
                clearInterval(refreshInterval);
            }
        } catch (e) {
            container.innerHTML = '<div class="empty-state"><h3>\u52a0\u8f7d\u5931\u8d25</h3><p>' + escapeHtml(e.message) + '</p></div>';
        }
    }
    await refresh();
}

// ============================================================
// Source Code Viewer (Feature #2)
// ============================================================
async function openSourceViewerByPath(fullPath) {
    if (!fullPath) { alert('\u65e0\u4ed3\u5e93\u8def\u5f84'); return; }
    // Pass full path directly - backend handles both absolute and relative paths
    openSourceViewer(fullPath);
}

async function openSourceViewer(repoPath) {
    if (!repoPath) { alert('\u65e0\u4ed3\u5e93\u8def\u5f84'); return; }

    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.className = 'source-modal-overlay';
    overlay.id = 'source-modal';
    overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
    overlay.innerHTML =
        '<div class="source-modal">' +
            '<div class="source-modal-header">' +
                '<h3 id="source-modal-title">\ud83d\udcc2 ' + escapeHtml(repoPath.split(/[\\/]/).pop() || repoPath) + '</h3>' +
                '<button class="source-modal-close" onclick="document.getElementById(\'source-modal\').remove()">&#215;</button>' +
            '</div>' +
            '<div class="source-modal-body" id="source-modal-body">' +
                '<div class="loading"><div class="spinner"></div></div>' +
            '</div>' +
        '</div>';
    document.body.appendChild(overlay);

    // Load file tree
    await loadSourceTree(repoPath, '');
}


function goUpDir() {
    const current = sourceViewerCurrentPath || '';
    const parent = current.includes('/') ? current.substring(0, current.lastIndexOf('/')) : '';
    loadSourceTree(sourceViewerRepo, parent);
}

async function loadSourceTree(repoPath, subPath) {
    sourceViewerRepo = repoPath;
    const body = document.getElementById('source-modal-body');
    body.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const url = API + '/repos/files?path=' + encodeURIComponent(subPath || repoPath);
        const res = await fetch(url);
        const data = await res.json();
        const items = data.items || [];

        let html = '';
        if (subPath) {
            const parent = subPath.includes('/') ? subPath.substring(0, subPath.lastIndexOf('/')) : repoPath;
            html += '<div class="breadcrumb">' +
                '<span onclick="goUpDir()">~</span>' +
                '<span class="sep">/</span>' +
                '<span onclick="goUpDir()">..</span>' +
            '</div>';
        }

        html += '<div class="file-browser" style="border:none;border-radius:0;max-height:none">';
        items.forEach(item => {
            const icon = item.type === 'dir' ? '\ud83d\udcc1' : '\ud83d\udcc4';
            const clickHandler = item.type === 'dir'
                ? "loadSourceTree(this.dataset.repo, this.dataset.path)"
                : "loadSourceFile(this.dataset.repo, this.dataset.path)";
            html += '<div class="file-browser-item" data-repo="' + escapeAttr(repoPath) + '" data-path="' + escapeAttr(item.path) + '" onclick="' + clickHandler + '">' +
                '<span class="fb-icon">' + icon + '</span>' +
                '<span>' + escapeHtml(item.name) + '</span>' +
            '</div>';
        });
        html += '</div>';
        body.innerHTML = html;
    } catch(e) {
        body.innerHTML = '<div style="padding:16px;color:var(--danger)">\u52a0\u8f7d\u5931\u8d25</div>';
    }
}

async function loadSourceFile(repoPath, filePath) {
    const body = document.getElementById('source-modal-body');
    const title = document.getElementById('source-modal-title');
    title.textContent = '\ud83d\udcc4 ' + filePath;
    body.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const res = await fetch(API + '/repos/file?repo=' + encodeURIComponent(repoPath) + '&path=' + encodeURIComponent(filePath));
        if (!res.ok) throw new Error('Failed to load');
        const content = await res.text();
        renderSourceCode(body, content, filePath);
    } catch(e) {
        body.innerHTML = '<div style="padding:16px;color:var(--danger)">\u6587\u4ef6\u52a0\u8f7d\u5931\u8d25</div>';
    }
}

function renderSourceCode(container, content, filePath) {
    const lines = content.split('\n');
    const ext = filePath.split('.').pop().toLowerCase();

    // Python keywords to highlight in red
    const pyKeywords = ['def', 'class', 'import', 'from', 'return', 'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'finally', 'with', 'as', 'raise', 'pass', 'break', 'continue', 'and', 'or', 'not', 'in', 'is', 'None', 'True', 'False', 'lambda', 'yield', 'async', 'await'];

    // JS keywords
    const jsKeywords = ['function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'finally', 'new', 'class', 'import', 'export', 'from', 'async', 'await', 'null', 'undefined', 'true', 'false', 'throw', 'switch', 'case', 'break', 'continue'];

    const keywords = ext === 'py' ? pyKeywords : (ext === 'js' || ext === 'ts') ? jsKeywords : [];

    let html = '<div class="source-code">';
    lines.forEach((line, i) => {
        let escaped = escapeHtml(line);
        if (keywords.length) {
            keywords.forEach(kw => {
                const regex = new RegExp('\\b(' + kw + ')\\b', 'g');
                escaped = escaped.replace(regex, '<span class="kw-red">$1</span>');
            });
        }
        html += '<div class="code-line"><span class="line-num">' + (i + 1) + '</span><span class="line-content">' + escaped + '</span></div>';
    });
    html += '</div>';
    container.innerHTML = html;
}

// ============================================================
// Findings Rendering
// ============================================================
function renderFindings(data) {
    const findings = data.findings || [];
    if (!findings.length) return '<div class="detail-section"><h3>\ud83d\udd0d \u4ee3\u7801\u53d1\u73b0</h3><p style="color:var(--text-muted)">\u672a\u53d1\u73b0\u95ee\u9898\uff0c\u4ee3\u7801\u8d28\u91cf\u826f\u597d \u2728</p></div>';

    const counts = data.severity_counts || {};
    currentFindings = findings;
    let html = '<div class="detail-section">';
    html += '<h3>\ud83d\udd0d \u4ee3\u7801\u53d1\u73b0 <span class="section-count">' + findings.length + '</span></h3>';

    html += '<div class="severity-filter">';
    const sevColors = { P0: 'var(--p0)', P1: 'var(--p1)', P2: 'var(--p2)', P3: 'var(--p3)' };
    ['P0', 'P1', 'P2', 'P3'].forEach(sev => {
        const cnt = counts[sev] || 0;
        if (cnt > 0) html += '<span class="severity-chip" style="background:' + sevColors[sev] + '12;border-color:' + sevColors[sev] + '40"><span class="chip-dot" style="background:' + sevColors[sev] + '"></span>' + sev + ': ' + cnt + '</span>';
    });
    html += '</div>';

    findings.forEach(f => {
        const sev = (f.severity || 'p3').toLowerCase();
        html += '<div class="finding-card" data-severity="' + escapeAttr(f.severity) + '" onclick="this.classList.toggle(\'open\')">';
        html += '<div class="finding-header">';
        html += '<span class="severity-dot ' + sev + '"></span>';
        html += '<div class="finding-title-group">';
        html += '<div class="finding-title"><span class="finding-id">' + escapeHtml(f.id) + '</span>' + escapeHtml(f.title) + '</div>';
        html += '<div class="finding-quick-meta"><span>' + escapeHtml(f.category) + '</span><span>' + escapeHtml(f.file_path) + (f.line_range ? ' L' + f.line_range : '') + '</span><span>\u7f6e\u4fe1\u5ea6: ' + Math.round((f.confidence || 0) * 100) + '%</span></div>';
        html += '</div>';
        html += '<svg class="finding-toggle" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>';
        html += '</div>';
        html += '<div class="finding-body">';
        html += '<div class="finding-detail-grid">';
        html += '<span class="finding-detail-label">\u4e25\u91cd\u7ea7\u522b</span><span><span class="badge badge-' + sev + '">' + escapeHtml(f.severity) + '</span></span>';
        html += '<span class="finding-detail-label">\u5206\u7c7b</span><span>' + escapeHtml(f.category) + '</span>';
        html += '<span class="finding-detail-label">\u6587\u4ef6</span><span>' + escapeHtml(f.file_path) + '</span>';
        if (f.line_range) html += '<span class="finding-detail-label">\u884c\u53f7</span><span>' + escapeHtml(f.line_range) + '</span>';
        html += '</div>';
        if (f.description) html += '<p style="margin-top:10px;font-size:13px;line-height:1.6">' + escapeHtml(f.description) + '</p>';
        if (f.evidence) html += '<div class="finding-evidence">' + escapeHtml(f.evidence) + '</div>';
        if (f.suggestion) html += '<div class="finding-suggestion">' + escapeHtml(f.suggestion) + '</div>';
        if (f.spec_reference) html += '<p style="margin-top:6px;font-size:11px;color:var(--text-muted)">\ud83d\udcda ' + escapeHtml(f.spec_reference) + '</p>';
        html += '</div></div>';
    });

    html += '</div>';
    return html;
}

// ============================================================
// Report Rendering
// ============================================================
function renderReport(reportText, task) {
    if (!reportText || !reportText.trim()) return '';
    let html = '<div class="detail-section">';
    html += '<h3>\ud83d\udcdd \u5ba1\u67e5\u62a5\u544a</h3>';
    if (task.verdict) {
        const vIcons = { approve: '\u2705', comment: '\ud83d\udcac', request_changes: '\u274c' };
        const vLabels = { approve: '\u6279\u51c6\u5408\u5e76', comment: '\u5efa\u8bae\u4fee\u6539', request_changes: '\u8981\u6c42\u4fee\u6539' };
        html += '<div class="verdict-banner verdict-' + task.verdict + '"><span class="verdict-icon">' + (vIcons[task.verdict] || '') + '</span><span>' + (vLabels[task.verdict] || task.verdict) + '</span></div>';
    }
    html += '<div class="report-container">' + markdownToHtml(reportText) + '</div></div>';
    return html;
}

function markdownToHtml(md) {
    let h = escapeHtml(md);
    h = h.replace(/\x60\x60\x60(\w*)\n([\s\S]*?)\n\x60\x60\x60/g, (m, l, c) => '<pre><code>' + c + '</code></pre>');
    h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/\*(.+?)\*/g, '<em>$1</em>');
    h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
    h = h.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    h = h.replace(/^- (.+)$/gm, '<li>$1</li>');
    h = h.replace(/(<li>[\s\S]*?<\/li>\n?)+/g, '<ul>$&</ul>');
    h = h.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    h = h.replace(/^---$/gm, '<hr>');
    h = h.replace(/\n\n/g, '</p><p>');
    h = '<p>' + h + '</p>';
    h = h.replace(/<p>\s*<\/p>/g, '');
    ['h1','h2','h3','pre','ul','table','blockquote','hr'].forEach(tag => {
        h = h.replace(new RegExp('<p>\\s*(<' + tag + '[^>]*>)', 'g'), '$1');
        h = h.replace(new RegExp('(<\/' + tag + '>)\\s*<\/p>', 'g'), '$1');
    });
    return h;
}

// ============================================================
// Judge Chart
// ============================================================
function renderJudge(judge) {
    if (!judge || !judge.scores) return '';
    return '<div class="detail-section"><h3>\ud83c\udfaf AI \u8bc4\u5ba1 <span class="section-count">\u603b\u5206: ' + (judge.scores.total_score || 0) + '/100</span></h3><div class="chart-container"><canvas id="judgeChart"></canvas></div></div>';
}

function initJudgeChart(scores) {
    const ctx = document.getElementById('judgeChart');
    if (!ctx) return;
    const labels = ['\u5173\u952e\u98ce\u9669', '\u8bc1\u636e\u8d28\u91cf', '\u98ce\u9669\u51c6\u786e', '\u566a\u58f0', '\u53ef\u64cd\u4f5c', '\u62a5\u544a\u6e05\u6670'];
    const keys = ['critical_risk_coverage', 'evidence_quality', 'risk_accuracy', 'noise_control', 'actionability', 'report_clarity'];
    const values = keys.map(k => scores[k] || 0);
    const colors = values.map(v => v >= 80 ? '#10b981' : v >= 60 ? '#f59e0b' : '#ef4444');
    new Chart(ctx, {
        type: 'radar',
        data: { labels, datasets: [{ label: '\u8bc4\u5206', data: values, backgroundColor: 'rgba(99,102,241,0.15)', borderColor: 'rgba(99,102,241,0.8)', borderWidth: 2, pointBackgroundColor: colors, pointBorderColor: '#fff', pointBorderWidth: 2, pointRadius: 5 }] },
        options: { responsive: true, scales: { r: { beginAtZero: true, max: 100, ticks: { stepSize: 20 }, pointLabels: { font: { size: 12 } }, grid: { color: 'rgba(0,0,0,0.06)' } } }, plugins: { legend: { display: false } } }
    });
}

// ============================================================
// Config
// ============================================================
async function loadConfig() {
    try {
        const res = await fetch(API + '/config');
        const data = await res.json();
        const ci = (k, v) => '<div class="config-item"><span class="config-key">' + escapeHtml(k) + '</span><span class="config-value">' + escapeHtml(v || '\u672a\u8bbe\u7f6e') + '</span></div>';
        let html = '<div class="config-card"><h3>\ud83e\udde0 MiMo \u6a21\u578b</h3>';
        html += ci('API \u5730\u5740', data.mimo?.api_url);
        html += ci('API \u5bc6\u94a5', data.mimo?.api_key);
        html += ci('\u6a21\u578b\u540d\u79f0', data.mimo?.model_name);
        html += ci('\u79bb\u7ebf\u6a21\u5f0f', data.offline_mode ? '\u662f' : '\u5426');
        html += '</div><div class="config-card"><h3>\ud83d\udcc2 Embedding</h3>';
        html += ci('API \u5730\u5740', data.embedding?.api_url);
        html += ci('API \u5bc6\u94a5', data.embedding?.api_key);
        html += '</div><p style="font-size:12px;color:var(--text-muted);margin-top:16px">\u5bc6\u94a5\u5b58\u50a8\u5728 .env \u6587\u4ef6\u4e2d</p>';
        document.getElementById('config-content').innerHTML = html;
    } catch (e) {
        document.getElementById('config-content').innerHTML = '<div class="empty-state"><h3>\u52a0\u8f7d\u5931\u8d25</h3></div>';
    }
}

// ============================================================
// Actions
// ============================================================
async function deleteTask(taskId) {
    if (!confirm('\u786e\u8ba4\u5220\u9664\u4efb\u52a1 ' + taskId + ' \u5417\uff1f')) return;
    await fetch(API + '/tasks/' + taskId, { method: 'DELETE' });
    loadDashboard();
}

async function restartTask(taskId) {
    const res = await fetch(API + '/tasks/' + taskId + '/restart', { method: 'POST' });
    const data = await res.json();
    showTaskDetail(data.task_id);
}

// ============================================================
// Helpers
// ============================================================
function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text || '';
    return d.innerHTML;
}

function escapeAttr(text) {
    return (text || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

loadDashboard();
