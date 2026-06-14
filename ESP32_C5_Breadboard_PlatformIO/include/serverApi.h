/*
    Handles REST and WebSockets endpoints
*/
#pragma once
#include <Arduino.h>
#include "RoamingWiFiManager.h"

void initServer(RoamingWiFiManager& manager);
void serverApiLoop();
