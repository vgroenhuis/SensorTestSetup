#pragma once
#include <Arduino.h>

enum class MotorMode {
    Direct,
    Potentiometer,
    MotorAPI
};

enum class MotorDirection {
    Forward,
    Reverse
};

enum class ForwardSense {
    Ccw,
    Cw
};

// Initialization
void initDcMotor();

// Conversion functions
String motorModeToString(MotorMode mode);
String motorDirectionToString(MotorDirection direction);
String forwardSenseToString(ForwardSense sense);

// Parsing functions
bool parseMotorMode(const String &value, MotorMode &outMode);
bool parseMotorDirection(const String &value, MotorDirection &outDirection);
bool parseForwardSense(const String &value, ForwardSense &outSense);
bool parseDuty(const String &value, int &outDuty);

// Motor control
void setMotorMode(MotorMode mode);
void setDirectInput1(bool state);
void setDirectInput2(bool state);
void setPwmDuty(int duty);
void setPwmDirection(MotorDirection direction);
void setForwardSense(ForwardSense sense);
void applyMotorOutputs();

// Motor control via API (only works when motorMode == MotorAPI)
void setMotorNormalizedAPI(float normalized); // normalized range: 0.0 to 1.0, where 0.5 is stop, <0.5 is reverse, >0.5 is forward
void setMotorDirectionAPI(bool forward);
void setMotorPwmNormalizedAPI(float normalized); // normalized range: 0.0 to 1.0, where 0 = stop, 1 = full speed

// State access
MotorMode getMotorMode();
bool getDirectInput1();
bool getDirectInput2();
int getPwmDuty();
MotorDirection getPwmDirection();
ForwardSense getForwardSense();

// JSON representation
String getMotorStateJson();

// Persistence
bool saveMotorSettingsToNvs();
void loadMotorSettingsFromNvs();
