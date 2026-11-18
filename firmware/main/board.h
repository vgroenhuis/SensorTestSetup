// Pins of the breadboard setup (ESP32-C5-DevKitC-1 N16R8), as wired in the PlatformIO firmware
// (ESP32_C5_Breadboard_PlatformIO/src). Its README pinout table is older than the wiring in places.
#pragma once

// SPI bus: OLED display and MCP3008 A/D converter
#define PIN_SPI_SCLK        7
#define PIN_SPI_MOSI        8
#define PIN_SPI_MISO        0
#define PIN_OLED_CS         25
#define PIN_OLED_DC         9
#define PIN_MCP3008_CS      28

// I2C bus: MCP23017, PCA9685, TCA9548 (pressure sensors), VL53L7CX
#define PIN_I2C_SDA         2
#define PIN_I2C_SCL         3

// L298N motor driver and the motor's encoder
#define PIN_MOTOR_IN1       24
#define PIN_MOTOR_IN2       23
#define PIN_ENC_A           26
#define PIN_ENC_B           4

// HC-SR04 ultrasonic sensor
#define PIN_US_TRIG         6
#define PIN_US_ECHO         10

// HX711 load cell amplifier
#define PIN_HX711_DOUT      5
#define PIN_HX711_SCK       1

// MCP3008 channels
#define MCP3008_CH_MH       6       // MH sensor module (analog out)
#define MCP3008_CH_POT      7       // potentiometer
#define MCP3008_VREF        3.3f
