import math
import logging
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class SpatialProcessor:
    """Spatial processing engine for grid aggregation and heatmap generation."""

    # Approximate meters per degree at different latitudes
    METERS_PER_DEG_LAT = 111000
    METERS_PER_DEG_LON = 111000  # At equator, decreases with latitude

    def __init__(self, grid_size: float = 0.001, heatmap_radius: int = 200):
        self.grid_size = grid_size  # Degrees (~100m at equator)
        self.heatmap_radius = heatmap_radius  # Meters
        self.grid_cache = {}

    def _get_grid_key(self, lat: float, lon: float) -> Tuple[int, int]:
        """Convert lat/lon to grid cell key."""
        lat_key = int(lat / self.grid_size)
        lon_key = int(lon / self.grid_size)
        return (lat_key, lon_key)

    def _get_grid_center(self, lat_key: int, lon_key: int) -> Tuple[float, float]:
        """Get center coordinates of grid cell."""
        lat = (lat_key + 0.5) * self.grid_size
        lon = (lon_key + 0.5) * self.grid_size
        return (lat, lon)

    def _meters_per_degree(self, latitude: float) -> Tuple[float, float]:
        """Calculate meters per degree at given latitude."""
        lat_factor = math.cos(math.radians(abs(latitude)))
        return (
            self.METERS_PER_DEG_LAT,
            self.METERS_PER_DEG_LON * lat_factor
        )

    def aggregate_by_grid(self, readings: List[Dict]) -> List[Dict]:
        """
        Aggregate readings by grid cells.

        Returns:
            List of grid cells with aggregated data
        """
        grid_data = defaultdict(lambda: {
            'aqi_values': [],
            'mq135_values': [],
            'mq137_values': [],
            'timestamps': [],
            'count': 0
        })

        for reading in readings:
            lat = reading.get('latitude')
            lon = reading.get('longitude')

            if lat is None or lon is None:
                continue

            key = self._get_grid_key(lat, lon)
            grid_data[key]['aqi_values'].append(reading['aqi'])
            grid_data[key]['mq135_values'].append(reading['mq135'])
            grid_data[key]['mq137_values'].append(reading['mq137'])
            grid_data[key]['timestamps'].append(reading['timestamp'])
            grid_data[key]['count'] += 1

        # Calculate aggregates
        result = []
        for (lat_key, lon_key), data in grid_data.items():
            center_lat, center_lon = self._get_grid_center(lat_key, lon_key)

            result.append({
                'grid_key': (lat_key, lon_key),
                'latitude': center_lat,
                'longitude': center_lon,
                'count': data['count'],
                'avg_aqi': sum(data['aqi_values']) / len(data['aqi_values']),
                'min_aqi': min(data['aqi_values']),
                'max_aqi': max(data['aqi_values']),
                'avg_mq135': sum(data['mq135_values']) / len(data['mq135_values']),
                'avg_mq137': sum(data['mq137_values']) / len(data['mq137_values']),
                'latest_timestamp': max(data['timestamps'])
            })

        return sorted(result, key=lambda x: x['count'], reverse=True)

    def generate_heatmap_data(self, readings: List[Dict],
                               decay_hours: float = 24) -> List[Dict]:
        """
        Generate heatmap data with time-based decay.

        Args:
            readings: List of readings
            decay_hours: How quickly older readings lose influence

        Returns:
            List of heatmap points with intensity
        """
        import time

        if not readings:
            return []

        current_time = time.time()
        max_age = decay_hours * 3600

        heatmap_points = []

        for reading in readings:
            lat = reading.get('latitude')
            lon = reading.get('longitude')
            aqi = reading.get('aqi', 0)
            timestamp = reading.get('timestamp', current_time)

            if lat is None or lon is None:
                continue

            # Calculate recency factor (1.0 = now, 0.0 = max_age ago)
            age = current_time - timestamp
            recency = max(0, 1 - (age / max_age))

            # Intensity based on AQI and recency
            intensity = (aqi / 500) * recency

            if intensity > 0.01:  # Skip very low intensity
                heatmap_points.append({
                    'latitude': lat,
                    'longitude': lon,
                    'intensity': round(intensity, 3),
                    'aqi': aqi,
                    'recency': round(recency, 2),
                    'timestamp': timestamp
                })

        return heatmap_points

    def detect_hotspots(self, readings: List[Dict],
                        threshold: float = 150,
                        min_readings: int = 3) -> List[Dict]:
        """
        Detect pollution hotspots.

        Returns:
            List of hotspot definitions
        """
        grid_data = self.aggregate_by_grid(readings)

        hotspots = []
        for cell in grid_data:
            if cell['avg_aqi'] > threshold and cell['count'] >= min_readings:
                hotspots.append({
                    'latitude': cell['latitude'],
                    'longitude': cell['longitude'],
                    'avg_aqi': round(cell['avg_aqi'], 1),
                    'max_aqi': cell['max_aqi'],
                    'count': cell['count'],
                    'severity': 'high' if cell['avg_aqi'] > 200 else 'medium'
                })

        return sorted(hotspots, key=lambda x: x['avg_aqi'], reverse=True)

    def get_clustered_readings(self, readings: List[Dict],
                                radius_deg: float = 0.005) -> List[Dict]:
        """
        Cluster nearby readings to reduce map clutter.

        Returns:
            List of clustered points
        """
        if not readings:
            return []

        # Sort by timestamp (newest first)
        sorted_readings = sorted(readings, key=lambda r: r['timestamp'], reverse=True)

        clusters = []
        processed = set()

        for reading in sorted_readings:
            lat = reading.get('latitude')
            lon = reading.get('longitude')
            key = (round(lat, 3), round(lon, 3))

            if key in processed:
                continue

            # Find nearby readings
            cluster = [r for r in sorted_readings
                      if abs(r.get('latitude', 0) - lat) < radius_deg
                      and abs(r.get('longitude', 0) - lon) < radius_deg]

            if cluster:
                avg_aqi = sum(r['aqi'] for r in cluster) / len(cluster)
                latest = max(r['timestamp'] for r in cluster)

                clusters.append({
                    'latitude': lat,
                    'longitude': lon,
                    'count': len(cluster),
                    'avg_aqi': round(avg_aqi, 1),
                    'latest_aqi': cluster[0]['aqi'],
                    'latest_timestamp': latest
                })

                for r in cluster:
                    k = (round(r.get('latitude', 0), 3), round(r.get('longitude', 0), 3))
                    processed.add(k)

        return sorted(clusters, key=lambda x: x['count'], reverse=True)[:50]

    def get_bounds(self, readings: List[Dict]) -> Optional[Dict]:
        """Get geographic bounds of readings."""
        if not readings:
            return None

        lats = [r['latitude'] for r in readings if r.get('latitude') is not None]
        lons = [r['longitude'] for r in readings if r.get('longitude') is not None]

        if not lats or not lons:
            return None

        return {
            'min_lat': min(lats),
            'max_lat': max(lats),
            'min_lon': min(lons),
            'max_lon': max(lons),
            'center_lat': (min(lats) + max(lats)) / 2,
            'center_lon': (min(lons) + max(lons)) / 2
        }

    def smooth_heatmap(self, heatmap_points: List[Dict],
                       radius_deg: float = 0.002) -> List[Dict]:
        """
        Apply Gaussian smoothing to heatmap data.

        Returns:
            Smoothed heatmap points
        """
        if len(heatmap_points) < 2:
            return heatmap_points

        # Simple box blur for smoothing
        smoothed = []

        for point in heatmap_points:
            lat, lon = point['latitude'], point['longitude']
            aqi = point['aqi']

            # Find nearby points
            nearby = [p for p in heatmap_points
                     if abs(p['latitude'] - lat) < radius_deg
                     and abs(p['longitude'] - lon) < radius_deg
                     and p.get('aqi', 0) > 0]

            if nearby:
                avg_intensity = sum(p.get('intensity', 0) for p in nearby) / len(nearby)
                avg_aqi = sum(p.get('aqi', 0) for p in nearby) / len(nearby)

                smoothed.append({
                    'latitude': lat,
                    'longitude': lon,
                    'intensity': round(avg_intensity, 3),
                    'aqi': round(avg_aqi, 1),
                    'recency': point.get('recency', 1),
                    'timestamp': point.get('timestamp')
                })

        return smoothed