#include "gpioExpanders.h"
#include <Arduino.h>
#include <Wire.h>
#include <MCP23017.h>
#include <MCP_ADC.h>
#include <Preferences.h>

MCP23017 mcp(0x20); // A0, A1, A2 all pulled LOW

//SPIClass* mySPI = new SPIClass(VSPI);
MCP3008 adc(&SPI);

volatile int interruptTriggerCount = 0;
volatile int encoderDoubleStepCount = 0; // it can increase if an interrupt is missed
volatile int encoderPos = 0;

namespace {
    const char *MCP23017_SETTINGS_NAMESPACE = "mcp23017";
    const char *KEY_MODE_A = "modeA";
    const char *KEY_PULLUP_A = "pullA";
    const char *KEY_MODE_B = "modeB";
    const char *KEY_PULLUP_B = "pullB";
    const char *KEY_OUTPUT_A = "outA";
    const char *KEY_OUTPUT_B = "outB";

    Mcp23017Settings mcpSettings = {
        0x00,
        0x00,
        0xff,
        0xff,
        0x03,
        0x00
    };

    bool saveMcp23017SettingsToNvs() {
        Preferences preferences;
        if (!preferences.begin(MCP23017_SETTINGS_NAMESPACE, false)) {
            Serial.println("NVS open failed for writing MCP23017 settings");
            return false;
        }

        bool okModeA = preferences.putUChar(KEY_MODE_A, mcpSettings.modeA) > 0;
        bool okPullupA = preferences.putUChar(KEY_PULLUP_A, mcpSettings.pullupA) > 0;
        bool okModeB = preferences.putUChar(KEY_MODE_B, mcpSettings.modeB) > 0;
        bool okPullupB = preferences.putUChar(KEY_PULLUP_B, mcpSettings.pullupB) > 0;
        bool okOutputA = preferences.putUChar(KEY_OUTPUT_A, mcpSettings.outputA) > 0;
        bool okOutputB = preferences.putUChar(KEY_OUTPUT_B, mcpSettings.outputB) > 0;
        preferences.end();

        return okModeA && okPullupA && okModeB && okPullupB && okOutputA && okOutputB;
    }

    void loadMcp23017SettingsFromNvs() {
        Preferences preferences;
        if (!preferences.begin(MCP23017_SETTINGS_NAMESPACE, true)) {
            Serial.println("NVS open failed for reading MCP23017 settings");
            saveMcp23017SettingsToNvs();
            return;
        }

        mcpSettings.modeA = preferences.getUChar(KEY_MODE_A, mcpSettings.modeA);
        mcpSettings.pullupA = preferences.getUChar(KEY_PULLUP_A, mcpSettings.pullupA);
        mcpSettings.modeB = preferences.getUChar(KEY_MODE_B, mcpSettings.modeB);
        mcpSettings.pullupB = preferences.getUChar(KEY_PULLUP_B, mcpSettings.pullupB);
        mcpSettings.outputA = preferences.getUChar(KEY_OUTPUT_A, mcpSettings.outputA);
        mcpSettings.outputB = preferences.getUChar(KEY_OUTPUT_B, mcpSettings.outputB);
        preferences.end();
    }

    void applyMcp23017SettingsToHardware() {
        mcp.pinMode8(0, mcpSettings.modeA);
        mcp.setPullup8(0, mcpSettings.pullupA);
        mcp.pinMode8(1, mcpSettings.modeB);
        mcp.setPullup8(1, mcpSettings.pullupB);
        mcp.write8(0, mcpSettings.outputA);
        mcp.write8(1, mcpSettings.outputB);
    }
}

// Order of bit pattern in forward motion: 00 -> 01 -> 11 -> 10
inline void processEncoder(byte bits)
{
    static byte oldBits; // previous state
    const int phase[4] = {0, 3, 1, 2};

    if (bits != oldBits)
    {
        int delta = phase[bits] - phase[oldBits];
        if (delta > 2)
            delta -= 4;
        if (delta <= -2)
            delta += 4;
        if (delta == 2) {
            encoderDoubleStepCount = encoderDoubleStepCount + 1;
        }
        encoderPos += delta;
        oldBits = bits;
    }
}

void IRAM_ATTR handleEncoderInterrupt() {
    interruptTriggerCount = interruptTriggerCount + 1;

    const int aPin = encAPin;
    const int bPin = encBPin;
    byte bits = static_cast<byte>(gpio_get_level(static_cast<gpio_num_t>(aPin))) |
                (static_cast<byte>(gpio_get_level(static_cast<gpio_num_t>(bPin))) << 1);

    processEncoder(bits);
}

byte getEncABPins() {
    byte bits = static_cast<byte>(gpio_get_level(static_cast<gpio_num_t>(encAPin))) |
                (static_cast<byte>(gpio_get_level(static_cast<gpio_num_t>(encBPin))) << 1);
    return bits;    
}

int getEncoderInterruptCount() {
    return interruptTriggerCount;
}

int getencoderDoubleStepCount() {
    return encoderDoubleStepCount;
}

int getEncoderPos() {
    return encoderPos;
}

void gpioExpandersSetup() {
    Serial.println("Setting up GPIO expanders");
    // Wire already has been initialized at this point
    pinMode(motorIn1Pin, OUTPUT); // L298N 1
    pinMode(motorIn2Pin, OUTPUT); // L298N 2

    pinMode(encAPin, INPUT);
    pinMode(encBPin, INPUT);

    loadMcp23017SettingsFromNvs();
    applyMcp23017SettingsToHardware();

    adc.begin(MCP3088_CS);

    attachInterrupt(digitalPinToInterrupt(encAPin), handleEncoderInterrupt, CHANGE);
    attachInterrupt(digitalPinToInterrupt(encBPin), handleEncoderInterrupt, CHANGE);
}

float readAdcAnalogVolt(int pin) {
    int x = adc.read(pin);
    return x*3.3/adc.maxValue();
}

std::array<float, 8> readAdcAnalogVoltAll() {
    int16_t rawAdc[8];
    uint8_t channels[8] = {0, 1, 2, 3, 4, 5, 6, 7};
    adc.readMultiple(channels, 8, rawAdc);
    std::array<float, 8> adcVolt;
    for (int i=0;i<8;i++) {
        adcVolt[i]=rawAdc[i]*3.3/adc.maxValue();
    }
    return adcVolt;
}

float readAnalogVolt(int pin) {
    int x = analogReadMilliVolts(pin);
    return x/1000.0;
}

void setDigitalBankA(uint8_t values) {
    mcpSettings.outputA = values;
    mcp.write8(0, values);
}

// Sets output pins of MCP23017 I/O expander, bank B.
void setDigitalBankB(uint8_t values) {
    mcpSettings.outputB = values;
    mcp.write8(1, values);
}

// Returns state of MCP23017 I/O expander, bank A.
uint8_t getDigitalBankA() {
    return mcp.read8(0);
}

// Returns state of MCP23017 I/O expander, bank B.
uint8_t getDigitalBankB() {
    return mcp.read8(1);
}

uint8_t getDigitalBankAOutput() {
    return mcpSettings.outputA;
}

uint8_t getDigitalBankBOutput() {
    return mcpSettings.outputB;
}

void setModeAndPullupAB(uint8_t modeA, uint8_t pullupA, uint8_t modeB, uint8_t pullupB) {
    mcpSettings.modeA = modeA;
    mcpSettings.pullupA = pullupA;
    mcpSettings.modeB = modeB;
    mcpSettings.pullupB = pullupB;
    mcp.pinMode8(0, modeA);
    mcp.setPullup8(0, pullupA);
    mcp.pinMode8(1, modeB);
    mcp.setPullup8(1, pullupB);
}

Mcp23017Settings getMcp23017Settings() {
    return mcpSettings;
}

bool setMcp23017Settings(const Mcp23017Settings &settings, bool persist) {
    mcpSettings = settings;
    applyMcp23017SettingsToHardware();

    if (!persist) {
        return true;
    }

    return saveMcp23017SettingsToNvs();
}
