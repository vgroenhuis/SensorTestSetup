#include "pwmServo.h"
#include <Arduino.h>
#include <PCA9685.h>
#include <Wire.h>
#include <Preferences.h>

PCA9685 servoArray(0x40);

// NVS constants
static const char *PWM_SERVO_NAMESPACE = "pwm_servo";
static const char *KEY_PWM_FREQUENCY = "frequency";
static const char *KEY_CHANNEL_PREFIX = "ch_";

// Current frequency (cached)
static float currentFrequency = 50.0f;

// Channel configurations (16 channels, default to servo mode with standard pulse widths)
static PwmChannelConfig channelConfigs[16] = {
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500},
    {PwmChannelMode::Servo, 500, 2500}
};

void initPwmServo() {
    servoArray.begin();
    loadPwmFrequencyFromNvs();
    loadChannelConfigFromNvs();
    // Apply the loaded frequency
    servoArray.setFrequency(currentFrequency);
    Serial.printf("PWM servo initialized with frequency %.2f Hz\n", currentFrequency);
}

// Recommended is 50 Hz for hobby servos, but can be set to other values if needed
void setPwmFrequency(float frequency) {
    if (frequency < 24.0f) {
        Serial.printf("WARNING: PWM frequency %.2f Hz is below minimum 24 Hz, clamping to 24 Hz\n", frequency);
        frequency = 24.0f;
    }
    if (frequency > 1000.0f) {
        Serial.printf("WARNING: PWM frequency %.2f Hz exceeds safe maximum 1000 Hz, clamping to 1000 Hz\n", frequency);
        frequency = 1000.0f;
    }
    
    currentFrequency = frequency;
    servoArray.setFrequency(frequency);
    Serial.printf("PWM frequency set to %.2f Hz\n", frequency);
}

float getPwmFrequency() {
    return currentFrequency;
}

bool savePwmFrequencyToNvs() {
    Preferences preferences;
    if (!preferences.begin(PWM_SERVO_NAMESPACE, false)) {
        Serial.println("ERROR: NVS open failed for writing PWM servo settings");
        return false;
    }

    bool ok = preferences.putFloat(KEY_PWM_FREQUENCY, currentFrequency) > 0;
    
    if (!ok) {
        Serial.println("ERROR: PWM servo NVS write failed");
    } else {
        Serial.printf("PWM frequency %.2f Hz saved to NVS\n", currentFrequency);
    }
    
    preferences.end();
    return ok;
}

void loadPwmFrequencyFromNvs() {
    Preferences preferences;
    if (!preferences.begin(PWM_SERVO_NAMESPACE, true)) {
        Serial.println("ERROR: NVS open failed for reading PWM servo settings - Using default 50 Hz");
        currentFrequency = 50.0f;
        return;
    }

    currentFrequency = preferences.getFloat(KEY_PWM_FREQUENCY, 50.0f);
    Serial.printf("PWM frequency loaded from NVS: %.2f Hz\n", currentFrequency);
    
    preferences.end();
}

// Conversion functions
String channelModeToString(PwmChannelMode mode) {
    return mode == PwmChannelMode::Servo ? "servo" : "raw_pwm";
}

bool parseChannelMode(const String &value, PwmChannelMode &outMode) {
    if (value == "servo") {
        outMode = PwmChannelMode::Servo;
        return true;
    }
    if (value == "raw_pwm") {
        outMode = PwmChannelMode::RawPWM;
        return true;
    }
    return false;
}

// Channel configuration
PwmChannelConfig getChannelConfig(int channel) {
    if (channel < 0 || channel >= 16) {
        Serial.printf("ERROR: Invalid channel %d\n", channel);
        return {PwmChannelMode::Servo, 500, 2500};
    }
    return channelConfigs[channel];
}

void setChannelConfig(int channel, const PwmChannelConfig& config) {
    if (channel < 0 || channel >= 16) {
        Serial.printf("ERROR: Invalid channel %d\n", channel);
        return;
    }
    channelConfigs[channel] = config;
    Serial.printf("Channel %d config set: mode=%s, min=%d us, max=%d us\n", 
                  channel, channelModeToString(config.mode).c_str(), config.minPulseUs, config.maxPulseUs);
}

bool saveChannelConfigToNvs() {
    Preferences preferences;
    if (!preferences.begin(PWM_SERVO_NAMESPACE, false)) {
        Serial.println("ERROR: NVS open failed for writing channel config");
        return false;
    }

    bool allOk = true;
    for (int i = 0; i < 16; i++) {
        String key = String(KEY_CHANNEL_PREFIX) + String(i);
        // Store as "servo:500:2500" or "raw_pwm:0:0"
        String configStr = channelModeToString(channelConfigs[i].mode) + ":" + 
                          String(channelConfigs[i].minPulseUs) + ":" + 
                          String(channelConfigs[i].maxPulseUs);
        
        size_t written = preferences.putString(key.c_str(), configStr);
        if (written == 0) {
            Serial.printf("ERROR: Failed to write channel %d config to NVS\n", i);
            allOk = false;
        }
    }
    
    preferences.end();
    if (allOk) {
        Serial.println("Channel configs saved to NVS");
    }
    return allOk;
}

void loadChannelConfigFromNvs() {
    Preferences preferences;
    if (!preferences.begin(PWM_SERVO_NAMESPACE, true)) {
        Serial.println("ERROR: NVS open failed for reading channel config - Using defaults");
        return;
    }

    int loadedCount = 0;
    for (int i = 0; i < 16; i++) {
        String key = String(KEY_CHANNEL_PREFIX) + String(i);
        String configStr = preferences.getString(key.c_str(), "");
        
        if (configStr.length() > 0) {
            // Parse "servo:500:2500"
            int pos1 = configStr.indexOf(':');
            int pos2 = configStr.indexOf(':', pos1 + 1);
            
            if (pos1 > 0 && pos2 > 0) {
                String modeStr = configStr.substring(0, pos1);
                String minStr = configStr.substring(pos1 + 1, pos2);
                String maxStr = configStr.substring(pos2 + 1);
                
                PwmChannelMode mode = PwmChannelMode::Servo;
                parseChannelMode(modeStr, mode);
                
                int minPulse = minStr.toInt();
                int maxPulse = maxStr.toInt();
                
                channelConfigs[i] = {mode, minPulse, maxPulse};
                loadedCount++;
            }
        }
    }
    
    Serial.printf("Channel configs loaded from NVS: %d/16 channels found\n", loadedCount);
    preferences.end();
    
    // If some channels are missing (e.g., ch_0-ch_4), automatically recover
    if (loadedCount < 16) {
        Serial.printf("WARNING: Only %d/16 channels found. Attempting automatic recovery...\n", loadedCount);
        if (resetPwmServoNvs()) {
            Serial.println("Auto-recovery successful - all 16 channels restored");
        }
    }
}

// Convert microseconds to 12-bit PCA9685 tick count based on current PWM period
static uint16_t microsecondsToTicks(int microseconds) {
    // ticks = microseconds / period_us * 4096
    //       = microseconds * currentFrequency / 1,000,000 * 4096
    float ticks = (float)microseconds * currentFrequency * 4096.0f / 1000000.0f;
    if (ticks < 0.0f) ticks = 0.0f;
    if (ticks > 4095.0f) ticks = 4095.0f;
    return (uint16_t)(ticks + 0.5f);
}

void setServoMicroseconds(int channel, int microseconds) {
    uint16_t ticks = microsecondsToTicks(microseconds);
    servoArray.setPWM(channel, 0, ticks);
    //Serial.printf("Set servo channel %d to %d us -> %u ticks (%.1f Hz)\n", channel, microseconds, ticks, currentFrequency);
}

void setServoPwmNormalized(int channel, float normalized) {
    if (channel < 0 || channel >= 16) {
        Serial.printf("ERROR: Invalid channel %d\n", channel);
        return;
    }
    if (normalized < 0.0f) normalized = 0.0f;
    if (normalized > 1.0f) normalized = 1.0f;

    const PwmChannelConfig& config = channelConfigs[channel];

    if (config.mode == PwmChannelMode::RawPWM) {
        // Map 0-1 to 0-4095 (full 12-bit duty cycle range)
        uint16_t ticks = (uint16_t)(normalized * 4095.0f);
        //Serial.printf("Set raw PWM channel %d to %.3f normalized -> %u ticks\n", channel, normalized, ticks);
        servoArray.setPWM(channel, ticks);
    } else {
        // Servo mode: map 0-1 to minPulseUs-maxPulseUs, then convert to ticks
        int microseconds = config.minPulseUs + (int)((config.maxPulseUs - config.minPulseUs) * normalized);
        uint16_t ticks = microsecondsToTicks(microseconds);
        //Serial.printf("Set servo channel %d to %.3f normalized -> %d us -> %u ticks (%.1f Hz)\n", channel, normalized, microseconds, ticks, currentFrequency);
        servoArray.setPWM(channel, 0, ticks);
    }
}

bool resetPwmServoNvs() {
    Serial.println("Resetting pwm_servo namespace in NVS...");
    
    Preferences preferences;
    if (!preferences.begin(PWM_SERVO_NAMESPACE, false)) {
        Serial.println("ERROR: NVS open failed for reset");
        return false;
    }
    
    // Clear the entire namespace
    preferences.clear();
    Serial.println("Cleared pwm_servo namespace");
    
    // Re-save frequency
    size_t freqWritten = preferences.putFloat(KEY_PWM_FREQUENCY, currentFrequency);
    if (freqWritten == 0) {
        Serial.println("ERROR: Failed to re-save frequency");
        preferences.end();
        return false;
    }
    Serial.printf("Saved frequency: %.2f Hz\n", currentFrequency);
    
    // Re-save all 16 channel configs
    bool allOk = true;
    for (int i = 0; i < 16; i++) {
        String key = String(KEY_CHANNEL_PREFIX) + String(i);
        String configStr = channelModeToString(channelConfigs[i].mode) + ":" + 
                          String(channelConfigs[i].minPulseUs) + ":" + 
                          String(channelConfigs[i].maxPulseUs);
        
        size_t written = preferences.putString(key.c_str(), configStr);
        if (written == 0) {
            Serial.printf("ERROR: Failed to write channel %d during reset\n", i);
            allOk = false;
        } else {
            Serial.printf("Recovered channel %d: %s\n", i, configStr.c_str());
        }
    }
    
    preferences.end();
    
    if (allOk) {
        Serial.println("SUCCESS: pwm_servo namespace fully recovered with all 16 channels");
    }
    return allOk;
}