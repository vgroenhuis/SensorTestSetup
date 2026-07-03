#include "pressureSensor.h"
#include <TCA9548.h>
#include <Preferences.h>

/*
 * WF100DPZ datasheet:
 * WFsensors WF100DPZ (no communication details): https://wfsensors.com/digital-pressure-sensor-i2c-spi/wf100dpz-digital-pressure-sensor-series
 * WFsensors 
 * JLCPCB WF100DPZ: https://jlc-prod-smt.oss-eu-central-1.aliyuncs.com/smtDataManualFile/8589835840462348288-C3001181.pdfhttps://jlcpcb.com/partdetail/WF-WF100DPZ_1BG_D6DT/C3001181
 *
 * Protocol:
 *  
 */

TCA9548 pressureSensorMultiplexer(TCA_ADDR);

float sensorOffsetBar[PRESSURE_SENSOR_COUNT] = {0, 0};

namespace {
    const char *PRESSURE_SETTINGS_NAMESPACE = "press_cfg";
    const char *KEY_SENSOR_OFFSET_PREFIX = "off";
    const char *KEY_ENABLED = "enabled";
    bool pressureSensorsEnabled = true;
    bool pressureMultiplexerInitialized = false;

    bool loadPressureOffsetsFromNvs() {
        Preferences preferences;
        if (!preferences.begin(PRESSURE_SETTINGS_NAMESPACE, true)) {
            Serial.println("NVS open failed for reading pressure offsets");
            return false;
        }

        for (int i = 0; i < PRESSURE_SENSOR_COUNT; i++) {
            const String key = String(KEY_SENSOR_OFFSET_PREFIX) + String(i);
            sensorOffsetBar[i] = preferences.getFloat(key.c_str(), sensorOffsetBar[i]);
        }

        preferences.end();
        return true;
    }

    bool loadPressureEnabledFromNvs() {
        Preferences preferences;
        if (!preferences.begin(PRESSURE_SETTINGS_NAMESPACE, true)) {
            Serial.println("NVS open failed for reading pressure settings");
            return false;
        }

        pressureSensorsEnabled = preferences.getBool(KEY_ENABLED, pressureSensorsEnabled);
        preferences.end();
        return true;
    }

    bool savePressureOffsetsToNvs() {
        Preferences preferences;
        if (!preferences.begin(PRESSURE_SETTINGS_NAMESPACE, false)) {
            Serial.println("NVS open failed for writing pressure offsets");
            return false;
        }

        bool allOk = true;
        for (int i = 0; i < PRESSURE_SENSOR_COUNT; i++) {
            const String key = String(KEY_SENSOR_OFFSET_PREFIX) + String(i);
            const size_t bytesWritten = preferences.putFloat(key.c_str(), sensorOffsetBar[i]);
            if (bytesWritten != sizeof(float)) {
                allOk = false;
            }
        }

        preferences.end();
        return allOk;
    }

    bool savePressureEnabledToNvs() {
        Preferences preferences;
        if (!preferences.begin(PRESSURE_SETTINGS_NAMESPACE, false)) {
            Serial.println("NVS open failed for writing pressure settings");
            return false;
        }

        const bool ok = preferences.putBool(KEY_ENABLED, pressureSensorsEnabled) > 0;
        preferences.end();
        return ok;
    }
}

void initPressureSensor() {
    Serial.println("Initializing pressure sensor");
    loadPressureEnabledFromNvs();
    loadPressureOffsetsFromNvs();

    if (!pressureSensorsEnabled) {
        pressureMultiplexerInitialized = false;
        Serial.println("Pressure sensors disabled in settings, skipping initialization");
        return;
    }

    if(!pressureSensorMultiplexer.begin()) {
        Serial.println("Pressure sensor multiplexer failed to initialize!");
        pressureMultiplexerInitialized = false;
        return;
    }

    pressureMultiplexerInitialized = true;
}

bool arePressureSensorsEnabled() {
    return pressureSensorsEnabled;
}

bool setPressureSensorsEnabled(bool enabled) {
    if (pressureSensorsEnabled == enabled) {
        return true;
    }

    pressureSensorsEnabled = enabled;
    if (!savePressureEnabledToNvs()) {
        Serial.println("Failed to persist pressure sensor enabled setting");
        return false;
    }

    if (!pressureSensorsEnabled) {
        pressureMultiplexerInitialized = false;
        return true;
    }

    if (!pressureSensorMultiplexer.begin()) {
        Serial.println("Pressure sensor multiplexer failed to initialize while enabling");
        pressureSensorsEnabled = false;
        savePressureEnabledToNvs();
        pressureMultiplexerInitialized = false;
        return false;
    }

    pressureMultiplexerInitialized = true;
    return true;
}

// Zero-calibrates sensor of this id
void zeroCalibratePressure(int sensorId) {
    if (!pressureSensorsEnabled || !pressureMultiplexerInitialized) {
        Serial.println("Pressure sensors are disabled; skipping zero calibration");
        return;
    }

    if (sensorId < 0 || sensorId >= PRESSURE_SENSOR_COUNT) {
        Serial.println("Invalid pressure sensor ID for zero calibration");
        return;
    }

    const float measuredPressure = readPressureSensorSingleShot(sensorId);
    if (isnan(measuredPressure)) {
        Serial.println("Pressure zero calibration failed: sensor read returned NaN");
        return;
    }

    sensorOffsetBar[sensorId] -= measuredPressure;
    if (!savePressureOffsetsToNvs()) {
        Serial.println("Failed to persist pressure sensor offsets to NVS");
    }
}

// Send command to start measurement on WF100DPZ10BG sensor, assuming it is already selected by the I2C multiplexer
void startPressureMeasurementSingleShot() {
    Wire.beginTransmission(PRESSURE_SENSOR_ADDR);
    Wire.write(0x30);      // Command register
    //Wire.write(0x09);      // Command to perform one output measurement. = 1000b, which is "once sensor signal conversion"
    Wire.write(0x0A);      // Command to perform one output measurement. = 1010b, which is "once temperature conversion immediately followed by once sensor signal conversion"
    Wire.endTransmission();
}

/**
 * @brief Reads pressure in bar from the WF100DPZ10BG using TCA9548 multiplexer channel.
 * 
 * Steps:
 * - Uses TCA9548.selectChannel(channel) to route I2C to selected sensor.
 * - Polls sensor status register 0x02 for measurement readiness.
 * - Reads 3 bytes raw pressure data from register 0x06.
 * - Converts raw 24-bit signed integer to normalized float.
 * - Maps normalized value to calibrated pressure range (0-10 bar).
 * - Starts next measurement for continuous reading.
 * 
 * @param sensorId I2C multiplexer channel where sensor is connected.
 * @return float Pressure in bars or NAN if communication fails.
 */
float readPressureSensorSingleShot(uint8_t sensorId){
    if (!pressureSensorsEnabled || !pressureMultiplexerInitialized) {
        return NAN;
    }

    // check if sensorId is valid
    if(sensorId >= PRESSURE_SENSOR_COUNT){
        Serial.println("Invalid pressure sensor ID");
        return NAN;
    } 

    // Select desired I2C channel on internal multiplexer of pressure sensor
    if (!pressureSensorMultiplexer.selectChannel(sensorId)) {
        Serial.print("Failed to select I2C channel: ");
        Serial.println(sensorId);
        return NAN;
    }

    // Poll sensor status register (0x02) for measurement ready bit (bit0)
    Wire.beginTransmission(PRESSURE_SENSOR_ADDR);
    Wire.write(0x02);
    Wire.endTransmission();
    Wire.requestFrom(PRESSURE_SENSOR_ADDR, 1);

    bool statusOk = false;
    if (Wire.available()) {
        statusOk = Wire.read() & 0x01;
    }

    // If not ready, trigger a measurement and retry once
    if (!statusOk) {
        startPressureMeasurementSingleShot();
        delay(10);

        Wire.beginTransmission(PRESSURE_SENSOR_ADDR);
        Wire.write(0x02);
        Wire.endTransmission();
        Wire.requestFrom(PRESSURE_SENSOR_ADDR, 1);

        if (Wire.available()) {
            statusOk = Wire.read() & 0x01;
        } else {
            return NAN;
        }
    }

    if (!statusOk) {
        return NAN;
    }

    // Read 3-byte pressure register 0x06 MSB first
    Wire.beginTransmission(PRESSURE_SENSOR_ADDR);
    Wire.write(0x06);
    Wire.endTransmission();
    Wire.requestFrom(PRESSURE_SENSOR_ADDR, 3);

    if (Wire.available() < 3) {
        return NAN;
    }

    // Collect 3 bytes of raw pressure data
    uint32_t rawPressure = 0;
    for (int i = 0; i < 3; i++) {
        rawPressure = (rawPressure << 8) | Wire.read();
    }

    // Start next measurement immediately after reading for continuous operation
    startPressureMeasurementSingleShot();

    // Convert 24-bit signed integer raw pressure to normalized float
    float pressureNormalized = (rawPressure < 8388608)
        ? (float)rawPressure / 8388608.0f
        : ((float)rawPressure - 16777216.0f) / 8388608.0f;

    // Map normalized pressure value to calibrated pressure range (0-10 bar)
    float pressureBar = (pressureNormalized + 0.731f) * 10.0f;

    return pressureBar + sensorOffsetBar[sensorId];
}

std::array<float, PRESSURE_SENSOR_COUNT> readPressureSensorsSingleShot() {
    std::array<float, PRESSURE_SENSOR_COUNT> pressures;
    for (int i=0; i<PRESSURE_SENSOR_COUNT; i++) {
        pressures[i] = readPressureSensorSingleShot(i);
    }

    return pressures;
}