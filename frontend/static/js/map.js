/**
 * map.js — Leaflet + leaflet-heat integration for AirIQ Dashboard
 * No API key required. Dark CartoDB tiles + leaflet.heat heatmap layer.
 */

const CHENNAI = { lat: 12.9716, lng: 80.2209 };

let gMap = null;
let gmHeatLayer = null;
let gmMarkers = [];
let showHeatmapLayer = true;
let showMarkersLayer = true;

// ── AQI Helpers ───────────────────────────────────────────
function aqiToColor(aqi) {
    if (aqi <= 50)  return '#10b981';
    if (aqi <= 100) return '#f59e0b';
    if (aqi <= 150) return '#f97316';
    if (aqi <= 200) return '#ef4444';
    if (aqi <= 300) return '#a855f7';
    return '#7c2d12';
}

function aqiToCategory(aqi) {
    if (aqi <= 50)  return 'Good';
    if (aqi <= 100) return 'Moderate';
    if (aqi <= 150) return 'Unhealthy for Sensitive Groups';
    if (aqi <= 200) return 'Unhealthy';
    if (aqi <= 300) return 'Very Unhealthy';
    return 'Hazardous';
}

// ── Map Init ─────────────────────────────────────────────
function initMap() {
    if (typeof L === 'undefined') {
        console.error('[AirIQ] Leaflet not loaded');
        return;
    }

    gMap = L.map('map', {
        center: [CHENNAI.lat, CHENNAI.lng],
        zoom: 13,
        zoomControl: false,
        attributionControl: false
    });

    // Dark CartoDB map tile (no API key needed)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(gMap);

    // Origin pin — sensor station
    const originIcon = L.divIcon({
        className: '',
        html: `<div style="
            width:16px;height:16px;border-radius:50%;
            background:rgba(34,211,238,0.35);
            border:2px solid #22d3ee;
            box-shadow:0 0 14px #22d3ee, 0 0 28px rgba(34,211,238,0.4);
        "></div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });

    L.marker([CHENNAI.lat, CHENNAI.lng], { icon: originIcon, zIndexOffset: 9999 })
        .bindPopup(`
            <div>
                <div style="font-family:'JetBrains Mono',monospace;color:#22d3ee;font-size:14px;font-weight:700">SENSOR ORIGIN</div>
                <div style="font-size:11px;color:#64748b;margin-top:2px">Chennai, Tamil Nadu</div>
                <div style="font-size:11px;color:#94a3b8;margin-top:6px;border-top:1px solid rgba(255,255,255,.06);padding-top:6px">
                    Lat <span style="color:#e2e8f0;font-family:'JetBrains Mono',monospace;float:right">${CHENNAI.lat}</span><br>
                    Lon <span style="color:#e2e8f0;font-family:'JetBrains Mono',monospace;float:right">${CHENNAI.lng}</span>
                </div>
            </div>`)
        .addTo(gMap);

    // Notify app.js the map is ready
    window._mapReady = true;
    if (window._onMapReady) window._onMapReady();
}

// ── Heatmap Layer ─────────────────────────────────────────
function updateHeatmap(dataPoints) {
    if (!gMap || typeof L === 'undefined') return;

    if (gmHeatLayer) {
        gMap.removeLayer(gmHeatLayer);
        gmHeatLayer = null;
    }

    if (!dataPoints || dataPoints.length === 0) return;

    const pts = dataPoints.map(pt => [
        pt.lat,
        pt.lng,
        Math.min(1, (pt.aqi || 0) / 300)
    ]);

    gmHeatLayer = L.heatLayer(pts, {
        radius: 40,
        blur: 28,
        maxZoom: 18,
        max: 1,
        gradient: {
            0.0: '#10b981',
            0.2: '#f59e0b',
            0.45: '#f97316',
            0.65: '#ef4444',
            0.85: '#a855f7',
            1.0:  '#7c2d12'
        }
    });

    if (showHeatmapLayer) {
        gmHeatLayer.addTo(gMap);
    }
}

// ── Sensor Point Markers ─────────────────────────────────
function updateMarkers(dataPoints) {
    if (!gMap || typeof L === 'undefined') return;

    gmMarkers.forEach(m => gMap.removeLayer(m));
    gmMarkers = [];

    if (!dataPoints || dataPoints.length === 0 || !showMarkersLayer) return;

    dataPoints.forEach(pt => {
        const color = aqiToColor(pt.aqi);
        const hot = pt.aqi > 200;

        const icon = L.divIcon({
            className: '',
            html: `<div style="
                width:${hot ? 16 : 9}px;height:${hot ? 16 : 9}px;border-radius:50%;
                background:${color};opacity:0.92;
                border:${hot ? '1.5px solid #fff' : '0.8px solid rgba(255,255,255,0.3)'};
                box-shadow:0 0 ${hot ? 10 : 5}px ${color};
            "></div>`,
            iconSize: [hot ? 16 : 9, hot ? 16 : 9],
            iconAnchor: [hot ? 8 : 4.5, hot ? 8 : 4.5]
        });

        const marker = L.marker([pt.lat, pt.lng], { icon })
            .bindPopup(`
                <div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:28px;font-weight:700;color:${color};line-height:1">${pt.aqi}</div>
                    <div style="font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:${color};margin-bottom:8px">${aqiToCategory(pt.aqi)}</div>
                    <div style="font-size:11px;color:#64748b;border-top:1px solid rgba(255,255,255,.06);padding-top:6px;margin-top:6px">
                        <div style="display:flex;justify-content:space-between;margin-bottom:3px">Latitude <span style="color:#e2e8f0;font-family:'JetBrains Mono',monospace">${pt.lat.toFixed(5)}</span></div>
                        <div style="display:flex;justify-content:space-between">Longitude <span style="color:#e2e8f0;font-family:'JetBrains Mono',monospace">${pt.lng.toFixed(5)}</span></div>
                    </div>
                </div>`);

        marker.addTo(gMap);
        gmMarkers.push(marker);
    });
}

// ── Pan to location ───────────────────────────────────────
function panMapTo(lat, lng) {
    if (gMap && lat && lng) gMap.panTo([lat, lng]);
}

// ── Layer toggles ─────────────────────────────────────────
function setHeatmapVisible(on) {
    showHeatmapLayer = on;
    if (!gMap || !gmHeatLayer) return;
    if (on) gmHeatLayer.addTo(gMap);
    else gMap.removeLayer(gmHeatLayer);
}

function setMarkersVisible(on) {
    showMarkersLayer = on;
    gmMarkers.forEach(m => {
        if (on) m.addTo(gMap);
        else gMap.removeLayer(m);
    });
}

// ── Button wiring ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const heatBtn    = document.getElementById('toggleHeatmapBtn');
    const markersBtn = document.getElementById('toggleMarkersBtn');

    if (heatBtn) {
        heatBtn.addEventListener('click', () => {
            showHeatmapLayer = !showHeatmapLayer;
            heatBtn.classList.toggle('active', showHeatmapLayer);
            setHeatmapVisible(showHeatmapLayer);
        });
    }
    if (markersBtn) {
        markersBtn.addEventListener('click', () => {
            showMarkersLayer = !showMarkersLayer;
            markersBtn.classList.toggle('active', showMarkersLayer);
            setMarkersVisible(showMarkersLayer);
        });
    }

    // Init map after DOM is ready
    initMap();
});