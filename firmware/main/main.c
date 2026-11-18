// SensorTestSetup: a permanent desk setup of sensors and actuators around an ESP32-C5, shown on the CloSer lab demos
// page. Every part runs in its own task and is optional: one that isn't connected (or breaks) shows as absent, and the
// rest carries on.
#include "board.h"
#include "display.h"
#include "sensors.h"
#include "i2cbus.h"
#include "gpioparts.h"
#include "tof.h"
#include "matrix.h"
#include "web.h"
#include "closer_access.h"
#include "closer_demo.h"

#include <stdio.h>
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "main";

#define SPI_HOST_ID SPI2_HOST

static void display_footer(char *out, size_t len) {
    sensors_t s;
    sensors_get(&s);
    if (!s.mcp3008_ok) snprintf(out, len, "MCP3008 not found");
    else snprintf(out, len, "Pot %.2f V   MH %.2f V", s.mcp3008_v[MCP3008_CH_POT], s.mcp3008_v[MCP3008_CH_MH]);
}

// Control moved (released, timed out, or taken by someone else): the motor stops (unless it follows the pot).
static void on_control_change(int from, int to) {
    gpioparts_stop();
}

static void stats_task(void *arg) {
    for (;;) {
        sensors_t s;
        sensors_get(&s);
        closer_demo_set_clients(web_clients());
        closer_demo_set_stat("mcp3008_ok", s.mcp3008_ok);
        if (s.mcp3008_ok) {
            closer_demo_set_stat("pot_v", s.mcp3008_v[MCP3008_CH_POT]);
            closer_demo_set_stat("mh_v", s.mcp3008_v[MCP3008_CH_MH]);
        }
        closer_demo_set_stat("sample_hz", s.rate_hz);
        i2cbus_t b;
        i2cbus_get(&b);
        closer_demo_set_stat("mcp23017_ok", b.mcp_ok);
        closer_demo_set_stat("pca9685_ok", b.pca_ok);
        // (closer_demo keeps 16 numbers, 4 of them its own: a sensor that's absent just doesn't update its own.)
        if (b.pressure_ok[0]) closer_demo_set_stat("pressure0_bar", b.pressure_bar[0]);
        if (b.pressure_ok[1]) closer_demo_set_stat("pressure1_bar", b.pressure_bar[1]);
        gpioparts_t g;
        gpioparts_get(&g);
        if (g.us_ok) closer_demo_set_stat("distance_mm", g.us_mm);
        closer_demo_set_stat("hx711_ok", g.hx_ok);
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}

static void spi_start(void) {
    spi_bus_config_t bc = {.sclk_io_num = PIN_SPI_SCLK, .mosi_io_num = PIN_SPI_MOSI, .miso_io_num = PIN_SPI_MISO,
                           .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = 256};
    // DMA: without it a transaction is at most 64 bytes, and an OLED page is 128.
    ESP_ERROR_CHECK(spi_bus_initialize(SPI_HOST_ID, &bc, SPI_DMA_CH_AUTO));
    gpio_pullup_en(PIN_SPI_MISO);       // (a missing MCP3008 then reads its null bit as 1: see sensors.c)
}

void app_main(void) {
    closer_demo_start(NULL);            // (named after its key: sensortest, ...) also initialises NVS
    static char control_page[64];       // (the QR code link; the site sends it on to the demo's page)
    snprintf(control_page, sizeof control_page, "q/%s", closer_demo_name());
    closer_access_init(control_page, on_control_change);
    closer_access_set_digits(4);        // (shown on the OLED, for whoever sits at the desk)
    spi_start();
    display_start(SPI_HOST_ID, display_footer);
    sensors_start(SPI_HOST_ID);
    i2cbus_start();
    gpioparts_start();
    tof_start();
    matrix_start();
    web_start();
    xTaskCreate(stats_task, "stats", 3072, NULL, 2, NULL);
    ESP_LOGI(TAG, "SensorTest running, firmware %s", closer_demo_version());
}
