#pragma once
#include <Arduino.h>

bool isIpDisplayed();

// Displays IP and main loop FPS
void displayStatus(String ip);

void initOledDisplay();