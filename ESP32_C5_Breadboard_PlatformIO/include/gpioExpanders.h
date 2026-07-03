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

struct Mcp23017Settings {
	uint8_t modeA;
	uint8_t pullupA;
	uint8_t modeB;
	uint8_t pullupB;
	uint8_t outputA;
	uint8_t outputB;
};

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
void setDigitalBankA(uint8_t values);

// Sets output pins of MCP23017 I/O expander, bank B.
void setDigitalBankB(uint8_t values);

// Returns state of MCP23017 I/O expander, bank A.
uint8_t getDigitalBankA();

// Returns state of MCP23017 I/O expander, bank B.
uint8_t getDigitalBankB();

// Returns the configured output latch value for bank A.
uint8_t getDigitalBankAOutput();

// Returns the configured output latch value for bank B.
uint8_t getDigitalBankBOutput();

void setModeAndPullupAB(uint8_t modeA, uint8_t pullupA, uint8_t modeB, uint8_t pullupB);

Mcp23017Settings getMcp23017Settings();

bool setMcp23017Settings(const Mcp23017Settings &settings, bool persist);



