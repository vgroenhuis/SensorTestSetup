# SensorTestSetup firmware (ESP-IDF 6.1, ESP32-C5)

ESP-IDF rewrite of `../ESP32_C5_Breadboard_PlatformIO`, for the CloSer lab demos
(https://closer.ram.eemcs.utwente.nl/labdemos/). Being ported one group of sensors at a time; until a sensor is
here, the PlatformIO firmware is the one that has it.

| Done | Part | Bus |
| --- | --- | --- |
| yes | OLED (SSD1306, 128x64): Wi-Fi state, address, access code, updates | SPI |
| yes | MCP3008: potentiometer (ch 7), MH sensor (ch 6), all 8 channels | SPI |
| | MCP23017, PCA9685 servos, TCA9548 + 2x WF100DPZ pressure, VL53L7CX ToF | I2C |
| | L298N motor + encoder, HC-SR04 ultrasonic, HX711 load cell | GPIO |
| | Input-output matrix | |

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
* Web pages are in `web/`, gzipped into the firmware at build time (`tools/pack_web.py`): an OTA update carries them
  too. All links are relative, so the pages work on the board and through `/labdemos/device/<id>/` on the server.

## Build
In an ESP-IDF 6.1 shell (Windows: ESP-IDF PowerShell from the installer):

    idf.py build

The version is the first line of `VERSION`.

## First flash (USB, once)
Register the demo on the CloSer server (`python -m labdemos.cli add sensortest`, prints the key once), then put
in `local/` (not in git):
* `sensortest.json`: `{"ssid": "...", "password": "...", "base_url": "https://closer.ram.eemcs.utwente.nl/labdemos"}`
  (optionally `"more": [{"ssid": ..., "password": ...}]`)
* `sensortest.key`: the key

    python tools/provision.py
    python -m esptool --chip esp32c5 -p <port> write_flash 0x0 local/sensortest-factory.bin

Wi-Fi settings and key live in the nvs partition (0x9000); OTA updates never touch them. Change them later with
`local/sensortest-settings.bin` at 0x9000.

## Updates
Bump `VERSION`, `idf.py build`, then on the server `labdemos.cli publish sensortest build/sensortest.bin`. The board
installs it within a minute; a version that can't report to the server within 2 minutes is rolled back.
