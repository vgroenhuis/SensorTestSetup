#include "gpioDirect.h"
#include <Arduino.h>

void gpioDirectSetup() {

    pinMode(motorIn1Pin, OUTPUT); // L298N 1
    pinMode(motorIn2Pin, OUTPUT); // L298N 2

    pinMode(encoderAPin, INPUT); // encoder A
    pinMode(encoderBPin, INPUT); // encoder B

    Serial.println("GPIO pins set.");
}

float readAnalogVolt(int pin) {
    int x = analogReadMilliVolts(pin);
    return x/1000.0;
}
