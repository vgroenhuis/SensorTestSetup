<!-- Press Ctrl-Shift-V in Visual Studio Code to preview this file.
Press Ctrl-Shift-V again to go back to the code view. -->

# Office ESP32-C5

Permanent setup for electronics.

Device: [WaveShare ESP32-C5](https://www.waveshare.com/wiki/ESP32-C5-WIFI6-KIT-NXRX).

## Pinout

| Left pins functions | J1 (ESP32-C5-DevKitC-1 v1.2) | J3 (ESP32-C5-DevKitC-1 v1.2) | Right pins functions |
| --- | --- | --- | --- |
|  | 3.3V | GND |  |
|  | RST | 11 (TX) |  |
| I2C_SDA | 2 (strap) | 12 (RX) |  |
| I2C_SCL | 3 | 24 | L298N motor OUT1 |
| SPI0_MISO | 0 | 23 | L298N motor OUT2 |
| 12-24V sens | 1 | NC/15 (PSRAM) | |
| BAT sens | 6 (BAT sens) | 27 | Motor encoder A |
| SPI0_CLK | 7 | 4 | Motor encoder B |
| SPI0_MOSI | 8 | 5/A4 | Potentiometer |
| Display DC | 9 | NC |  |
| Emergency | 10 | 28 (strap) | CSx |
| CS OLED display | 26 | GND |  |
| CSx | 25 (strap) | 14 (USB+)|  |
|  | 5V | 13 (USB-) |  |
|  | GND | GND |  |
|  | VBAT | VBAT |  |

## SPI0
CLK

MOSI

MISO

## Command to upload filesystem

The default "Upload Filesystem Image" command does not work if multiple devices are connected. Instead, use:

```pio run --target uploadfs --upload_port COM13```
