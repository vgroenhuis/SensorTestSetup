#pragma once
#include <Arduino.h>

/*
 * For controlling hobby servos and other things that need pwm input
*/

enum class PwmChannelMode {
    Servo,   // Calibrated servo mode with min/max pulse widths
    RawPWM   // Raw PWM output mode
};

struct PwmChannelConfig {
    PwmChannelMode mode;
    int minPulseUs;  // Minimum pulse width in microseconds (servo mode)
    int maxPulseUs;  // Maximum pulse width in microseconds (servo mode)
};

void initPwmServo();

// Recommended is 50 Hz for hobby servos, but can be set to other values if needed
void setPwmFrequency(float frequency);
float getPwmFrequency();

void setServoMicroseconds(int channel, int microseconds);
void setServoPwmNormalized(int channel, float normalized);

// Channel configuration
PwmChannelConfig getChannelConfig(int channel);
void setChannelConfig(int channel, const PwmChannelConfig& config);

// Conversion functions
String channelModeToString(PwmChannelMode mode);
bool parseChannelMode(const String &value, PwmChannelMode &outMode);

// Persistence
bool savePwmFrequencyToNvs();
void loadPwmFrequencyFromNvs();
bool saveChannelConfigToNvs();
void loadChannelConfigFromNvs();
bool resetPwmServoNvs();  // Clear and re-save all pwm_servo settings

