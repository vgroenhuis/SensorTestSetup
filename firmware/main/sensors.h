// Sensor readings, sampled in their own task; everyone else (web, display, reports) reads the latest snapshot.
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "driver/spi_master.h"

typedef struct {
    bool mcp3008_ok;            // the MCP3008 answers (its null bit reads 0)
    float mcp3008_v[8];         // volts, 0..MCP3008_VREF
    float rate_hz;              // samples per second actually achieved
    int64_t t_us;               // when sampled (esp_timer)
} sensors_t;

void sensors_start(spi_host_device_t host);
void sensors_get(sensors_t *out);
