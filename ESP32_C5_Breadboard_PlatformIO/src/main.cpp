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
#include "pwmServo.h"
#include "matrix.h"
#include "dcMotor.h"
#include "nvs_flash.h"

RoamingWiFiManager manager;

void initNvs() {
    // Initialize NVS and repair if corrupted
    Serial.println("Initializing NVS");
    esp_err_t err = nvs_flash_init();
    
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        Serial.println("NVS partition was truncated/corrupted. Erasing and reinitializing...");
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    
    if (err == ESP_OK) {
        Serial.println("NVS initialized successfully");
    } else {
        Serial.printf("NVS initialization failed with error 0x%x\n", err);
    }
}

void initFileSystem() {
    if (!LittleFS.begin(true, "/littlefs", 10, "littlefs")) {
        Serial.println("LittleFS Mount Failed");
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("Setup started");
    initNvs(); // Initialize NVS before using Preferences
    listNvsNamespaces(); // List all NVS namespaces at startup for debugging
    listAllNvsEntries(); // List all NVS entries at startup for debugging
    printNvsStatistics(); // Print NVS statistics (total, used, available sizes)
    //listNVSEntries(); // List all NVS entries at startup for debugging
    SPI.begin(7,0,8);
    Wire.begin(2,3); // SDA pin 2, SCL pin 3
    Wire.setClock(400000);
    
    loadSerialSettingsFromNvs();
    initFileSystem();
    gpioExpandersSetup();
    initPwmServo();
    initPressureSensor();
    initOledDisplay();
    initTofSensor();
    initMatrix();
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
    processAllRoutes();

    displayStatus(manager.getConnectedIp());

    calcMainLoopFps();
}
