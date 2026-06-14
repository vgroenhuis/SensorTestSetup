<!-- Press Ctrl-Shift-V in Visual Studio Code to preview this file -->

# Office ESP32-C5

Permanent setup for electronics.

Device: [WaveShare ESP32-C5](https://www.waveshare.com/wiki/ESP32-C5-WIFI6-KIT-NXRX).

## Command to upload filesystem

The default "Upload Filesystem Image" command does not work if multiple devices are connected. Instead, use:

```pio run --target uploadfs --upload_port COM13```
