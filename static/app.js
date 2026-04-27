(() => {
    const ALLOWED_EXTENSIONS = ['.mp3', '.mp4', '.wav', '.m4a'];
    const MAX_UPLOAD_MB = 1024;

    const $ = (id) => document.getElementById(id);

    const loginScreen = $('login-screen');
    const appScreen = $('app-screen');
    const loginForm = $('login-form');
    const passwordInput = $('password-input');
    const loginError = $('login-error');
    const logoutBtn = $('logout-btn');

    const dropzone = $('dropzone');
    const fileInput = $('file-input');
    const fileInfo = $('file-info');
    const fileNameEl = $('file-name');
    const fileMetaEl = $('file-meta');
    const clearFileBtn = $('clear-file');
    const transcribeBtn = $('transcribe-btn');
    const cancelBtn = $('cancel-btn');

    const progressCard = $('progress-card');
    const statusText = $('status-text');
    const langText = $('lang-text');
    const durationText = $('duration-text');
    const progressFill = $('progress-fill');
    const progressLabel = $('progress-label');

    const resultCard = $('result-card');
    const resultText = $('result-text');
    const copyBtn = $('copy-btn');
    const downloadBtn = $('download-btn');
    const banner = $('banner');
    const deviceBadge = $('device-badge');

    let selectedFile = null;
    let activeAbort = null;
    let lastResult = null;

    // ---------- helpers ----------

    function showBanner(message, kind = 'error', timeoutMs = 6000) {
        banner.textContent = message;
        banner.className = `banner ${kind}`;
        banner.hidden = false;
        if (timeoutMs > 0) {
            clearTimeout(showBanner._t);
            showBanner._t = setTimeout(() => { banner.hidden = true; }, timeoutMs);
        }
    }

    function hideBanner() {
        banner.hidden = true;
    }

    function formatBytes(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
        return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    }

    function formatDuration(seconds) {
        if (!seconds || isNaN(seconds)) return '—';
        const s = Math.floor(seconds);
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const sec = s % 60;
        if (h > 0) return `${h}h ${m}m ${sec}s`;
        if (m > 0) return `${m}m ${sec}s`;
        return `${sec}s`;
    }

    function fileExt(name) {
        const i = name.lastIndexOf('.');
        return i >= 0 ? name.slice(i).toLowerCase() : '';
    }

    function setProgress(percent) {
        const p = Math.max(0, Math.min(100, percent));
        progressFill.style.width = `${p}%`;
        progressLabel.textContent = `${p.toFixed(1)}%`;
    }

    function resetProgressUi() {
        progressCard.hidden = true;
        statusText.textContent = 'Idle';
        langText.textContent = '—';
        durationText.textContent = '—';
        setProgress(0);
    }

    // ---------- auth ----------

    async function checkAuth() {
        try {
            const res = await fetch('/api/me');
            const data = await res.json();
            return !!data.authenticated;
        } catch {
            return false;
        }
    }

    async function checkHealth() {
        try {
            const res = await fetch('/api/health');
            if (!res.ok) return;
            const data = await res.json();
            if (data && data.device) {
                deviceBadge.textContent = `${data.model} · ${data.device}`;
                deviceBadge.hidden = false;
            }
        } catch { /* ignore */ }
    }

    function showLogin() {
        loginScreen.hidden = false;
        appScreen.hidden = true;
        logoutBtn.hidden = true;
        passwordInput.focus();
    }

    function showApp() {
        loginScreen.hidden = true;
        appScreen.hidden = false;
        logoutBtn.hidden = false;
        checkHealth();
    }

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        loginError.hidden = true;
        const password = passwordInput.value;
        const fd = new FormData();
        fd.append('password', password);
        try {
            const res = await fetch('/api/login', { method: 'POST', body: fd });
            if (res.ok) {
                passwordInput.value = '';
                showApp();
            } else {
                loginError.textContent = 'Invalid password.';
                loginError.hidden = false;
            }
        } catch {
            loginError.textContent = 'Network error. Please try again.';
            loginError.hidden = false;
        }
    });

    logoutBtn.addEventListener('click', async () => {
        try { await fetch('/api/logout', { method: 'POST' }); } catch { /* ignore */ }
        showLogin();
    });

    // ---------- file selection ----------

    function setSelectedFile(file) {
        if (!file) {
            selectedFile = null;
            fileInfo.hidden = true;
            transcribeBtn.disabled = true;
            return;
        }
        const ext = fileExt(file.name);
        if (!ALLOWED_EXTENSIONS.includes(ext)) {
            showBanner(`Unsupported file type "${ext || '(none)'}". Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`, 'error');
            selectedFile = null;
            fileInfo.hidden = true;
            transcribeBtn.disabled = true;
            return;
        }
        if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
            showBanner(`File is too large (${formatBytes(file.size)}). Max is ${MAX_UPLOAD_MB} MB.`, 'error');
            selectedFile = null;
            fileInfo.hidden = true;
            transcribeBtn.disabled = true;
            return;
        }
        hideBanner();
        selectedFile = file;
        fileNameEl.textContent = file.name;
        fileMetaEl.textContent = `${formatBytes(file.size)} · ${ext}`;
        fileInfo.hidden = false;
        transcribeBtn.disabled = false;
    }

    dropzone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        const f = e.target.files && e.target.files[0];
        if (f) setSelectedFile(f);
        fileInput.value = '';
    });

    ['dragenter', 'dragover'].forEach((ev) => {
        dropzone.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dragover');
        });
    });
    ['dragleave', 'drop'].forEach((ev) => {
        dropzone.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');
        });
    });
    dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length > 1) {
            showBanner('Please drop only one file at a time.', 'warn');
            return;
        }
        if (files && files[0]) setSelectedFile(files[0]);
    });

    clearFileBtn.addEventListener('click', () => {
        setSelectedFile(null);
        resetProgressUi();
        resultCard.hidden = true;
    });

    // ---------- SSE parsing over fetch ----------

    async function* sseEvents(stream) {
        const reader = stream.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                let idx;
                while ((idx = buffer.indexOf('\n\n')) !== -1) {
                    const raw = buffer.slice(0, idx);
                    buffer = buffer.slice(idx + 2);
                    const evt = parseSseBlock(raw);
                    if (evt) yield evt;
                }
            }
        } finally {
            reader.releaseLock();
        }
    }

    function parseSseBlock(block) {
        if (!block || block.startsWith(':')) return null; // comment / keepalive
        let event = 'message';
        const dataLines = [];
        for (const line of block.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
        }
        if (!dataLines.length) return null;
        try {
            return { event, data: JSON.parse(dataLines.join('\n')) };
        } catch {
            return { event, data: dataLines.join('\n') };
        }
    }

    // ---------- transcribe ----------

    transcribeBtn.addEventListener('click', async () => {
        if (!selectedFile) return;
        hideBanner();
        resultCard.hidden = true;
        progressCard.hidden = false;
        statusText.textContent = 'Uploading...';
        langText.textContent = '—';
        durationText.textContent = '—';
        setProgress(0);
        transcribeBtn.disabled = true;
        cancelBtn.hidden = false;

        const fd = new FormData();
        fd.append('file', selectedFile);

        activeAbort = new AbortController();
        try {
            const res = await fetch('/api/transcribe', {
                method: 'POST',
                body: fd,
                signal: activeAbort.signal,
            });

            if (res.status === 401) {
                showBanner('Session expired. Please sign in again.', 'warn');
                showLogin();
                return;
            }
            if (!res.ok) {
                let msg = `Server returned ${res.status}`;
                try {
                    const err = await res.json();
                    if (err && err.detail) msg = err.detail;
                } catch { /* ignore */ }
                throw new Error(msg);
            }

            for await (const { event, data } of sseEvents(res.body)) {
                if (event === 'status') {
                    statusText.textContent = data.message || data.phase || '...';
                } else if (event === 'language') {
                    const prob = (data.probability * 100).toFixed(1);
                    langText.textContent = `${data.language} (${prob}%)`;
                    if (data.duration_seconds) {
                        durationText.textContent = formatDuration(data.duration_seconds);
                    }
                } else if (event === 'progress') {
                    setProgress(data.percent);
                    if (data.current_seconds && data.total_seconds) {
                        statusText.textContent = `Transcribing… ${formatDuration(data.current_seconds)} / ${formatDuration(data.total_seconds)}`;
                    }
                } else if (event === 'complete') {
                    setProgress(100);
                    statusText.textContent = 'Done';
                    lastResult = data;
                    resultText.textContent = data.text || '(empty transcript)';
                    resultCard.hidden = false;
                    showBanner('Transcription complete.', 'success', 4000);
                } else if (event === 'error') {
                    throw new Error(data.message || 'Transcription failed');
                }
            }
        } catch (err) {
            if (err.name === 'AbortError') {
                statusText.textContent = 'Cancelled';
                showBanner('Transcription cancelled.', 'warn', 3000);
            } else {
                statusText.textContent = 'Error';
                showBanner(`Error: ${err.message}`, 'error', 0);
            }
        } finally {
            activeAbort = null;
            cancelBtn.hidden = true;
            transcribeBtn.disabled = !selectedFile;
        }
    });

    cancelBtn.addEventListener('click', () => {
        if (activeAbort) activeAbort.abort();
    });

    // ---------- result actions ----------

    downloadBtn.addEventListener('click', () => {
        if (!lastResult) return;
        const blob = new Blob([lastResult.text || ''], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = lastResult.filename || 'transcript.txt';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    });

    copyBtn.addEventListener('click', async () => {
        if (!lastResult) return;
        try {
            await navigator.clipboard.writeText(lastResult.text || '');
            showBanner('Copied to clipboard.', 'success', 2500);
        } catch {
            showBanner('Could not copy. Select and copy manually.', 'warn', 4000);
        }
    });

    // ---------- boot ----------

    (async () => {
        const ok = await checkAuth();
        if (ok) showApp();
        else showLogin();
    })();
})();
