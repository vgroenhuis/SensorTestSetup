#pragma once
#include <Arduino.h>

bool isIpDisplayed();

// Displays IP and main loop FPS
void displayStatus(String ip);

void initOledDisplay();

// Get OLED enabled state
bool isOledEnabled();

// Set OLED enabled state and optionally persist to NVS
bool setOledEnabled(bool enabled, bool persist);