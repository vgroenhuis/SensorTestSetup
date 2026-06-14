#include "website_root.h"
#include <LittleFS.h>

// serve simple HTML page with link to wifi manager and its credentials
void handleRoot(AsyncWebServerRequest *request) {
    static String cachedIndexHtml = "";
    static bool isLoaded = false;
    
    // Load the file only once
    if (!isLoaded) {
        if (LittleFS.exists("/index.html")) {
            File f = LittleFS.open("/index.html", "r");
            if (f) {
                // read entire file into cachedIndexHtml
                cachedIndexHtml = "";
                size_t bytes = 0;
                while (f.available()) {
                    char c = (char)f.read();
                    cachedIndexHtml += c;
                    bytes++;
                }
                f.close();
                //Serial.printf("LittleFS: read /index.html %u bytes (cached)\n");
                isLoaded = true;
            } else {
                Serial.println("Failed to open LittleFS /index.html!");
            }
        } else {
            Serial.println("LittleFS /index.html not found!");
        }
    }
    
    // Serve the cached content
    if (isLoaded) {
        String html = cachedIndexHtml;
        if (adminCredentials.first == "" || adminCredentials.second == "") {
            html.replace("$AUTH_INFO$", "(no authentication)");
        } else {
            html.replace("$AUTH_INFO$", "(user: " + adminCredentials.first + ", pass: " + (showPasswordOnRootPage?adminCredentials.second:"****") + ")");
        }
        request->send(200, "text/html", html);
    } else {
        request->send(404, "text/plain", "index.html not found, did you upload filesystem image?");
    }
}