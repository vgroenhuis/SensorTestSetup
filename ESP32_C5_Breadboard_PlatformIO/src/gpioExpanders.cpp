#include "gpioExpanders.h"
#include <Arduino.h>
#include <Wire.h>
#include <MCP23017.h>
#include <MCP_ADC.h>

MCP23017 mcp(0x20); // A0, A1, A2 all pulled LOW

//SPIClass* mySPI = new SPIClass(VSPI);
MCP3008 adc(&SPI);

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

void gpioExpandersSetup() {
    Serial.println("Setting up GPIO expanders");
    // Wire already has been initialized at this point
    pinMode(motorIn1Pin, OUTPUT); // L298N 1
    pinMode(motorIn2Pin, OUTPUT); // L298N 2

    pinMode(encAPin, INPUT);
    pinMode(encBPin, INPUT);

    mcp.pinMode8(0, 0x00); // output
    mcp.pinMode8(1, 0xff); // input
    mcp.setPullup8(1, 0xff); // all eight inputs have pull-up enabled
    
    setDigitalBankB(0x03); // LEDs ON

    adc.begin(MCP3088_CS);
    /*
    Serial.println("ADC\tCHAN\tMAXVALUE");
    Serial.print("adc\t");
    Serial.print(adc.channels());
    Serial.print("\t");
    Serial.println(adc.maxValue());
    Serial.printf("ch 0: %f V\n",readAdcAnalogVolt(0));
    */

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

// Sets output pins of MCP23017 I/O expander, bank A.
void setDigitalBankB(uint8_t values) {
    mcp.write8(0, values);
}

// Returns state of MCP23017 I/O expander, bank B.
uint8_t getDigitalBankA() {
    return mcp.read8(1);
}
