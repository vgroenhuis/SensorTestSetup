#include <Arduino.h>
#include "RoamingWiFiManager.h"
#include "websiteRoot.h"
#include "credentials.h"
#include <LittleFS.h>
#include <Preferences.h>
#include "gpioDirect.h"
#include "nvsSettings.h"
#include "serverApi.h"
#include "serialComms.h"
#include "oled.h"
#include <SPI.h>

RoamingWiFiManager manager;

void initFileSystem() {
    if (!LittleFS.begin(true, "/littlefs", 10, "littlefs")) {
        Serial.println("LittleFS Mount Failed");
    }
}

void setup() {
    Serial.begin(115200);
    SPI.begin(7,0,8);
    loadSerialSettingsFromNvs();
    initFileSystem();
    gpioDirectSetup();
    initOledDisplay();
    manager.init(knownNetworks, adminCredentials, aliasUrl);
    initServer(manager);
}

void loop() {
    manager.loop();
    serverApiLoop();
    serialManagerLoop();

    if (manager.isConnected() && !isIpDisplayed()) {
        displayIp(manager.getConnectedIp());
    }
}
