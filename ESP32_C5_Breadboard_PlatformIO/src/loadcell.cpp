#include "loadcell.h"

#include <Arduino.h>
#include "HX711.h"

HX711 loadcell;

namespace {
    constexpr uint8_t loadcellDataPin = 5;
    constexpr uint8_t loadcellClockPin = 1;
}

float calibrationFactor = 7050.0; // from Jurrian Mulder
 
void initLoadcell() {
    Serial.println("Initializing loadcell...");
    loadcell.begin(loadcellDataPin, loadcellClockPin);
    Serial.println("Loadcell setting scale and gain...");
    loadcell.set_scale(calibrationFactor); // Set the scale factor
    loadcell.set_gain(HX711_CHANNEL_A_GAIN_128);
    Serial.println("Loadcell tare...");
    loadcell.tare();
    Serial.println("Finished initializing loadcell.");
}

float readLoadcell() {
    // Strictly avoid blocking reads unless DOUT is actively low.
    if (digitalRead(loadcellDataPin) != LOW || !loadcell.is_ready()) {
        return NAN;
    }

    loadcell.wait_ready(); // Wait until the load cell is ready to read

    // Use a single sample to prevent internal averaging from waiting
    // for multiple conversion cycles when DOUT goes high again.
    return loadcell.get_units(1);
    //return loadcell.get_units(3);
}
