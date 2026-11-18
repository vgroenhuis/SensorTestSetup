# SensorTestSetup

A permanent desk setup of common lab sensors and actuators around one ESP32-C5, used to explain and try out each part.
Switch it on and everything works: every part has a live page in the browser, on the university network or through the
CloSer lab demos site (https://closer.ram.eemcs.utwente.nl/labdemos/demo?id=sensortest).

| Folder | What |
| --- | --- |
| [`firmware/`](firmware/) | The firmware (ESP-IDF 6.1): every part, its web pages, the input-output matrix, updates over the air |
| [`labdemo/`](labdemo/) | The lab demos page for it (`demo.json`, `README.md`): copied to the server |
| [`ESP32_C5_Breadboard_PlatformIO/`](ESP32_C5_Breadboard_PlatformIO/) | The earlier Arduino/PlatformIO firmware, kept for reference (its README pinout is older than the wiring: `firmware/main/board.h` has the pins) |
| [`Electronics_KiCad/`](Electronics_KiCad/) | KiCad files of the setup |

The parts: SSD1306 OLED, MCP3008 (potentiometer, MH sensor), MCP23017, PCA9685 servos, TCA9548 with two WF100DPZ pressure
sensors, VL53L7CX time-of-flight, HC-SR04 ultrasonic, HX711 load cell, L298N with a DC gear motor and encoder. Build,
first flash and updates: [`firmware/README.md`](firmware/README.md).
