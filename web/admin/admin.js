/**
 * PulseGuard Admin/Owner dashboard logic.
 * Simple views: "Is my machine okay?", service requests, reports.
 */

const auth = AuthStore.requireRole('admin');
if (auth) {
    initAdmin();
}

function initAdmin() {
    document.getElementById('user-name').textContent =
        `${auth.user.name || auth.user.email} - ${auth.user.role}`;

    document.getElementById('logout').addEventListener('click', (e) => {
        e.preventDefault();
        AuthStore.clear();
        window.location.href = '../login.html';
    });

    document.getElementById('request-service-btn').addEventListener('click', requestService);
    document.getElementById('admin-report-btn').addEventListener('click', generateReport);

    document.getElementById('email-form').addEventListener('submit', saveEmailSettings);
    document.getElementById('email-verify-btn').addEventListener('click', () => testEmail(false));
    document.getElementById('email-sendtest-btn').addEventListener('click', () => testEmail(true));
    loadEmailSettings();

    refreshAll();
    // Perf: loop guard prevents overlapping refreshes if the API slows down
    const guardAll = pgCreateLoopGuard();
    setInterval(() => guardAll(refreshAll), 10000);
}

async function refreshAll() {
    await Promise.all([
        refreshLive(),
        refreshMachines(),
        refreshRequests(),
        refreshMaintenance()
    ]);
}

// ------------------------------------------------------------
// Live condition
// ------------------------------------------------------------
let lastHealth = 'unknown';

async function refreshLive() {
    try {
        const data = await pgFetch('/api/latest');
        const health = (data.prediction || 'unknown').toLowerCase();

        document.getElementById('temp-value').textContent =
            data.temperature != null ? data.temperature.toFixed(1) + ' C' : '--';
        document.getElementById('vib-value').textContent =
            data.vibration != null ? data.vibration.toFixed(2) : '--';
        document.getElementById('last-update').textContent = pgFormatTime(data.timestamp);

        // Only rebuild the banner when the state changes (avoids flicker)
        if (health !== lastHealth) {
            lastHealth = health;
            const banner = document.getElementById('health-banner');
            const title = document.getElementById('health-title');
            const msg = document.getElementById('health-msg');

            banner.className = 'health-banner ' + health;
            if (health === 'normal') {
                title.textContent = 'MACHINE NORMAL';
                msg.textContent = 'Everything looks good.';
            } else if (health === 'warning') {
                title.textContent = 'MACHINE ATTENTION';
                msg.textContent = 'Please check the machine.';
            } else if (health === 'critical') {
                title.textContent = 'MACHINE PROBLEM';
                msg.textContent = 'Immediate attention required.';
            } else {
                title.textContent = 'NO DATA';
                msg.textContent = 'Waiting for sensor data...';
            }
        }
    } catch (err) {
        console.error('Live refresh failed:', err);
    }
}

// ------------------------------------------------------------
// Machines
// ------------------------------------------------------------
async function refreshMachines() {
    const tbody = document.getElementById('machines-body');
    const sel = document.getElementById('sr-machine');
    try {
        const data = await pgFetch('/api/machines');
        const machines = data.machines || [];

        if (!machines.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">' +
                'No machines registered yet. The Technical Team registers machines from their dashboard.</td></tr>';
            sel.innerHTML = '<option value="">Select machine...</option>';
            return;
        }

        tbody.innerHTML = machines.map(m => `
            <tr>
                <td class="mono">${pgEscape(m.machine_id)}</td>
                <td>${pgEscape(m.machine_name)}</td>
                <td>${pgEscape(m.machine_type)}</td>
                <td>${pgEscape(m.location)}</td>
                <td><span class="status-chip ${pgEscape(m.current_health || 'UNKNOWN')}">${pgEscape(m.current_health || 'UNKNOWN')}</span></td>
                <td><span class="power-state ${m.status === 'ON' ? 'on' : 'off'}">${m.status === 'ON' ? 'ON' : 'OFF'}</span></td>
            </tr>`).join('');

        // Keep selection stable across refreshes
        const current = sel.value;
        sel.innerHTML = '<option value="">Select machine...</option>' +
            machines.map(m => `<option value="${pgEscape(m.machine_id)}">${pgEscape(m.machine_id)} - ${pgEscape(m.machine_name)}</option>`).join('');
        if (current) sel.value = current;
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Could not load machines: ${pgEscape(err.message)}</td></tr>`;
    }
}

// ------------------------------------------------------------
// Service requests
// ------------------------------------------------------------
async function refreshRequests() {
    const tbody = document.getElementById('requests-body');
    try {
        const data = await pgFetch('/api/service-requests');
        const requests = data.service_requests || [];

        if (!requests.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No service requests yet.</td></tr>';
            return;
        }

        tbody.innerHTML = requests.map(r => `
            <tr>
                <td class="mono">${pgFormatTime(r.requested_at)}</td>
                <td class="mono">${pgEscape(r.machine_id)}</td>
                <td>${pgEscape(r.issue)}</td>
                <td><span class="status-chip ${pgEscape(r.status)}">${pgEscape(r.status)}</span></td>
                <td>${pgEscape(r.accepted_by || '-')}</td>
            </tr>`).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Could not load requests: ${pgEscape(err.message)}</td></tr>`;
    }
}

// ------------------------------------------------------------
// Maintenance history
// ------------------------------------------------------------
async function refreshMaintenance() {
    const tbody = document.getElementById('maintenance-body');
    try {
        const data = await pgFetch('/api/maintenance-reports');
        const reports = data.maintenance_reports || [];

        if (!reports.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No maintenance performed yet.</td></tr>';
            return;
        }

        tbody.innerHTML = reports.map(r => `
            <tr>
                <td class="mono">${pgFormatTime(r.completed_at)}</td>
                <td class="mono">${pgEscape(r.machine_id)}</td>
                <td>${pgEscape(r.problem_found)}</td>
                <td>${pgEscape(r.action_taken)}</td>
            </tr>`).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Could not load history: ${pgEscape(err.message)}</td></tr>`;
    }
}

// ------------------------------------------------------------
// Actions
// ------------------------------------------------------------
async function requestService() {
    const msg = document.getElementById('sr-msg');
    const machineId = document.getElementById('sr-machine').value;
    const issue = document.getElementById('sr-issue').value.trim() || 'Not specified';

    msg.className = 'msg-banner';
    if (!machineId) {
        msg.textContent = 'Select a machine first.';
        msg.className = 'msg-banner err';
        return;
    }

    try {
        const resp = await pgFetch('/api/service-requests', {
            method: 'POST',
            body: JSON.stringify({
                machine_id: machineId,
                issue: issue,
                prediction: lastHealth
            })
        });
        msg.textContent = `Service request created (${resp.request_id}). The Technical Team has been notified.`;
        msg.className = 'msg-banner ok';
        document.getElementById('sr-issue').value = '';
        refreshRequests();
    } catch (err) {
        msg.textContent = err.message;
        msg.className = 'msg-banner err';
    }
}

async function generateReport() {
    const msg = document.getElementById('report-msg');
    const links = document.getElementById('report-links');
    const btn = document.getElementById('admin-report-btn');

    msg.className = 'msg-banner';
    links.innerHTML = '';
    btn.disabled = true;

    try {
        const resp = await pgFetch('/api/reports/admin');
        const parts = [];
        for (const [fmt, info] of Object.entries(resp.reports || {})) {
            if (info && info.file) {
                const name = info.file.split(/[\\/]/).pop();
                parts.push(`<a href="#" data-file="${encodeURIComponent(name)}">` +
                    `<i class="fas fa-${fmt === 'pdf' ? 'file-pdf' : 'file-excel'}"></i> ${name}</a>`);
            }
        }
        links.innerHTML = parts.join('') || 'No files generated.';
        links.querySelectorAll('a[data-file]').forEach(a =>
            a.addEventListener('click', ev => {
                ev.preventDefault();
                pgDownloadFile(decodeURIComponent(a.dataset.file), a);
            }));
        msg.textContent = 'Reports generated below - click a file to download.';
        msg.className = 'msg-banner ok';
    } catch (err) {
        msg.textContent = err.message;
        msg.className = 'msg-banner err';
    } finally {
        btn.disabled = false;
    }
}

// ------------------------------------------------------------
// Email settings (Set Up Your Mails)
// ------------------------------------------------------------
async function loadEmailSettings() {
    try {
        const s = await pgFetch('/api/settings/email');
        document.getElementById('es-username').value = s.username || '';
        document.getElementById('es-recipient').value = s.recipient || '';
        document.getElementById('es-tech').value = s.tech_recipient || '';
        document.getElementById('es-server').value = s.smtp_server || 'smtp.gmail.com';
        document.getElementById('es-port').value = s.smtp_port || 587;

        const hint = document.getElementById('es-password-hint');
        hint.textContent = s.password_set
            ? 'A password is saved. Leave blank to keep it.'
            : 'Required before alerts can be sent.';
    } catch (err) {
        console.error('Could not load email settings:', err.message);
    }
}

async function saveEmailSettings(e) {
    e.preventDefault();
    const msg = document.getElementById('email-msg');
    msg.className = 'msg-banner';

    // Only send filled fields - blanks keep stored values server-side
    const payload = {};
    const fields = {
        username: 'es-username',
        recipient: 'es-recipient',
        tech_recipient: 'es-tech',
        smtp_server: 'es-server',
        smtp_port: 'es-port'
    };
    for (const [key, id] of Object.entries(fields)) {
        const v = document.getElementById(id).value.trim();
        if (v) payload[key] = v;
    }
    const pw = document.getElementById('es-password').value.trim();
    if (pw) payload.password = pw;

    if (!payload.username) {
        msg.textContent = 'Enter the Gmail / sender account.';
        msg.className = 'msg-banner err';
        return;
    }
    if (!payload.password && !document.getElementById('es-password-hint')
            .textContent.includes('A password is saved')) {
        msg.textContent = 'Enter the App Password (or the saved one is kept automatically).';
        msg.className = 'msg-banner err';
        return;
    }

    try {
        const resp = await pgFetch('/api/settings/email', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        msg.textContent = resp.message;
        msg.className = 'msg-banner ok';
        document.getElementById('es-password').value = '';
        loadEmailSettings();
    } catch (err) {
        msg.textContent = err.message;
        msg.className = 'msg-banner err';
    }
}

async function testEmail(sendReal) {
    const msg = document.getElementById('email-msg');
    msg.className = 'msg-banner';
    msg.textContent = sendReal ? 'Sending test email...' : 'Verifying connection...';
    msg.className = 'msg-banner ok';

    try {
        const resp = await pgFetch('/api/settings/email/test', {
            method: 'POST',
            body: JSON.stringify({ send: sendReal })
        });
        if (resp.success) {
            msg.textContent = sendReal
                ? `Test email sent to ${resp.recipients ? resp.recipients.join(', ') : 'your address'}.`
                : 'Connection verified - SMTP login works.';
            msg.className = 'msg-banner ok';
        } else {
            msg.textContent = resp.message || 'Test failed.';
            msg.className = 'msg-banner err';
        }
    } catch (err) {
        msg.textContent = err.message;
        msg.className = 'msg-banner err';
    }
}
