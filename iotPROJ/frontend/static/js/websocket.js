/**
 * websocket.js — SocketIO connection manager for AirIQ
 * Handles live data events and connection state
 */

let socket = null;
let isConnected = false;
let reconnectDelay = 2000;

// ── Connect ───────────────────────────────────────────────
function initWebSocket() {
    try {
        socket = io({
            transports: ['websocket', 'polling'],
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 10000,
        });

        socket.on('connect', () => {
            isConnected = true;
            reconnectDelay = 2000;
            setConnectionUI(true);
            console.log('[AirIQ] WebSocket connected');
            socket.emit('request_update');
        });

        socket.on('disconnect', (reason) => {
            isConnected = false;
            setConnectionUI(false);
            console.warn('[AirIQ] WebSocket disconnected:', reason);
        });

        socket.on('connect_error', (err) => {
            isConnected = false;
            setConnectionUI(false, 'Signal Lost');
            console.error('[AirIQ] Connection error:', err.message);
        });

        // Main data event
        socket.on('data_update', (payload) => {
            try {
                handleDataUpdate(payload);
            } catch (e) {
                console.error('[AirIQ] Data update error:', e);
            }
        });

    } catch (err) {
        console.error('[AirIQ] Failed to init WebSocket:', err);
        setConnectionUI(false, 'Init Failed');
    }
}

// ── Connection UI ─────────────────────────────────────────
function setConnectionUI(connected, customText = null) {
    const dot  = document.getElementById('connectionStatus')?.querySelector('.conn-dot');
    const text = document.getElementById('connText');

    if (dot) {
        dot.className = 'conn-dot ' + (connected ? 'connected' : 'disconnected');
    }
    if (text) {
        text.textContent = customText || (connected ? 'Live · Chennai' : 'Reconnecting…');
    }

    // Update last update bar
    const lu = document.getElementById('lastUpdate');
    if (!connected && lu) {
        lu.textContent = 'Signal lost — attempting reconnect…';
    }
}

// ── Handle Incoming Data ──────────────────────────────────
function handleDataUpdate(payload) {
    const { reading, aqi: aqiResult, alerts } = payload;

    if (!reading || !aqiResult) return;

    // Update timestamp
    const now = new Date();
    const ts = now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const lu = document.getElementById('lastUpdate');
    if (lu) lu.textContent = `Last update: ${ts} · MQ135=${Math.round(reading.mq135)} MQ137=${Math.round(reading.mq137)}`;

    // Dispatch to app.js handlers
    if (window.onSensorReading) {
        window.onSensorReading(reading, aqiResult, alerts);
    }
}

// ── Request manual update ─────────────────────────────────
function requestUpdate() {
    if (socket && isConnected) {
        socket.emit('request_update');
    }
}

// ── Init on DOMContentLoaded ──────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Small delay to let other scripts init first
    setTimeout(initWebSocket, 500);
});