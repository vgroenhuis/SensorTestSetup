#pragma once

/*
 * For controlling hobby servos and other things that need pwm input
*/

void initPwmServo();

void setServo(int channel, int microseconds);