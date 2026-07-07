#include "serialComms.h"
#include "nvsSettings.h"
#include "gpioExpanders.h"
#include "loadcell.h"

void printSerialData() {
    if (!serialOutputEnabled) {
        return;
    }

    Serial.printf("%.5f", micros()/1000000.0);

    if (includePotentiometerValue) {
        Serial.printf(", %.3f", readAdcAnalogVolt(7));
    }

    if (1) {
        Serial.printf(", %.2f", readLoadcell());
    }

    Serial.printf("\n");
}

void serialManagerLoop() {
    printSerialData();
}
