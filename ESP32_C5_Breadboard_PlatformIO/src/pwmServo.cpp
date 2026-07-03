#include "pwmServo.h"
#include <Arduino.h>
#include <PCA9685.h>
#include <Wire.h>

PCA9685 servoArray(0x20);

void initPwmServo() {
    servoArray.begin();
}

void setServo(int channel, int microseconds) {
    servoArray.setPWM(channel, 0, microseconds);
    Serial.printf("Set servo channel %d to %d microseconds\n", channel, microseconds);    
}