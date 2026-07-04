#include "dcMotor.h"
#include "globalVars.h"
#include "gpioExpanders.h"
#include "serverApi.h"
#include <Preferences.h>

// ==================== OUTPUT WRITE HIERARCHY ====================
// Functions that ACTUALLY WRITE to motor GPIO pins (via pinMode/digitalWrite/analogWrite):
//   1. applyMotorPwmWithDirection() - static helper
//      - Sets motorIn1Pin/motorIn2Pin direction based on Forward/Reverse
//      - Writes PWM duty to appropriate pin
//   2. applyMotorStop() - static helper
//      - Sets both motorIn1Pin and motorIn2Pin LOW
//
// Functions that DISPATCH to above based on motor mode:
//   - applyMotorOutputs() - public
//     - Direct mode: directly uses digitalWrite(motorIn1Pin/In2Pin)
//     - MotorAPI mode: calls applyMotorPwmWithDirection()
//     - Potentiometer mode: calls applyMotorStop() and applyMotorPwmWithDirection()
//
// Functions that TRIGGER output updates by calling applyMotorOutputs():
//   - setMotorNormalizedAPI(float normalized) - only works if motorMode == MotorAPI
//   - setMotorDirectionAPI(bool forward) - only works if motorMode == MotorAPI
//   - setMotorPwmNormalizedAPI(float normalized) - only works if motorMode == MotorAPI
//   - initDcMotor()
//   - Matrix routing functions indirectly via above functions
// ================================================================

// Motor settings
static MotorMode motorMode = MotorMode::MotorAPI;
static bool directIn1 = false;
static bool directIn2 = false;
static int pwmDuty = 0;
static MotorDirection pwmDirection = MotorDirection::Forward;
static ForwardSense forwardSense = ForwardSense::Ccw; // Maps logical "forward" to physical direction

// External function declarations
extern float readAdcAnalogVolt(int channel);

// NVS constants
static const char *MOTOR_SETTINGS_NAMESPACE = "motor_cfg";
static const char *KEY_MOTOR_MODE = "motor_mode";
static const char *KEY_FORWARD_SENSE = "fwd";

// Motor parameters
static const float motorCenterVoltage = 1.65f;
static const float motorHalfRangeVoltage = 1.65f;
static const float motorDeadbandVoltage = 0.04f;

// Conversion functions
String motorModeToString(MotorMode mode) {
    if (mode == MotorMode::Direct) {
        return "direct";
    }
    if (mode == MotorMode::MotorAPI) {
        return "motor_api";
    }
    return "potentiometer";
}

String motorDirectionToString(MotorDirection direction) {
    return direction == MotorDirection::Forward ? "forward" : "reverse";
}

String forwardSenseToString(ForwardSense sense) {
    return sense == ForwardSense::Ccw ? "ccw" : "cw";
}

// Parsing functions
bool parseMotorMode(const String &value, MotorMode &outMode) {
    if (value == "direct") {
        outMode = MotorMode::Direct;
        return true;
    }
    if (value == "motor_api") {
        outMode = MotorMode::MotorAPI;
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

// Motor control helper functions
static void applyMotorPwmWithDirection(int duty, MotorDirection direction) {
    if (direction == MotorDirection::Forward) {
        pinMode(motorIn2Pin, OUTPUT);
        digitalWrite(motorIn2Pin, LOW);
        analogWrite(motorIn1Pin, duty);
    } else {
        pinMode(motorIn1Pin, OUTPUT);
        digitalWrite(motorIn1Pin, LOW);
        analogWrite(motorIn2Pin, duty);
    }
}

static MotorDirection mapLogicalToPhysicalDirection(MotorDirection logicalDirection) {
    if (forwardSense == ForwardSense::Ccw) {
        return logicalDirection;
    }
    return logicalDirection == MotorDirection::Forward ? MotorDirection::Reverse : MotorDirection::Forward;
}

static void applyMotorStop() {
    pinMode(motorIn1Pin, OUTPUT);
    pinMode(motorIn2Pin, OUTPUT);
    digitalWrite(motorIn1Pin, LOW);
    digitalWrite(motorIn2Pin, LOW);
}

// Public API
void setMotorMode(MotorMode mode) {
    motorMode = mode;
}

void setDirectInput1(bool state) {
    directIn1 = state;
}

void setDirectInput2(bool state) {
    directIn2 = state;
}

void setPwmDuty(int duty) {
    pwmDuty = duty;
}

void setPwmDirection(MotorDirection direction) {
    pwmDirection = direction;
}

void setForwardSense(ForwardSense sense) {
    forwardSense = sense;
}

MotorMode getMotorMode() {
    return motorMode;
}

bool getDirectInput1() {
    return directIn1;
}

bool getDirectInput2() {
    return directIn2;
}

int getPwmDuty() {
    return pwmDuty;
}

MotorDirection getPwmDirection() {
    return pwmDirection;
}

ForwardSense getForwardSense() {
    return forwardSense;
}

void setMotorNormalizedAPI(float normalized) {
    // Only works if motor is in MotorAPI mode
    if (motorMode != MotorMode::MotorAPI) {
        //Serial.printf("WARNING: setMotorNormalizedAPI called but motor mode is not MotorAPI (mode=%s)\n", motorModeToString(motorMode).c_str());
        return;
    }

    // normalized range: 0.0 to 1.0, where 0.5 is stop, <0.5 is reverse, >0.5 is forward
    if (normalized < 0.0f) {
        normalized = 0.0f;
    }
    if (normalized > 1.0f) {
        normalized = 1.0f;
    }

    // Calculate duty cycle (0-255) and direction based on normalized input
    float centered = normalized - 0.5f;  // Range: -0.5 to 0.5
    float dutyCycleNormalized = fabs(centered) * 2.0f;  // Range: 0.0 to 1.0
    int duty = (int)(dutyCycleNormalized * 255.0f + 0.5f);

    pwmDuty = duty;
    pwmDirection = centered < 0.0f ? MotorDirection::Reverse : MotorDirection::Forward;
    applyMotorOutputs();
}

void setMotorDirectionAPI(bool forward) {
    // Only works if motor is in MotorAPI mode
    if (motorMode != MotorMode::MotorAPI) {
        //Serial.printf("WARNING: setMotorDirectionAPI called but motor mode is not MotorAPI (mode=%s)\n", motorModeToString(motorMode).c_str());
        return;
    }

    pwmDirection = forward ? MotorDirection::Forward : MotorDirection::Reverse;
    applyMotorOutputs();
}

void setMotorPwmNormalizedAPI(float normalized) {
    // Only works if motor is in MotorAPI mode
    if (motorMode != MotorMode::MotorAPI) {
        //Serial.printf("WARNING: setMotorPwmNormalizedAPI called but motor mode is not MotorAPI (mode=%s)\n", motorModeToString(motorMode).c_str());
        return;
    }

    // normalized range: 0.0 to 1.0, where 0 is stop, 1 is full speed
    if (normalized < 0.0f) {
        normalized = 0.0f;
    }
    if (normalized > 1.0f) {
        normalized = 1.0f;
    }

    pwmDuty = (int)(normalized * 255.0f + 0.5f);
    applyMotorOutputs();
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

    if (motorMode == MotorMode::MotorAPI) {
        applyMotorPwmWithDirection(pwmDuty, mapLogicalToPhysicalDirection(pwmDirection));
        return;
    }

    if (motorMode == MotorMode::Potentiometer) {
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
}

String getMotorStateJson() {
    return String("{\"mode\":\"") + motorModeToString(motorMode) +
           "\",\"directIn1\":" + (directIn1 ? "true" : "false") +
           ",\"directIn2\":" + (directIn2 ? "true" : "false") +
           ",\"pwmDuty\":" + pwmDuty +
           ",\"direction\":\"" + motorDirectionToString(pwmDirection) +
           "\",\"forwardSense\":\"" + forwardSenseToString(forwardSense) + "\"}";
}

// Persistence
bool saveMotorSettingsToNvs() {
    Preferences preferences;
    if (!preferences.begin(MOTOR_SETTINGS_NAMESPACE, false)) {
        Serial.println("ERROR: NVS open failed for writing motor settings");
        return false;
    }

    bool okMode = preferences.putString(KEY_MOTOR_MODE, motorModeToString(motorMode)) > 0;
    bool okSense = preferences.putString(KEY_FORWARD_SENSE, forwardSenseToString(forwardSense)) > 0;
    
    if (!okMode || !okSense) {
        Serial.printf("ERROR: Motor NVS write failed - Mode: %s, Sense: %s\n", okMode ? "OK" : "FAIL", okSense ? "OK" : "FAIL");
    } else {
        Serial.println("Motor settings saved to NVS");
    }
    
    preferences.end();
    return okMode && okSense;
}

void loadMotorSettingsFromNvs() {
    Preferences preferences;
    if (!preferences.begin(MOTOR_SETTINGS_NAMESPACE, true)) {
        Serial.println("ERROR: NVS open failed for reading motor settings - Saving defaults");
        saveMotorSettingsToNvs();
        return;
    }

    MotorMode parsedMode = motorMode;
    String storedMode = preferences.getString(KEY_MOTOR_MODE, motorModeToString(motorMode));
    if (parseMotorMode(storedMode, parsedMode)) {
        motorMode = parsedMode;
        Serial.printf("Motor mode loaded from NVS: %s\n", motorModeToString(motorMode).c_str());
    } else {
        Serial.printf("WARNING: Failed to parse motor mode from NVS: %s\n", storedMode.c_str());
    }

    ForwardSense parsedSense = forwardSense;
    String storedSense = preferences.getString(KEY_FORWARD_SENSE, forwardSenseToString(forwardSense));
    if (parseForwardSense(storedSense, parsedSense)) {
        forwardSense = parsedSense;
        Serial.printf("Forward sense loaded from NVS: %s\n", forwardSenseToString(forwardSense).c_str());
    } else {
        Serial.printf("WARNING: Failed to parse forward sense from NVS: %s\n", storedSense.c_str());
    }

    preferences.end();
}

void initDcMotor() {
    loadMotorSettingsFromNvs();
    applyMotorOutputs();
}