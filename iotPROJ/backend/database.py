import sqlite3
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for air quality readings."""

    def __init__(self, db_path: str = "data/air_quality.db", retention_days: int = 7):
        self.db_path = db_path
        self.retention_days = retention_days
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def _init_database(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Main readings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    mq135 REAL NOT NULL,
                    mq137 REAL NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    aqi REAL NOT NULL,
                    category TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Alerts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    aqi_value REAL,
                    latitude REAL,
                    longitude REAL,
                    acknowledged INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Insights table (generated insights cache)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    insight_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    confidence REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Context cache table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS context_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    search_radius REAL NOT NULL,
                    result_json TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
            ''')

            # Create indexes for common queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_readings_timestamp
                ON readings(timestamp DESC)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_readings_location
                ON readings(latitude, longitude)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
                ON alerts(timestamp DESC)
            ''')

            logger.info("Database initialized")

    def insert_reading(self, data: Dict) -> int:
        """Insert a new reading."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO readings (timestamp, mq135, mq137, latitude, longitude, aqi, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('timestamp', time.time()),
                data.get('mq135'),
                data.get('mq137'),
                data.get('latitude'),
                data.get('longitude'),
                data.get('aqi'),
                data.get('category', 'unknown')
            ))
            return cursor.lastrowid

    def get_latest_reading(self) -> Optional[Dict]:
        """Get the most recent reading."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM readings
                ORDER BY timestamp DESC
                LIMIT 1
            ''')
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_readings(self, hours: int = 24, limit: int = 1000) -> List[Dict]:
        """Get readings from the last N hours."""
        cutoff = time.time() - (hours * 3600)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM readings
                WHERE timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (cutoff, limit))

            return [dict(row) for row in cursor.fetchall()]

    def get_readings_for_location(self, lat: float, lon: float,
                                   radius: float = 0.01, hours: int = 24) -> List[Dict]:
        """Get readings near a location."""
        cutoff = time.time() - (hours * 3600)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM readings
                WHERE timestamp > ?
                AND latitude BETWEEN ? AND ?
                AND longitude BETWEEN ? AND ?
                ORDER BY timestamp DESC
            ''', (cutoff, lat - radius, lat + radius, lon - radius, lon + radius))

            return [dict(row) for row in cursor.fetchall()]

    def get_moving_average(self, window: int = 10, hours: int = 1) -> Optional[float]:
        """Calculate moving average AQI."""
        cutoff = time.time() - (hours * 3600)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT aqi FROM readings
                WHERE timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (cutoff, window))

            rows = cursor.fetchall()
            if not rows:
                return None

            return sum(row['aqi'] for row in rows) / len(rows)

    def get_statistics(self, hours: int = 24) -> Dict:
        """Get statistics for time period."""
        cutoff = time.time() - (hours * 3600)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    COUNT(*) as count,
                    AVG(aqi) as avg_aqi,
                    MIN(aqi) as min_aqi,
                    MAX(aqi) as max_aqi,
                    AVG(mq135) as avg_mq135,
                    AVG(mq137) as avg_mq137
                FROM readings
                WHERE timestamp > ?
            ''', (cutoff,))

            row = cursor.fetchone()
            if not row or row['count'] == 0:
                return {
                    'count': 0,
                    'avg_aqi': 0,
                    'min_aqi': 0,
                    'max_aqi': 0,
                    'avg_mq135': 0,
                    'avg_mq137': 0
                }

            return {
                'count': row['count'],
                'avg_aqi': round(row['avg_aqi'], 1) if row['avg_aqi'] else 0,
                'min_aqi': row['min_aqi'] or 0,
                'max_aqi': row['max_aqi'] or 0,
                'avg_mq135': round(row['avg_mq135'], 1) if row['avg_mq135'] else 0,
                'avg_mq137': round(row['avg_mq137'], 1) if row['avg_mq137'] else 0
            }

    def insert_alert(self, data: Dict) -> int:
        """Insert a new alert."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alerts (timestamp, alert_type, severity, message, aqi_value, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('timestamp', time.time()),
                data.get('alert_type', 'general'),
                data.get('severity', 'low'),
                data.get('message'),
                data.get('aqi_value'),
                data.get('latitude'),
                data.get('longitude')
            ))
            return cursor.lastrowid

    def get_alerts(self, hours: int = 24, limit: int = 50) -> List[Dict]:
        """Get recent alerts."""
        cutoff = time.time() - (hours * 3600)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM alerts
                WHERE timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (cutoff, limit))

            return [dict(row) for row in cursor.fetchall()]

    def acknowledge_alert(self, alert_id: int):
        """Mark alert as acknowledged."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE alerts SET acknowledged = 1
                WHERE id = ?
            ''', (alert_id,))

    def insert_insight(self, data: Dict) -> int:
        """Insert a new insight."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO insights (timestamp, insight_type, message, latitude, longitude, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                data.get('timestamp', time.time()),
                data.get('insight_type'),
                data.get('message'),
                data.get('latitude'),
                data.get('longitude'),
                data.get('confidence', 0.5)
            ))
            return cursor.lastrowid

    def get_insights(self, hours: int = 24, limit: int = 20) -> List[Dict]:
        """Get recent insights."""
        cutoff = time.time() - (hours * 3600)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM insights
                WHERE timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (cutoff, limit))

            return [dict(row) for row in cursor.fetchall()]

    def cache_context(self, lat: float, lon: float, radius: float, data: Dict):
        """Cache context search results."""
        now = time.time()
        expires = now + 3600  # 1 hour TTL

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Remove old cache entries for this location
            cursor.execute('''
                DELETE FROM context_cache
                WHERE latitude = ? AND longitude = ?
            ''', (lat, lon))

            cursor.execute('''
                INSERT INTO context_cache (latitude, longitude, search_radius, result_json, timestamp, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (lat, lon, radius, json.dumps(data), now, expires))

    def get_cached_context(self, lat: float, lon: float, radius: float) -> Optional[Dict]:
        """Get cached context results if not expired."""
        now = time.time()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT result_json FROM context_cache
                WHERE latitude = ?
                AND longitude = ?
                AND search_radius = ?
                AND expires_at > ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (lat, lon, radius, now))

            row = cursor.fetchone()
            if row:
                return json.loads(row['result_json'])
            return None

    def cleanup_old_data(self):
        """Remove data older than retention period."""
        cutoff = time.time() - (self.retention_days * 24 * 3600)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM readings WHERE timestamp < ?', (cutoff,))
            cursor.execute('DELETE FROM alerts WHERE timestamp < ?', (cutoff,))
            cursor.execute('DELETE FROM insights WHERE timestamp < ?', (cutoff,))
            cursor.execute('DELETE FROM context_cache WHERE expires_at < ?', (cutoff,))

            logger.info(f"Cleaned up data older than {self.retention_days} days")