# SensorTestSetup firmware (ESP-IDF 6.1, ESP32-C5)

ESP-IDF rewrite of `../ESP32_C5_Breadboard_PlatformIO`, for the CloSer lab demos
(https://closer.ram.eemcs.utwente.nl/labdemos/). It has every part of the PlatformIO firmware; the lab demos page for it
is in `../labdemo/`.

| Part | Bus | Code |
| --- | --- | --- |
| OLED (SSD1306, 128x64): Wi-Fi state, address, access code, updates | SPI | `display.c` |
| MCP3008: potentiometer (ch 7), MH sensor (ch 6), all 8 channels | SPI | `sensors.c` |
| MCP23017 (16 GPIO), PCA9685 (16 servo/PWM), TCA9548 + 2x WF100DPZ pressure | I2C | `i2cbus.c` |
| VL53L7CX ToF (4x4 / 8x8; ST's driver in `components/vl53l7cx`) | I2C | `tof.cpp` |
| L298N motor (speed, direct, follow the pot) + encoder (PCNT), HC-SR04 ultrasonic, HX711 load cell | GPIO | `gpioparts.c` |
| Input-output matrix: routes from any sensor to a servo, the motor or an MCP23017 pin | | `matrix.c` |
| Web server: pages, `/ws` topics and commands (list in `web.h`) | | `web.c` |

Pins: `main/board.h`.

## Design
* `components/closer_demo/`: Wi-Fi (saved networks, iotroam roaming), clock, reports to the lab demos page, OTA
  updates with rollback, access codes, `/wifi` and `/udp` pages. Copied from BesBot 1.8.14 (the same component is in
  LedDemo, BesBot, ATLAS, HandTool and SpaceMouse); `components/u8g2/` likewise.
* Every sensor group samples in its own task into a snapshot (`sensors.c`); the web server, display and reports only
  read snapshots, so a slow or missing sensor can't stall anything else. A part that doesn't answer is reported as
  absent (`"ok":false`) and the rest carries on.
* One WebSocket, `/ws`, for every page: a page sends `{"sub":["pot"]}` and gets `{"t":"pot",...}` messages at that
  topic's rate (see `main/web.h`). The CloSer server's proxy allows 3 sockets per device, so one is all a page uses.
* Watching is open to everyone; changing something (MCP23017 pins, servos and PWM, zero calibration) needs control:
  one person at a time, with the 2-digit code the OLED shows (`closer_access` in `closer_demo`; the pages share
  `web/device.js` for it). Settings are kept in NVS, and a part that is re-plugged or glitches gets them again.
* Web pages are in `web/`, gzipped into the firmware at build time (`tools/pack_web.py`): an OTA update carries them
  too. All links are relative, so the pages work on the board and through `/labdemos/device/<id>/` on the server.

## Build
In an ESP-IDF 6.1 shell (Windows: ESP-IDF PowerShell from the installer):

    idf.py build

The version is the first line of `VERSION`.

## First flash (USB, once)
Register the demo on the CloSer server. `labdemos.cli` is part of the server code (GitHub `vgroenhuis/closer-server`)
and runs there, from its virtualenv:

    cd ~/closer-deploy/labdemos && .venv/bin/python -m labdemos.cli add sensortest

It prints the key once. Then put in `local/` (not in git):
* `sensortest.json`: `{"ssid": "...", "password": "...", "base_url": "https://closer.ram.eemcs.utwente.nl/labdemos"}`
  (optionally `"more": [{"ssid": ..., "password": ...}]`)
* `sensortest.key`: the key

    python tools/provision.py
    python -m esptool --chip esp32c5 -p <port> write_flash 0x0 local/sensortest-factory.bin

Wi-Fi settings and key live in the nvs partition (0x9000); OTA updates never touch them. Change them later with
`local/sensortest-settings.bin` at 0x9000.

## Updates
Bump `VERSION`, `idf.py build`, copy `build/sensortest.bin` to the server, then there (in `~/closer-deploy/labdemos`)
`.venv/bin/python -m labdemos.cli publish sensortest <path>/sensortest.bin`. The board
installs it within a minute; a version that can't report to the server within 2 minutes is rolled back.
