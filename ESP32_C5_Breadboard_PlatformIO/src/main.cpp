#include <Arduino.h>
#include "RoamingWiFiManager.h"
#include "website_root.h"
#include "credentials.h"
#include <LittleFS.h>
#include "gpio_direct.h"
#include "test.h"

RoamingWiFiManager manager;
 
void init_file_system() {
    if (!LittleFS.begin(true, "/littlefs", 10, "littlefs")) {
        Serial.println("LittleFS Mount Failed");
    } else {
        //Serial.println("LittleFS Mounted Successfully");
    }
}

void setup() {
    Serial.begin(115200);
    init_file_system();
    manager.init(knownNetworks, adminCredentials, aliasUrl);
    manager.server.on("/", [] (AsyncWebServerRequest *request) {
        handleRoot(request);
    });
    // Serve CSS file from LittleFS
    manager.server.on("/stylesheet.css", HTTP_GET, [] (AsyncWebServerRequest *request) {
        if (LittleFS.exists("/stylesheet.css")) {
            request->send(LittleFS, "/stylesheet.css", "text/css");
        } else {
            request->send(404, "text/plain", "stylesheet.css not found");
        }
    });
    manager.debugLevel = 3;


}

void printStatistics() {
    Serial.printf("%d, %3.3f\n",millis(),readAnalogVolt(A4));
}

void loop() {
    manager.loop();
    printStatistics();
}
