/**
 * PulseGuard shared API + auth helper
 * Used by index.html (public monitor), admin/, technical/
 */

// Flask API base (CORS is enabled server-side)
const API_BASE_URL = 'http://localhost:5000';

const AuthStore = {
    save(login) {
        localStorage.setItem('pg_auth', JSON.stringify({
            id_token: login.id_token,
            user: login.user,
            saved_at: Date.now()
        }));
    },
    get() {
        try {
            const raw = localStorage.getItem('pg_auth');
            if (!raw) return null;
            const data = JSON.parse(raw);
            // Firebase ID tokens expire after 1 hour
            if (Date.now() - data.saved_at > 55 * 60 * 1000) return null;
            return data;
        } catch (e) {
            return null;
        }
    },
    clear() {
        localStorage.removeItem('pg_auth');
    },
    requireRole(role) {
        const auth = this.get();
        if (!auth) {
            window.location.href = '../login.html?next=' +
                encodeURIComponent(window.location.pathname);
            return null;
        }
        if (role && auth.user.role !== role) {
            // Wrong dashboard for this role - send them to their own
            window.location.href = auth.user.role === 'admin'
                ? '../admin/' : '../technical/';
            return null;
        }
        return auth;
    }
};

/** Fetch helper that attaches the Firebase ID token when present. */
async function pgFetch(endpoint, options = {}) {
    const auth = AuthStore.get();
    const headers = Object.assign({
        'Accept': 'application/json'
    }, options.headers || {});

    if (auth && auth.id_token) {
        headers['Authorization'] = 'Bearer ' + auth.id_token;
    }
    if (options.body) {
        headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers
    });

    // Token expired / revoked: force re-login
    if (response.status === 401) {
        AuthStore.clear();
        if (!window.location.pathname.includes('login.html')) {
            window.location.href = '../login.html';
        }
        throw new Error('Session expired - please sign in again');
    }

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.message || `HTTP ${response.status}`);
    }
    return data;
}

/** Escape untrusted text before inserting into HTML. */
function pgEscape(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

/** Format an epoch-ms timestamp for display. */
function pgFormatTime(ts) {
    if (!ts) return '--';
    const d = new Date(Number(ts));
    return isNaN(d.getTime()) ? '--' : d.toLocaleString();
}

/**
 * Authenticated file download.
 * <a href> links cannot send the Authorization header, so report/export
 * downloads must go through fetch() with the Bearer token attached.
 */
async function pgDownloadFile(fileName, linkEl) {
    const auth = AuthStore.get();
    if (!auth || !auth.id_token) {
        window.location.href = '../login.html';
        return;
    }
    if (linkEl) linkEl.style.pointerEvents = 'none';
    try {
        const response = await fetch(
            `${API_BASE_URL}/api/download?file=${encodeURIComponent(fileName)}`,
            { headers: { 'Authorization': 'Bearer ' + auth.id_token } }
        );
        if (response.status === 401) {
            AuthStore.clear();
            window.location.href = '../login.html';
            return;
        }
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || data.message || `HTTP ${response.status}`);
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        alert('Download failed: ' + err.message);
    } finally {
        if (linkEl) linkEl.style.pointerEvents = '';
    }
}
