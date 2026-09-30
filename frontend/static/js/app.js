/**
 * app.js — Main AirIQ Dashboard Controller
 * Orchestrates UI updates from WebSocket data and API polling
 */

// ── AQI Helpers ───────────────────────────────────────────
const AQI_LEVELS = [
    { max: 50,  label: 'Good',                      color: '#10b981', glow: '#10b981' },
    { max: 100, label: 'Moderate',                  color: '#f59e0b', glow: '#f59e0b' },
    { max: 150, label: 'Sensitive Groups',           color: '#f97316', glow: '#f97316' },
    { max: 200, label: 'Unhealthy',                 color: '#ef4444', glow: '#ef4444' },
    { max: 300, label: 'Very Unhealthy',             color: '#a855f7', glow: '#a855f7' },
    { max: 500, label: 'Hazardous',                 color: '#7c2d12', glow: '#c084fc' },
];

function getAqiLevel(aqi) {
    return AQI_LEVELS.find(l => aqi <= l.max) || AQI_LEVELS[AQI_LEVELS.length - 1];
}

// AQI → PM2.5 estimate
function aqiToPm25(aqi) {
    if (aqi <= 50)  return (aqi / 50 * 12).toFixed(1);
    if (aqi <= 100) return (12 + (aqi - 50) / 50 * 23.4).toFixed(1);
    if (aqi <= 150) return (35.4 + (aqi - 100) / 50 * 20.3).toFixed(1);
    if (aqi <= 200) return (55.7 + (aqi - 150) / 50 * 89.4).toFixed(1);
    if (aqi <= 300) return (150.5 + (aqi - 200) / 100 * 149.4).toFixed(1);
    return (250 + (aqi - 300) / 200 * 250).toFixed(1);
}

// AQI circumference for SVG gauge (r=90, full circle = 2πr ≈ 565)
function aqiToDash(aqi) {
    const fraction = Math.min(aqi / 400, 1);
    const circumference = 565;
    return `${(fraction * circumference).toFixed(1)} ${circumference}`;
}

// ── Gauge Update ──────────────────────────────────────────
function updateGauge(aqi) {
    const level = getAqiLevel(aqi);

    // Value
    const valEl = document.getElementById('aqiValue');
    if (valEl) {
        valEl.textContent = aqi;
        // Smooth number flip
        valEl.style.transform = 'scale(1.04)';
        setTimeout(() => { valEl.style.transform = 'scale(1)'; }, 300);
    }

    // Category pill
    const catEl = document.getElementById('aqiCategory');
    if (catEl) {
        catEl.textContent = level.label;
        catEl.style.color = level.color;
        catEl.style.borderColor = level.color;
    }

    // SVG arc
    const arc = document.getElementById('gaugeArc');
    if (arc) arc.setAttribute('stroke-dasharray', aqiToDash(aqi));

    // Glow
    const glow = document.getElementById('aqiGlow');
    if (glow) {
        glow.style.background = level.glow;
        glow.style.opacity = aqi > 100 ? '0.45' : '0.28';
    }

    // Meta row
    const pm25 = document.getElementById('pm25Value');
    if (pm25) pm25.textContent = aqiToPm25(aqi);

    const statusText = document.getElementById('aqiStatusText');
    if (statusText) statusText.textContent = level.label;
}

// ── Telemetry Update ──────────────────────────────────────
function updateTelemetry(reading) {
    const set = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };

    set('mq135Value', Math.round(reading.mq135));
    set('mq137Value', Math.round(reading.mq137));

    if (reading.latitude && reading.latitude !== 0) {
        set('latValue', parseFloat(reading.latitude).toFixed(5));
    }
    if (reading.longitude && reading.longitude !== 0) {
        set('lonValue', parseFloat(reading.longitude).toFixed(5));
    }
}

// ── Recommendations Update ────────────────────────────────
function updateRecommendations(aqi) {
    const list = document.getElementById('recommendationsList');
    if (!list) return;

    fetch(`/api/current`)
        .then(r => r.json())
        .then(data => {
            if (data.recommendations && data.recommendations.length > 0) {
                list.innerHTML = data.recommendations
                    .map(r => `<li class="rec-item">${r}</li>`)
                    .join('');
            } else {
                setFallbackRecommendations(aqi, list);
            }
        })
        .catch(() => setFallbackRecommendations(aqi, list));
}

function setFallbackRecommendations(aqi, list) {
    const recs = {
        good:     ['No precautions needed — ideal for all outdoor activities.', 'Air quality is satisfactory.'],
        moderate: ['Unusually sensitive people should limit prolonged exertion.', 'Air quality is acceptable for most people.'],
        sensitive:['Sensitive groups should reduce outdoor activity.', 'Children and elderly: limit exertion.', 'Consider wearing a mask outdoors.'],
        unhealthy:['Everyone should reduce outdoor exertion.', 'Sensitive groups should stay indoors.', 'Monitor symptoms closely.'],
        very:     ['Avoid outdoor activities — health alert conditions.', 'Use air purification indoors.', 'Wear N95 mask if going out.'],
        hazardous:['⚠ Stay indoors — hazardous conditions.', 'Seal windows and doors.', 'Use N95 mask if going outside is essential.'],
    };
    const key = aqi <= 50 ? 'good' : aqi <= 100 ? 'moderate' : aqi <= 150 ? 'sensitive' : aqi <= 200 ? 'unhealthy' : aqi <= 300 ? 'very' : 'hazardous';
    list.innerHTML = recs[key].map(r => `<li class="rec-item">${r}</li>`).join('');
}

// ── Alerts and Insights Feed ─────────────────────────────
let alertCount = 0;

function addAlert(msg, severity = 'medium') {
    const pane = document.getElementById('alertsList');
    if (!pane) return;

    // Remove placeholder
    const empty = pane.querySelector('.feed-empty');
    if (empty) empty.remove();

    const ico = severity === 'high' ? '🔴' : severity === 'low' ? '🔵' : '🟡';
    const item = document.createElement('div');
    item.className = 'feed-item alert';
    item.innerHTML = `
        <div class="feed-icon">${ico}</div>
        <div class="feed-content">
            <div class="feed-msg">${msg}</div>
            <div class="feed-time">${new Date().toLocaleTimeString('en-IN')}</div>
        </div>`;
    pane.insertBefore(item, pane.firstChild);

    // Trim
    while (pane.children.length > 10) pane.removeChild(pane.lastChild);

    alertCount++;
    const badge = document.getElementById('alertCount');
    if (badge) badge.textContent = alertCount;
}

function addInsight(msg) {
    const pane = document.getElementById('insightsList');
    if (!pane) return;

    const empty = pane.querySelector('.feed-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = 'feed-item insight';
    item.innerHTML = `
        <div class="feed-icon">💡</div>
        <div class="feed-content">
            <div class="feed-msg">${msg}</div>
            <div class="feed-time">${new Date().toLocaleTimeString('en-IN')}</div>
        </div>`;
    pane.insertBefore(item, pane.firstChild);

    while (pane.children.length > 10) pane.removeChild(pane.lastChild);
}

// ── Feed Tabs ─────────────────────────────────────────────
function initFeedTabs() {
    document.querySelectorAll('.feed-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.feed-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.feed-pane').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            const pane = document.getElementById(tab.dataset.tab === 'alerts' ? 'alertsPane' : 'insightsPane');
            if (pane) pane.classList.add('active');
        });
    });
}

// ── Main Sensor Callback (from websocket.js) ───────────────
window.onSensorReading = function(reading, aqiResult, alerts) {
    // Update gauge
    if (aqiResult?.aqi != null) {
        updateGauge(aqiResult.aqi);
    }

    // Update telemetry
    if (reading) {
        updateTelemetry(reading);
    }

    // Update chart
    if (aqiResult?.aqi != null && window.pushLiveReading) {
        pushLiveReading(aqiResult.aqi, reading.timestamp);
    }

    // Update recommendations
    if (aqiResult?.aqi != null) {
        updateRecommendations(aqiResult.aqi);
    }

    // Map heatmap update
    if (reading?.latitude && reading?.longitude && window.updateHeatmap) {
        updateHeatmap([{
            lat: reading.latitude,
            lng: reading.longitude,
            aqi: aqiResult.aqi
        }]);
    }

    // Process alerts
    if (alerts && alerts.length > 0) {
        alerts.forEach(a => addAlert(a.message, a.severity));
    }
};

// ── Periodic API Sync ─────────────────────────────────────
function syncFromAPI() {
    // AQI current
    fetch('/api/current')
        .then(r => r.json())
        .then(data => {
            if (data.aqi && !data.no_data) {
                updateGauge(data.aqi);
                if (data.mq135 != null) updateTelemetry({
                    mq135: data.mq135,
                    mq137: data.mq137,
                    latitude: data.latitude,
                    longitude: data.longitude,
                });
                updateRecommendations(data.aqi);
            }
        })
        .catch(() => {});

    // Heatmap data
    fetch('/api/heatmap?hours=2')
        .then(r => r.json())
        .then(data => {
            if (data.heatmap?.length && window.updateHeatmap) {
                const pts = data.heatmap.map(h => ({ lat: h.latitude, lng: h.longitude, aqi: h.aqi }));
                updateHeatmap(pts);
                if (window.updateMarkers) updateMarkers(pts);
            }
        })
        .catch(() => {});

    // Alerts
    fetch('/api/alerts?hours=1&limit=5')
        .then(r => r.json())
        .then(data => {
            if (data.alerts?.length) {
                data.alerts.forEach(a => addAlert(a.message, a.severity));
            }
        })
        .catch(() => {});

    // Insights
    fetch('/api/insights?hours=6&limit=4')
        .then(r => r.json())
        .then(data => {
            if (data.insights?.length) {
                data.insights.forEach(i => addInsight(i.message));
            }
        })
        .catch(() => {});
}

// ── Startup ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initFeedTabs();

    // Wait for map to be ready before syncing
    if (window._mapReady) {
        syncFromAPI();
    } else {
        window._onMapReady = syncFromAPI;
    }

    // Poll every 8 seconds
    setInterval(syncFromAPI, 8000);

    // Chart refresh every minute
    setInterval(() => {
        if (window.fetchChartData) fetchChartData(currentHours || 1);
    }, 60000);

    // Add startup insight
    setTimeout(() => {
        addInsight('System initialized — monitoring Chennai, Tamil Nadu air quality via IoT sensors.');
    }, 2000);
});