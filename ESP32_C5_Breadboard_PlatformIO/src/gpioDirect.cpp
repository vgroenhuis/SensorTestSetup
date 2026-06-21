#include "gpioDirect.h"
#include <Arduino.h>
#include <Wire.h>
#include <MCP23017.h>

MCP23017 mcp(0x20); // A0, A1, A2 all pulled LOW

volatile int interruptTriggerCount = 0;
volatile int encoderDoubleStepCount = 0; // it can increase if an interrupt is missed
volatile int encoderPos = 0;

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

void gpioDirectSetup() {
    // Wire already has been initialized at this point
    pinMode(motorIn1Pin, OUTPUT); // L298N 1
    pinMode(motorIn2Pin, OUTPUT); // L298N 2

    pinMode(encAPin, INPUT);
    pinMode(encBPin, INPUT);

    mcp.pinMode8(0, 0x00); // output
    mcp.pinMode8(1, 0xff); // input

    mcp.write8(0, 0x03); // LEDs ON

    attachInterrupt(digitalPinToInterrupt(encAPin), handleEncoderInterrupt, CHANGE);
    attachInterrupt(digitalPinToInterrupt(encBPin), handleEncoderInterrupt, CHANGE);
}

float readAnalogVolt(int pin) {
    int x = analogReadMilliVolts(pin);
    return x/1000.0;
}
