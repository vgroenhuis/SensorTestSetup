#pragma once
#include <Arduino.h>
#include <array>

#define TCA_ADDR 0x70 // I2C multiplexer     (A0 low, A1 low, A2 low)
#define PRESSURE_SENSOR_ADDR 0x6D // WF100DPZ10BG
constexpr int PRESSURE_SENSOR_COUNT = 2;

// Initializes the I2C multiplexer
void initPressureSensor();

bool arePressureSensorsEnabled();
bool setPressureSensorsEnabled(bool enabled);

// Zero-calibrates sensor of this id
void zeroCalibratePressure(int sensorId);

// Single-shot readout; returns pressure in bar
float readPressureSensorSingleShot(uint8_t sensorId);

// Single-shot readout of both pressure sensors
std::array<float, PRESSURE_SENSOR_COUNT> readPressureSensorsSingleShot();