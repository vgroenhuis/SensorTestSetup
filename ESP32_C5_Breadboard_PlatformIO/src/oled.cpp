#include "oled.h"
// consider changing to olikraus' u8g2 library
#include <Adafruit_SSD1306.h>
#include <SPI.h>
#include <Fonts/FreeSans9pt7b.h>


#define SCREEN_WIDTH 128 // OLED display width, in pixels
#define SCREEN_HEIGHT 64 // OLED display height, in pixels

#define OLED_DC     9
#define OLED_CS     26
#define OLED_RESET  -1

bool ipDisplayed = false;

Adafruit_SSD1306 oled(SCREEN_WIDTH, SCREEN_HEIGHT,  &SPI, OLED_DC, OLED_RESET, OLED_CS);

bool isIpDisplayed() {
    return ipDisplayed;
}

void displayIp(String ip) {
    oled.clearDisplay();
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(0, 12);

    oled.printf("%s\n", ip.c_str());
    oled.display();

    ipDisplayed = true;
}

void initOledDisplay() {
    pinMode(OLED_CS, OUTPUT);
    digitalWrite(OLED_CS, HIGH);

    if(!oled.begin(SSD1306_SWITCHCAPVCC)) {
        Serial.println(F("SSD1306 allocation failed"));
        for(;;); // Don't proceed, loop forever
    }

    oled.clearDisplay();
    oled.setTextSize(1);
    oled.setFont(&FreeSans9pt7b);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(0, 12);
    oled.println("Vincent's office");
    oled.println("Initializing...");
    oled.display();
    digitalWrite(OLED_CS, LOW);
}
