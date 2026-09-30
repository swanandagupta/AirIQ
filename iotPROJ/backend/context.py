import requests
import time
import logging
from typing import List, Dict, Optional
from geopy.distance import geodesic
from backend.database import Database

logger = logging.getLogger(__name__)


class ContextEngine:
    """Context awareness engine for industrial zone detection and insights."""

    # Types of places that may contribute to pollution
    INDUSTRIAL_KEYWORDS = [
        'industrial', 'factory', 'plant', 'manufacturing', 'warehouse',
        'refinery', 'power station', 'chemical', 'mill', 'foundry',
        'processing', 'production', 'assembly'
    ]

    # Potential pollution sources
    SOURCE_TYPES = {
        'industrial': 'Industrial facility',
        'commercial': 'Commercial activity',
        'construction': 'Construction site',
        'traffic': 'High traffic area',
        'residential': 'Residential heating'
    }

    def __init__(self, database: Database,
                 search_radius_km: float = 2,
                 cache_ttl_seconds: int = 3600):
        self.database = database
        self.search_radius_km = search_radius_km
        self.cache_ttl = cache_ttl_seconds

    def find_nearby_places(self, lat: float, lon: float,
                          radius_km: float = None) -> List[Dict]:
        """
        Find nearby places using Nominatim (OpenStreetMap).

        Returns:
            List of nearby places with type and distance
        """
        if radius_km is None:
            radius_km = self.search_radius_km

        # Check cache first
        cached = self.database.get_cached_context(lat, lon, radius_km)
        if cached:
            logger.debug("Using cached context data")
            return cached.get('places', [])

        # Search using Nominatim
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'lat': lat,
                'lon': lon,
                'format': 'json',
                'radius': radius_km * 1000,  # Convert to meters
                'limit': 20,
                'addressdetails': 1
            }
            headers = {
                'User-Agent': 'AirQualitySystem/1.0'
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                results = response.json()
                places = self._process_places(results, lat, lon)

                # Cache results
                self.database.cache_context(lat, lon, radius_km, {'places': places})
                return places
            else:
                logger.warning(f"Nominatim API returned status {response.status_code}")
                return []

        except requests.RequestException as e:
            logger.error(f"Failed to fetch nearby places: {e}")
            return []

    def _process_places(self, results: List[Dict], lat: float, lon: float) -> List[Dict]:
        """Process and filter Nominatim results."""
        places = []

        for result in results:
            place_type = result.get('type', '')
            display_name = result.get('display_name', '')
            address = result.get('address', {})

            # Check if it's potentially pollution-related
            keywords_found = []
            text_to_search = f"{place_type} {display_name}".lower()

            for keyword in self.INDUSTRIAL_KEYWORDS:
                if keyword in text_to_search:
                    keywords_found.append(keyword)

            # Calculate distance
            place_lat = float(result.get('lat', 0))
            place_lon = float(result.get('lon', 0))

            try:
                distance = geodesic((lat, lon), (place_lat, place_lon)).kilometers
            except:
                distance = 0

            places.append({
                'name': result.get('name', display_name.split(',')[0]),
                'type': place_type,
                'keywords': keywords_found,
                'distance_km': round(distance, 2),
                'latitude': place_lat,
                'longitude': place_lon,
                'is_potential_source': len(keywords_found) > 0,
                'display_name': display_name[:100]
            })

        # Sort by distance
        return sorted(places, key=lambda x: x['distance_km'])

    def identify_potential_sources(self, lat: float, lon: float,
                                    aqi: float) -> List[Dict]:
        """
        Identify potential pollution sources based on nearby places and AQI.

        Returns:
            List of potential sources with confidence
        """
        if aqi < 100:
            return []

        places = self.find_nearby_places(lat, lon)
        sources = []

        for place in places:
            if place['is_potential_source']:
                # Calculate confidence based on distance and AQI
                distance_factor = max(0, 1 - (place['distance_km'] / self.search_radius_km))
                aqi_factor = min(1, aqi / 200)
                confidence = (distance_factor * 0.6 + aqi_factor * 0.4)

                sources.append({
                    'name': place['name'],
                    'type': 'industrial' if 'industrial' in place['keywords'] else 'potential_source',
                    'distance_km': place['distance_km'],
                    'confidence': round(confidence, 2),
                    'keywords': place['keywords']
                })

        return sorted(sources, key=lambda x: x['confidence'], reverse=True)[:5]

    def generate_insights(self, lat: float, lon: float,
                          aqi: float, category: str,
                          trend: str = 'stable') -> List[Dict]:
        """
        Generate contextual insights.

        Returns:
            List of insight dictionaries
        """
        insights = []
        now = time.time()

        # High pollution insight
        if aqi > 150:
            places = self.find_nearby_places(lat, lon)
            nearby_industrial = [p for p in places
                               if p['is_potential_source']
                               and p['distance_km'] < 1.5]

            if nearby_industrial:
                source = nearby_industrial[0]
                insights.append({
                    'timestamp': now,
                    'insight_type': 'contextual',
                    'message': f"Elevated pollution detected near industrial area ({source['distance_km']}km). "
                              f"Possible contributing source: {source['name']}",
                    'latitude': lat,
                    'longitude': lon,
                    'confidence': 0.7,
                    'related_source': source['name']
                })
            else:
                insights.append({
                    'timestamp': now,
                    'insight_type': 'high_pollution',
                    'message': f"Elevated air pollution (AQI: {aqi}) detected at this location. "
                              f"No obvious industrial sources nearby.",
                    'latitude': lat,
                    'longitude': lon,
                    'confidence': 0.5
                })

        # Trend insight
        if trend == 'rising' and aqi > 100:
            insights.append({
                'timestamp': now,
                'insight_type': 'trend',
                'message': "Rapid increase in pollution levels. This could indicate "
                          "a new pollution source or changing environmental conditions.",
                'latitude': lat,
                'longitude': lon,
                'confidence': 0.6
            })

        # Persistent high pollution
        if category in ['unhealthy', 'very_unhealthy', 'hazardous']:
            insights.append({
                'timestamp': now,
                'insight_type': 'alert',
                'message': f"Persistent unhealthy air quality (AQI: {aqi}). "
                          f"Consider reducing outdoor exposure.",
                'latitude': lat,
                'longitude': lon,
                'confidence': 0.9
            })

        # Good air quality
        if category == 'good' and aqi < 50:
            insights.append({
                'timestamp': now,
                'insight_type': 'positive',
                'message': "Air quality is excellent. Ideal conditions for outdoor activities.",
                'latitude': lat,
                'longitude': lon,
                'confidence': 0.9
            })

        return insights

    def get_location_context(self, lat: float, lon: float) -> Dict:
        """
        Get comprehensive location context.

        Returns:
            Dictionary with all context information
        """
        places = self.find_nearby_places(lat, lon)

        industrial_nearby = [p for p in places
                           if p['is_potential_source']
                           and p['distance_km'] < self.search_radius_km]

        return {
            'total_places_found': len(places),
            'industrial_count': len(industrial_nearby),
            'nearest_industrial_km': industrial_nearby[0]['distance_km'] if industrial_nearby else None,
            'nearby_places': places[:10],
            'industrial_zones': industrial_nearby[:5]
        }

    def create_safe_insight(self, template: str, **kwargs) -> str:
        """
        Create a safe, probabilistic insight message.

        This ensures we never blame specific entities and always
        use probabilistic language.
        """
        # Replace placeholders
        message = template.format(**kwargs)

        # Ensure probabilistic language
        safe_words = ['possibly', 'likely', 'may', 'suggest', 'potential']
        unsafe_words = ['definitely', 'certainly', 'caused by', 'due to']

        for word in unsafe_words:
            if word in message.lower():
                message = message.replace(word, 'possibly')

        return message