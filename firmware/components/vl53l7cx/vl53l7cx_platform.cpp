/*
 * SensorTestSetup: the VL53L7CX driver's platform functions for ESP-IDF (i2c_master), in place of the STM32duino
 * library's Arduino Wire version. The rest of the driver (vl53l7cx_api.cpp, the plugins) is ST's, unchanged.
 * Registers have 16-bit addresses, MSB first; the sensor increments the address within a transfer.
 */
#include "vl53l7cx_class.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define CHUNK       256         // bytes per transfer (~7 ms at 400 kHz: the other parts on the bus get their turn
                                // in between, also during the ~84 kB firmware upload)
#define TIMEOUT_MS  200

uint8_t VL53L7CX::RdByte(VL53L7CX_Platform *p_platform, uint16_t RegisterAddress, uint8_t *p_value)
{
  return RdMulti(p_platform, RegisterAddress, p_value, 1);
}

uint8_t VL53L7CX::WrByte(VL53L7CX_Platform *p_platform, uint16_t RegisterAddress, uint8_t value)
{
  return WrMulti(p_platform, RegisterAddress, &value, 1);
}

uint8_t VL53L7CX::WrMulti(VL53L7CX_Platform *p_platform, uint16_t RegisterAddress, uint8_t *p_values, uint32_t size)
{
  for (uint32_t i = 0; i < size; i += CHUNK) {
    uint32_t n = size - i > CHUNK ? CHUNK : size - i;
    uint16_t reg = RegisterAddress + i;
    uint8_t addr[2] = {(uint8_t)(reg >> 8), (uint8_t)reg};
    i2c_master_transmit_multi_buffer_info_t bufs[2] = {{addr, 2}, {p_values + i, n}};
    if (i2c_master_multi_buffer_transmit(p_platform->dev, bufs, 2, TIMEOUT_MS) != ESP_OK) return 1;
  }
  return 0;
}

uint8_t VL53L7CX::RdMulti(VL53L7CX_Platform *p_platform, uint16_t RegisterAddress, uint8_t *p_values, uint32_t size)
{
  for (uint32_t i = 0; i < size; i += CHUNK) {
    uint32_t n = size - i > CHUNK ? CHUNK : size - i;
    uint16_t reg = RegisterAddress + i;
    uint8_t addr[2] = {(uint8_t)(reg >> 8), (uint8_t)reg};
    if (i2c_master_transmit_receive(p_platform->dev, addr, 2, p_values + i, n, TIMEOUT_MS) != ESP_OK) return 1;
  }
  return 0;
}

void VL53L7CX::SwapBuffer(uint8_t *buffer, uint16_t size)
{
  for (uint32_t i = 0; i < size; i += 4) {
    uint32_t tmp = (uint32_t)buffer[i] << 24 | (uint32_t)buffer[i + 1] << 16 | (uint32_t)buffer[i + 2] << 8 | buffer[i + 3];
    memcpy(&buffer[i], &tmp, 4);
  }
}

uint8_t VL53L7CX::WaitMs(VL53L7CX_Platform *p_platform, uint32_t TimeMs)
{
  (void)p_platform;
  // (the tick is 10 ms: shorter waits would be no wait at all)
  if (TimeMs < 10) esp_rom_delay_us(TimeMs * 1000);
  else vTaskDelay(pdMS_TO_TICKS(TimeMs));
  return 0;
}
