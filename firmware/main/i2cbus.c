#include "i2cbus.h"
#include "board.h"

#include <math.h>
#include <string.h>
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"

static const char *TAG = "i2c";

#define ADDR_MCP23017       0x20
#define ADDR_PCA9685        0x40
#define ADDR_TCA9548        0x70
#define ADDR_WF100DPZ       0x6D
#define TIMEOUT_MS          20
#define PERIOD_MS           20          // the input loop
#define RETRY_MS            1000        // looking again for an absent part, and checking a present one's settings

#define PCA_OSC_HZ          25000000.0f
#define PCA_OFF             (-1)        // pwm ticks: always off
#define PCA_ON              4096        //            always on

static i2c_master_bus_handle_t bus;
static i2c_master_dev_handle_t mcp_dev, pca_dev, tca_dev, wf_dev;
static SemaphoreHandle_t lock;          // the bus and everything below
static portMUX_TYPE snap_mux = portMUX_INITIALIZER_UNLOCKED;
static i2cbus_t state, snap;            // state: under lock; snap: the copy i2cbus_get hands out
static int16_t pwm_ticks[PWM_CHANNELS]; // what the PCA9685 is to output (PCA_OFF, 0..4095, PCA_ON)
static float pressure_offset[PRESSURE_SENSORS];

static void publish(void) {
    taskENTER_CRITICAL(&snap_mux);
    snap = state;
    taskEXIT_CRITICAL(&snap_mux);
}

void i2cbus_get(i2cbus_t *out) {
    taskENTER_CRITICAL(&snap_mux);
    *out = snap;
    taskEXIT_CRITICAL(&snap_mux);
}

static int64_t now_ms(void) { return esp_timer_get_time() / 1000; }

// ------------------------------------------------------------------ register access

static bool wr(i2c_master_dev_handle_t d, const uint8_t *b, size_t n) {
    return i2c_master_transmit(d, b, n, TIMEOUT_MS) == ESP_OK;
}
static bool wr1(i2c_master_dev_handle_t d, uint8_t reg, uint8_t v) {
    uint8_t b[2] = {reg, v};
    return wr(d, b, 2);
}
static bool rd(i2c_master_dev_handle_t d, uint8_t reg, uint8_t *out, size_t n) {
    return i2c_master_transmit_receive(d, &reg, 1, out, n, TIMEOUT_MS) == ESP_OK;
}
static bool present(uint8_t addr) { return i2c_master_probe(bus, addr, TIMEOUT_MS) == ESP_OK; }

// ------------------------------------------------------------------ settings in NVS

static void nvs_load(const char *key, void *v, size_t n) {
    nvs_handle_t h;
    if (nvs_open("sensortest", NVS_READONLY, &h) != ESP_OK) return;
    size_t len = n;
    uint8_t tmp[sizeof(pwm_channel_cfg_t) * PWM_CHANNELS];
    if (n <= sizeof tmp && nvs_get_blob(h, key, tmp, &len) == ESP_OK && len == n) memcpy(v, tmp, n);
    nvs_close(h);
}

static void nvs_save(const char *key, const void *v, size_t n) {
    nvs_handle_t h;
    if (nvs_open("sensortest", NVS_READWRITE, &h) != ESP_OK) return;
    if (nvs_set_blob(h, key, v, n) != ESP_OK || nvs_commit(h) != ESP_OK) ESP_LOGW(TAG, "can't save %s", key);
    nvs_close(h);
}

// ------------------------------------------------------------------ MCP23017 (register bank 0: A and B side by side)

#define MCP_IODIRA  0x00
#define MCP_GPPUA   0x0C
#define MCP_GPIOA   0x12
#define MCP_OLATA   0x14

static bool mcp_apply(void) {
    const mcp23017_cfg_t *c = &state.mcp;
    // The output levels first, so a pin that becomes an output starts at its level.
    uint8_t olat[3] = {MCP_OLATA, c->out_a, c->out_b}, gppu[3] = {MCP_GPPUA, c->pullup_a, c->pullup_b},
            iodir[3] = {MCP_IODIRA, c->mode_a, c->mode_b};
    return wr(mcp_dev, olat, 3) && wr(mcp_dev, gppu, 3) && wr(mcp_dev, iodir, 3);
}

// Present and holding our settings (a power glitch resets it to all inputs without the bus noticing).
static void mcp_check(void) {
    uint8_t iodir[2];
    bool ok = state.mcp_ok && rd(mcp_dev, MCP_IODIRA, iodir, 2) && iodir[0] == state.mcp.mode_a &&
              iodir[1] == state.mcp.mode_b;
    if (ok) return;
    bool was = state.mcp_ok;
    state.mcp_ok = present(ADDR_MCP23017) && mcp_apply();
    if (state.mcp_ok != was || state.mcp_ok) ESP_LOGI(TAG, "MCP23017 %s", state.mcp_ok ? "set up" : "not found");
}

bool i2cbus_mcp_set(const mcp23017_cfg_t *cfg) {
    xSemaphoreTake(lock, portMAX_DELAY);
    bool ok = state.mcp_ok;
    if (ok) {
        state.mcp = *cfg;
        ok = state.mcp_ok = mcp_apply();
        nvs_save("mcp", &state.mcp, sizeof state.mcp);
        publish();
    }
    xSemaphoreGive(lock);
    return ok;
}

// ------------------------------------------------------------------ PCA9685

#define PCA_MODE1       0x00
#define PCA_MODE2       0x01
#define PCA_LED0        0x06
#define PCA_PRESCALE    0xFE
#define PCA_MODE1_AI    0x20        // register auto-increment
#define PCA_MODE1_SLEEP 0x10
#define PCA_MODE1_RESTART 0x80

static bool pca_write_channel(int ch) {
    int t = pwm_ticks[ch];
    uint8_t b[5] = {PCA_LED0 + 4 * ch, 0, 0, 0, 0};
    if (t == PCA_OFF) b[4] = 0x10;                  // full off
    else if (t == PCA_ON) b[2] = 0x10;              // full on
    else { b[3] = t & 0xFF; b[4] = t >> 8; }        // on at 0, off at t
    return wr(pca_dev, b, 5);
}

static uint8_t pca_prescale(float hz) {
    float p = roundf(PCA_OSC_HZ / (4096.0f * hz)) - 1;
    return p < 3 ? 3 : p > 255 ? 255 : (uint8_t)p;
}

// The frequency (and the rest of the set-up), then every channel.
static bool pca_apply(void) {
    bool ok = wr1(pca_dev, PCA_MODE1, PCA_MODE1_AI | PCA_MODE1_SLEEP) &&      // (the prescaler only takes in sleep)
              wr1(pca_dev, PCA_PRESCALE, pca_prescale(state.pwm_hz)) &&
              wr1(pca_dev, PCA_MODE2, 0x04) &&                                // totem-pole outputs
              wr1(pca_dev, PCA_MODE1, PCA_MODE1_AI);
    if (!ok) return false;
    esp_rom_delay_us(500);                                                    // the oscillator starting
    ok = wr1(pca_dev, PCA_MODE1, PCA_MODE1_AI | PCA_MODE1_RESTART);
    for (int ch = 0; ch < PWM_CHANNELS && ok; ch++) ok = pca_write_channel(ch);
    return ok;
}

static void pca_check(void) {
    uint8_t m;
    // After a reset MODE1 is 0x11 (asleep, no auto-increment): set it up again.
    if (state.pca_ok && rd(pca_dev, PCA_MODE1, &m, 1) && (m & (PCA_MODE1_AI | PCA_MODE1_SLEEP)) == PCA_MODE1_AI) return;
    bool was = state.pca_ok;
    state.pca_ok = present(ADDR_PCA9685) && pca_apply();
    if (state.pca_ok != was || state.pca_ok) ESP_LOGI(TAG, "PCA9685 %s", state.pca_ok ? "set up" : "not found");
}

static float pca_real_hz(float hz) { return PCA_OSC_HZ / (4096.0f * (pca_prescale(hz) + 1)); }

static int us_to_ticks(int us) {
    float t = us * state.pwm_hz * 4096.0f / 1e6f;
    return t < 0 ? 0 : t > 4095 ? 4095 : (int)(t + 0.5f);
}

// Caller holds the lock; ch checked. us >= 0: a servo pulse; else duty 0..1.
static bool pwm_output(int ch, int us, float duty) {
    if (!state.pca_ok) return false;
    if (us >= 0) {
        pwm_ticks[ch] = us_to_ticks(us);
        duty = us * state.pwm_hz / 1e6f;
    } else {
        pwm_ticks[ch] = duty <= 0 ? PCA_OFF : duty >= 1 ? PCA_ON : (int)(duty * 4096 + 0.5f);
    }
    state.pwm_us[ch] = us;
    state.pwm_duty[ch] = duty;
    state.pca_ok = pca_write_channel(ch);
    publish();
    return state.pca_ok;
}

static bool ch_ok(int ch) { return ch >= 0 && ch < PWM_CHANNELS; }

bool i2cbus_pwm_set_us(int ch, int us) {
    if (!ch_ok(ch) || us < 100 || us > 5000) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    bool ok = pwm_output(ch, us, 0);
    xSemaphoreGive(lock);
    return ok;
}

bool i2cbus_pwm_set_value(int ch, float v) {
    if (!ch_ok(ch) || !(v >= 0 && v <= 1)) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    const pwm_channel_cfg_t *c = &state.pwm[ch];
    bool ok = c->mode == PWM_SERVO ? pwm_output(ch, c->min_us + (int)lroundf((c->max_us - c->min_us) * v), 0)
                                   : pwm_output(ch, -1, v);
    xSemaphoreGive(lock);
    return ok;
}

bool i2cbus_pwm_off(int ch) {
    if (!ch_ok(ch)) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    bool ok = pwm_output(ch, -1, 0);
    state.pwm_duty[ch] = -1;
    publish();
    xSemaphoreGive(lock);
    return ok;
}

bool i2cbus_pwm_set_cfg(int ch, const pwm_channel_cfg_t *cfg) {
    if (!ch_ok(ch) || (cfg->mode != PWM_SERVO && cfg->mode != PWM_RAW) ||
        (cfg->mode == PWM_SERVO && !(cfg->min_us >= 100 && cfg->min_us < cfg->max_us && cfg->max_us <= 5000)))
        return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    state.pwm[ch] = *cfg;
    nvs_save("pwm_cfg", state.pwm, sizeof state.pwm);
    publish();
    xSemaphoreGive(lock);
    return true;
}

bool i2cbus_pwm_set_hz(float hz) {
    if (!(hz >= 24 && hz <= 1500)) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    state.pwm_hz = pca_real_hz(hz);
    // Servo pulses keep their length; a duty cycle stays the same fraction.
    for (int ch = 0; ch < PWM_CHANNELS; ch++) {
        if (state.pwm_us[ch] >= 0) {
            pwm_ticks[ch] = us_to_ticks(state.pwm_us[ch]);
            state.pwm_duty[ch] = state.pwm_us[ch] * state.pwm_hz / 1e6f;
        }
    }
    nvs_save("pwm_hz", &state.pwm_hz, sizeof state.pwm_hz);
    bool ok = state.pca_ok && (state.pca_ok = pca_apply());
    publish();
    xSemaphoreGive(lock);
    return ok;
}

// ------------------------------------------------------------------ TCA9548 + WF100DPZ pressure sensors
//
// WF100DPZ10BG: 0x30 <- 0x0A starts a temperature conversion and then a pressure conversion; status 0x02 bit 0 is set
// when done; 0x06..0x08 is the pressure, 24 bits signed, MSB first. Scale from the PlatformIO firmware.

typedef struct {
    bool started;
    int64_t started_ms, retry_ms;
} wf_t;
static wf_t wf[PRESSURE_SENSORS];

static bool tca_select(int ch) { uint8_t b = 1 << ch; return wr(tca_dev, &b, 1); }

static float wf_bar(const uint8_t r[3]) {
    int32_t raw = (int32_t)((uint32_t)r[0] << 16 | r[1] << 8 | r[2]);
    if (raw & 0x800000) raw -= 0x1000000;
    return (raw / 8388608.0f + 0.731f) * 10.0f;
}

static bool wf_start(int i) {
    bool ok = wr1(wf_dev, 0x30, 0x0A);
    wf[i].started = ok;
    wf[i].started_ms = now_ms();
    return ok;
}

// One step for sensor i: a finished conversion is read and the next one started. Caller holds the lock.
static bool wf_step(int i, int64_t now) {
    if (!state.pressure_ok[i]) {
        if (now < wf[i].retry_ms) return false;
        wf[i].retry_ms = now + RETRY_MS;
        if (!tca_select(i)) return state.tca_ok = false;
        if (!present(ADDR_WF100DPZ) || !wf_start(i)) return false;
        ESP_LOGI(TAG, "pressure sensor %d found", i);
        state.pressure_ok[i] = true;
        return false;
    }
    if (!tca_select(i)) return state.tca_ok = false;
    uint8_t st, r[3];
    bool ok = rd(wf_dev, 0x02, &st, 1);
    if (ok && (st & 1)) {
        ok = rd(wf_dev, 0x06, r, 3);
        if (ok) state.pressure_bar[i] = wf_bar(r) + pressure_offset[i];
        ok = ok && wf_start(i);
        if (ok) return true;
    } else if (ok && now - wf[i].started_ms > 200) {
        ok = wf_start(i);                              // (lost its command: start again)
    }
    if (!ok) {
        ESP_LOGW(TAG, "pressure sensor %d stopped answering", i);
        state.pressure_ok[i] = false;
        wf[i].retry_ms = now + RETRY_MS;
    }
    return false;
}

bool i2cbus_pressure_zero(int i) {
    if (i < 0 || i >= PRESSURE_SENSORS) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    bool ok = state.pressure_ok[i];
    if (ok) {
        pressure_offset[i] -= state.pressure_bar[i];
        state.pressure_bar[i] = 0;
        nvs_save("p_offset", pressure_offset, sizeof pressure_offset);
        publish();
    }
    xSemaphoreGive(lock);
    return ok;
}

// ------------------------------------------------------------------ the task

static void i2c_task(void *arg) {
    int64_t next_check = 0, rate_start = now_ms();
    int readings = 0;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(PERIOD_MS));
        xSemaphoreTake(lock, portMAX_DELAY);
        int64_t now = now_ms();
        if (now >= next_check) {
            next_check = now + RETRY_MS;
            mcp_check();
            pca_check();
            if (!state.tca_ok) {
                state.tca_ok = present(ADDR_TCA9548);
                if (state.tca_ok) ESP_LOGI(TAG, "TCA9548 found");
            }
        }
        if (state.mcp_ok) {
            uint8_t g[2];
            if (rd(mcp_dev, MCP_GPIOA, g, 2)) {
                state.gpio_a = g[0];
                state.gpio_b = g[1];
            } else {
                ESP_LOGW(TAG, "MCP23017 stopped answering");
                state.mcp_ok = false;
            }
        }
        bool was_tca = state.tca_ok;
        for (int i = 0; i < PRESSURE_SENSORS && state.tca_ok; i++) readings += wf_step(i, now);
        if (!state.tca_ok) {
            if (was_tca) ESP_LOGW(TAG, "TCA9548 stopped answering");
            for (int i = 0; i < PRESSURE_SENSORS; i++) state.pressure_ok[i] = false;
        }
        if (now - rate_start >= 1000) {
            state.pressure_hz = readings * 1000.0f / (now - rate_start) / PRESSURE_SENSORS;
            readings = 0;
            rate_start = now;
        }
        publish();
        xSemaphoreGive(lock);
    }
}

static i2c_master_dev_handle_t add(uint8_t addr) {
    i2c_device_config_t dc = {.dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = addr, .scl_speed_hz = 400000};
    i2c_master_dev_handle_t d = NULL;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &dc, &d));
    return d;
}

void i2cbus_start(void) {
    lock = xSemaphoreCreateMutex();
    i2c_master_bus_config_t bc = {.i2c_port = -1, .sda_io_num = PIN_I2C_SDA, .scl_io_num = PIN_I2C_SCL,
                                  .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7,
                                  .flags.enable_internal_pullup = true};
    ESP_ERROR_CHECK(i2c_new_master_bus(&bc, &bus));
    mcp_dev = add(ADDR_MCP23017);
    pca_dev = add(ADDR_PCA9685);
    tca_dev = add(ADDR_TCA9548);
    wf_dev = add(ADDR_WF100DPZ);

    // Defaults (as the PlatformIO firmware): bank A outputs with A0 and A1 high, bank B inputs with pull-ups; every
    // PWM channel a servo of 500..2500 us at 50 Hz, off until set.
    state.mcp = (mcp23017_cfg_t){.mode_a = 0x00, .pullup_a = 0x00, .mode_b = 0xFF, .pullup_b = 0xFF, .out_a = 0x03};
    state.pwm_hz = 50;
    for (int ch = 0; ch < PWM_CHANNELS; ch++) {
        state.pwm[ch] = (pwm_channel_cfg_t){PWM_SERVO, 500, 2500};
        state.pwm_us[ch] = -1;
        state.pwm_duty[ch] = -1;
        pwm_ticks[ch] = PCA_OFF;
    }
    nvs_load("mcp", &state.mcp, sizeof state.mcp);
    nvs_load("pwm_hz", &state.pwm_hz, sizeof state.pwm_hz);
    nvs_load("pwm_cfg", state.pwm, sizeof state.pwm);
    nvs_load("p_offset", pressure_offset, sizeof pressure_offset);
    if (!(state.pwm_hz >= 24 && state.pwm_hz <= 1500)) state.pwm_hz = 50;
    state.pwm_hz = pca_real_hz(state.pwm_hz);
    publish();
    xTaskCreate(i2c_task, "i2c", 3584, NULL, 5, NULL);
}
