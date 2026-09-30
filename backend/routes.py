from flask import Blueprint, jsonify, request
import logging
import serial.tools.list_ports

logger = logging.getLogger(__name__)

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')


def create_routes(db, aqi_engine, temporal_analyzer, spatial_processor, context_engine):
    """Create API routes with dependencies injected."""

    @api_bp.route('/status', methods=['GET'])
    def get_status():
        """Get system status."""
        from backend.main import serial_reader

        status = {
            'connected': serial_reader.is_connected if serial_reader else False,
            'port': serial_reader.port if serial_reader else 'N/A',
            'last_reading': db.get_latest_reading(),
            'statistics': db.get_statistics(hours=1)
        }
        return jsonify(status)

    @api_bp.route('/current', methods=['GET'])
    def get_current():
        """Get current air quality data."""
        latest = db.get_latest_reading()
        if not latest:
            return jsonify({
                'aqi': 0,
                'category': 'unknown',
                'no_data': True
            })

        return jsonify({
            'aqi': latest['aqi'],
            'category': latest['category'],
            'mq135': latest['mq135'],
            'mq137': latest['mq137'],
            'latitude': latest['latitude'],
            'longitude': latest['longitude'],
            'timestamp': latest['timestamp'],
            'recommendations': aqi_engine.get_health_recommendations(latest['aqi'])
        })

    @api_bp.route('/history', methods=['GET'])
    def get_history():
        """Get historical readings."""
        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 1000, type=int)

        hours = min(hours, 168)  # Max 7 days

        readings = db.get_readings(hours=hours, limit=limit)
        time_series = temporal_analyzer.get_time_series_data(readings, interval_minutes=5)

        return jsonify({
            'readings': readings,
            'time_series': time_series,
            'statistics': temporal_analyzer.get_statistics_summary(readings)
        })

    @api_bp.route('/heatmap', methods=['GET'])
    def get_heatmap():
        """Get heatmap data for visualization."""
        hours = request.args.get('hours', 24, type=int)
        readings = db.get_readings(hours=hours, limit=5000)

        heatmap_data = spatial_processor.generate_heatmap_data(readings)
        clusters = spatial_processor.get_clustered_readings(readings)
        hotspots = spatial_processor.detect_hotspots(readings)
        bounds = spatial_processor.get_bounds(readings)

        return jsonify({
            'heatmap': heatmap_data,
            'clusters': clusters,
            'hotspots': hotspots,
            'bounds': bounds
        })

    @api_bp.route('/alerts', methods=['GET'])
    def get_alerts():
        """Get recent alerts."""
        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 50, type=int)

        alerts = db.get_alerts(hours=hours, limit=limit)

        return jsonify({
            'alerts': alerts,
            'count': len(alerts)
        })

    @api_bp.route('/insights', methods=['GET'])
    def get_insights():
        """Get generated insights."""
        hours = request.args.get('hours', 24, type=int)
        insights = db.get_insights(hours=hours, limit=20)

        return jsonify({
            'insights': insights,
            'count': len(insights)
        })

    @api_bp.route('/location/<lat>/<lon>', methods=['GET'])
    def get_location_context(lat, lon):
        """Get context for a specific location."""
        try:
            lat = float(lat)
            lon = float(lon)
        except ValueError:
            return jsonify({'error': 'Invalid coordinates'}), 400

        context = context_engine.get_location_context(lat, lon)
        return jsonify(context)

    @api_bp.route('/grid', methods=['GET'])
    def get_grid_data():
        """Get grid-aggregated data."""
        hours = request.args.get('hours', 24, type=int)
        readings = db.get_readings(hours=hours, limit=5000)

        grid_data = spatial_processor.aggregate_by_grid(readings)

        return jsonify({
            'grid': grid_data,
            'count': len(grid_data)
        })

    # ─────────────────────────────────────────────────────
    # SERIAL PORT MANAGEMENT — dynamic, no hardcoding
    # ─────────────────────────────────────────────────────

    @api_bp.route('/serial/ports', methods=['GET'])
    def list_serial_ports():
        """List all available COM ports on the host machine."""
        try:
            ports = []
            for p in serial.tools.list_ports.comports():
                ports.append({
                    'device': p.device,
                    'description': p.description or p.device,
                    'hwid': p.hwid or ''
                })
            ports.sort(key=lambda x: x['device'])
            return jsonify({'ports': ports, 'count': len(ports)})
        except Exception as e:
            logger.error(f"Error listing serial ports: {e}")
            return jsonify({'ports': [], 'count': 0, 'error': str(e)})

    @api_bp.route('/serial/connect', methods=['POST'])
    def connect_serial():
        """Connect to a specific COM port at runtime."""
        from backend.main import serial_reader, handle_new_data
        body = request.get_json(silent=True) or {}
        port = body.get('port', '').strip()
        baudrate = int(body.get('baudrate', 115200))

        if not port:
            return jsonify({'success': False, 'error': 'port is required'}), 400

        try:
            # Stop existing reader
            if serial_reader and serial_reader.running:
                serial_reader.stop()
            if serial_reader:
                serial_reader.disconnect()

            # Reconfigure the existing reader with the new port
            serial_reader.port = port
            serial_reader.baudrate = baudrate
            serial_reader.reconnect_attempts = 0
            serial_reader.set_callback(handle_new_data)

            ok = serial_reader.connect()
            if ok:
                serial_reader.start()
                logger.info(f"Connected to {port} at {baudrate} baud")
                return jsonify({'success': True, 'port': port})
            else:
                return jsonify({'success': False, 'error': f'Could not open {port}. Is Arduino IDE Serial Monitor open?'}), 500
        except Exception as e:
            logger.error(f"Connect error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @api_bp.route('/serial/disconnect', methods=['POST'])
    def disconnect_serial():
        """Disconnect the current serial reader."""
        from backend.main import serial_reader
        try:
            if serial_reader:
                serial_reader.stop()
                serial_reader.disconnect()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # ─────────────────────────────────────────────────────
    # MANUAL READING INJECTION
    # Allows the dashboard to push a reading when hardware is
    # NOT on serial but the user types values directly into the UI.
    # ─────────────────────────────────────────────────────

    @api_bp.route('/manual-reading', methods=['POST'])
    def manual_reading():
        """
        Inject a manual sensor reading into the pipeline.
        Body JSON: { mq135: float, mq137: float, latitude?: float, longitude?: float }
        GPS defaults to VIT Chennai if not provided.
        """
        from backend.main import handle_new_data
        import time as _time
        body = request.get_json(silent=True) or {}

        try:
            mq135 = float(body.get('mq135', 0))
            mq137 = float(body.get('mq137', 0))

            # VIT Chennai fallback — but only as fallback, never hardcoded override
            lat = float(body.get('latitude', 12.8432))
            lon = float(body.get('longitude', 80.1546))

            if not (0 <= mq135 <= 1023):
                return jsonify({'error': 'mq135 must be 0–1023'}), 400
            if not (0 <= mq137 <= 1023):
                return jsonify({'error': 'mq137 must be 0–1023'}), 400

            data = {
                'mq135': mq135,
                'mq137': mq137,
                'latitude': lat,
                'longitude': lon,
                'timestamp': _time.time()
            }
            handle_new_data(data)
            return jsonify({'success': True, 'received': data})
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Invalid input: {e}'}), 400

    return api_bp