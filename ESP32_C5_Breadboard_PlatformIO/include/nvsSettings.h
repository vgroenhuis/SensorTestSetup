/*
    Manages Preferences stored in nvs
*/
#pragma once
#include <Arduino.h>

static const char *SERIAL_SETTINGS_NAMESPACE = "serial_cfg";
static const char *KEY_SERIAL_ENABLED = "serial_en";
static const char *KEY_INCLUDE_POT = "pot_en";

extern bool serialOutputEnabled;
extern bool includePotentiometerValue;


void loadSerialSettingsFromNvs();
bool saveSerialSettingsToNvs();