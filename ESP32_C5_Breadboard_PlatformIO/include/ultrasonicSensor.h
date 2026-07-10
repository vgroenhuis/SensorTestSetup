#pragma once
#include <Arduino.h>

void initUltrasonicSensor();

// Returns measured range in mm
float readUltrasonicSensor();
