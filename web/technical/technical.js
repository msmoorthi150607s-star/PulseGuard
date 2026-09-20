/**
 * PulseGuard Technical Team dashboard logic.
 * Detailed views: live monitoring, machine management, data pipeline,
 * service workflow, maintenance reports, technical reports.
 */

const auth = AuthStore.requireRole('technical');
if (auth) {
    initTechnical();
}

function initTechnical() {
    document.getElementById('user-name').textContent =
        `${auth.user.name || auth.user.email} - ${auth.user.role}`;

    document.getElementById('logout').addEventListener('click', (e) => {
        e.preventDefault();
        AuthStore.clear();
        window.location.href = '../login.html';
    });

    document.getElementById('machine-form').addEventListener('submit', saveMachine);
    document.getElementById('maintenance-form').addEventListener('submit', saveMaintenance);
    document.getElementById('clean-export-btn').addEventListener('click', runCleaning);
    document.getElementById('raw-export-btn').addEventListener('click', downloadRaw);
    document.getElementById('tech-report-btn').addEventListener('click', generateReport);

    refreshAll();
    setInterval(refreshLive, 5000);
    setInterval(refreshLists, 15000);
}

async function refreshAll() {
    await Promise.all([refreshLive(), refreshLists()]);
}

async function refreshLists() {
    await Promise.all([
        refreshMachines(),
        refreshRequests(),
        refreshPredictions()
    ]);
}

// ------------------------------------------------------------
// Live monitoring
// ------------------------------------------------------------
async function refreshLive() {
    try {
        const data = await pgFetch('/api/latest');

        document.getElementById('temp-value').textContent =
            data.temperature != null ? data.temperature.toFixed(1) + ' C' : '--';
        document.getElementById('vib-value').textContent =
            data.vibration != null ? data.vibration.toFixed(2) : '--';

        const pred = (data.prediction || 'unknown').toUpperCase();
        const predEl = document.getElementById('pred-value');
        predEl.textContent = pred;
        predEl.className = 'value status-chip ' + (data.prediction || 'unknown');
        document.getElementById('pred-source').textContent =
            data.prediction_source === 'stored'
                ? 'from stored prediction'
                : 'computed for display';

        document.getElementById('reading-ts').textContent = pgFormatTime(data.timestamp);

        // Sensor health heuristic: a reading within the last 60s = OK
        const age = data.timestamp ? Date.now() - Number(data.timestamp) : Infinity;
        const sensorEl = document.getElementById('sensor-health');
        if (age < 60000) {
            sensorEl.textContent = 'OK (fresh)';
            sensorEl.style.color = 'var(--normal)';
        } else if (isFinite(age)) {
            sensorEl.textContent = `STALE (${Math.round(age / 60000)}m old)`;
            sensorEl.style.color = 'var(--warning)';
        } else {
            sensorEl.textContent = 'NO DATA';
            sensorEl.style.color = 'var(--text-faint)';
        }
    } catch (err) {
        console.error('Live refresh failed:', err);
    }
}

// ------------------------------------------------------------
// Machine management
// ------------------------------------------------------------
async function refreshMachines() {
    const tbody = document.getElementById('machines-body');
    try {
        const data = await pgFetch('/api/machines');
        const machines = data.machines || [];

        if (!machines.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No machines registered - use the form above.</td></tr>';
        } else {
            tbody.innerHTML = machines.map(m => `
                <tr>
                    <td class="mono">${pgEscape(m.machine_id)}</td>
                    <td>${pgEscape(m.machine_name)}</td>
                    <td>${pgEscape(m.machine_type)}</td>
                    <td>${pgEscape(m.location)}</td>
                    <td class="mono">${pgEscape(m.device_id)}</td>
                    <td><span class="status-chip ${pgEscape(m.current_health || 'UNKNOWN')}">${pgEscape(m.current_health || 'UNKNOWN')}</span></td>
                    <td>
                        <button class="power-toggle ${m.status === 'ON' ? 'on' : 'off'}"
                                onclick="togglePower('${pgEscape(m.machine_id)}', '${m.status === 'ON' ? 'OFF' : 'ON'}')">
                            ${m.status === 'ON' ? 'ON' : 'OFF'}
                        </button>
                    </td>
                </tr>`).join('');
        }

        // Fill maintenance form selects
        const mSel = document.getElementById('mr-machine');
        const curM = mSel.value;
        mSel.innerHTML = '<option value="">Select machine...</option>' +
            machines.map(m => `<option value="${pgEscape(m.machine_id)}">${pgEscape(m.machine_id)}</option>`).join('');
        if (curM) mSel.value = curM;
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state">${pgEscape(err.message)}</td></tr>`;
    }
}

// ------------------------------------------------------------
// Machine power ON/OFF (technical only; admin sees the status)
// ------------------------------------------------------------
async function togglePower(machineId, newState) {
    const authData = AuthStore.get();
    try {
        const resp = await fetch(`${API_BASE_URL}/api/machines/${encodeURIComponent(machineId)}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + authData.id_token
            },
            body: JSON.stringify({ status: newState })
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.message || `HTTP ${resp.status}`);
        refreshMachines();
    } catch (err) {
        alert(`Could not set ${machineId} to ${newState}: ` + err.message);
    }
}

async function saveMachine(e) {
    e.preventDefault();
    const msg = document.getElementById('machine-msg');
    msg.className = 'msg-banner';

    const payload = {
        machine_id: document.getElementById('m-id').value.trim(),
        machine_name: document.getElementById('m-name').value.trim(),
        machine_type: document.getElementById('m-type').value.trim() || 'Rotating Motor',
        location: document.getElementById('m-location').value.trim(),
        device_id: document.getElementById('m-device').value.trim()
    };

    try {
        const resp = await pgFetch('/api/machines', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        msg.textContent = resp.message;
        msg.className = 'msg-banner ok';
        refreshMachines();
    } catch (err) {
        msg.textContent = err.message;
        msg.className = 'msg-banner err';
    }
}

// ------------------------------------------------------------
// Data pipeline
// ------------------------------------------------------------
async function downloadRaw(e) {
    e.preventDefault();
    const authData = AuthStore.get();
    const url = `${API_BASE_URL}/api/export/raw`;
    try {
        const resp = await fetch(url, {
            headers: { 'Authorization': 'Bearer ' + authData.id_token }
        });
        if (!resp.ok) throw new Error('Export failed (HTTP ' + resp.status + ')');
        const blob = await resp.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'readings_raw.xlsx';
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (err) {
        alert('RAW export failed: ' + err.message);
    }
}

async function runCleaning() {
    const msg = document.getElementById('clean-report');
    const links = document.getElementById('clean-links');
    try {
        const resp = await pgFetch('/api/export/clean');
        const r = resp.cleaning_report;
        msg.style.display = 'block';
        msg.textContent =
            `RAW: ${resp.raw_rows} rows -> CLEAN: ${resp.clean_rows} rows\n` +
            `- removed (missing/invalid sensors): ${r.removed_missing_sensor_values}\n` +
            `- removed (duplicates): ${r.removed_duplicates}\n` +
            `- flagged out-of-range (preserved): ${r.flagged_out_of_range}\n` +
            `- interpolated values: ${r.interpolated_values} (no interpolation by design)`;
        links.innerHTML =
            `<a href="#" data-file="readings_clean.xlsx">` +
            `<i class="fas fa-file-excel"></i> readings_clean.xlsx</a>` +
            `<a href="#" data-file="readings_raw.xlsx">` +
            `<i class="fas fa-file-excel"></i> readings_raw.xlsx</a>`;
        links.querySelectorAll('a[data-file]').forEach(a =>
            a.addEventListener('click', ev => {
                ev.preventDefault();
                pgDownloadFile(a.dataset.file, a);
            }));
    } catch (err) {
        msg.style.display = 'block';
        msg.textContent = 'Cleaning failed: ' + err.message;
    }
}

// ------------------------------------------------------------
// Service requests
// ------------------------------------------------------------
async function refreshRequests() {
    const tbody = document.getElementById('requests-body');
    const sel = document.getElementById('mr-request');
    try {
        const data = await pgFetch('/api/service-requests');
        const requests = data.service_requests || [];

        if (!requests.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No service requests.</td></tr>';
        } else {
            tbody.innerHTML = requests.map(r => {
                const canAccept = r.status === 'REQUESTED';
                const canProgress = ['ACCEPTED', 'VISITED', 'IN_PROGRESS'].includes(r.status);
                const actions = [];
                if (canAccept) {
                    actions.push(`<button class="btn btn-success" style="padding:4px 10px; font-size:12px;" onclick="acceptRequest('${pgEscape(r.request_id)}')">Accept</button>`);
                }
                if (canProgress) {
                    for (const s of ['VISITED', 'IN_PROGRESS', 'FIXED']) {
                        if (s !== r.status) {
                            actions.push(`<button class="btn btn-secondary" style="padding:4px 10px; font-size:12px;" onclick="setStatus('${pgEscape(r.request_id)}','${s}')">${s.replace('_', ' ')}</button>`);
                        }
                    }
                }
                if (!actions.length) actions.push('-');
                return `
                <tr>
                    <td class="mono">${pgFormatTime(r.requested_at)}</td>
                    <td class="mono">${pgEscape(r.machine_id)}</td>
                    <td>${pgEscape(r.issue)}</td>
                    <td><span class="status-chip ${pgEscape(r.status)}">${pgEscape(r.status)}</span></td>
                    <td><div class="actions-row">${actions.join('')}</div></td>
                </tr>`;
            }).join('');
        }

        // Maintenance form: only requests that can be completed
        const cur = sel.value;
        const open = requests.filter(r => ['ACCEPTED', 'VISITED', 'IN_PROGRESS', 'FIXED'].includes(r.status));
        sel.innerHTML = '<option value="">- none -</option>' +
            open.map(r => `<option value="${pgEscape(r.request_id)}">${pgEscape(r.request_id)} (${pgEscape(r.machine_id)})</option>`).join('');
        if (cur) sel.value = cur;
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${pgEscape(err.message)}</td></tr>`;
    }
}

async function acceptRequest(requestId) {
    try {
        const resp = await pgFetch(`/api/service-requests/${requestId}/accept`, { method: 'POST' });
        alert(resp.owner_notified
            ? 'Accepted. The owner has been notified by email.'
            : 'Accepted. (Owner email notification was not configured/sent.)');
        refreshRequests();
    } catch (err) {
        alert('Accept failed: ' + err.message);
    }
}

async function setStatus(requestId, status) {
    try {
        await pgFetch(`/api/service-requests/${requestId}/status`, {
            method: 'POST',
            body: JSON.stringify({ status })
        });
        refreshRequests();
    } catch (err) {
        alert('Update failed: ' + err.message);
    }
}

// ------------------------------------------------------------
// Prediction history
// ------------------------------------------------------------
async function refreshPredictions() {
    const tbody = document.getElementById('predictions-body');
    try {
        const data = await pgFetch('/api/history?limit=50');
        const readings = (data.readings || []).filter(r => r.prediction_source === 'stored');

        if (!readings.length) {
            tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No stored predictions yet (poller generates them automatically).</td></tr>';
            return;
        }

        tbody.innerHTML = readings.slice(0, 20).map(r => `
            <tr>
                <td class="mono">${pgFormatTime(r.timestamp)}</td>
                <td class="mono">${pgEscape(String(r.record_id).slice(0, 14))}...</td>
                <td><span class="status-chip ${pgEscape(r.prediction)}">${pgEscape((r.prediction || 'unknown').toUpperCase())}</span></td>
            </tr>`).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" class="empty-state">${pgEscape(err.message)}</td></tr>`;
    }
}

// ------------------------------------------------------------
// Maintenance report
// ------------------------------------------------------------
async function saveMaintenance(e) {
    e.preventDefault();
    const msg = document.getElementById('maintenance-msg');
    msg.className = 'msg-banner';

    const payload = {
        request_id: document.getElementById('mr-request').value || null,
        machine_id: document.getElementById('mr-machine').value,
        problem_found: document.getElementById('mr-problem').value.trim(),
        action_taken: document.getElementById('mr-action').value.trim(),
        parts_replaced: document.getElementById('mr-parts').value.trim() || 'None',
        technician_notes: document.getElementById('mr-notes').value.trim()
    };

    if (!payload.machine_id) {
        msg.textContent = 'Select a machine.';
        msg.className = 'msg-banner err';
        return;
    }

    try {
        const resp = await pgFetch('/api/maintenance-reports', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        msg.textContent = 'Maintenance report saved.';
        msg.className = 'msg-banner ok';
        document.getElementById('maintenance-form').reset();
        refreshLists();
    } catch (err) {
        msg.textContent = err.message;
        msg.className = 'msg-banner err';
    }
}

// ------------------------------------------------------------
// Technical reports
// ------------------------------------------------------------
async function generateReport() {
    const msg = document.getElementById('report-msg');
    const links = document.getElementById('report-links');
    const btn = document.getElementById('tech-report-btn');

    msg.className = 'msg-banner';
    links.innerHTML = '';
    btn.disabled = true;

    try {
        const resp = await pgFetch('/api/reports/technical');
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
