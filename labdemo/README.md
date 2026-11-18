A permanent desk setup of common lab sensors and actuators, all wired to one ESP32-C5 on a breadboard. Each part has its
own page on the board's web server with its live values, so you can see how a sensor behaves before you use it in your own
project.

![The sensor test setup](sensortest.jpg)

## What is on the board

| Part | What it measures or does | Bus |
|---|---|---|
| SSD1306 OLED | Wi-Fi state, IP address, access code | SPI |
| MCP3008 A/D converter | potentiometer, MH sensor module, 8 analog channels | SPI |
| MCP23017 | 16 digital inputs and outputs | I2C |
| PCA9685 | up to 16 servos or PWM outputs | I2C |
| TCA9548 + 2x WF100DPZ | air pressure | I2C |
| VL53L7CX | time-of-flight distance, 4x4 or 8x8 zones, in 2D and 3D | I2C |
| HC-SR04 | ultrasonic distance | GPIO |
| HX711 + load cell | force / weight | GPIO |
| L298N + gear motor | DC motor with encoder | GPIO |

The **input-output matrix** connects any sensor to an actuator: the potentiometer to a servo, a distance to the motor, a
pressure to an output pin. Its routes run on the board itself, also with no page open.

## Try it

**Open demo** (above, while it is active) opens the board's own page with a link to each part. Everyone can watch every
page. Changing something (a servo, the motor, an output pin, a setting, a route) needs **control**: one person at a time.
Click *Ask for control* and type the 2-digit code the board's display shows; control ends when you release it, close the
page, or after 10 minutes without using it. Nothing on the board can be changed without someone at the desk.

The motor's *follow the potentiometer* mode and the matrix routes keep running without control, so the setup shows
something as soon as it is switched on.

## Set up

1. Plug in the USB cable. The display shows the firmware version, then the Wi-Fi state and the **IP address**.
2. About a minute later this page shows **Active**.

A part that is not connected (or comes loose) shows as absent on the board's main page; the rest keeps working, and the
part is found again when it is plugged back in.

## If it doesn't work

* The demo stays *Inactive*: check the display. "Offline" means it doesn't find a known Wi-Fi network: add one with the
  board's *Wi-Fi settings* page (from the university network), or reprovision it over USB (see the repository's
  `firmware/README.md`).
* A page says *Disconnected, retrying*: the board restarts or lost Wi-Fi; the page reconnects by itself.

## Updates

New firmware goes over the air: `labdemos.cli publish sensortest <file>.bin`. The board installs it within a minute and
rolls back if the new version can't report to this site.
