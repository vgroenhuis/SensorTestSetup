// The 128x64 SSD1306 OLED on SPI: Wi-Fi state and address, the access code when someone asks for control, firmware
// updates, and a footer line the app fills in (live readings).
#pragma once
#include <stddef.h>
#include "driver/spi_master.h"

typedef void (*display_footer_fn)(char *out, size_t len);

void display_start(spi_host_device_t host, display_footer_fn footer);
