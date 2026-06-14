// GPIO pins on ESP32-C5

#pragma once

void gpio_direct_setup();

// returns measured voltage (0..3.3V)
// pin: A0..A5
// Potmeter is connected to A4
float readAnalogVolt(int pin);
