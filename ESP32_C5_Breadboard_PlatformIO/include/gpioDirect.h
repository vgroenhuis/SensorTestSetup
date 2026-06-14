// GPIO pins on ESP32-C5

#pragma once

static const int motorIn1Pin = 24;
static const int motorIn2Pin = 23;

static const int encoderAPin = 27;
static const int encoderBPin = 4;


void gpioDirectSetup();

// Potmeter is connected to A4
float readAnalogVolt(int pin);
