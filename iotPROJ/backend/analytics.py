import numpy as np
import time
import logging
from typing import List, Dict, Tuple, Optional
from collections import deque

logger = logging.getLogger(__name__)


class TemporalAnalyzer:
    """Temporal analysis engine for time-series air quality data."""

    def __init__(self, moving_average_window: int = 10, anomaly_threshold: float = 2.0):
        self.moving_average_window = moving_average_window
        self.anomaly_threshold = anomaly_threshold
        self.aqi_history = deque(maxlen=100)
        self.last_alert_time = 0

    def add_reading(self, aqi: float):
        """Add a reading to the history."""
        self.aqi_history.append({
            'aqi': aqi,
            'timestamp': time.time()
        })

    def calculate_moving_average(self) -> Optional[float]:
        """Calculate moving average AQI."""
        if len(self.aqi_history) < 3:
            return None

        recent = list(self.aqi_history)[-self.moving_average_window:]
        return sum(r['aqi'] for r in recent) / len(recent)

    def calculate_exponential_smoothed(self, alpha: float = 0.3) -> Optional[float]:
        """Calculate exponentially smoothed AQI."""
        if len(self.aqi_history) < 2:
            return None

        # Start with first value
        smoothed = self.aqi_history[0]['aqi']

        # Apply exponential smoothing
        for reading in list(self.aqi_history)[1:]:
            smoothed = alpha * reading['aqi'] + (1 - alpha) * smoothed

        return smoothed

    def detect_trend(self) -> Tuple[str, float]:
        """
        Detect if AQI is rising, falling, or stable.

        Returns:
            Tuple of (trend_name, trend_strength)
            trend_name: 'rising', 'falling', 'stable'
            trend_strength: -1 to 1 (negative=falling, positive=rising)
        """
        if len(self.aqi_history) < 10:
            return 'stable', 0.0

        # Compare recent 5-minute average vs 30-minute average
        recent_5 = list(self.aqi_history)[-5:]
        recent_30 = list(self.aqi_history)[-30:]

        avg_5 = sum(r['aqi'] for r in recent_5) / len(recent_5)
        avg_30 = sum(r['aqi'] for r in recent_30) / len(recent_30)

        if avg_30 == 0:
            return 'stable', 0.0

        # Calculate trend strength as percentage change
        change = (avg_5 - avg_30) / avg_30

        if change > 0.1:
            return 'rising', min(change, 1.0)
        elif change < -0.1:
            return 'falling', max(change, -1.0)
        else:
            return 'stable', change

    def detect_anomaly(self, aqi: float) -> Optional[Dict]:
        """
        Detect if current AQI is anomalous.

        Returns:
            Dictionary with anomaly info or None
        """
        if len(self.aqi_history) < 10:
            return None

        # Calculate mean and std
        values = np.array([r['aqi'] for r in self.aqi_history])
        mean = np.mean(values)
        std = np.std(values)

        # Check if current value exceeds threshold
        z_score = (aqi - mean) / std if std > 0 else 0

        if abs(z_score) > self.anomaly_threshold:
            anomaly_type = 'spike' if z_score > 0 else 'drop'
            severity = 'high' if abs(z_score) > 3 else 'medium' if abs(z_score) > 2.5 else 'low'

            return {
                'type': anomaly_type,
                'severity': severity,
                'z_score': round(z_score, 2),
                'expected_range': (mean - std * 2, mean + std * 2),
                'value': aqi
            }

        return None

    def get_trend_modifier(self) -> float:
        """
        Get temporal modifier for AQI calculation.
        Returns value between -0.1 and 0.1 based on trend.
        """
        trend, strength = self.detect_trend()

        if trend == 'rising':
            return 0.1 * strength  # 0 to 0.1
        elif trend == 'falling':
            return 0.1 * strength  # -0.1 to 0
        else:
            return 0.0

    def check_alert_conditions(self, aqi: float, category: str,
                                lat: float, lon: float) -> List[Dict]:
        """
        Check if alert conditions are met.

        Returns:
            List of alert dictionaries
        """
        alerts = []
        now = time.time()

        # Rate limit alerts (minimum 60 seconds between alerts)
        if now - self.last_alert_time < 60:
            return alerts

        # High AQI alert
        if aqi > 150:
            severity = 'high' if aqi > 200 else 'medium'

            alerts.append({
                'timestamp': now,
                'alert_type': 'high_aqi',
                'severity': severity,
                'message': f"Unhealthy air quality detected (AQI: {aqi})",
                'aqi_value': aqi,
                'latitude': lat,
                'longitude': lon
            })
            self.last_alert_time = now

        # Anomaly detection
        anomaly = self.detect_anomaly(aqi)
        if anomaly and anomaly['severity'] in ['high', 'medium']:
            alerts.append({
                'timestamp': now,
                'alert_type': 'anomaly',
                'severity': anomaly['severity'],
                'message': f"AQI {anomaly['type']} detected: {aqi} (expected: {anomaly['expected_range']})",
                'aqi_value': aqi,
                'latitude': lat,
                'longitude': lon
            })
            self.last_alert_time = now

        # Rapid rise alert
        trend, strength = self.detect_trend()
        if trend == 'rising' and strength > 0.5 and aqi > 100:
            alerts.append({
                'timestamp': now,
                'alert_type': 'rapid_rise',
                'severity': 'medium',
                'message': f"Rapid pollution increase detected ({int(strength * 100)}% rise)",
                'aqi_value': aqi,
                'latitude': lat,
                'longitude': lon
            })
            self.last_alert_time = now

        return alerts

    def get_time_series_data(self, readings: List[Dict],
                            interval_minutes: int = 5) -> List[Dict]:
        """
        Aggregate readings into time series intervals.

        Returns:
            List of aggregated data points
        """
        if not readings:
            return []

        # Sort by timestamp
        sorted_readings = sorted(readings, key=lambda r: r['timestamp'])

        # Calculate bucket size in seconds
        bucket_size = interval_minutes * 60

        buckets = {}
        for reading in sorted_readings:
            bucket_key = int(reading['timestamp'] / bucket_size) * bucket_size

            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    'timestamp': bucket_key,
                    'aqi_values': [],
                    'mq135_values': [],
                    'mq137_values': []
                }

            buckets[bucket_key]['aqi_values'].append(reading['aqi'])
            buckets[bucket_key]['mq135_values'].append(reading['mq135'])
            buckets[bucket_key]['mq137_values'].append(reading['mq137'])

        # Calculate aggregates
        result = []
        for timestamp, bucket in sorted(buckets.items()):
            aqi_vals = bucket['aqi_values']
            result.append({
                'timestamp': timestamp,
                'aqi': round(sum(aqi_vals) / len(aqi_vals), 1),
                'aqi_min': min(aqi_vals),
                'aqi_max': max(aqi_vals),
                'count': len(aqi_vals),
                'mq135': round(sum(bucket['mq135_values']) / len(bucket['mq135_values']), 1),
                'mq137': round(sum(bucket['mq137_values']) / len(bucket['mq137_values']), 1)
            })

        return result

    def predict_next_aqi(self) -> Optional[float]:
        """
        Simple prediction of next AQI using linear trend.

        Returns:
            Predicted AQI or None
        """
        if len(self.aqi_history) < 10:
            return None

        # Use last 20 points for prediction
        recent = list(self.aqi_history)[-20:]
        timestamps = np.array([r['timestamp'] for r in recent])
        values = np.array([r['aqi'] for r in recent])

        # Linear regression
        if len(timestamps) < 3:
            return None

        # Normalize timestamps
        t_norm = (timestamps - timestamps[0]) / (timestamps[-1] - timestamps[0] + 1)

        # Simple linear fit
        coeffs = np.polyfit(t_norm, values, 1)
        predicted = coeffs[0] * 1.0 + coeffs[1]  # Extrapolate one unit ahead

        return max(0, min(500, predicted))

    def get_statistics_summary(self, readings: List[Dict]) -> Dict:
        """Get comprehensive statistics from readings."""
        if not readings:
            return {
                'count': 0,
                'mean': 0,
                'std': 0,
                'min': 0,
                'max': 0,
                'trend': 'stable',
                'trend_strength': 0
            }

        aqi_values = [r['aqi'] for r in readings]

        trend, trend_strength = self.detect_trend()

        return {
            'count': len(readings),
            'mean': round(np.mean(aqi_values), 1),
            'std': round(np.std(aqi_values), 1),
            'min': min(aqi_values),
            'max': max(aqi_values),
            'trend': trend,
            'trend_strength': round(trend_strength, 2)
        }