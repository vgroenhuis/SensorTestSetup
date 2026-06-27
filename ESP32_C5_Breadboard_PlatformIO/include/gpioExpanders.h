// GPIO pins on ESP32-C5
// Also includes MCP23017 expander

#pragma once
#include <Arduino.h>
#include <array>

static const int motorIn1Pin = 24;
static const int motorIn2Pin = 23;

static const int encAPin = 26;
static const int encBPin = 4;

static const int MCP3088_CS = 28;


void gpioExpandersSetup();

// Read analog input directly connected to ESP32-C5
float readAnalogVolt(int pin);

// Read analog input through MCP3008
float readAdcAnalogVolt(int pin);

std::array<float, 8> readAdcAnalogVoltAll();

// Total interrupt count
int getEncoderInterruptCount();

// Double-step count, indicating an encoder event was missed / count incrementing too quickly
int getencoderDoubleStepCount();

// Returns current encoder position, in steps
int getEncoderPos();

// Bit 0: A. Bit 1: B.
byte getEncABPins();

// Sets output pins of MCP23017 I/O expander, bank A.
void setDigitalBankB(uint8_t values);

// Returns state of MCP23017 I/O expander, bank B.
uint8_t getDigitalBankA();


