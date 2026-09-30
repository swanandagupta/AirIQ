/**
 * charts.js — AQI trend chart using Chart.js
 * Gradient fills, smooth animations, responsive
 */

let trendsChart = null;
let currentHours = 1;
const MAX_POINTS = 60;

// ── Chart Init ───────────────────────────────────────────
function initChart() {
    const canvas = document.getElementById('trendsChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, 'rgba(34, 211, 238, 0.35)');
    gradient.addColorStop(0.6, 'rgba(34, 211, 238, 0.08)');
    gradient.addColorStop(1, 'rgba(34, 211, 238, 0)');

    trendsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'AQI',
                data: [],
                borderColor: '#22d3ee',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: '#22d3ee',
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2,
                fill: true,
                backgroundColor: gradient,
                tension: 0.45,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400, easing: 'easeInOutQuart' },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(8,14,32,0.95)',
                    borderColor: 'rgba(56,189,248,0.3)',
                    borderWidth: 1,
                    titleColor: '#94a3b8',
                    bodyColor: '#22d3ee',
                    bodyFont: { family: "'JetBrains Mono', monospace", size: 14, weight: '600' },
                    titleFont: { family: "'Inter', sans-serif", size: 11 },
                    padding: 10,
                    cornerRadius: 8,
                    displayColors: false,
                    callbacks: {
                        label: (ctx) => 'AQI: ' + Math.round(ctx.raw),
                        afterLabel: (ctx) => '  ' + aqiLabel(ctx.raw)
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                    ticks: {
                        color: '#475569',
                        font: { family: "'JetBrains Mono', monospace", size: 10 },
                        maxTicksLimit: 6,
                        maxRotation: 0,
                    },
                    border: { display: false }
                },
                y: {
                    min: 0,
                    suggestedMax: 150,
                    grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                    ticks: {
                        color: '#475569',
                        font: { family: "'JetBrains Mono', monospace", size: 10 },
                        maxTicksLimit: 5,
                        callback: (v) => v
                    },
                    border: { display: false }
                }
            }
        }
    });

    // Time range buttons
    document.querySelectorAll('.time-pills .pill-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.time-pills .pill-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentHours = parseInt(btn.dataset.hours);
            fetchChartData(currentHours);
        });
    });
}

// ── AQI Label helper ─────────────────────────────────────
function aqiLabel(v) {
    if (v <= 50)  return '✓ Good';
    if (v <= 100) return '◈ Moderate';
    if (v <= 150) return '⚠ Sensitive';
    if (v <= 200) return '⚠ Unhealthy';
    if (v <= 300) return '⛔ Very Unhealthy';
    return '☠ Hazardous';
}

// ── Update Chart Data ─────────────────────────────────────
function updateChart(labels, data) {
    if (!trendsChart) return;

    trendsChart.data.labels = labels;
    trendsChart.data.datasets[0].data = data;

    // Dynamic Y-axis max
    const maxVal = Math.max(...data, 50);
    trendsChart.options.scales.y.suggestedMax = Math.min(500, maxVal * 1.15);

    // Dynamic border color based on latest AQI
    const latest = data[data.length - 1] || 0;
    const color = aqiToColorChart(latest);
    trendsChart.data.datasets[0].borderColor = color;

    // Update gradient
    const canvas = document.getElementById('trendsChart');
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    gradient.addColorStop(0, hexToRgba(color, 0.35));
    gradient.addColorStop(0.6, hexToRgba(color, 0.06));
    gradient.addColorStop(1, hexToRgba(color, 0));
    trendsChart.data.datasets[0].backgroundColor = gradient;

    trendsChart.update('active');
}

function aqiToColorChart(aqi) {
    if (aqi <= 50)  return '#10b981';
    if (aqi <= 100) return '#22d3ee';
    if (aqi <= 150) return '#f59e0b';
    if (aqi <= 200) return '#f97316';
    if (aqi <= 300) return '#ef4444';
    return '#a855f7';
}

function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}

// ── Fetch Chart Data from API ─────────────────────────────
function fetchChartData(hours = 1) {
    fetch(`/api/history?hours=${hours}&limit=300`)
        .then(r => r.json())
        .then(data => {
            if (data.time_series && data.time_series.length > 0) {
                const labels = data.time_series.map(p => {
                    const d = new Date(p.timestamp * 1000);
                    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
                });
                const values = data.time_series.map(p => p.avg_aqi);
                updateChart(labels, values);
            } else {
                // Simulated fallback
                simulateChart(hours);
            }
        })
        .catch(() => simulateChart(hours));
}

// ── Simulated data fallback ──────────────────────────────
function simulateChart(hours) {
    const now = Date.now();
    const points = Math.min(MAX_POINTS, hours * 12);
    const labels = [], data = [];

    for (let i = points; i >= 0; i--) {
        const t = new Date(now - i * (hours * 3600000 / points));
        labels.push(t.getHours().toString().padStart(2, '0') + ':' + t.getMinutes().toString().padStart(2, '0'));
        data.push(Math.round(60 + Math.sin(i * 0.3) * 30 + Math.random() * 25));
    }
    updateChart(labels, data);
}

// ── Push a single live reading ───────────────────────────
function pushLiveReading(aqi, timestamp) {
    if (!trendsChart) return;

    const t = timestamp ? new Date(timestamp * 1000) : new Date();
    const label = t.getHours().toString().padStart(2, '0') + ':' + t.getMinutes().toString().padStart(2, '0');

    const labels = trendsChart.data.labels;
    const data   = trendsChart.data.datasets[0].data;

    labels.push(label);
    data.push(Math.round(aqi));

    if (labels.length > MAX_POINTS) {
        labels.shift();
        data.shift();
    }

    updateChart(labels, data);
}

// ── Init on DOM ready ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    simulateChart(1);
});