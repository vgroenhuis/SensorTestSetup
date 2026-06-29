#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <LittleFS.h>
#include <Preferences.h>

#include "RoamingWiFiManager.h"
#include "websiteRoot.h"
#include "credentials.h"
#include "gpioExpanders.h"
#include "nvsSettings.h"
#include "serverApi.h"
#include "serialComms.h"
#include "oled.h"
#include "pressureSensor.h"
#include "tofSensor.h"

RoamingWiFiManager manager;

void initFileSystem() {
    if (!LittleFS.begin(true, "/littlefs", 10, "littlefs")) {
        Serial.println("LittleFS Mount Failed");
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("Setup started");
    SPI.begin(7,0,8);
    Wire.begin(2,3); // SDA pin 2, SCL pin 3
    Wire.setClock(400000);
    
    loadSerialSettingsFromNvs();
    initFileSystem();
    gpioExpandersSetup();
    initPressureSensor();
    initOledDisplay();
    initTofSensor();
    manager.init(knownNetworks, adminCredentials, aliasUrl);
    initServer(manager);
    Serial.println("Setup finished");
}

void loop() {
    manager.loop();
    serverApiLoop();
    serialManagerLoop();
    //tofSensorLoopPrintSerial();

    if (manager.isConnected() && !isIpDisplayed()) {
        displayIp(manager.getConnectedIp());
    }
}
