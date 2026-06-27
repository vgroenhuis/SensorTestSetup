/*
    Handles REST and WebSockets endpoints
*/
#pragma once
#include <Arduino.h>
#include "RoamingWiFiManager.h"

constexpr int POTMETER_ADC_PIN = 7;

void initServer(RoamingWiFiManager& manager);
void serverApiLoop();
