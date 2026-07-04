#include "serverApi.h"
#include "nvsSettings.h"
#include "RoamingWiFiManager.h"
#include <LittleFS.h>
#include <Preferences.h>
#include "websiteRoot.h"
#include "gpioExpanders.h"
#include "pressureSensor.h"
#include "tofSensor.h"
#include "globalVars.h"
#include "pwmServo.h"
#include "oled.h"
#include "matrix.h"
#include <array>
#include "dcMotor.h"

namespace {
    AsyncWebSocket potentiometerWebSocket("/ws/potentiometer");
    AsyncWebSocket statisticsWebSocket("/ws/statistics");
    AsyncWebSocket mhSensorWebSocket("/ws/mhSensor");
    AsyncWebSocket mcp3008WebSocket("/ws/mcp3008");
    AsyncWebSocket mcp23017InputsWebSocket("/ws/mcp23017inputs");
    AsyncWebSocket rotaryEncoderWebSocket("/ws/rotaryEncoder");
    AsyncWebSocket pressureSensorsWebSocket("/ws/pressureSensors");
    AsyncWebSocket tofSensorWebSocket("/ws/tofSensor");
    unsigned long lastPotentiometerPublishMs = 0;
    unsigned long lastStatisticsPublishMs = 0;
    unsigned long lastMhSensorPublishMs = 0;
    unsigned long lastMcp3008PublishMs = 0;
    unsigned long lastMcp23017InputsPublishMs = 0;
    unsigned long lastRotaryEncoderPublishMs = 0;
    unsigned long lastPressureSensorsPublishMs = 0;
    unsigned long lastTofSensorPublishMs = 0;
    const unsigned long potentiometerPublishIntervalMs = 50;
    const unsigned long statisticsPublishIntervalMs = 50;
    const unsigned long mhSensorPublishIntervalMs = 50;
    const unsigned long mcp3008PublishIntervalMs = 50;
    const unsigned long mcp23017InputsPublishIntervalMs = 50;
    const unsigned long rotaryEncoderPublishIntervalMs = 50;
    const unsigned long pressureSensorsPublishIntervalMs = 50;
    const unsigned long tofSensorPublishIntervalMs = 50;

    String potentiometerJson() {
        return String("{\"millis\":") + millis() + ",\"voltage\":" + String(readAdcAnalogVolt(POTMETER_ADC_PIN), 3) + "}";
    }

    String statisticsJson() {
        return String("{\"millis\":") + millis() + ",\"mainLoopFps\":" + String(mainLoopFps, 2) + "}";
    }

    String mhSensorJson() {
        return String("{\"millis\":") + millis() + ",\"voltage\":" + String(readAdcAnalogVolt(6), 3) + "}";
    }

    String rotaryEncoderJson() {
        return String("{\"interruptCount\":") + getEncoderInterruptCount() +
               ",\"encoderCount\":" + getEncoderPos() +
               ",\"encoderDoubleStepCount\":" + getencoderDoubleStepCount() +
               ",\"encABBits\":" + getEncABPins() + "}";
    }

    String mcp3008Json() {
        const std::array<float, 8> values = readAdcAnalogVoltAll();
        String json = String("{\"millis\":") + millis() + ",\"channels\":[";
        for (size_t i = 0; i < values.size(); ++i) {
            if (i > 0) {
                json += ",";
            }
            json += String(values[i], 3);
        }
        json += "]}";
        return json;
    }

    String mcp23017InputsJson() {
        const uint8_t bankAValue = getDigitalBankA();
        const uint8_t bankBValue = getDigitalBankB();
        const Mcp23017Settings settings = getMcp23017Settings();
        String json = String("{\"millis\":") + millis() +
                      ",\"bankA\":" + String(bankAValue) +
                      ",\"bankB\":" + String(bankBValue) +
                      ",\"outputA\":" + String(settings.outputA) +
                      ",\"outputB\":" + String(settings.outputB) +
                      ",\"bitsA\":[";
        for (int bit = 0; bit < 8; ++bit) {
            if (bit > 0) {
                json += ",";
            }
            json += ((bankAValue >> bit) & 0x01) ? "1" : "0";
        }
        json += "],\"bitsB\":[";
        for (int bit = 0; bit < 8; ++bit) {
            if (bit > 0) {
                json += ",";
            }
            json += ((bankBValue >> bit) & 0x01) ? "1" : "0";
        }
        json += "]}";
        return json;
    }

    String mcp23017SettingsJson() {
        const Mcp23017Settings settings = getMcp23017Settings();
        return String("{\"modeA\":") + settings.modeA +
               ",\"pullupA\":" + settings.pullupA +
               ",\"modeB\":" + settings.modeB +
               ",\"pullupB\":" + settings.pullupB +
               ",\"outputA\":" + settings.outputA +
               ",\"outputB\":" + settings.outputB +
               ",\"readA\":" + getDigitalBankA() +
               ",\"readB\":" + getDigitalBankB() + "}";
    }

    String pressureSensorsJson() {
        const std::array<float, PRESSURE_SENSOR_COUNT> values = readPressureSensorsSingleShot();
        String json = String("{\"millis\":") + millis() +
                      ",\"enabled\":" + (arePressureSensorsEnabled() ? "true" : "false") +
                      ",\"pressures\":[";
        for (size_t i = 0; i < values.size(); ++i) {
            if (i > 0) {
                json += ",";
            }
            if (isnan(values[i])) {
                json += "null";
            } else {
                json += String(values[i], 3);
            }
        }
        json += "]}";
        return json;
    }

    String pressureSensorsSettingsJson() {
        return String("{\"enabled\":") + (arePressureSensorsEnabled() ? "true" : "false") + "}";
    }

    bool tofStatusIsValid(uint8_t status) {
        return status == 5 || status == 9;
    }

    bool parseTofMode(const String &value, uint8_t &outResolution) {
        if (value == "4x4") {
            outResolution = VL53L7CX_RESOLUTION_4X4;
            return true;
        }
        if (value == "8x8") {
            outResolution = VL53L7CX_RESOLUTION_8X8;
            return true;
        }
        return false;
    }

    String tofModeToString(uint8_t resolution) {
        return resolution == VL53L7CX_RESOLUTION_8X8 ? "8x8" : "4x4";
    }

    String tofSensorJson() {
        const uint8_t tofZonesPerLine = getTofGridSide();
        const uint8_t tofZoneCount = getTofZoneCount();

        VL53L7CX_ResultsData results;
        const TofServerSettings settings = getTofServerSettings();
        const bool hasData = getLatestTofDataForPublish(results);
        String json = String("{\"millis\":") + millis() +
                      ",\"resolution\":\"" + tofModeToString(settings.resolution) + "\"" +
                      ",\"gridSide\":" + tofZonesPerLine +
                      ",\"zones\":[";

        for (uint8_t zone = 0; zone < tofZoneCount; ++zone) {
            if (zone > 0) {
                json += ",";
            }

            const uint8_t targetIndex = zone * VL53L7CX_NB_TARGET_PER_ZONE;
            const uint8_t targetCount = hasData ? results.nb_target_detected[zone] : 0;
            const bool hasTarget = targetCount > 0;
            const uint8_t status = hasData ? results.target_status[targetIndex] : 0;
            const bool valid = hasTarget && tofStatusIsValid(status);

            json += String("{\"index\":") + zone +
                    ",\"row\":" + (zone / tofZonesPerLine) +
                    ",\"col\":" + (zone % tofZonesPerLine) +
                    ",\"targetCount\":" + targetCount +
                    ",\"status\":" + status +
                    ",\"valid\":" + (valid ? "true" : "false") +
                    ",\"distanceMm\":" + (hasTarget ? String((long)results.distance_mm[targetIndex]) : String("null")) +
                    "}";
        }

        json += "]}";
        return json;
    }

    void onPotentiometerWebSocketEvent(AsyncWebSocket *server,
                                       AsyncWebSocketClient *client,
                                       AwsEventType type,
                                       void *arg,
                                       uint8_t *data,
                                       size_t len) {
        (void)server;
        (void)arg;
        (void)data;
        (void)len;

        if (type == WS_EVT_CONNECT) {
            client->text(potentiometerJson());
        }
    }

    void onRotaryEncoderWebSocketEvent(AsyncWebSocket *server,
                                       AsyncWebSocketClient *client,
                                       AwsEventType type,
                                       void *arg,
                                       uint8_t *data,
                                       size_t len) {
        (void)server;
        (void)arg;
        (void)data;
        (void)len;

        if (type == WS_EVT_CONNECT) {
            client->text(rotaryEncoderJson());
        }
    }

    void onStatisticsWebSocketEvent(AsyncWebSocket *server,
                                    AsyncWebSocketClient *client,
                                    AwsEventType type,
                                    void *arg,
                                    uint8_t *data,
                                    size_t len) {
        (void)server;
        (void)arg;
        (void)data;
        (void)len;

        if (type == WS_EVT_CONNECT) {
            client->text(statisticsJson());
        }
    }

    void onMhSensorWebSocketEvent(AsyncWebSocket *server,
                                  AsyncWebSocketClient *client,
                                  AwsEventType type,
                                  void *arg,
                                  uint8_t *data,
                                  size_t len) {
        (void)server;
        (void)arg;
        (void)data;
        (void)len;

        if (type == WS_EVT_CONNECT) {
            client->text(mhSensorJson());
        }
    }

    void onMcp3008WebSocketEvent(AsyncWebSocket *server,
                                 AsyncWebSocketClient *client,
                                 AwsEventType type,
                                 void *arg,
                                 uint8_t *data,
                                 size_t len) {
        (void)server;
        (void)arg;
        (void)data;
        (void)len;

        if (type == WS_EVT_CONNECT) {
            client->text(mcp3008Json());
        }
    }

    void onMcp23017InputsWebSocketEvent(AsyncWebSocket *server,
                                        AsyncWebSocketClient *client,
                                        AwsEventType type,
                                        void *arg,
                                        uint8_t *data,
                                        size_t len) {
        (void)server;
        (void)arg;
        (void)data;
        (void)len;

        if (type == WS_EVT_CONNECT) {
            client->text(mcp23017InputsJson());
        }
    }

    void onPressureSensorsWebSocketEvent(AsyncWebSocket *server,
                                       AsyncWebSocketClient *client,
                                       AwsEventType type,
                                       void *arg,
                                       uint8_t *data,
                                       size_t len) {
        (void)server;
        (void)arg;
        (void)data;
        (void)len;

        if (type == WS_EVT_CONNECT) {
            client->text(pressureSensorsJson());
        }
    }

    void onTofSensorWebSocketEvent(AsyncWebSocket *server,
                                   AsyncWebSocketClient *client,
                                   AwsEventType type,
                                   void *arg,
                                   uint8_t *data,
                                   size_t len) {
        (void)server;
        (void)arg;
        (void)data;
        (void)len;

        if (type == WS_EVT_CONNECT) {
            client->text(tofSensorJson());
        }
    }

    bool parseServoChannel(const String &value, int &outChannel) {
        for (size_t i = 0; i < value.length(); ++i) {
            if (!isDigit(value[i])) {
                return false;
            }
        }

        const int parsed = value.toInt();
        if (parsed < 0 || parsed > 15) {
            return false;
        }

        outChannel = parsed;
        return true;
    }

    bool parseServoPulseUs(const String &value, int &outPulseUs) {
        for (size_t i = 0; i < value.length(); ++i) {
            if (!isDigit(value[i])) {
                return false;
            }
        }

        const int parsed = value.toInt();
        if (parsed < 100 || parsed > 5000) {
            return false;
        }

        outPulseUs = parsed;
        return true;
    }
}

bool parseBoolParam(const String &value, bool &outValue) {
    if (value == "1" || value == "true" || value == "on") {
        outValue = true;
        return true;
    }
    if (value == "0" || value == "false" || value == "off") {
        outValue = false;
        return true;
    }
    return false;
}

bool parseSensorIdParam(const String &value, int &outSensorId) {
    if (value.length() == 0) {
        return false;
    }

    for (size_t i = 0; i < value.length(); ++i) {
        if (!isDigit(value[i])) {
            return false;
        }
    }

    const int parsed = value.toInt();
    if (parsed < 0 || parsed >= PRESSURE_SENSOR_COUNT) {
        return false;
    }

    outSensorId = parsed;
    return true;
}

bool parseByteParam(const String &value, uint8_t &outValue) {
    if (value.length() == 0) {
        return false;
    }

    for (size_t i = 0; i < value.length(); ++i) {
        if (!isDigit(value[i])) {
            return false;
        }
    }

    const int parsed = value.toInt();
    if (parsed < 0 || parsed > 255) {
        return false;
    }

    outValue = (uint8_t)parsed;
    return true;
}

String serialSettingsJson() {
    return String("{\"serialOutputEnabled\":") + (serialOutputEnabled ? "true" : "false") +
           ",\"includePotentiometerValue\":" + (includePotentiometerValue ? "true" : "false") + "}";
}

String oledSettingsJson() {
    return String("{\"enabled\":") + (isOledEnabled() ? "true" : "false") + "}";
}

String tofServerSettingsJson() {
    const TofServerSettings settings = getTofServerSettings();
    return String("{\"enabled\":") + (settings.enabled ? "true" : "false") +
           ",\"outlierEnabled\":" + (settings.outlierEnabled ? "true" : "false") +
           ",\"outlierThresholdMm\":" + settings.outlierThresholdMm +
           ",\"mode\":\"" + tofModeToString(settings.resolution) + "\"}";
}

void initServer(RoamingWiFiManager& manager) {
    initDcMotor();

    potentiometerWebSocket.onEvent(onPotentiometerWebSocketEvent);
    manager.server.addHandler(&potentiometerWebSocket);
    statisticsWebSocket.onEvent(onStatisticsWebSocketEvent);
    manager.server.addHandler(&statisticsWebSocket);
    mhSensorWebSocket.onEvent(onMhSensorWebSocketEvent);
    manager.server.addHandler(&mhSensorWebSocket);
    mcp3008WebSocket.onEvent(onMcp3008WebSocketEvent);
    manager.server.addHandler(&mcp3008WebSocket);
    mcp23017InputsWebSocket.onEvent(onMcp23017InputsWebSocketEvent);
    manager.server.addHandler(&mcp23017InputsWebSocket);
    rotaryEncoderWebSocket.onEvent(onRotaryEncoderWebSocketEvent);
    manager.server.addHandler(&rotaryEncoderWebSocket);
    pressureSensorsWebSocket.onEvent(onPressureSensorsWebSocketEvent);
    manager.server.addHandler(&pressureSensorsWebSocket);
    tofSensorWebSocket.onEvent(onTofSensorWebSocketEvent);
    manager.server.addHandler(&tofSensorWebSocket);

    manager.server.on("/", [] (AsyncWebServerRequest *request) {
        handleRoot(request);
    });
    // Serve CSS file from LittleFS
    manager.server.on("/stylesheet.css", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/stylesheet.css")) {
            request->send(LittleFS, "/stylesheet.css", "text/css");
        } else {
            request->send(404, "text/plain", "stylesheet.css not found");
        }
    });
    manager.server.on("/serialSettings", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/serialSettings.html")) {
            request->send(LittleFS, "/serialSettings.html", "text/html");
        } else {
            request->send(404, "text/plain", "serialSettings.html not found");
        }
    });
    manager.server.on("/serialSettings.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/serialSettings.ts")) {
            request->send(LittleFS, "/serialSettings.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "serialSettings.ts not found");
        }
    });
    manager.server.on("/oledSettings", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/oledSettings.html")) {
            request->send(LittleFS, "/oledSettings.html", "text/html");
        } else {
            request->send(404, "text/plain", "oledSettings.html not found");
        }
    });
    manager.server.on("/oledSettings.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/oledSettings.ts")) {
            request->send(LittleFS, "/oledSettings.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "oledSettings.ts not found");
        }
    });
    manager.server.on("/potentiometer", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/potentiometer.html")) {
            request->send(LittleFS, "/potentiometer.html", "text/html");
        } else {
            request->send(404, "text/plain", "potentiometer.html not found");
        }
    });
    manager.server.on("/potentiometer.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/potentiometer.ts")) {
            request->send(LittleFS, "/potentiometer.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "potentiometer.ts not found");
        }
    });
    manager.server.on("/statistics", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/statistics.html")) {
            request->send(LittleFS, "/statistics.html", "text/html");
        } else {
            request->send(404, "text/plain", "statistics.html not found");
        }
    });
    manager.server.on("/pwmServo", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/pwmServo.html")) {
            request->send(LittleFS, "/pwmServo.html", "text/html");
        } else {
            request->send(404, "text/plain", "pwmServo.html not found");
        }
    });
    manager.server.on("/pwmServo.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/pwmServo.ts")) {
            request->send(LittleFS, "/pwmServo.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "pwmServo.ts not found");
        }
    });
    // Register /api/pwmServo/config FIRST (more specific routes must be before generic ones)
    manager.server.on("/api/pwmServo/config", HTTP_GET, [] (AsyncWebServerRequest *request) {
        // Return all 16 channel configs as JSON array
        Serial.println("GET /api/pwmServo/config - Returning all channel configs");
        String response = "[";
        for (int i = 0; i < 16; i++) {
            PwmChannelConfig config = getChannelConfig(i);
            response += "{\"channel\":" + String(i) + ",\"mode\":\"" + channelModeToString(config.mode) + 
                       "\",\"minPulseUs\":" + String(config.minPulseUs) + ",\"maxPulseUs\":" + String(config.maxPulseUs) + "}";
            if (i < 15) response += ",";
        }
        response += "]";
        request->send(200, "application/json", response);
    });
    manager.server.on("/api/pwmServo/config", HTTP_POST, [] (AsyncWebServerRequest *request) {
        // Set channel config
        Serial.println("POST /api/pwmServo/config - Setting channel config");
        Serial.printf("  Params: channel=%s, mode=%s\n", 
                     request->hasParam("channel", true) ? request->getParam("channel", true)->value().c_str() : "MISSING",
                     request->hasParam("mode", true) ? request->getParam("mode", true)->value().c_str() : "MISSING");
        
        if (!request->hasParam("channel", true) || !request->hasParam("mode", true)) {
            Serial.println("  ERROR: missing channel or mode");
            request->send(400, "application/json", "{\"error\":\"missing channel or mode\"}");
            return;
        }

        int channel = request->getParam("channel", true)->value().toInt();
        String modeStr = request->getParam("mode", true)->value();
        
        Serial.printf("  Channel: %d, Mode: %s\n", channel, modeStr.c_str());
        
        if (channel < 0 || channel >= 16) {
            Serial.printf("  ERROR: invalid channel %d\n", channel);
            request->send(400, "application/json", "{\"error\":\"invalid channel\"}");
            return;
        }

        PwmChannelMode mode;
        if (!parseChannelMode(modeStr, mode)) {
            Serial.printf("  ERROR: invalid mode %s\n", modeStr.c_str());
            request->send(400, "application/json", "{\"error\":\"invalid mode\"}");
            return;
        }

        int minPulseUs = 500;  // Default values
        int maxPulseUs = 2500;

        // For servo mode, require min/max pulse widths
        if (mode == PwmChannelMode::Servo) {
            if (!request->hasParam("minPulseUs", true) || !request->hasParam("maxPulseUs", true)) {
                Serial.println("  ERROR: servo mode requires minPulseUs and maxPulseUs");
                request->send(400, "application/json", "{\"error\":\"servo mode requires minPulseUs and maxPulseUs\"}");
                return;
            }
            minPulseUs = request->getParam("minPulseUs", true)->value().toInt();
            maxPulseUs = request->getParam("maxPulseUs", true)->value().toInt();
            
            Serial.printf("  Min pulse: %d, Max pulse: %d\n", minPulseUs, maxPulseUs);
            
            if (minPulseUs < 100 || maxPulseUs > 5000 || minPulseUs >= maxPulseUs) {
                Serial.println("  ERROR: invalid pulse width range");
                request->send(400, "application/json", "{\"error\":\"invalid pulse width range\"}");
                return;
            }
        }

        PwmChannelConfig config = {mode, minPulseUs, maxPulseUs};
        setChannelConfig(channel, config);
        saveChannelConfigToNvs();
        
        String response = "{\"ok\":true,\"channel\":" + String(channel) + ",\"mode\":\"" + modeStr + 
                         "\",\"minPulseUs\":" + String(minPulseUs) + ",\"maxPulseUs\":" + String(maxPulseUs) + "}";
        Serial.printf("  SUCCESS: Channel %d saved\n", channel);
        request->send(200, "application/json", response);
    });
    // Register generic /api/pwmServo AFTER /api/pwmServo/config (more specific routes first)
    manager.server.on("/api/pwmServo", HTTP_POST, [] (AsyncWebServerRequest *request) {
        // Check for frequency change request
        if (request->hasParam("frequency", true)) {
            const String freqValue = request->getParam("frequency", true)->value();
            float frequency = freqValue.toFloat();
            
            if (frequency < 24.0f || frequency > 1000.0f) {
                request->send(400, "application/json", "{\"error\":\"frequency must be 24-1000 Hz\"}");
                return;
            }
            
            setPwmFrequency(frequency);
            savePwmFrequencyToNvs();
            request->send(200, "application/json", String("{\"ok\":true,\"frequency\":") + frequency + "}");
            return;
        }
        
        // Normalized duty cycle control
        if (request->hasParam("normalized", true)) {
            if (!request->hasParam("channel", true)) {
                request->send(400, "application/json", "{\"error\":\"missing channel\"}");
                return;
            }
            int channel = 0;
            const String channelValue = request->getParam("channel", true)->value();
            if (!parseServoChannel(channelValue, channel)) {
                request->send(400, "application/json", "{\"error\":\"invalid channel\"}");
                return;
            }
            float normalized = request->getParam("normalized", true)->value().toFloat();
            if (normalized < 0.0f || normalized > 1.0f) {
                request->send(400, "application/json", "{\"error\":\"normalized must be 0.0-1.0\"}");
                return;
            }
            setServoPwmNormalized(channel, normalized);
            request->send(200, "application/json", String("{\"ok\":true,\"channel\":") + channel + ",\"normalized\":" + normalized + "}");
            return;
        }

        // Microseconds servo control
        if (!request->hasParam("channel", true) || !request->hasParam("microseconds", true)) {
            request->send(400, "application/json", "{\"error\":\"missing channel or microseconds\"}");
            return;
        }

        int channel = 0;
        int microseconds = 1500;
        const String channelValue = request->getParam("channel", true)->value();
        const String pulseValue = request->getParam("microseconds", true)->value();

        if (!parseServoChannel(channelValue, channel)) {
            request->send(400, "application/json", "{\"error\":\"invalid channel\"}");
            return;
        }

        if (!parseServoPulseUs(pulseValue, microseconds)) {
            request->send(400, "application/json", "{\"error\":\"invalid microseconds\"}");
            return;
        }

        setServoMicroseconds(channel, microseconds);
        request->send(200, "application/json", String("{\"ok\":true,\"channel\":") + channel + ",\"microseconds\":" + microseconds + "}");
    });
    
    manager.server.on("/api/pwmServo/recover", HTTP_POST, [] (AsyncWebServerRequest *request) {
        // Manually trigger NVS recovery for missing channels
        Serial.println("POST /api/pwmServo/recover - Manual recovery requested");
        if (resetPwmServoNvs()) {
            request->send(200, "application/json", "{\"ok\":true,\"message\":\"pwm_servo namespace recovered with all 16 channels\"}");
        } else {
            request->send(500, "application/json", "{\"error\":\"recovery failed\"}");
        }
    });
    
    manager.server.on("/statistics.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/statistics.ts")) {
            request->send(LittleFS, "/statistics.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "statistics.ts not found");
        }
    });
    manager.server.on("/api/statistics", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", statisticsJson());
    });
    manager.server.on("/mhSensor", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/mhSensor.html")) {
            request->send(LittleFS, "/mhSensor.html", "text/html");
        } else {
            request->send(404, "text/plain", "mhSensor.html not found");
        }
    });
    manager.server.on("/mhSensor.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/mhSensor.ts")) {
            request->send(LittleFS, "/mhSensor.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "mhSensor.ts not found");
        }
    });
    manager.server.on("/mcp3008", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/mcp3008.html")) {
            request->send(LittleFS, "/mcp3008.html", "text/html");
        } else {
            request->send(404, "text/plain", "mcp3008.html not found");
        }
    });
    manager.server.on("/pressureSensors", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/pressureSensors.html")) {
            request->send(LittleFS, "/pressureSensors.html", "text/html");
        } else {
            request->send(404, "text/plain", "pressureSensors.html not found");
        }
    });
    manager.server.on("/pressureSensors.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/pressureSensors.ts")) {
            request->send(LittleFS, "/pressureSensors.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "pressureSensors.ts not found");
        }
    });
    manager.server.on("/api/pressureSensors/settings", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", pressureSensorsSettingsJson());
    });
    manager.server.on("/tofSensor", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/tofSensor.html")) {
            request->send(LittleFS, "/tofSensor.html", "text/html");
        } else {
            request->send(404, "text/plain", "tofSensor.html not found");
        }
    });
    manager.server.on("/tofSensor.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/tofSensor.ts")) {
            request->send(LittleFS, "/tofSensor.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "tofSensor.ts not found");
        }
    });
    manager.server.on("/tofSensor3d.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/tofSensor3d.ts")) {
            request->send(LittleFS, "/tofSensor3d.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "tofSensor3d.ts not found");
        }
    });
    manager.server.on("/tofServerSettings.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/tofServerSettings.ts")) {
            request->send(LittleFS, "/tofServerSettings.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "tofServerSettings.ts not found");
        }
    });
    manager.server.on("/api/tofSensor", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", tofSensorJson());
    });
    manager.server.on("/api/tofServerSettings", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", tofServerSettingsJson());
    });
    manager.server.on("/api/tofServerSettings", HTTP_POST, [] (AsyncWebServerRequest *request) {
        bool hasAnyUpdate = false;

        if (request->hasParam("enabled", true)) {
            bool parsedValue = false;
            String value = request->getParam("enabled", true)->value();
            if (!parseBoolParam(value, parsedValue)) {
                request->send(400, "application/json", "{\"error\":\"invalid enabled\"}");
                return;
            }
            if (!setTofEnabled(parsedValue)) {
                request->send(500, "application/json", "{\"error\":\"failed to apply enabled\"}");
                return;
            }
            hasAnyUpdate = true;
        }

        if (request->hasParam("outlierThresholdMm", true)) {
            String value = request->getParam("outlierThresholdMm", true)->value();
            for (size_t i = 0; i < value.length(); ++i) {
                if (!isDigit(value[i])) {
                    request->send(400, "application/json", "{\"error\":\"invalid outlierThresholdMm\"}");
                    return;
                }
            }

            const int parsedThreshold = value.toInt();
            if (parsedThreshold <= 0) {
                request->send(400, "application/json", "{\"error\":\"invalid outlierThresholdMm\"}");
                return;
            }

            if (!setTofOutlierThresholdMm((uint16_t)parsedThreshold)) {
                request->send(500, "application/json", "{\"error\":\"failed to persist outlierThresholdMm\"}");
                return;
            }
            hasAnyUpdate = true;
        }

        if (request->hasParam("outlierEnabled", true)) {
            bool parsedValue = false;
            String value = request->getParam("outlierEnabled", true)->value();
            if (!parseBoolParam(value, parsedValue)) {
                request->send(400, "application/json", "{\"error\":\"invalid outlierEnabled\"}");
                return;
            }
            if (!setTofOutlierEnabled(parsedValue)) {
                request->send(500, "application/json", "{\"error\":\"failed to persist outlierEnabled\"}");
                return;
            }
            hasAnyUpdate = true;
        }

        if (request->hasParam("mode", true)) {
            uint8_t parsedResolution = VL53L7CX_RESOLUTION_4X4;
            String value = request->getParam("mode", true)->value();
            if (!parseTofMode(value, parsedResolution)) {
                request->send(400, "application/json", "{\"error\":\"invalid mode\"}");
                return;
            }

            if (!setTofResolution(parsedResolution)) {
                request->send(500, "application/json", "{\"error\":\"failed to set mode\"}");
                return;
            }
            hasAnyUpdate = true;
        }

        if (!hasAnyUpdate) {
            request->send(400, "application/json", "{\"error\":\"no valid parameters provided\"}");
            return;
        }

        request->send(200, "application/json", tofServerSettingsJson());
    });
    manager.server.on("/mcp3008.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/mcp3008.ts")) {
            request->send(LittleFS, "/mcp3008.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "mcp3008.ts not found");
        }
    });
    manager.server.on("/mcp23017Inputs", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/mcp23017Inputs.html")) {
            request->send(LittleFS, "/mcp23017Inputs.html", "text/html");
        } else {
            request->send(404, "text/plain", "mcp23017Inputs.html not found");
        }
    });
    manager.server.on("/mcp23017Inputs.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/mcp23017Inputs.ts")) {
            request->send(LittleFS, "/mcp23017Inputs.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "mcp23017Inputs.ts not found");
        }
    });
    manager.server.on("/api/mcp23017/settings", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", mcp23017SettingsJson());
    });
    manager.server.on("/rotaryEncoder", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/rotaryEncoder.html")) {
            request->send(LittleFS, "/rotaryEncoder.html", "text/html");
        } else {
            request->send(404, "text/plain", "rotaryEncoder.html not found");
        }
    });
    manager.server.on("/rotaryEncoder.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/rotaryEncoder.ts")) {
            request->send(LittleFS, "/rotaryEncoder.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "rotaryEncoder.ts not found");
        }
    });
    manager.server.on("/api/rotaryEncoder", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", rotaryEncoderJson());
    });
    manager.server.on("/dcMotor", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/dcMotor.html")) {
            request->send(LittleFS, "/dcMotor.html", "text/html");
        } else {
            request->send(404, "text/plain", "dcMotor.html not found");
        }
    });
    manager.server.on("/dcMotor.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/dcMotor.ts")) {
            request->send(LittleFS, "/dcMotor.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "dcMotor.ts not found");
        }
    });
    manager.server.on("/api/motor", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", getMotorStateJson());
    });
    manager.server.on("/api/motor", HTTP_POST, [] (AsyncWebServerRequest *request) {
        bool hasAnyUpdate = false;
        bool hasPersistentUpdate = false;

        if (request->hasParam("mode", true)) {
            MotorMode parsedMode = getMotorMode();
            String value = request->getParam("mode", true)->value();
            if (!parseMotorMode(value, parsedMode)) {
                request->send(400, "application/json", "{\"error\":\"invalid mode\"}");
                return;
            }
            setMotorMode(parsedMode);
            hasAnyUpdate = true;
            hasPersistentUpdate = true;
        }

        if (request->hasParam("directIn1", true)) {
            bool parsedValue = false;
            String value = request->getParam("directIn1", true)->value();
            if (!parseBoolParam(value, parsedValue)) {
                request->send(400, "application/json", "{\"error\":\"invalid directIn1\"}");
                return;
            }
            setDirectInput1(parsedValue);
            hasAnyUpdate = true;
        }

        if (request->hasParam("directIn2", true)) {
            bool parsedValue = false;
            String value = request->getParam("directIn2", true)->value();
            if (!parseBoolParam(value, parsedValue)) {
                request->send(400, "application/json", "{\"error\":\"invalid directIn2\"}");
                return;
            }
            setDirectInput2(parsedValue);
            hasAnyUpdate = true;
        }

        if (request->hasParam("pwmDuty", true)) {
            int parsedDuty = getPwmDuty();
            String value = request->getParam("pwmDuty", true)->value();
            if (!parseDuty(value, parsedDuty)) {
                request->send(400, "application/json", "{\"error\":\"invalid pwmDuty\"}");
                return;
            }
            setPwmDuty(parsedDuty);
            hasAnyUpdate = true;
        }

        if (request->hasParam("direction", true)) {
            MotorDirection parsedDirection = getPwmDirection();
            String value = request->getParam("direction", true)->value();
            if (!parseMotorDirection(value, parsedDirection)) {
                request->send(400, "application/json", "{\"error\":\"invalid direction\"}");
                return;
            }
            setPwmDirection(parsedDirection);
            hasAnyUpdate = true;
        }

        if (request->hasParam("forwardSense", true)) {
            ForwardSense parsedSense = getForwardSense();
            String value = request->getParam("forwardSense", true)->value();
            if (!parseForwardSense(value, parsedSense)) {
                request->send(400, "application/json", "{\"error\":\"invalid forwardSense\"}");
                return;
            }
            setForwardSense(parsedSense);
            hasAnyUpdate = true;
            hasPersistentUpdate = true;
        }

        if (request->hasParam("normalized", true)) {
            String value = request->getParam("normalized", true)->value();
            float normalized = value.toFloat();
            setMotorNormalizedAPI(normalized);
            hasAnyUpdate = true;
        }

        if (request->hasParam("pwmNormalized", true)) {
            String value = request->getParam("pwmNormalized", true)->value();
            float normalized = value.toFloat();
            setMotorPwmNormalizedAPI(normalized);
            hasAnyUpdate = true;
        }

        if (request->hasParam("direction_boolean", true)) {
            String value = request->getParam("direction_boolean", true)->value();
            bool forward = (value == "true" || value == "1" || value == "on");
            setMotorDirectionAPI(forward);
            hasAnyUpdate = true;
        }

        if (!hasAnyUpdate) {
            request->send(400, "application/json", "{\"error\":\"no valid parameters provided\"}");
            return;
        }

        if (hasPersistentUpdate && !saveMotorSettingsToNvs()) {
            request->send(500, "application/json", "{\"error\":\"failed to persist motor settings\"}");
            return;
        }

        applyMotorOutputs();
        request->send(200, "application/json", getMotorStateJson());
    });
    manager.server.on("/api/serialSettings", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", serialSettingsJson());
    });
    manager.server.on("/api/serialSettings", HTTP_POST, [] (AsyncWebServerRequest *request) {
        bool hasAnyUpdate = false;

        if (request->hasParam("serialOutputEnabled", true)) {
            bool parsedValue = false;
            String value = request->getParam("serialOutputEnabled", true)->value();
            if (!parseBoolParam(value, parsedValue)) {
                request->send(400, "application/json", "{\"error\":\"invalid serialOutputEnabled\"}");
                return;
            }
            serialOutputEnabled = parsedValue;
            hasAnyUpdate = true;
        }

        if (request->hasParam("includePotentiometerValue", true)) {
            bool parsedValue = false;
            String value = request->getParam("includePotentiometerValue", true)->value();
            if (!parseBoolParam(value, parsedValue)) {
                request->send(400, "application/json", "{\"error\":\"invalid includePotentiometerValue\"}");
                return;
            }
            includePotentiometerValue = parsedValue;
            hasAnyUpdate = true;
        }

        if (!hasAnyUpdate) {
            request->send(400, "application/json", "{\"error\":\"no valid parameters provided\"}");
            return;
        }

        if (!saveSerialSettingsToNvs()) {
            request->send(500, "application/json", "{\"error\":\"failed to persist settings\"}");
            return;
        }

        request->send(200, "application/json", serialSettingsJson());
    });
    manager.server.on("/api/oledSettings", HTTP_GET, [] (AsyncWebServerRequest *request) {
        request->send(200, "application/json", oledSettingsJson());
    });
    manager.server.on("/api/oledSettings", HTTP_POST, [] (AsyncWebServerRequest *request) {
        if (!request->hasParam("enabled", true)) {
            request->send(400, "application/json", "{\"error\":\"missing enabled\"}");
            return;
        }

        bool parsedValue = false;
        String value = request->getParam("enabled", true)->value();
        if (!parseBoolParam(value, parsedValue)) {
            request->send(400, "application/json", "{\"error\":\"invalid enabled\"}");
            return;
        }

        if (!setOledEnabled(parsedValue, true)) {
            request->send(500, "application/json", "{\"error\":\"failed to persist OLED settings\"}");
            return;
        }

        request->send(200, "application/json", oledSettingsJson());
    });

    // Matrix routing pages and API
    manager.server.on("/matrix", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/matrix.html")) {
            request->send(LittleFS, "/matrix.html", "text/html");
        } else {
            request->send(404, "text/plain", "matrix.html not found");
        }
    });
    manager.server.on("/matrix.ts", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/matrix.ts")) {
            request->send(LittleFS, "/matrix.ts", "application/javascript");
        } else {
            request->send(404, "text/plain", "matrix.ts not found");
        }
    });

    // Matrix routes - GET all
    manager.server.on("/api/matrix/routes", HTTP_GET, [] (AsyncWebServerRequest *request) {
        auto routes = getAllRoutes();
        String json = "[";
        for (size_t i = 0; i < routes.size(); i++) {
            if (i > 0) json += ",";
            const auto& route = routes[i];
            char buf[50];
            sprintf(buf, "%.2f", route.threshold);
            json += "{\"id\":" + String(route.id) + 
                   ",\"name\":\"" + route.name + 
                   "\",\"inputType\":\"" + route.inputType + 
                   "\",\"inputPin\":" + String(route.inputPin) +
                   ",\"outputType\":\"" + route.outputType +
                   "\",\"outputPin\":" + String(route.outputPin) +
                   ",\"enabled\":" + (route.enabled ? "true" : "false") +
                   ",\"invert\":" + (route.invert ? "true" : "false") +
                   ",\"threshold\":" + String(buf) + "}";
        }
        json += "]";
        request->send(200, "application/json", json);
    });

    // Matrix routes - POST create
    manager.server.on("/api/matrix/routes", HTTP_POST, [] (AsyncWebServerRequest *request) {
        if (!request->hasParam("inputType", true) || !request->hasParam("inputPin", true) ||
            !request->hasParam("outputType", true) || !request->hasParam("outputPin", true)) {
            request->send(400, "application/json", "{\"error\":\"missing required parameters\"}");
            return;
        }

        RouteEntry entry;
        entry.name = request->hasParam("name", true) ? request->getParam("name", true)->value() : "";
        entry.inputType = request->getParam("inputType", true)->value();
        entry.inputPin = request->getParam("inputPin", true)->value().toInt();
        entry.outputType = request->getParam("outputType", true)->value();
        entry.outputPin = request->getParam("outputPin", true)->value().toInt();
        entry.enabled = true;
        entry.invert = request->hasParam("invert", true) && 
                      request->getParam("invert", true)->value().equals("true");
        entry.threshold = request->hasParam("threshold", true) ?
                         request->getParam("threshold", true)->value().toFloat() : 0.5f;
        // Validate threshold
        if (entry.threshold <= 0.0f || entry.threshold > 1.0f) {
            entry.threshold = 0.5f;
        }

        if (addRoute(entry)) {
            request->send(200, "application/json", "{\"success\":true}");
        } else {
            request->send(500, "application/json", "{\"error\":\"failed to add route\"}");
        }
    });

    // Matrix routes - PUT (handles both /id and /id/enabled based on URL)
    manager.server.on("/api/matrix/routes", HTTP_PUT, [] (AsyncWebServerRequest *request) {
        String path = request->url();
        
        // Parse ID from path
        int lastSlash = path.lastIndexOf('/');
        String lastSegment = path.substring(lastSlash + 1);
        
        uint8_t id = 0;
        bool isEnabledEndpoint = false;
        
        if (lastSegment.equals("enabled")) {
            isEnabledEndpoint = true;
            int secondLastSlash = path.lastIndexOf('/', lastSlash - 1);
            String idStr = path.substring(secondLastSlash + 1, lastSlash);
            id = idStr.toInt();
        } else {
            id = lastSegment.toInt();
        }
        
        if (id == 0) {
            request->send(400, "application/json", "{\"error\":\"invalid route ID\"}");
            return;
        }
        
        RouteEntry* route = getRoute(id);
        
        if (!route) {
            request->send(404, "application/json", "{\"error\":\"route not found\"}");
            return;
        }
        
        if (isEnabledEndpoint) {
            if (!request->hasParam("enabled", true)) {
                request->send(400, "application/json", "{\"error\":\"missing enabled parameter\"}");
                return;
            }
            String enabledValue = request->getParam("enabled", true)->value();
            route->enabled = enabledValue.equals("true");
            updateRoute(id, *route);
            request->send(200, "application/json", "{\"success\":true}");
        } else {
            // Generic update - update all provided fields
            if (request->hasParam("name", true)) {
                route->name = request->getParam("name", true)->value();
            }
            if (request->hasParam("inputType", true)) {
                route->inputType = request->getParam("inputType", true)->value();
            }
            if (request->hasParam("inputPin", true)) {
                route->inputPin = request->getParam("inputPin", true)->value().toInt();
            }
            if (request->hasParam("outputType", true)) {
                route->outputType = request->getParam("outputType", true)->value();
            }
            if (request->hasParam("outputPin", true)) {
                route->outputPin = request->getParam("outputPin", true)->value().toInt();
            }
            if (request->hasParam("invert", true)) {
                route->invert = request->getParam("invert", true)->value().equals("true");
            }
            if (request->hasParam("threshold", true)) {
                float threshold = request->getParam("threshold", true)->value().toFloat();
                if (threshold > 0.0f && threshold <= 1.0f) {
                    route->threshold = threshold;
                }
            }
            updateRoute(id, *route);
            request->send(200, "application/json", "{\"success\":true}");
        }
    });

    // Matrix routes - DELETE (handles both specific ID and clear all)
    manager.server.on("/api/matrix/routes", HTTP_DELETE, [] (AsyncWebServerRequest *request) {
        String path = request->url();
        int lastSlash = path.lastIndexOf('/');
        String lastSegment = path.substring(lastSlash + 1);
        
        if (lastSegment.length() == 0 || lastSegment.equals("routes")) {
            // Clear all routes
            clearAllRoutes();
            request->send(200, "application/json", "{\"success\":true}");
        } else {
            // Delete specific route by ID
            uint8_t id = lastSegment.toInt();
            
            if (id == 0) {
                request->send(400, "application/json", "{\"error\":\"invalid route ID\"}");
                return;
            }
            
            if (deleteRoute(id)) {
                request->send(200, "application/json", "{\"success\":true}");
            } else {
                request->send(404, "application/json", "{\"error\":\"route not found\"}");
            }
        }
    });

    manager.server.on("/api/mcp23017/settings", HTTP_POST, [] (AsyncWebServerRequest *request) {
            Mcp23017Settings settings = getMcp23017Settings();
            bool hasAnyUpdate = false;

            if (request->hasParam("modeA", true)) {
                uint8_t parsedValue = 0;
                String value = request->getParam("modeA", true)->value();
                if (!parseByteParam(value, parsedValue)) {
                    request->send(400, "application/json", "{\"error\":\"invalid modeA\"}");
                    return;
                }
                settings.modeA = parsedValue;
                hasAnyUpdate = true;
            }

            if (request->hasParam("pullupA", true)) {
                uint8_t parsedValue = 0;
                String value = request->getParam("pullupA", true)->value();
                if (!parseByteParam(value, parsedValue)) {
                    request->send(400, "application/json", "{\"error\":\"invalid pullupA\"}");
                    return;
                }
                settings.pullupA = parsedValue;
                hasAnyUpdate = true;
            }

            if (request->hasParam("modeB", true)) {
                uint8_t parsedValue = 0;
                String value = request->getParam("modeB", true)->value();
                if (!parseByteParam(value, parsedValue)) {
                    request->send(400, "application/json", "{\"error\":\"invalid modeB\"}");
                    return;
                }
                settings.modeB = parsedValue;
                hasAnyUpdate = true;
            }

            if (request->hasParam("pullupB", true)) {
                uint8_t parsedValue = 0;
                String value = request->getParam("pullupB", true)->value();
                if (!parseByteParam(value, parsedValue)) {
                    request->send(400, "application/json", "{\"error\":\"invalid pullupB\"}");
                    return;
                }
                settings.pullupB = parsedValue;
                hasAnyUpdate = true;
            }

            if (request->hasParam("outputA", true)) {
                uint8_t parsedValue = 0;
                String value = request->getParam("outputA", true)->value();
                if (!parseByteParam(value, parsedValue)) {
                    request->send(400, "application/json", "{\"error\":\"invalid outputA\"}");
                    return;
                }
                settings.outputA = parsedValue;
                hasAnyUpdate = true;
            }

            if (request->hasParam("outputB", true)) {
                uint8_t parsedValue = 0;
                String value = request->getParam("outputB", true)->value();
                if (!parseByteParam(value, parsedValue)) {
                    request->send(400, "application/json", "{\"error\":\"invalid outputB\"}");
                    return;
                }
                settings.outputB = parsedValue;
                hasAnyUpdate = true;
            }

            if (!hasAnyUpdate) {
                request->send(400, "application/json", "{\"error\":\"no valid parameters provided\"}");
                return;
            }

            if (!setMcp23017Settings(settings, true)) {
                request->send(500, "application/json", "{\"error\":\"failed to persist MCP23017 settings\"}");
                return;
            }

            request->send(200, "application/json", mcp23017SettingsJson());
        });
        manager.server.on("/api/pressureSensors/settings", HTTP_POST, [] (AsyncWebServerRequest *request) {
            if (!request->hasParam("enabled", true)) {
                request->send(400, "application/json", "{\"error\":\"missing enabled\"}");
                return;
            }

            bool parsedValue = false;
            String value = request->getParam("enabled", true)->value();
            if (!parseBoolParam(value, parsedValue)) {
                request->send(400, "application/json", "{\"error\":\"invalid enabled\"}");
                return;
            }

            if (!setPressureSensorsEnabled(parsedValue)) {
                request->send(500, "application/json", "{\"error\":\"failed to apply enabled\"}");
                return;
            }

            request->send(200, "application/json", pressureSensorsSettingsJson());
        });
        manager.server.on("/api/pressureSensors/zeroCalibrate", HTTP_POST, [] (AsyncWebServerRequest *request) {
            if (!arePressureSensorsEnabled()) {
                request->send(400, "application/json", "{\"error\":\"pressure sensors are disabled\"}");
                return;
            }

            if (!request->hasParam("sensorId", true)) {
                request->send(400, "application/json", "{\"error\":\"missing sensorId\"}");
                return;
            }

            int sensorId = 0;
            const String value = request->getParam("sensorId", true)->value();
            if (!parseSensorIdParam(value, sensorId)) {
                request->send(400, "application/json", "{\"error\":\"invalid sensorId\"}");
                return;
            }

            zeroCalibratePressure(sensorId);
            request->send(200, "application/json", String("{\"ok\":true,\"sensorId\":") + sensorId + "}");
        });
}

void serverApiLoop() {
    potentiometerWebSocket.cleanupClients();
    statisticsWebSocket.cleanupClients();
    mhSensorWebSocket.cleanupClients();
    mcp3008WebSocket.cleanupClients();
    mcp23017InputsWebSocket.cleanupClients();
    rotaryEncoderWebSocket.cleanupClients();
    pressureSensorsWebSocket.cleanupClients();
    tofSensorWebSocket.cleanupClients();

    if (getMotorMode() == MotorMode::Potentiometer) {
        applyMotorOutputs();
    }

    const unsigned long now = millis();
    if (now - lastPotentiometerPublishMs >= potentiometerPublishIntervalMs) {
        lastPotentiometerPublishMs = now;
        if (potentiometerWebSocket.count() > 0) {
            potentiometerWebSocket.textAll(potentiometerJson());
        }
    }

    if (now - lastStatisticsPublishMs >= statisticsPublishIntervalMs) {
        lastStatisticsPublishMs = now;
        if (statisticsWebSocket.count() > 0) {
            statisticsWebSocket.textAll(statisticsJson());
        }
    }

    if (now - lastMhSensorPublishMs >= mhSensorPublishIntervalMs) {
        lastMhSensorPublishMs = now;
        if (mhSensorWebSocket.count() > 0) {
            mhSensorWebSocket.textAll(mhSensorJson());
        }
    }

    if (now - lastMcp3008PublishMs >= mcp3008PublishIntervalMs) {
        lastMcp3008PublishMs = now;
        if (mcp3008WebSocket.count() > 0) {
            mcp3008WebSocket.textAll(mcp3008Json());
        }
    }

    if (now - lastMcp23017InputsPublishMs >= mcp23017InputsPublishIntervalMs) {
        lastMcp23017InputsPublishMs = now;
        if (mcp23017InputsWebSocket.count() > 0) {
            mcp23017InputsWebSocket.textAll(mcp23017InputsJson());
        }
    }

    if (now - lastRotaryEncoderPublishMs >= rotaryEncoderPublishIntervalMs) {
        lastRotaryEncoderPublishMs = now;
        if (rotaryEncoderWebSocket.count() > 0) {
            rotaryEncoderWebSocket.textAll(rotaryEncoderJson());
        }
    }

    if (now - lastPressureSensorsPublishMs >= pressureSensorsPublishIntervalMs) {
        lastPressureSensorsPublishMs = now;
        if (pressureSensorsWebSocket.count() > 0) {
            pressureSensorsWebSocket.textAll(pressureSensorsJson());
        }
    }

    if (now - lastTofSensorPublishMs >= tofSensorPublishIntervalMs) {
        lastTofSensorPublishMs = now;
        if (tofSensorWebSocket.count() > 0 && tofSensorWebSocket.availableForWriteAll()) {
            tofSensorWebSocket.textAll(tofSensorJson());
        }
    }
}