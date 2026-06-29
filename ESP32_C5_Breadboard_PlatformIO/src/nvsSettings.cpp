#include "nvsSettings.h"
#include <Preferences.h>

bool serialOutputEnabled = false;
bool includePotentiometerValue = true;

void loadSerialSettingsFromNvs() {
    Serial.println("Loading settings from NVS");
    Preferences preferences;
    if (!preferences.begin(SERIAL_SETTINGS_NAMESPACE, true)) {
        Serial.println("NVS open failed for reading serial settings");
        if (!saveSerialSettingsToNvs()) {
            Serial.println("NVS also failed for writing serial settings");
            return;
        }

        return;
    }

    serialOutputEnabled = preferences.getBool(KEY_SERIAL_ENABLED, serialOutputEnabled);
    includePotentiometerValue = preferences.getBool(KEY_INCLUDE_POT, includePotentiometerValue);
    preferences.end();
}

bool saveSerialSettingsToNvs() {
    Preferences preferences;
    if (!preferences.begin(SERIAL_SETTINGS_NAMESPACE, false)) {
        Serial.println("NVS open failed for writing serial settings");
        return false;
    }

    bool okSerial = preferences.putBool(KEY_SERIAL_ENABLED, serialOutputEnabled) > 0;
    bool okPot = preferences.putBool(KEY_INCLUDE_POT, includePotentiometerValue) > 0;
    preferences.end();
    return okSerial && okPot;
}