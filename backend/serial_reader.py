import serial
import json
import logging
import threading
import time
from collections import deque
from typing import Optional, Tuple, Callable

logger = logging.getLogger(__name__)


class SerialReader:
    """Handles serial communication with ESP32 for sensor data ingestion."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: int = 5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.data_callback: Optional[Callable] = None
        self.filter_window = deque(maxlen=5)

        # Connection state
        self.is_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10

    def set_callback(self, callback: Callable):
        """Set callback function for new data."""
        self.data_callback = callback

    def connect(self) -> bool:
        """Establish serial connection."""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            self.is_connected = True
            self.reconnect_attempts = 0
            logger.info(f"Connected to serial port {self.port}")
            return True
        except serial.SerialException as e:
            error_msg = str(e)
            if "Access is denied" in error_msg or "PermissionError" in error_msg:
                logger.error(f"Access Denied to {self.port}. Is the Arduino IDE Serial Monitor open? Please close it.")
            else:
                logger.error(f"Failed to connect to {self.port}: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """Close serial connection."""
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.is_connected = False
        logger.info("Disconnected from serial port")

    def start(self):
        """Start reading from serial port in background thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        logger.info("Serial reader started")

    def stop(self):
        """Stop reading from serial port."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("Serial reader stopped")

    def _read_loop(self):
        """Background loop to read and process serial data."""
        while self.running:
            if not self.is_connected or not self.serial_conn:
                if not self._reconnect():
                    time.sleep(2)
                    continue

            try:
                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    data = self._parse_line(line)
                    if data:
                        processed = self._apply_filter(data)
                        if processed and self.data_callback:
                            self.data_callback(processed)
                else:
                    time.sleep(0.1)
            except serial.SerialException as e:
                logger.error(f"Serial error: {e}")
                self.is_connected = False
            except Exception as e:
                logger.error(f"Error reading data: {e}")
                time.sleep(0.5)

    def _parse_line(self, line: str) -> Optional[dict]:
        """Parse serial line into structured data."""
        try:
            # Expected format: mq135,mq137,latitude,longitude
            parts = line.split(',')
            if len(parts) < 4:
                return None

            try:
                mq135 = float(parts[0].strip())
            except ValueError:
                mq135 = 0.0 # MQ135 is disconnected/malformed
                
            mq137 = float(parts[1].strip())
            lat = float(parts[2].strip())
            lon = float(parts[3].strip())

            # Validate data
            if mq135 < 0 or mq135 > 1023:
                mq135 = 0.0

            if mq137 < 0 or mq137 > 1023:
                return None

            # Filter invalid GPS (0,0 is invalid)
            # NOTE: The ESP32 sketch itself already sends VIT Chennai default (12.8432, 80.1546)
            # when GPS has no fix. This fallback only catches corrupted/zero reads from the wire.
            if lat == 0.0 and lon == 0.0:
                # Treat a raw 0,0 from the wire as a GPS drop — use VIT Chennai
                lat = 12.8432
                lon = 80.1546
            elif lat < -90 or lat > 90 or lon < -180 or lon > 180:
                return None

            return {
                'mq135': mq135,
                'mq137': mq137,
                'latitude': lat,
                'longitude': lon,
                'timestamp': time.time()
            }
        except (ValueError, IndexError) as e:
            logger.debug(f"Failed to parse line: {line} - {e}")
            return None

    def _apply_filter(self, data: dict) -> Optional[dict]:
        """Apply moving average filter to reduce noise."""
        # Check if we have enough samples for filtering
        if len(self.filter_window) < 3:
            self.filter_window.append(data)
            return data

        # Calculate moving averages for smoothing
        mq135_sum = sum(d['mq135'] for d in self.filter_window)
        mq137_sum = sum(d['mq137'] for d in self.filter_window)

        avg_mq135 = mq135_sum / len(self.filter_window)
        avg_mq137 = mq137_sum / len(self.filter_window)

        # Apply slight smoothing to current reading
        smoothed = {
            'mq135': (data['mq135'] + avg_mq135) / 2,
            'mq137': (data['mq137'] + avg_mq137) / 2,
            'latitude': data['latitude'],
            'longitude': data['longitude'],
            'timestamp': data['timestamp']
        }

        self.filter_window.append(data)
        return smoothed

    def _reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff."""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached. Resetting attempts and waiting before retrying...")
            time.sleep(5)
            self.reconnect_attempts = 0
            return False

        self.reconnect_attempts += 1
        delay = min(2 ** self.reconnect_attempts, 30)
        logger.info(f"Reconnecting in {delay}s (attempt {self.reconnect_attempts})")
        time.sleep(delay)

        return self.connect()

    def get_status(self) -> dict:
        """Get connection status."""
        return {
            'connected': self.is_connected,
            'port': self.port,
            'reconnect_attempts': self.reconnect_attempts
        }


class SimulatedSerialReader:
    """Simulated serial reader for testing without ESP32."""

    def __init__(self, port: str = "SIM", baudrate: int = 115200, timeout: int = 5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.data_callback: Optional[Callable] = None
        self.is_connected = True

        # Simulation parameters
        self.base_lat = 12.8432
        self.base_lon = 80.1546
        self.aqi_trend = 0

    def set_callback(self, callback: Callable):
        self.data_callback = callback

    def connect(self) -> bool:
        self.is_connected = True
        return True

    def disconnect(self):
        self.is_connected = False

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._simulate_loop, daemon=True)
        self.thread.start()
        logger.info("Simulated serial reader started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _simulate_loop(self):
        """Generate simulated sensor data."""
        import random

        while self.running:
            try:
                # Simulate varying pollution levels
                self.aqi_trend += random.uniform(-5, 5)
                self.aqi_trend = max(-50, min(50, self.aqi_trend))

                # Generate MQ135 (0-1023) - base + trend
                # Real Average is ~197, Min is 50
                base_mq135 = 197 + self.aqi_trend * 2
                mq135 = max(50, min(900, base_mq135 + random.gauss(0, 40)))

                # Generate MQ137 (0-1023) - ammonia
                # Real Average is ~57, Min is 10
                base_mq137 = 57 + max(0, self.aqi_trend) * 0.5
                mq137 = max(10, min(500, base_mq137 + random.gauss(0, 15)))

                # Simulate GPS movement
                lat = self.base_lat + random.gauss(0, 0.001)
                lon = self.base_lon + random.gauss(0, 0.001)

                data = {
                    'mq135': mq135,
                    'mq137': mq137,
                    'latitude': lat,
                    'longitude': lon,
                    'timestamp': time.time()
                }

                if self.data_callback:
                    self.data_callback(data)

                time.sleep(2)  # Every 2 seconds

            except Exception as e:
                logger.error(f"Simulation error: {e}")
                time.sleep(1)

    def get_status(self) -> dict:
        return {
            'connected': self.is_connected,
            'port': self.port,
            'reconnect_attempts': 0
        }