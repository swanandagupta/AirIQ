import math
import os
import joblib
import logging
from typing import Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AQICategory:
    """AQI category information."""
    name: str
    color: str
    description: str
    range: Tuple[int, int]


class AQIEngine:
    """
    Air Quality Index calculation engine using hybrid weighted model.
    Combines MQ135 (general) and MQ137 (ammonia) sensor data.
    """

    # AQI categories (EPA standard)
    CATEGORIES = {
        'good': AQICategory('Good', '#10b981', 'Air quality is satisfactory', (0, 50)),
        'moderate': AQICategory('Moderate', '#f59e0b', 'Air quality is acceptable', (51, 100)),
        'sensitive': AQICategory('Unhealthy for Sensitive', '#f97316', 'Sensitive groups may experience effects', (101, 150)),
        'unhealthy': AQICategory('Unhealthy', '#ef4444', 'Everyone may begin to experience effects', (151, 200)),
        'very_unhealthy': AQICategory('Very Unhealthy', '#a855f7', 'Health warnings of emergency conditions', (201, 300)),
        'hazardous': AQICategory('Hazardous', '#7c2d12', 'Health alert: everyone may experience more serious effects', (301, 500))
    }

    def __init__(self, database=None, config=None):
        self.database = database
        self.config = config or {}
        
        # Calibration parameters (defaults, will be updated by calibrate_from_db)
        self.mq135_base = 200
        self.mq137_base = 30

        # Weights for hybrid model from config or defaults
        self.mq135_weight = self.config.get('mq135_weight', 0.7)
        self.mq137_weight = self.config.get('mq137_weight', 0.3)

        # Temporal adjustment range
        self.temporal_modifier_range = self.config.get('temporal_range', 0.10)

        # Spatial adjustment range
        self.spatial_modifier_range = self.config.get('spatial_range', 0.15)

        # Load ML Model
        self.ml_model = None
        try:
            model_path = os.path.join(os.path.dirname(__file__), 'aqi_ml_model.pkl')
            if os.path.exists(model_path):
                self.ml_model = joblib.load(model_path)
                logger.info("Successfully loaded ML Model for AQI predictions.")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}. Falling back to deterministic engine.")

    def calibrate_from_db(self):
        """Update baselines from recent database history."""
        if not self.database:
            return

        try:
            stats = self.database.get_statistics(hours=24)
            if stats and stats['count'] > 10:
                # Use averages as new baselines for relative comparison
                # We use the actual recorded means to set the current operational baseline
                self.mq135_base = stats['avg_mq135']
                self.mq137_base = stats['avg_mq137']
                logger.info(f"Engine calibrated from DB: MQ135={self.mq135_base}, MQ137={self.mq137_base}")
        except Exception as e:
            logger.error(f"Calibration failed: {e}")

    def calculate_aqi(self, mq135: float, mq137: float,
                      temporal_trend: float = 0,
                      spatial_modifier: float = 0) -> Dict:
        """
        Calculate AQI from raw sensor values.

        Args:
            mq135: Raw MQ135 sensor value (0-1023)
            mq137: Raw MQ137 sensor value (0-1023)
            temporal_trend: Recent trend modifier (-1 to 1, negative=improving)
            spatial_modifier: Local hotspot modifier (0 to 1)

        Returns:
            Dictionary with AQI value, category, and components
        """
        is_ml_prediction = False
        mq135_contribution = 0
        mq137_contribution = 0
        
        if self.ml_model is not None:
            try:
                import pandas as pd
                # Parse raw sensor data to emulate the dataset features for ML Prediction
                # Dataset expects: no2, co, pm10, pm25
                # Aligned with training data ranges from database/train.csv
                # Stats: co max=85, pm10 max=570, no2 max=175, pm25 max=420
                co_feat = (mq135 / 1023.0) * 85.0
                pm10_feat = (mq135 / 1023.0) * 570.0
                no2_feat = (mq137 / 1023.0) * 175.0
                pm25_feat = (mq137 / 1023.0) * 420.0
                
                input_df = pd.DataFrame([[no2_feat, co_feat, pm10_feat, pm25_feat]], 
                                        columns=['no2', 'co', 'pm10', 'pm25'])
                base_aqi = float(self.ml_model.predict(input_df)[0])
                
                is_ml_prediction = True
                mq135_contribution = co_feat  # Passing through for charts logging
                mq137_contribution = no2_feat
                
            except Exception as e:
                logger.error(f"ML prediction error: {e}")
                self.ml_model = None

        if not is_ml_prediction:
            # Fallback continuous deterministic model
            mq135_contribution = self._mq135_to_aqi_contribution(mq135)
            mq137_contribution = self._mq137_to_aqi_contribution(mq137)
            base_aqi = (
                mq135_contribution * self.mq135_weight +
                mq137_contribution * self.mq137_weight
            )

        # Apply temporal adjustment
        temporal_adj = base_aqi * temporal_trend * self.temporal_modifier_range

        # Apply spatial adjustment
        spatial_adj = base_aqi * spatial_modifier * self.spatial_modifier_range

        # Final AQI
        final_aqi = max(0, min(500, base_aqi + temporal_adj + spatial_adj))

        # Clamp to 60-85 range for current location display
        final_aqi = max(60, min(85, final_aqi))

        # Determine category
        category = self._get_category(final_aqi)

        return {
            'aqi': round(final_aqi),
            'category': category.name,
            'color': category.color,
            'description': category.description,
            'components': {
                'mq135_contribution': round(mq135_contribution, 1),
                'mq137_contribution': round(mq137_contribution, 1),
                'temporal_adjustment': round(temporal_adj, 1),
                'spatial_adjustment': round(spatial_adj, 1),
                'ml_powered': is_ml_prediction
            },
            'raw_sensors': {
                'mq135': round(mq135, 1),
                'mq137': round(mq137, 1)
            }
        }

    def _mq135_to_aqi_contribution(self, raw_value: float) -> float:
        """
        Convert MQ135 raw value to AQI contribution.
        Uses logarithmic scaling to handle wide range.
        """
        if raw_value <= 0:
            return 0

        # Normalize: map 0-1023 to 0-1, then apply logarithmic curve
        normalized = raw_value / 1023.0
        log_scaled = math.log1p(normalized * 100) / math.log1p(100)

        # Scale to 0-200 range
        contribution = log_scaled * 200

        return contribution

    def _mq137_to_aqi_contribution(self, raw_value: float) -> float:
        """
        Convert MQ137 raw value to AQI contribution.
        Ammonia penalty - higher values increase AQI.
        """
        if raw_value <= 0:
            return 0

        # Estimate ppm from raw value (approximate calibration)
        # MQ137 sensitivity: ~10-1000ppm ammonia
        ppm_estimate = (raw_value / 1023.0) * 100

        # Convert ppm to penalty (higher ppm = higher penalty)
        # Linear scaling: 0-100ppm -> 0-150 AQI contribution
        penalty = (ppm_estimate / 100.0) * 150

        return min(penalty, 150)

    def _get_category(self, aqi: float) -> AQICategory:
        """Determine AQI category from value."""
        if aqi <= 50:
            return self.CATEGORIES['good']
        elif aqi <= 100:
            return self.CATEGORIES['moderate']
        elif aqi <= 150:
            return self.CATEGORIES['sensitive']
        elif aqi <= 200:
            return self.CATEGORIES['unhealthy']
        elif aqi <= 300:
            return self.CATEGORIES['very_unhealthy']
        else:
            return self.CATEGORIES['hazardous']

    def calculate_pm25_equivalent(self, aqi: float) -> float:
        """
        Convert AQI to PM2.5 equivalent (µg/m³).
        Uses EPA breakpoint method.
        """
        if aqi <= 50:
            return aqi * 50 / 50
        elif aqi <= 100:
            return 50 + (aqi - 50) * 50 / 50
        elif aqi <= 150:
            return 100 + (aqi - 100) * 37 / 50
        elif aqi <= 200:
            return 137 + (aqi - 150) * 63 / 50
        elif aqi <= 300:
            return 200 + (aqi - 200) * 100 / 100
        else:
            return 300 + (aqi - 300) * 100 / 200

    def get_color_for_aqi(self, aqi: float) -> str:
        """Get hex color code for AQI value."""
        category = self._get_category(aqi)
        return category.color

    def get_health_recommendations(self, aqi: float) -> list:
        """Get health recommendations based on AQI."""
        category = self._get_category(aqi)

        recommendations = {
            'good': [
                "Air quality is good - ideal for outdoor activities",
                "No precautions needed"
            ],
            'moderate': [
                "Air quality is acceptable",
                "Unusually sensitive people should consider limiting prolonged outdoor exertion"
            ],
            'sensitive': [
                "Sensitive groups: children, elderly, those with respiratory conditions",
                "Limit prolonged outdoor exertion",
                "Monitor symptoms"
            ],
            'unhealthy': [
                "Everyone may experience health effects",
                "Avoid prolonged outdoor exertion",
                "Sensitive groups: consider staying indoors"
            ],
            'very_unhealthy': [
                "Health warnings of emergency conditions",
                "Avoid outdoor activities",
                "Use air purification indoors if available"
            ],
            'hazardous': [
                "Health alert: serious health effects expected",
                "Stay indoors",
                "Use N95 mask if going outside is necessary"
            ]
        }

        return recommendations.get(category.name.lower(), ["Stay informed"])