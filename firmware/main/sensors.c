#include "sensors.h"
#include "board.h"

#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "sensors";

#define SAMPLE_PERIOD_MS 20

static spi_device_handle_t mcp3008;
static sensors_t latest;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;

// Single-ended conversion of one channel. The chip clocks out a null bit before the 10 data bits; with MISO pulled up,
// a missing chip reads it as 1.
static bool mcp3008_read(int ch, uint16_t *raw) {
    spi_transaction_t t = {.length = 24, .flags = SPI_TRANS_USE_TXDATA | SPI_TRANS_USE_RXDATA,
                           .tx_data = {0x01, (uint8_t)(0x80 | ch << 4), 0x00}};
    if (spi_device_polling_transmit(mcp3008, &t) != ESP_OK) return false;
    *raw = (uint16_t)((t.rx_data[1] & 0x03) << 8 | t.rx_data[2]);
    return (t.rx_data[1] & 0x04) == 0;
}

static void sensors_task(void *arg) {
    TickType_t wake = xTaskGetTickCount();
    int64_t rate_start = esp_timer_get_time();
    int rate_count = 0;
    float rate_hz = 0;
    bool was_ok = true;
    for (;;) {
        sensors_t s = {.t_us = esp_timer_get_time()};
        bool ok = true;
        for (int ch = 0; ch < 8; ch++) {
            uint16_t raw = 0;
            ok &= mcp3008_read(ch, &raw);
            s.mcp3008_v[ch] = raw * MCP3008_VREF / 1023.0f;
        }
        s.mcp3008_ok = ok;
        if (ok != was_ok) ESP_LOGW(TAG, "MCP3008 %s", ok ? "found" : "not answering");
        was_ok = ok;

        rate_count++;
        if (s.t_us - rate_start >= 1000000) {
            rate_hz = rate_count * 1e6f / (s.t_us - rate_start);
            rate_start = s.t_us;
            rate_count = 0;
        }
        s.rate_hz = rate_hz;

        portENTER_CRITICAL(&lock);
        latest = s;
        portEXIT_CRITICAL(&lock);
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
    }
}

void sensors_start(spi_host_device_t host) {
    spi_device_interface_config_t dc = {.clock_speed_hz = 1000000, .mode = 0, .spics_io_num = PIN_MCP3008_CS,
                                        .queue_size = 1};
    if (spi_bus_add_device(host, &dc, &mcp3008) != ESP_OK) {
        ESP_LOGE(TAG, "MCP3008: can't add SPI device");
        return;
    }
    xTaskCreate(sensors_task, "sensors", 3072, NULL, 5, NULL);
}

void sensors_get(sensors_t *out) {
    portENTER_CRITICAL(&lock);
    *out = latest;
    portEXIT_CRITICAL(&lock);
}
