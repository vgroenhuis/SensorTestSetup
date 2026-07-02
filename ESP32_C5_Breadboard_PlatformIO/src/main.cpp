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
#include "globalVars.h"

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

void calcMainLoopFps() {
    static unsigned long lastTimeUs = micros();
    static bool filterInitialized = false;
    static float filteredFps = 0.0f;

    const unsigned long currentTimeUs = micros();
    const unsigned long deltaTimeUs = currentTimeUs - lastTimeUs;
    lastTimeUs = currentTimeUs;

    if (deltaTimeUs == 0) {
        return;
    }

    const float instantaneousFps = 1000000.0f / (float)deltaTimeUs;
    const float dtSec = (float)deltaTimeUs / 1000000.0f;
    const float tauSec = 0.2f;
    const float alpha = dtSec / (tauSec + dtSec);

    if (!filterInitialized) {
        filteredFps = instantaneousFps;
        filterInitialized = true;
    } else {
        filteredFps += alpha * (instantaneousFps - filteredFps);
    }

    mainLoopFps = filteredFps;
}


void loop() {
    manager.loop();
    serverApiLoop();
    serialManagerLoop();
    tofSensorLoop();

//    if (manager.isConnected() && !isIpDisplayed()) {
    displayStatus(manager.getConnectedIp());
//    }

    calcMainLoopFps();
}
