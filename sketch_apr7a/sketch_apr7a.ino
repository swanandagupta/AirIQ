#include <TinyGPS++.h>
#include <HardwareSerial.h>

// MQ Sensors
#define MQ137_PIN 4
#define MQ135_PIN 5

// GPS
#define GPS_RX 18
#define GPS_TX 19

// Chennai, Tamil Nadu default coordinates (used when GPS has no fix)
#define DEFAULT_LAT 12.9716
#define DEFAULT_LON 80.2209

TinyGPSPlus gps;
HardwareSerial gpsSerial(1);

void setup() {
  Serial.begin(115200);

  // Start GPS
  gpsSerial.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);

  Serial.println("AirIQ Sensor System Starting...");
  Serial.println("Location default: Chennai, Tamil Nadu");
}

void loop() {

  // ===== READ SENSORS =====
  int mq137Value = analogRead(MQ137_PIN);
  int mp135Value = analogRead(MQ135_PIN);

  // ===== READ GPS =====
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  // ===== PRINT OUTPUT FORMATTED FOR PYTHON BACKEND =====
  // Expected format: mq135,mq137,latitude,longitude
  Serial.print(mp135Value);
  Serial.print(",");
  Serial.print(mq137Value);
  Serial.print(",");
  
  if (gps.location.isValid() && 
      !(gps.location.lat() == 0.0 && gps.location.lng() == 0.0)) {
    // Valid GPS fix
    Serial.print(gps.location.lat(), 6);
    Serial.print(",");
    Serial.println(gps.location.lng(), 6);
  } else {
    // GPS not available (indoor use) — use Chennai, Tamil Nadu as default
    Serial.print(DEFAULT_LAT, 4);
    Serial.print(",");
    Serial.println(DEFAULT_LON, 4);
  }

  delay(2000);
}