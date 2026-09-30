import json
import logging
import os
import sys
import time
import threading
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules
from backend.serial_reader import SerialReader, SimulatedSerialReader
from backend.aqi_engine import AQIEngine
from backend.database import Database
from backend.analytics import TemporalAnalyzer
from backend.spatial import SpatialProcessor
from backend.context import ContextEngine
from backend.routes import create_routes

# Ensure logs directory exists before configuring logger
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'system.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global instances (will be initialized in app)
serial_reader = None
database = None
aqi_engine = None
temporal_analyzer = None
spatial_processor = None
context_engine = None
socketio = None


def load_config():
    """Load configuration from file."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load config: {e}, using defaults")
        return {
            'serial': {'port': 'COM3', 'baudrate': 115200, 'timeout': 5},
            'database': {'path': 'data/air_quality.db', 'retention_days': 7},
            'analytics': {'moving_average_window': 10, 'anomaly_threshold': 2.0},
            'spatial': {'grid_size': 0.001, 'heatmap_radius': 200},
            'context': {'search_radius_km': 2, 'cache_ttl_seconds': 3600},
            'server': {'host': '0.0.0.0', 'port': 5000}
        }


def create_app(simulate=False):
    """Create and configure Flask application."""
    global serial_reader, database, aqi_engine
    global temporal_analyzer, spatial_processor, context_engine, socketio

    # Get absolute paths - use __file__ for correct resolution
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(backend_dir)
    frontend_dir = os.path.join(base_dir, 'frontend')
    static_dir = os.path.join(frontend_dir, 'static')

    logger.info(f"Backend dir: {backend_dir}")
    logger.info(f"Base dir: {base_dir}")
    logger.info(f"Frontend dir: {frontend_dir}")
    logger.info(f"Static dir: {static_dir}")
    logger.info(f"Static exists: {os.path.exists(static_dir)}")

    app = Flask(__name__,
                template_folder=frontend_dir,
                static_folder=static_dir,
                static_url_path='/static')

    # Emergency fallback static route just in case Flask static gets lost
    @app.route('/assets/<path:filename>')
    def custom_asset_serving(filename):
        from flask import send_from_directory
        return send_from_directory(static_dir, filename)

    # Debug route to check static folder manually
    @app.route('/debug/static')
    def debug_static():
        return {
            'static_dir_value': static_dir,
            'static_exists': os.path.exists(static_dir)
        }

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

    # Load configuration
    config = load_config()

    # Ensure data directory exists
    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)

    # Initialize database
    db_path = config['database']['path']
    if not os.path.isabs(db_path):
        db_path = os.path.join(base_dir, db_path)
        
    database = Database(
        db_path=db_path,
        retention_days=config['database']['retention_days']
    )

    # Initialize AQI engine (with database for dynamic calibration)
    aqi_engine = AQIEngine(database=database, config=config.get('engine', {}))
    aqi_engine.calibrate_from_db()

    # Initialize analyzers
    temporal_analyzer = TemporalAnalyzer(
        moving_average_window=config['analytics']['moving_average_window'],
        anomaly_threshold=config['analytics']['anomaly_threshold']
    )

    spatial_processor = SpatialProcessor(
        grid_size=config['spatial']['grid_size'],
        heatmap_radius=config['spatial']['heatmap_radius']
    )

    context_engine = ContextEngine(
        database=database,
        search_radius_km=config['context']['search_radius_km'],
        cache_ttl_seconds=config['context']['cache_ttl_seconds']
    )

    # Initialize serial reader
    if simulate:
        serial_reader = SimulatedSerialReader()
        logger.info("Using simulated serial reader")
    else:
        serial_reader = SerialReader(
            port=config['serial']['port'],
            baudrate=config['serial']['baudrate'],
            timeout=config['serial']['timeout']
        )

    # Set up data callback
    serial_reader.set_callback(handle_new_data)

    # Create routes
    api_bp = create_routes(
        database, aqi_engine, temporal_analyzer,
        spatial_processor, context_engine
    )
    app.register_blueprint(api_bp)

    # Main routes
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/heatmap')
    def heatmap():
        return render_template('heatmap.html')

    @app.route('/health')
    def health():
        return {'status': 'ok', 'connected': serial_reader.is_connected}

    # WebSocket events
    @socketio.on('connect')
    def handle_connect():
        logger.info('Client connected')
        # Send current state on connect
        emit_current_data()

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('Client disconnected')

    @socketio.on('request_update')
    def handle_request_update():
        emit_current_data()

    # Background tasks
    def background_tasks():
        """Handle periodic cleanup and calibration."""
        while True:
            time.sleep(3600)  # Every hour
            try:
                database.cleanup_old_data()
                # Refresh engine calibration based on latest data trends
                if aqi_engine:
                    aqi_engine.calibrate_from_db()
                logger.info("Executed periodic background tasks (cleanup & calibration)")
            except Exception as e:
                logger.error(f"Background task error: {e}")

    # Start background tasks
    bg_thread = threading.Thread(target=background_tasks, daemon=True)
    bg_thread.start()

    return app, socketio


def handle_new_data(data: dict):
    """Process new sensor data."""
    try:
        # Get temporal modifier from trend
        temporal_modifier = temporal_analyzer.get_trend_modifier()

        # Calculate AQI
        result = aqi_engine.calculate_aqi(
            mq135=data['mq135'],
            mq137=data['mq137'],
            temporal_trend=temporal_modifier,
            spatial_modifier=0
        )

        # Add to temporal analyzer
        temporal_analyzer.add_reading(result['aqi'])

        # Prepare full reading record
        reading = {
            'timestamp': data['timestamp'],
            'mq135': data['mq135'],
            'mq137': data['mq137'],
            'latitude': data['latitude'],
            'longitude': data['longitude'],
            'aqi': result['aqi'],
            'category': result['category']
        }

        # Save to database
        database.insert_reading(reading)

        # Check for alerts
        alerts = temporal_analyzer.check_alert_conditions(
            aqi=result['aqi'],
            category=result['category'],
            lat=data['latitude'],
            lon=data['longitude']
        )

        for alert in alerts:
            database.insert_alert(alert)

        # Generate insights if AQI is notable
        if result['aqi'] > 75:
            trend, _ = temporal_analyzer.detect_trend()
            insights = context_engine.generate_insights(
                lat=data['latitude'],
                lon=data['longitude'],
                aqi=result['aqi'],
                category=result['category'],
                trend=trend
            )

            for insight in insights:
                database.insert_insight(insight)

        # Emit to connected clients
        emit_data_update(reading, result, alerts)

    except Exception as e:
        logger.error(f"Error processing data: {e}")


def emit_current_data():
    """Emit current reading to client."""
    latest = database.get_latest_reading()
    if latest:
        result = aqi_engine.calculate_aqi(
            mq135=latest['mq135'],
            mq137=latest['mq137']
        )
        emit_data_update(latest, result, [])


def emit_data_update(reading: dict, aqi_result: dict, alerts: list):
    """Emit data update via WebSocket."""
    if socketio:
        socketio.emit('data_update', {
            'reading': reading,
            'aqi': aqi_result,
            'alerts': alerts
        })


def run_app(simulate=False):
    """Run the application."""
    global socketio

    app, socketio = create_app(simulate=simulate)
    config = load_config()

    # Start serial reader
    serial_reader.connect()
    serial_reader.start()

    # Run with SocketIO
    socketio.run(
        app,
        host=config['server']['host'],
        port=config['server']['port'],
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )


if __name__ == '__main__':
    simulate = '--simulate' in sys.argv or '-s' in sys.argv
    run_app(simulate=simulate)