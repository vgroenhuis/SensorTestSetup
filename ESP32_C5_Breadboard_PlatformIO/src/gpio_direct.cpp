#include "gpio_direct.h"
#include <Arduino.h>

void gpio_direct_setup() {
    pinMode(24, OUTPUT); // L298N 1
    pinMode(25, OUTPUT); // L298N 2
    pinMode(15, OUTPUT); // L298N 3
    pinMode(27, OUTPUT); // L298N 4
    pinMode(4, INPUT); // encoder A
    pinMode(28, INPUT); // encoder B
}

float readAnalogVolt(int pin) {
    int x = analogReadMilliVolts(pin);
    return x/1000.0;
}
