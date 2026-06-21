// GPIO pins on ESP32-C5
// Also includes MCP23017 expander

#pragma once
#include <Arduino.h>

static const int motorIn1Pin = 24;
static const int motorIn2Pin = 23;

static const int encAPin = 26;
static const int encBPin = 4;


void gpioDirectSetup();

// Potmeter is connected to A4
float readAnalogVolt(int pin);

// Total interrupt count
int getEncoderInterruptCount();

// Double-step count, indicating an encoder event was missed / count incrementing too quickly
int getencoderDoubleStepCount();

// Returns current encoder position, in steps
int getEncoderPos();

// Bit 0: A. Bit 1: B.
byte getEncABPins();