#include "serverApi.h"
#include "nvsSettings.h"
#include "RoamingWiFiManager.h"
#include <LittleFS.h>
#include <Preferences.h>
#include "websiteRoot.h"
#include "gpioExpanders.h"
#include "pressureSensor.h"

namespace {
    AsyncWebSocket potentiometerWebSocket("/ws/potentiometer");
    AsyncWebSocket mhSensorWebSocket("/ws/mhSensor");
    AsyncWebSocket mcp3008WebSocket("/ws/mcp3008");
    AsyncWebSocket mcp23017InputsWebSocket("/ws/mcp23017inputs");
    AsyncWebSocket rotaryEncoderWebSocket("/ws/rotaryEncoder");
    AsyncWebSocket pressureSensorsWebSocket("/ws/pressureSensors");
    unsigned long lastPotentiometerPublishMs = 0;
    unsigned long lastMhSensorPublishMs = 0;
    unsigned long lastMcp3008PublishMs = 0;
    unsigned long lastMcp23017InputsPublishMs = 0;
    unsigned long lastRotaryEncoderPublishMs = 0;
    unsigned long lastPressureSensorsPublishMs = 0;
    const unsigned long potentiometerPublishIntervalMs = 50;
    const unsigned long mhSensorPublishIntervalMs = 50;
    const unsigned long mcp3008PublishIntervalMs = 50;
    const unsigned long mcp23017InputsPublishIntervalMs = 50;
    const unsigned long rotaryEncoderPublishIntervalMs = 50;
    const unsigned long pressureSensorsPublishIntervalMs = 50;

    enum class MotorMode {
        Direct,
        Pwm,
        Potentiometer
    };

    enum class MotorDirection {
        Forward,
        Reverse
    };

    enum class ForwardSense {
        Ccw,
        Cw
    };

    MotorMode motorMode = MotorMode::Direct;
    bool directIn1 = false;
    bool directIn2 = false;
    int pwmDuty = 0;
    MotorDirection pwmDirection = MotorDirection::Forward;
    ForwardSense forwardSense = ForwardSense::Ccw;
    const float motorCenterVoltage = 1.65f;
    const float motorHalfRangeVoltage = 1.65f;
    const float motorDeadbandVoltage = 0.04f;
    const char *MOTOR_SETTINGS_NAMESPACE = "motor_cfg";
    const char *KEY_MOTOR_MODE = "motor_mode";
    const char *KEY_FORWARD_SENSE = "fwd";

    String potentiometerJson() {
        return String("{\"millis\":") + millis() + ",\"voltage\":" + String(readAdcAnalogVolt(POTMETER_ADC_PIN), 3) + "}";
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
        const uint8_t bankValue = getDigitalBankA();
        String json = String("{\"millis\":") + millis() +
                      ",\"bankValue\":" + String(bankValue) +
                      ",\"bits\":[";
        for (int bit = 0; bit < 8; ++bit) {
            if (bit > 0) {
                json += ",";
            }
            json += ((bankValue >> bit) & 0x01) ? "1" : "0";
        }
        json += "]}";
        return json;
    }

    String pressureSensorsJson() {
        const std::array<float, PRESSURE_SENSOR_COUNT> values = readPressureSensorsSingleShot();
        String json = String("{\"millis\":") + millis() + ",\"pressures\":[";
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

    String motorModeToString(MotorMode mode) {
        if (mode == MotorMode::Direct) {
            return "direct";
        }
        if (mode == MotorMode::Pwm) {
            return "pwm";
        }
        return "potentiometer";
    }

    String motorDirectionToString(MotorDirection direction) {
        return direction == MotorDirection::Forward ? "forward" : "reverse";
    }

    String forwardSenseToString(ForwardSense sense) {
        return sense == ForwardSense::Ccw ? "ccw" : "cw";
    }

    bool parseMotorMode(const String &value, MotorMode &outMode) {
        if (value == "direct") {
            outMode = MotorMode::Direct;
            return true;
        }
        if (value == "pwm") {
            outMode = MotorMode::Pwm;
            return true;
        }
        if (value == "potentiometer") {
            outMode = MotorMode::Potentiometer;
            return true;
        }
        return false;
    }

    bool parseMotorDirection(const String &value, MotorDirection &outDirection) {
        if (value == "forward") {
            outDirection = MotorDirection::Forward;
            return true;
        }
        if (value == "reverse") {
            outDirection = MotorDirection::Reverse;
            return true;
        }
        return false;
    }

    bool parseForwardSense(const String &value, ForwardSense &outSense) {
        if (value == "ccw") {
            outSense = ForwardSense::Ccw;
            return true;
        }
        if (value == "cw") {
            outSense = ForwardSense::Cw;
            return true;
        }
        return false;
    }

    bool parseDuty(const String &value, int &outDuty) {
        for (size_t i = 0; i < value.length(); ++i) {
            if (!isDigit(value[i])) {
                return false;
            }
        }

        int parsed = value.toInt();
        if (parsed < 0 || parsed > 255) {
            return false;
        }

        outDuty = parsed;
        return true;
    }

    void applyMotorPwmWithDirection(int duty, MotorDirection direction) {
        if (direction == MotorDirection::Forward) {
            pinMode(motorIn2Pin, OUTPUT);
            digitalWrite(motorIn2Pin, LOW);
            analogWrite(motorIn1Pin, duty);
            return;
        }

        pinMode(motorIn1Pin, OUTPUT);
        digitalWrite(motorIn1Pin, LOW);
        analogWrite(motorIn2Pin, duty);
    }

    MotorDirection mapLogicalToPhysicalDirection(MotorDirection logicalDirection) {
        if (forwardSense == ForwardSense::Ccw) {
            return logicalDirection;
        }

        return logicalDirection == MotorDirection::Forward ? MotorDirection::Reverse : MotorDirection::Forward;
    }

    void applyMotorStop() {
        pinMode(motorIn1Pin, OUTPUT);
        pinMode(motorIn2Pin, OUTPUT);
        digitalWrite(motorIn1Pin, LOW);
        digitalWrite(motorIn2Pin, LOW);
    }

    void applyMotorOutputs() {
        if (motorMode == MotorMode::Direct) {
            // Re-assert GPIO function in case pins were previously used for PWM.
            pinMode(motorIn1Pin, OUTPUT);
            pinMode(motorIn2Pin, OUTPUT);
            digitalWrite(motorIn1Pin, directIn1 ? HIGH : LOW);
            digitalWrite(motorIn2Pin, directIn2 ? HIGH : LOW);
            return;
        }

        if (motorMode == MotorMode::Pwm) {
            applyMotorPwmWithDirection(pwmDuty, mapLogicalToPhysicalDirection(pwmDirection));
            return;
        }

        const float voltage = readAdcAnalogVolt(POTMETER_ADC_PIN);
        const float centered = voltage - motorCenterVoltage;
        if (centered > -motorDeadbandVoltage && centered < motorDeadbandVoltage) {
            applyMotorStop();
            return;
        }

        float normalized = centered / motorHalfRangeVoltage;
        if (normalized > 1.0f) {
            normalized = 1.0f;
        }
        if (normalized < -1.0f) {
            normalized = -1.0f;
        }

        const int interpolatedDuty = (int)(fabs(normalized) * 255.0f + 0.5f);
        const MotorDirection direction = normalized < 0.0f ? MotorDirection::Reverse : MotorDirection::Forward;
        applyMotorPwmWithDirection(interpolatedDuty, mapLogicalToPhysicalDirection(direction));
    }

    String motorStateJson() {
        return String("{\"mode\":\"") + motorModeToString(motorMode) +
               "\",\"directIn1\":" + (directIn1 ? "true" : "false") +
               ",\"directIn2\":" + (directIn2 ? "true" : "false") +
               ",\"pwmDuty\":" + pwmDuty +
               ",\"direction\":\"" + motorDirectionToString(pwmDirection) +
               "\",\"forwardSense\":\"" + forwardSenseToString(forwardSense) + "\"}";
    }

    void loadMotorSettingsFromNvs() {
        Preferences preferences;
        if (!preferences.begin(MOTOR_SETTINGS_NAMESPACE, true)) {
            Serial.println("NVS open failed for reading motor settings");
            return;
        }

        MotorMode parsedMode = motorMode;
        String storedMode = preferences.getString(KEY_MOTOR_MODE, motorModeToString(motorMode));
        if (parseMotorMode(storedMode, parsedMode)) {
            motorMode = parsedMode;
        }

        ForwardSense parsedSense = forwardSense;
        String storedSense = preferences.getString(KEY_FORWARD_SENSE, forwardSenseToString(forwardSense));
        if (parseForwardSense(storedSense, parsedSense)) {
            forwardSense = parsedSense;
        }

        preferences.end();
    }

    bool saveMotorSettingsToNvs() {
        Preferences preferences;
        if (!preferences.begin(MOTOR_SETTINGS_NAMESPACE, false)) {
            Serial.println("NVS open failed for writing motor settings");
            return false;
        }

        bool okMode = preferences.putString(KEY_MOTOR_MODE, motorModeToString(motorMode)) > 0;
        bool okSense = preferences.putString(KEY_FORWARD_SENSE, forwardSenseToString(forwardSense)) > 0;
        preferences.end();
        return okMode && okSense;
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

String serialSettingsJson() {
    return String("{\"serialOutputEnabled\":") + (serialOutputEnabled ? "true" : "false") +
           ",\"includePotentiometerValue\":" + (includePotentiometerValue ? "true" : "false") + "}";
}

void initServer(RoamingWiFiManager& manager) {
    loadMotorSettingsFromNvs();
    applyMotorOutputs();

    potentiometerWebSocket.onEvent(onPotentiometerWebSocketEvent);
    manager.server.addHandler(&potentiometerWebSocket);
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
        request->send(200, "application/json", motorStateJson());
    });
    manager.server.on("/api/motor", HTTP_POST, [] (AsyncWebServerRequest *request) {
        bool hasAnyUpdate = false;
        bool hasPersistentUpdate = false;

        if (request->hasParam("mode", true)) {
            MotorMode parsedMode = motorMode;
            String value = request->getParam("mode", true)->value();
            if (!parseMotorMode(value, parsedMode)) {
                request->send(400, "application/json", "{\"error\":\"invalid mode\"}");
                return;
            }
            motorMode = parsedMode;
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
            directIn1 = parsedValue;
            hasAnyUpdate = true;
        }

        if (request->hasParam("directIn2", true)) {
            bool parsedValue = false;
            String value = request->getParam("directIn2", true)->value();
            if (!parseBoolParam(value, parsedValue)) {
                request->send(400, "application/json", "{\"error\":\"invalid directIn2\"}");
                return;
            }
            directIn2 = parsedValue;
            hasAnyUpdate = true;
        }

        if (request->hasParam("pwmDuty", true)) {
            int parsedDuty = pwmDuty;
            String value = request->getParam("pwmDuty", true)->value();
            if (!parseDuty(value, parsedDuty)) {
                request->send(400, "application/json", "{\"error\":\"invalid pwmDuty\"}");
                return;
            }
            pwmDuty = parsedDuty;
            hasAnyUpdate = true;
        }

        if (request->hasParam("direction", true)) {
            MotorDirection parsedDirection = pwmDirection;
            String value = request->getParam("direction", true)->value();
            if (!parseMotorDirection(value, parsedDirection)) {
                request->send(400, "application/json", "{\"error\":\"invalid direction\"}");
                return;
            }
            pwmDirection = parsedDirection;
            hasAnyUpdate = true;
        }

        if (request->hasParam("forwardSense", true)) {
            ForwardSense parsedSense = forwardSense;
            String value = request->getParam("forwardSense", true)->value();
            if (!parseForwardSense(value, parsedSense)) {
                request->send(400, "application/json", "{\"error\":\"invalid forwardSense\"}");
                return;
            }
            forwardSense = parsedSense;
            hasAnyUpdate = true;
            hasPersistentUpdate = true;
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
        request->send(200, "application/json", motorStateJson());
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
        manager.server.on("/api/pressureSensors/zeroCalibrate", HTTP_POST, [] (AsyncWebServerRequest *request) {
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
    mhSensorWebSocket.cleanupClients();
    mcp3008WebSocket.cleanupClients();
    mcp23017InputsWebSocket.cleanupClients();
    rotaryEncoderWebSocket.cleanupClients();
    pressureSensorsWebSocket.cleanupClients();

    if (motorMode == MotorMode::Potentiometer) {
        applyMotorOutputs();
    }

    const unsigned long now = millis();
    if (now - lastPotentiometerPublishMs >= potentiometerPublishIntervalMs) {
        lastPotentiometerPublishMs = now;
        if (potentiometerWebSocket.count() > 0) {
            potentiometerWebSocket.textAll(potentiometerJson());
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
}