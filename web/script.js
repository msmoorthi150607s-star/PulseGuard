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

// API configuration - change this to your Flask API URL
const API_BASE_URL = '';  // Empty string for relative URLs (same server)
                          // Or use: 'http://localhost:5000' for local Flask API
                          // Or use: 'https://your-domain.com' for production

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
    const alertIcon = document.getElementById('alert-icon');
    
    if (!alert || !alertMessage) return;
    
    alertMessage.textContent = message;
    
    if (type === 'critical') {
        alertIcon.innerHTML = '<i class="fas fa-exclamation-circle"></i>';
        alert.style.borderColor = 'var(--color-critical)';
        alert.style.background = 'var(--color-critical-bg)';
    } else if (type === 'warning') {
        alertIcon.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
        alert.style.borderColor = 'var(--color-warning)';
        alert.style.background = 'var(--color-warning-bg)';
    }
    
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
function updateApiStatus(connected) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.getElementById('api-status-text');
    
    if (!statusDot || !statusText) return;
    
    if (connected) {
        statusDot.style.background = 'var(--color-normal)';
        statusText.textContent = 'Connected';
    } else {
        statusDot.style.background = 'var(--color-critical)';
        statusText.textContent = 'Disconnected';
    }
}

/**
 * Format temperature with color based on value
 */
function formatTemperature(temp) {
    const tempEl = document.getElementById('temperature');
    if (!tempEl) return;
    
    tempEl.textContent = temp !== null ? temp.toFixed(1) : '--';
    
    // Color based on temperature
    if (temp > 40) {
        tempEl.style.color = 'var(--color-critical)';
    } else if (temp > 38) {
        tempEl.style.color = 'var(--color-warning)';
    } else {
        tempEl.style.color = 'var(--color-text)';
    }
}

/**
 * Format vibration with color based on value
 */
function formatVibration(vib) {
    const vibEl = document.getElementById('vibration');
    if (!vibEl) return;
    
    vibEl.textContent = vib !== null ? vib.toFixed(2) : '--';
    
    // Color based on vibration
    if (vib > 5) {
        vibEl.style.color = 'var(--color-critical)';
    } else if (vib > 2) {
        vibEl.style.color = 'var(--color-warning)';
    } else {
        vibEl.style.color = 'var(--color-text)';
    }
}

/**
 * Update machine status display
 */
function updateMachineStatus(prediction, message, shortMessage) {
    const statusEl = document.getElementById('machine-status');
    const messageEl = document.getElementById('status-message');
    const statusIcon = document.getElementById('status-icon');
    
    if (!statusEl || !messageEl) return;
    
    const status = prediction || 'unknown';
    statusEl.textContent = status ? status.toUpperCase() : '--';
    
    // Set message
    if (shortMessage) {
        messageEl.textContent = shortMessage;
    } else if (message) {
        // Truncate long message for display
        messageEl.textContent = message.length > 100 ? 
            message.substring(0, 100) + '...' : message;
    } else {
        messageEl.textContent = 'No prediction available';
    }
    
    // Update icon and color based on status
    // Reset icon class first
    statusIcon.className = 'fas fa-circle';  // Default
    
    if (status === 'critical') {
        statusEl.style.color = 'var(--color-critical)';
        statusIcon.className = 'fas fa-exclamation-circle';  // Critical icon
        messageEl.style.color = 'var(--color-critical)';
    } else if (status === 'warning') {
        statusEl.style.color = 'var(--color-warning)';
        statusIcon.className = 'fas fa-exclamation-triangle';  // Warning icon
        messageEl.style.color = 'var(--color-warning)';
    } else if (status === 'normal') {
        statusEl.style.color = 'var(--color-normal)';
        statusIcon.className = 'fas fa-check-circle';  // Normal icon
        messageEl.style.color = 'var(--color-normal)';
    } else {
        statusEl.style.color = 'var(--color-text-secondary)';
        statusIcon.className = 'fas fa-question-circle';  // Unknown icon
        messageEl.style.color = 'var(--color-text-secondary)';
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
    
    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
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
    
    // Add subtle glow effect to status cards based on values
    const tempCard = document.querySelector('.temperature-card');
    const vibCard = document.querySelector('.vibration-card');
    
    if (tempCard) {
        if (temperature > 40) {
            tempCard.style.boxShadow = '0 0 25px rgba(239, 68, 68, 0.3)';
        } else if (temperature > 38) {
            tempCard.style.boxShadow = '0 0 25px rgba(245, 158, 11, 0.3)';
        } else {
            tempCard.style.boxShadow = '';
        }
    }
    
    if (vibCard) {
        if (vibration > 5) {
            vibCard.style.boxShadow = '0 0 25px rgba(239, 68, 68, 0.3)';
        } else if (vibration > 2) {
            vibCard.style.boxShadow = '0 0 25px rgba(245, 158, 11, 0.3)';
        } else {
            vibCard.style.boxShadow = '';
        }
    }
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
                <td colspan="4" class="loading">No readings available</td>
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
        
        // Badge class based on status
        let badgeClass = 'badge-normal';
        if (status === 'critical') badgeClass = 'badge-critical';
        else if (status === 'warning') badgeClass = 'badge-warning';
        
        return `
            <tr>
                <td>${formattedTime}</td>
                <td>${temperature !== null ? temperature.toFixed(1) + ' °C' : '--'}</td>
                <td>${vibration !== null ? vibration.toFixed(2) : '--'}</td>
                <td>
                    <span class="badge ${badgeClass}">
                        ${status ? status.toUpperCase() : '--'}
                    </span>
                </td>
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
                label: 'Temperature (°C)',
                data: chartTemperatures,
                borderColor: '#f59e0b',
                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 5
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
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxTicksLimit: 10,
                        maxRotation: 45
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
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 5
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
                    title: {
                        display: true,
                        text: 'Vibration'
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxTicksLimit: 10,
                        maxRotation: 45
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
    console.log('✨ Initializing PulseGuard Dashboard...');
    
    // Initialize charts first
    initCharts();
    
    // Initial data fetch
    await refreshData();
    
    // Update status to show system is active
    const statusMessage = document.getElementById('status-message');
    if (statusMessage && statusMessage.textContent.includes('Initializing')) {
        statusMessage.textContent = 'System ready • Monitoring active';
    }
    
    // Start auto-refresh
    startAutoRefresh();
    
    // Set up refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin fa-fw"></i> Refreshing...';
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
    
    console.log('✅ PulseGuard Dashboard initialized successfully!');
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
