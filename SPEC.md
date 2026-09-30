# Hyperlocal Air Quality Intelligence System - Specification

## 1. Project Overview

**Project Name**: AirIQ - Hyperlocal Air Quality Intelligence System
**Type**: IoT + ML + Geospatial Visualization
**Core Functionality**: Real-time air quality monitoring with intelligent interpretation, temporal analysis, spatial mapping, and contextual insights
**Target Users**: Environmental researchers, smart city planners, urban residents

---

## 2. Architecture

```
┌─────────────────┐     Serial      ┌──────────────────┐
│   ESP32 +      │ ───────────────▶│  Python Backend  │
│  Sensors       │                 │  - Data Ingestion│
│  (MQ135,       │                 │  - AQI Engine    │
│   MQ137, GPS)  │                 │  - Analytics    │
└─────────────────┘                 │  - API Server   │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │   Web Frontend   │
                                    │  - Heatmap       │
                                    │  - Charts        │
                                    │  - Alerts        │
                                    └──────────────────┘
```

---

## 3. UI/UX Specification

### 3.1 Layout Structure

**Single-Page Dashboard Layout**:
- **Header**: Logo, system status, connection indicator
- **Main Content**: 3-column grid on desktop
  - Left: Map + Controls panel
  - Center: AQI Gauge + Live readings
  - Right: Trends + Alerts panel
- **Footer**: System info, last update timestamp

**Responsive Breakpoints**:
- Desktop: ≥1200px (3 columns)
- Tablet: 768px-1199px (2 columns)
- Mobile: <768px (1 column, stacked)

### 3.2 Visual Design

**Color Palette**:
- Background: `#0a0e17` (deep navy black)
- Surface: `#111827` (dark slate)
- Card Background: `#1a2332` (elevated surface)
- Primary: `#22d3ee` (cyan accent)
- Secondary: `#a78bfa` (violet)
- Success/Good: `#10b981` (emerald)
- Warning/Moderate: `#f59e0b` (amber)
- Danger/Unhealthy: `#ef4444` (red)
- Critical/Hazardous: `#7c2d12` (dark orange)
- Text Primary: `#f1f5f9` (off-white)
- Text Secondary: `#94a3b8` (slate gray)

**AQI Color Scale**:
- 0-50 (Good): `#10b981`
- 51-100 (Moderate): `#f59e0b`
- 101-150 (Unhealthy for Sensitive): `#f97316`
- 151-200 (Unhealthy): `#ef4444`
- 201-300 (Very Unhealthy): `#a855f7`
- 301-500 (Hazardous): `#7c2d12`

**Typography**:
- Font Family: 'JetBrains Mono' for data, 'Outfit' for UI
- Headings: Outfit, 600 weight
  - H1: 28px
  - H2: 22px
  - H3: 18px
- Body: 14px, 400 weight
- Data Values: JetBrains Mono, 16px, 500 weight
- Small/Labels: 12px

**Spacing System**:
- Base unit: 8px
- Card padding: 24px
- Section gap: 24px
- Element gap: 16px

**Visual Effects**:
- Card shadows: `0 4px 24px rgba(0,0,0,0.4)`
- Glow effects on primary elements: `0 0 20px rgba(34,211,238,0.3)`
- Border radius: 12px (cards), 8px (buttons), 4px (inputs)
- Subtle gradient overlays on cards

### 3.3 Components

**AQI Gauge**:
- Circular gauge with gradient (green→red)
- Large center number (AQI value)
- Category label below
- Animated needle/indicator
- Pulsing glow when in danger zone

**Live Readings Panel**:
- MQ135 value with trend arrow
- MQ137 value with trend arrow
- Temperature (if available)
- Humidity (if available)
- Each with mini sparkline

**Map Component**:
- Leaflet.js with dark tiles (CartoDB Dark Matter)
- Heatmap layer with color intensity
- Marker clustering for data points
- Popup on click showing historical data
- Legend overlay

**Trends Chart**:
- Line chart showing AQI over time
- Time range selector (1h, 6h, 24h, 7d)
- Moving average overlay
- Anomaly markers

**Alerts Panel**:
- Scrollable list of recent alerts
- Alert cards with severity icon
- Timestamp and description
- Dismiss button

**Status Indicator**:
- Green dot: Connected, streaming
- Yellow dot: Reconnecting
- Red dot: Disconnected

---

## 4. Functional Specification

### 4.1 Data Ingestion Module

**Serial Communication**:
- Baud rate: 115200
- Data format: `mq135,mq137,latitude,longitude`
- Example: `245,12,40.7128,-74.0060`
- Polling interval: 2 seconds
- Buffer size: 1024 bytes

**Error Handling**:
- Timeout after 5 seconds of no data
- Automatic reconnection with exponential backoff
- Invalid GPS (0,0) filtered out
- Invalid sensor values (-1, NaN) discarded
- Moving average filter for noise (window=5)

### 4.2 AQI Calculation Engine

**Algorithm**: Weighted hybrid model

```
AQI = base_aqi + mq135_contribution + mq137_contribution

where:
- base_aqi: Normalized baseline from MQ135 (0-100)
- mq137_contribution: Ammonia penalty based on MQ137
- Temporal adjustment: Recent trend modifier (±10%)
- Spatial adjustment: Local hotspot modifier (±15%)
```

**MQ135 Mapping** (general air quality):
- Raw 0-1023 → AQI contribution 0-200
- Calibration curve: logarithmic scaling
- Temperature/humidity compensation

**MQ137 Mapping** (ammonia-specific):
- Raw 0-1023 → Ammonia concentration estimate (0-100 ppm)
- Penalty applied to base AQI
- Weight: 0.5 (half weight in final AQI)

**Category Assignment**:
- 0-50: Good
- 51-100: Moderate
- 101-150: Unhealthy for Sensitive Groups
- 151-200: Unhealthy
- 201-300: Very Unhealthy
- 301-500: Hazardous

### 4.3 Temporal Intelligence

**Data Storage**:
- SQLite database for persistence
- Table: readings (id, timestamp, mq135, mq137, lat, lon, aqi)
- Automatic cleanup: Keep 7 days of data

**Analytics**:
- Moving average (window: 10 readings)
- Exponential smoothing (α=0.3)
- Trend detection: Compare 5-min avg vs 30-min avg
- Spike detection: >2 std deviations from mean

**Anomaly Classification**:
- Type: "spike", "sustained_high", "rapid_rise"
- Severity: "low", "medium", "high"

### 4.4 Spatial Intelligence

**Grid Aggregation**:
- Grid cell size: 0.001 degrees (~100m)
- Calculate mean AQI per cell
- Count readings per cell

**Heatmap Generation**:
- Gaussian kernel smoothing
- Radius: 200 meters
- Intensity: Based on AQI and recency
- Blur: 15px

**Hotspot Detection**:
- Identify cells with AQI > 150
- Cluster adjacent high-AQI cells
- Generate alerts for new hotspots

### 4.5 Context Awareness

**Industrial Zone Detection**:
- Use OpenStreetMap Nominatim API
- Search for: "industrial", "factory", "plant", "warehouse"
- Radius: 2km from measurement point
- Cache results for 1 hour

**Insight Generation**:
- "Elevated pollution detected near industrial zone (within 1.2km)"
- "Consistently high AQI in this area - possible persistent source"
- "Rapid pollution increase - check for recent activity"

**Disclaimer**: Always include probabilistic language

### 4.6 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Connection status, last reading |
| `/api/current` | GET | Current AQI and sensor values |
| `/api/history` | GET | Historical readings (query params: hours) |
| `/api/heatmap` | GET | Grid-aggregated heatmap data |
| `/api/alerts` | GET | Recent alerts |
| `/api/insights` | GET | Generated insights |
| `/ws` | WS | Real-time updates |

---

## 5. File Structure

```
air-quality-system/
├── backend/
│   ├── __init__.py
│   ├── main.py              # Flask app entry point
│   ├── serial_reader.py     # Serial communication
│   ├── aqi_engine.py        # AQI calculation
│   ├── database.py          # SQLite operations
│   ├── analytics.py        # Temporal analysis
│   ├── spatial.py          # Spatial processing
│   ├── context.py          # Context awareness
│   └── routes.py           # API routes
├── frontend/
│   ├── index.html          # Main dashboard
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css   # Custom styles
│   │   └── js/
│   │       ├── app.js      # Main application
│   │       ├── map.js      # Map initialization
│   │       ├── charts.js   # Chart rendering
│   │       └── websocket.js # Real-time updates
│   └── assets/
│       └── favicon.ico
├── data/
│   └── air_quality.db      # SQLite database
├── logs/
│   └── system.log          # Application logs
├── requirements.txt        # Python dependencies
├── config.json            # Configuration
└── README.md              # Documentation
```

---

## 6. Acceptance Criteria

### 6.1 Core Functionality
- [ ] Serial data is read continuously without blocking
- [ ] Invalid readings are filtered (no crashes on bad data)
- [ ] AQI is calculated and categorized correctly
- [ ] Data is persisted to SQLite

### 6.2 Temporal Analysis
- [ ] Moving average is calculated correctly
- [ ] Trends (rising/falling/stable) are detected
- [ ] Anomalies/spikes are identified and flagged
- [ ] Historical data is retrievable via API

### 6.3 Spatial Visualization
- [ ] Heatmap renders on the map
- [ ] Readings are plotted at correct GPS coordinates
- [ ] Grid aggregation produces meaningful clusters
- [ ] Hotspots are visually distinguishable

### 6.4 Context Awareness
- [ ] Industrial zones are detected nearby
- [ ] Contextual insights are generated
- [ ] API calls are cached to avoid rate limits

### 6.5 UI/UX
- [ ] Dashboard loads without errors
- [ ] Map displays with dark theme
- [ ] AQI gauge shows correct category color
- [ ] Charts update in real-time
- [ ] Alerts are displayed with severity
- [ ] Connection status is visible

### 6.6 Robustness
- [ ] System recovers from serial disconnect
- [ ] No memory leaks over extended runtime
- [ ] Logs are written for debugging

---

## 7. Dependencies

### Python
- Flask>=2.3.0
- Flask-SocketIO>=5.3.0
- pyserial>=3.5
- sqlite3 (stdlib)
- requests>=2.31.0
- numpy>=1.24.0
- scipy>=1.10.0

### Frontend
- Leaflet.js 1.9.4
- Chart.js 4.4.0
- Socket.io Client 4.7.0

---

## 8. Configuration

```json
{
  "serial": {
    "port": "COM3",
    "baudrate": 115200,
    "timeout": 5
  },
  "database": {
    "path": "data/air_quality.db",
    "retention_days": 7
  },
  "analytics": {
    "moving_average_window": 10,
    "anomaly_threshold": 2.0
  },
  "spatial": {
    "grid_size": 0.001,
    "heatmap_radius": 200
  },
  "context": {
    "search_radius_km": 2,
    "cache_ttl_seconds": 3600
  },
  "server": {
    "host": "0.0.0.0",
    "port": 5000
  }
}
```