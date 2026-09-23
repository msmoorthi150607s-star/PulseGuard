/**
 * PULSEGUARD Dashboard JavaScript
 * 
 * Handles:
 * - API communication
 * - Data display
 * - Chart updates
 * - Auto-refresh
 * - Alert notifications
 */

// ============================================
// Configuration
// ============================================

// API configuration - Flask API server address
// Default: Flask runs on port 5000, dashboard on port 8000
const API_BASE_URL = 'http://localhost:5000';  // Flask API
                          // Use '' only if dashboard is served BY Flask itself

// Refresh interval in milliseconds
const REFRESH_INTERVAL = 5000;  // 5 seconds

// Chart configuration
const CHART_MAX_POINTS = 50;  // Maximum points to show on charts

// ============================================
// State
// ============================================

let temperatureChart = null;
let vibrationChart = null;
let chartLabels = [];
let chartTemperatures = [];
let chartVibrations = [];
let lastReading = null;
let lastPrediction = null;

// ============================================
// Utility Functions
// ============================================

/**
 * Format timestamp to readable date/time
 */
function formatTimestamp(timestamp) {
    if (!timestamp) return '--';
    
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) {
        // Try to handle millisecond timestamps
        const msDate = new Date(timestamp);
        if (!isNaN(msDate.getTime())) {
            return msDate.toLocaleString();
        }
        return '--';
    }
    
    return date.toLocaleString();
}

/**
 * Format timestamp for API (milliseconds since epoch)
 */
function getTimestampMs() {
    return Date.now();
}

/**
 * Show alert banner
 */
function showAlert(message, type = 'critical') {
    const alert = document.getElementById('maintenance-alert');
    const alertMessage = document.getElementById('alert-message');
    
    if (!alert || !alertMessage) return;
    
    alertMessage.textContent = message;
    alert.style.display = 'flex';
}

/**
 * Hide alert banner
 */
function hideAlert() {
    const alert = document.getElementById('maintenance-alert');
    if (alert) {
        alert.style.display = 'none';
    }
}

/**
 * Update status indicator
 */
// Data freshness window: a reading counts as 'live' if newer than this.
// ESP32 sends every ~5s, so 30s gives plenty of margin.
const LIVE_DATA_WINDOW_MS = 30000;

/**
 * Update the header indicator based on DATA FRESHNESS, not just API reachability:
 *   LIVE           (green, pulsing) - newest reading within the last 30s
 *   DATA <age> OLD (amber)          - API works, device stopped sending
 *   NO DATA        (dim)            - API works, nothing in Firebase yet
 *   OFFLINE        (dim)            - Flask API unreachable
 */
function updateApiStatus(connected) {
    const statusDot = document.querySelector('.header-status .status-dot');
    const statusText = document.querySelector('.header-status .status-text');
    
    if (!statusDot || !statusText) return;
    
    statusDot.classList.remove('connected', 'stale');
    
    if (!connected) {
        statusText.textContent = 'OFFLINE';
        return;
    }
    
    const latestTs = lastReading?.timestamp || lastPrediction?.timestamp || 0;
    const age = Date.now() - latestTs;
    
    if (latestTs > 0 && age <= LIVE_DATA_WINDOW_MS) {
        statusDot.classList.add('connected');
        statusText.textContent = 'LIVE';
    } else if (latestTs > 0) {
        statusDot.classList.add('stale');
        const mins = Math.max(1, Math.floor(age / 60000));
        const ageLabel = mins >= 60
            ? `${Math.floor(mins / 60)}h ${mins % 60}m`
            : `${mins}m`;
        statusText.textContent = `DATA ${ageLabel} OLD`;
    } else {
        statusText.textContent = 'NO DATA';
    }
}

/**
 * Format temperature with color based on value
 */
function formatTemperature(temp) {
    const tempEl = document.getElementById('temperature');
    if (!tempEl) return;
    
    tempEl.textContent = temp !== null ? temp.toFixed(1) : '--';
}

/**
 * Format vibration with color based on value
 */
function formatVibration(vib) {
    const vibEl = document.getElementById('vibration');
    if (!vibEl) return;
    
    vibEl.textContent = vib !== null ? vib.toFixed(2) : '--';
}

/**
 * Update machine status display
 */
function updateMachineStatus(prediction, message, shortMessage) {
    const statusBadge = document.getElementById('status-badge');
    const statusLabel = document.getElementById('machine-status');
    const statusLight = statusBadge?.querySelector('.status-light');
    const statusDesc = document.getElementById('status-message');
    
    if (!statusLabel || !statusLight || !statusDesc) return;
    
    const status = prediction || 'unknown';
    statusLabel.textContent = status ? status.toUpperCase() : '--';
    statusLabel.className = 'status-label ' + status;
    statusLight.className = 'status-light ' + status;
    
    // Set description message
    if (shortMessage) {
        statusDesc.textContent = shortMessage;
    } else if (message) {
        statusDesc.textContent = message.length > 120 ? 
            message.substring(0, 120) + '...' : message;
    } else {
        statusDesc.textContent = 'Awaiting sensor data...';
    }
}

/**
 * Update last updated timestamp
 */
function updateTimestamp(timestamp) {
    const lastUpdatedEl = document.getElementById('last-updated');
    
    if (!lastUpdatedEl) return;
    
    const formatted = formatTimestamp(timestamp);
    lastUpdatedEl.textContent = `Last updated: ${formatted}`;
    
    
}

// ============================================
// API Functions
// ============================================

/**
 * Fetch data from API
 */
async function fetchApi(endpoint) {
    const url = API_BASE_URL ? `${API_BASE_URL}${endpoint}` : endpoint;

    // Perf: 8s timeout so a slow/hung API never leaves the 5s refresh loop
    // stacking up overlapping requests (main cause of dashboard-wide lag).
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);

    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            signal: controller.signal
        });
        clearTimeout(timer);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        clearTimeout(timer);
        console.error(`API error fetching ${endpoint}:`, error);
        updateApiStatus(false);
        throw error;
    }
}

/**
 * Fetch latest reading
 */
async function fetchLatestReading() {
    try {
        const data = await fetchApi('/api/latest');
        
        if (data.temperature !== undefined) {
            lastReading = data;
            updateDisplay(data);
            updateCharts(data);
        }
        
        return data;
    } catch (error) {
        console.error('Failed to fetch latest reading:', error);
        return null;
    }
}

/**
 * Fetch reading history
 */
async function fetchHistory(limit = 50) {
    try {
        const data = await fetchApi(`/api/history?limit=${limit}`);
        updateReadingsTable(data.readings || []);
        return data;
    } catch (error) {
        console.error('Failed to fetch history:', error);
        return null;
    }
}

/**
 * Fetch latest prediction
 */
async function fetchLatestPrediction() {
    try {
        const data = await fetchApi('/api/prediction');
        
        if (data.prediction) {
            lastPrediction = data;
            updateMachineStatus(
                data.prediction,
                data.message,
                data.short_message
            );
            
            // Show alert for critical status
            if (data.prediction === 'critical') {
                showAlert(data.short_message || data.message, 'critical');
            } else if (data.prediction === 'warning') {
                showAlert(data.short_message || data.message, 'warning');
            } else {
                hideAlert();
            }
        }
        
        return data;
    } catch (error) {
        console.error('Failed to fetch prediction:', error);
        return null;
    }
}

/**
 * Make prediction for readings
 */
async function makePrediction(temperature, vibration, recordId = null) {
    try {
        const response = await fetch(`${API_BASE_URL || ''}/api/predict`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                temperature: temperature,
                vibration: vibration,
                record_id: recordId || `manual_${getTimestampMs()}`
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update display with prediction
        if (data.prediction) {
            updateMachineStatus(
                data.prediction,
                data.message,
                data.short_message
            );
            
            // Show alert for critical
            if (data.prediction === 'critical') {
                showAlert(data.short_message || data.message, 'critical');
            } else {
                hideAlert();
            }
        }
        
        return data;
    } catch (error) {
        console.error('Failed to make prediction:', error);
        return null;
    }
}

// ============================================
// Display Functions
// ============================================

/**
 * Update display with latest reading
 */
function updateDisplay(reading) {
    if (!reading) return;
    
    const { temperature, vibration, timestamp } = reading;
    
    formatTemperature(temperature);
    formatVibration(vibration);
    updateTimestamp(timestamp);
}

/**
 * Update charts with new data point
 */
function updateCharts(reading) {
    if (!reading) return;
    
    const { temperature, vibration, timestamp } = reading;
    
    // Add to chart data
    const timeLabel = formatTimestamp(timestamp);
    
    chartLabels.push(timeLabel);
    chartTemperatures.push(temperature);
    chartVibrations.push(vibration);
    
    // Limit chart points
    if (chartLabels.length > CHART_MAX_POINTS) {
        chartLabels.shift();
        chartTemperatures.shift();
        chartVibrations.shift();
    }
    
    // Update charts
    updateTemperatureChart();
    updateVibrationChart();
}

/**
 * Update temperature chart
 */
function updateTemperatureChart() {
    if (!temperatureChart) return;
    
    temperatureChart.data.labels = chartLabels;
    temperatureChart.data.datasets[0].data = chartTemperatures;
    temperatureChart.update('none');  // 'none' for no animation
}

/**
 * Update vibration chart
 */
function updateVibrationChart() {
    if (!vibrationChart) return;
    
    vibrationChart.data.labels = chartLabels;
    vibrationChart.data.datasets[0].data = chartVibrations;
    vibrationChart.update('none');
}

/**
 * Update readings table
 */
function updateReadingsTable(readings) {
    const tbody = document.getElementById('readings-table-body');
    if (!tbody) return;
    
    if (!readings || readings.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="table-loading">Receiving sensor data...</td>
            </tr>
        `;
        return;
    }
    
    // Take last 20 readings for table
    const recentReadings = readings.slice(0, 20);
    
    tbody.innerHTML = recentReadings.map(reading => {
        const { temperature, vibration, timestamp, prediction } = reading;
        const formattedTime = formatTimestamp(timestamp);
        const status = prediction || 'unknown';
        
        return `
            <tr>
                <td class="col-timestamp">${formattedTime}</td>
                <td class="col-temp">${temperature !== null ? temperature.toFixed(1) : '--'}</td>
                <td class="col-vib">${vibration !== null ? vibration.toFixed(2) : '--'}</td>
                <td class="col-status ${status}">${status ? status.toUpperCase() : '--'}</td>
            </tr>
        `;
    }).join('');
}

// ============================================
// Chart Initialization
// ============================================

/**
 * Initialize charts
 */
function initCharts() {
    const tempCtx = document.getElementById('temperature-chart');
    const vibCtx = document.getElementById('vibration-chart');
    
    if (!tempCtx || !vibCtx) {
        console.error('Chart canvas elements not found');
        return;
    }
    
    // Temperature chart
    temperatureChart = new Chart(tempCtx, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [{
                label: 'Temperature',
                data: chartTemperatures,
                borderColor: '#F0A030',
                backgroundColor: 'rgba(240, 160, 48, 0.15)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: '#F0A030',
                pointHoverBorderColor: '#E8EDF1',
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: {
                        color: 'rgba(42, 52, 59, 0.8)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#4A545C',
                        font: {
                            family: 'JetBrains Mono',
                            size: 10
                        },
                        padding: 6
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        display: false
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    });
    
    // Vibration chart
    vibrationChart = new Chart(vibCtx, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [{
                label: 'Vibration',
                data: chartVibrations,
                borderColor: '#4FC3D9',
                backgroundColor: 'rgba(79, 195, 217, 0.15)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: '#4FC3D9',
                pointHoverBorderColor: '#E8EDF1',
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(42, 52, 59, 0.8)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#4A545C',
                        font: {
                            family: 'JetBrains Mono',
                            size: 10
                        },
                        padding: 6
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        display: false
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    });
}

// ============================================
// Main Functions
// ============================================

/**
 * Refresh all data
 */
async function refreshData() {
    try {
        updateApiStatus(true);
        
        // Fetch in parallel
        const [latest, history, prediction] = await Promise.all([
            fetchLatestReading(),
            fetchHistory(50),
            fetchLatestPrediction()
        ]);
        
        return { latest, history, prediction };
    } catch (error) {
        console.error('Refresh error:', error);
        updateApiStatus(false);
        return null;
    }
}

/**
 * Start auto-refresh
 */
function startAutoRefresh() {
    setInterval(refreshData, REFRESH_INTERVAL);
}

/**
 * Initialize dashboard
 */
async function initDashboard() {
    console.log('Initializing PulseGuard Dashboard...');
    
    // Initialize charts first
    initCharts();
    
    // Initial data fetch
    await refreshData();
    
    // Start auto-refresh
    startAutoRefresh();
    
    // Set up refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
            refreshBtn.disabled = true;
            
            await refreshData();
            
            refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
            refreshBtn.disabled = false;
        });
    }
    
    // Set up alert close button
    const alertClose = document.getElementById('alert-close');
    if (alertClose) {
        alertClose.addEventListener('click', hideAlert);
    }
    
    console.log('Dashboard initialized successfully!');
}

// ============================================
// Start Dashboard
// ============================================

// Run when DOM is ready
document.addEventListener('DOMContentLoaded', initDashboard);

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        refreshData,
        initDashboard,
        formatTimestamp,
        formatTemperature,
        formatVibration
    };
}
