#include "gpioparts.h"
#include "board.h"
#include "sensors.h"

#include <math.h>
#include <string.h>
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/pulse_cnt.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"

static const char *TAG = "gpio";

static SemaphoreHandle_t lock;          // state, and the motor outputs
static gpioparts_t state;

void gpioparts_get(gpioparts_t *out) {
    if (!lock) {
        memset(out, 0, sizeof *out);
        return;
    }
    xSemaphoreTake(lock, portMAX_DELAY);
    *out = state;
    xSemaphoreGive(lock);
}

static int64_t now_us(void) { return esp_timer_get_time(); }

// ------------------------------------------------------------------ motor (L298N: IN1, IN2)

#define MOTOR_PWM_HZ        1000        // (as analogWrite in the PlatformIO firmware)
#define MOTOR_PWM_BITS      LEDC_TIMER_10_BIT
#define MOTOR_PWM_MAX       1023
#define POT_CENTER_V        1.65f
#define POT_HALF_RANGE_V    1.65f
#define POT_DEADBAND_V      0.04f

typedef struct {
    uint8_t mode, ccw;
} motor_cfg_t;

static void motor_save(void) {
    motor_cfg_t c = {state.motor_mode, state.motor_ccw};
    nvs_handle_t h;
    if (nvs_open("sensortest", NVS_READWRITE, &h) != ESP_OK) return;
    if (nvs_set_blob(h, "motor", &c, sizeof c) != ESP_OK || nvs_commit(h) != ESP_OK) ESP_LOGW(TAG, "can't save motor");
    nvs_close(h);
}

static void motor_load(void) {
    nvs_handle_t h;
    motor_cfg_t c;
    size_t n = sizeof c;
    if (nvs_open("sensortest", NVS_READONLY, &h) != ESP_OK) return;
    if (nvs_get_blob(h, "motor", &c, &n) == ESP_OK && n == sizeof c && c.mode <= MOTOR_POT) {
        state.motor_mode = c.mode;
        state.motor_ccw = c.ccw;
    }
    nvs_close(h);
}

static void pwm_out(ledc_channel_t ch, uint32_t duty) {
    ledc_set_duty(LEDC_LOW_SPEED_MODE, ch, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, ch);
}

// Caller holds the lock.
static void motor_pins(uint32_t in1, uint32_t in2) {
    pwm_out(LEDC_CHANNEL_0, in1);
    pwm_out(LEDC_CHANNEL_1, in2);
}

// Caller holds the lock. speed -1..1 in "forward" terms.
static void motor_speed(float speed) {
    speed = speed < -1 ? -1 : speed > 1 ? 1 : speed;
    state.speed = speed;
    float physical = state.motor_ccw ? speed : -speed;
    uint32_t duty = (uint32_t)lroundf(fabsf(physical) * MOTOR_PWM_MAX);
    if (physical >= 0) motor_pins(duty, 0);
    else motor_pins(0, duty);
}

// Caller holds the lock.
static void motor_direct(bool in1, bool in2) {
    state.in1 = in1;
    state.in2 = in2;
    state.speed = in1 == in2 ? 0 : (in1 ? 1 : -1) * (state.motor_ccw ? 1 : -1);
    motor_pins(in1 ? MOTOR_PWM_MAX : 0, in2 ? MOTOR_PWM_MAX : 0);
}

// Caller holds the lock: the pot mode's speed from the potentiometer (stop when the MCP3008 doesn't answer).
static void motor_follow_pot(void) {
    sensors_t s;
    sensors_get(&s);
    float centered = s.mcp3008_v[MCP3008_CH_POT] - POT_CENTER_V;
    if (!s.mcp3008_ok || fabsf(centered) < POT_DEADBAND_V) motor_speed(0);
    else motor_speed(centered / POT_HALF_RANGE_V);
}

bool gpioparts_motor_mode(motor_mode_t mode) {
    if (mode > MOTOR_POT) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    state.motor_mode = mode;
    // A new mode starts stopped (pot mode then follows the potentiometer).
    state.in1 = state.in2 = false;
    motor_speed(0);
    motor_save();
    xSemaphoreGive(lock);
    return true;
}

bool gpioparts_motor_ccw(bool ccw) {
    xSemaphoreTake(lock, portMAX_DELAY);
    state.motor_ccw = ccw;
    if (state.motor_mode == MOTOR_API) motor_speed(state.speed * -1);     // (the motor keeps turning the same way)
    motor_save();
    xSemaphoreGive(lock);
    return true;
}

bool gpioparts_motor_direct(bool in1, bool in2) {
    xSemaphoreTake(lock, portMAX_DELAY);
    if (state.motor_mode != MOTOR_DIRECT) {
        state.motor_mode = MOTOR_DIRECT;
        motor_save();
    }
    motor_direct(in1, in2);
    xSemaphoreGive(lock);
    return true;
}

bool gpioparts_motor_speed(float speed) {
    if (!(speed >= -1 && speed <= 1)) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    if (state.motor_mode != MOTOR_API) {
        state.motor_mode = MOTOR_API;
        state.in1 = state.in2 = false;
        motor_save();
    }
    motor_speed(speed);
    xSemaphoreGive(lock);
    return true;
}

void gpioparts_stop(void) {
    if (!lock) return;              // (control can change before gpioparts_start: nothing runs yet then)
    xSemaphoreTake(lock, portMAX_DELAY);
    if (state.motor_mode == MOTOR_DIRECT) motor_direct(false, false);
    else if (state.motor_mode == MOTOR_API) motor_speed(0);
    xSemaphoreGive(lock);
}

static void motor_init(void) {
    ledc_timer_config_t tc = {.speed_mode = LEDC_LOW_SPEED_MODE, .duty_resolution = MOTOR_PWM_BITS,
                              .timer_num = LEDC_TIMER_0, .freq_hz = MOTOR_PWM_HZ, .clk_cfg = LEDC_AUTO_CLK};
    ESP_ERROR_CHECK(ledc_timer_config(&tc));
    const int pins[2] = {PIN_MOTOR_IN1, PIN_MOTOR_IN2};
    for (int i = 0; i < 2; i++) {
        ledc_channel_config_t cc = {.gpio_num = pins[i], .speed_mode = LEDC_LOW_SPEED_MODE, .channel = LEDC_CHANNEL_0 + i,
                                    .timer_sel = LEDC_TIMER_0, .duty = 0};
        ESP_ERROR_CHECK(ledc_channel_config(&cc));
    }
}

// ------------------------------------------------------------------ encoder (PCNT, 4 steps per line)

static pcnt_unit_handle_t enc;

static void encoder_init(void) {
    pcnt_unit_config_t uc = {.low_limit = -32768, .high_limit = 32767, .flags.accum_count = true};
    ESP_ERROR_CHECK(pcnt_new_unit(&uc, &enc));
    pcnt_glitch_filter_config_t fc = {.max_glitch_ns = 1000};
    ESP_ERROR_CHECK(pcnt_unit_set_glitch_filter(enc, &fc));
    pcnt_chan_config_t a = {.edge_gpio_num = PIN_ENC_A, .level_gpio_num = PIN_ENC_B};
    pcnt_chan_config_t b = {.edge_gpio_num = PIN_ENC_B, .level_gpio_num = PIN_ENC_A};
    pcnt_channel_handle_t ca, cb;
    ESP_ERROR_CHECK(pcnt_new_channel(enc, &a, &ca));
    ESP_ERROR_CHECK(pcnt_new_channel(enc, &b, &cb));
    pcnt_channel_set_edge_action(ca, PCNT_CHANNEL_EDGE_ACTION_DECREASE, PCNT_CHANNEL_EDGE_ACTION_INCREASE);
    pcnt_channel_set_level_action(ca, PCNT_CHANNEL_LEVEL_ACTION_KEEP, PCNT_CHANNEL_LEVEL_ACTION_INVERSE);
    pcnt_channel_set_edge_action(cb, PCNT_CHANNEL_EDGE_ACTION_INCREASE, PCNT_CHANNEL_EDGE_ACTION_DECREASE);
    pcnt_channel_set_level_action(cb, PCNT_CHANNEL_LEVEL_ACTION_KEEP, PCNT_CHANNEL_LEVEL_ACTION_INVERSE);
    // (accum_count needs the limits as watch points: the count then carries on past them)
    pcnt_unit_add_watch_point(enc, uc.low_limit);
    pcnt_unit_add_watch_point(enc, uc.high_limit);
    ESP_ERROR_CHECK(pcnt_unit_enable(enc));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(enc));
    ESP_ERROR_CHECK(pcnt_unit_start(enc));
}

void gpioparts_encoder_zero(void) { pcnt_unit_clear_count(enc); }

// ------------------------------------------------------------------ HC-SR04 ultrasonic

#define US_PERIOD_MS        60          // (the datasheet's minimum between measurements)
#define US_MAX_ECHO_US      25000       // ~4.3 m; no obstacle gives a ~38 ms echo

static TaskHandle_t us_task_handle;
static volatile int64_t us_rise;

static void IRAM_ATTR echo_isr(void *arg) {
    int64_t t = esp_timer_get_time();
    if (gpio_get_level(PIN_US_ECHO)) {
        us_rise = t;
    } else if (us_rise) {
        BaseType_t woken = pdFALSE;
        xTaskNotifyFromISR(us_task_handle, (uint32_t)(t - us_rise), eSetValueWithOverwrite, &woken);
        us_rise = 0;
        portYIELD_FROM_ISR(woken);
    }
}

static void us_task(void *arg) {
    int64_t rate_start = now_us();
    int n = 0;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(US_PERIOD_MS));
        xTaskNotifyStateClear(NULL);
        us_rise = 0;
        gpio_set_level(PIN_US_TRIG, 1);
        esp_rom_delay_us(10);
        gpio_set_level(PIN_US_TRIG, 0);
        uint32_t width = 0;
        bool echo = xTaskNotifyWait(0, 0, &width, pdMS_TO_TICKS(50)) == pdTRUE;
        bool ok = echo && width > 0 && width < US_MAX_ECHO_US;
        n += ok;
        xSemaphoreTake(lock, portMAX_DELAY);
        state.us_ok = ok;
        if (ok) state.us_mm = width * 0.343f / 2;
        int64_t now = now_us();
        if (now - rate_start >= 1000000) {
            state.us_hz = n * 1e6f / (now - rate_start);
            n = 0;
            rate_start = now;
        }
        xSemaphoreGive(lock);
    }
}

static void us_init(void) {
    gpio_config_t trig = {.pin_bit_mask = 1ULL << PIN_US_TRIG, .mode = GPIO_MODE_OUTPUT};
    gpio_config(&trig);
    gpio_set_level(PIN_US_TRIG, 0);
    gpio_config_t echo = {.pin_bit_mask = 1ULL << PIN_US_ECHO, .mode = GPIO_MODE_INPUT,
                          .pull_down_en = GPIO_PULLDOWN_ENABLE, .intr_type = GPIO_INTR_ANYEDGE};
    gpio_config(&echo);
    esp_err_t e = gpio_install_isr_service(0);
    if (e != ESP_OK && e != ESP_ERR_INVALID_STATE) ESP_ERROR_CHECK(e);
    xTaskCreate(us_task, "ultrasonic", 2560, NULL, 6, &us_task_handle);
    gpio_isr_handler_add(PIN_US_ECHO, echo_isr, NULL);
}

// ------------------------------------------------------------------ HX711 load cell (channel A, gain 128)
//
// DOUT goes low when a sample is ready; then 24 clock pulses shift it out (MSB first) and a 25th selects channel A,
// gain 128 for the next one. SCK high for more than 60 us powers the HX711 down, hence the short critical section.

#define HX_SCALE            7050.0f     // (from the PlatformIO firmware)
#define HX_TARE_SAMPLES     8
#define HX_TIMEOUT_US       500000

static portMUX_TYPE hx_mux = portMUX_INITIALIZER_UNLOCKED;
static int32_t hx_tare_sum;
static int hx_tare_left = HX_TARE_SAMPLES;
static int32_t hx_tare;

static int32_t hx_read(void) {
    uint32_t v = 0;
    taskENTER_CRITICAL(&hx_mux);
    for (int i = 0; i < 25; i++) {
        gpio_set_level(PIN_HX711_SCK, 1);
        esp_rom_delay_us(1);
        if (i < 24) v = v << 1 | gpio_get_level(PIN_HX711_DOUT);
        gpio_set_level(PIN_HX711_SCK, 0);
        esp_rom_delay_us(1);
    }
    taskEXIT_CRITICAL(&hx_mux);
    return (int32_t)(v << 8) >> 8;      // (24 bits, signed)
}

bool gpioparts_loadcell_tare(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    bool ok = state.hx_ok;
    if (ok) {
        hx_tare_sum = 0;
        hx_tare_left = HX_TARE_SAMPLES;
    }
    xSemaphoreGive(lock);
    return ok;
}

static void hx_init(void) {
    gpio_config_t sck = {.pin_bit_mask = 1ULL << PIN_HX711_SCK, .mode = GPIO_MODE_OUTPUT};
    gpio_config(&sck);
    gpio_set_level(PIN_HX711_SCK, 0);
    // (pull-up: without an HX711, DOUT stays high, "not ready")
    gpio_config_t dout = {.pin_bit_mask = 1ULL << PIN_HX711_DOUT, .mode = GPIO_MODE_INPUT,
                          .pull_up_en = GPIO_PULLUP_ENABLE};
    gpio_config(&dout);
}

// ------------------------------------------------------------------ the task: HX711, pot mode, encoder

static void gpio_task(void *arg) {
    int64_t last_hx = 0, rate_start = now_us();
    int hx_n = 0, tick = 0, enc_last = 0;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(10));     // (one tick at CONFIG_FREERTOS_HZ=100; less would be 0)
        int64_t now = now_us();
        bool sample = gpio_get_level(PIN_HX711_DOUT) == 0;
        int32_t raw = sample ? hx_read() : 0;

        xSemaphoreTake(lock, portMAX_DELAY);
        if (sample) {
            last_hx = now;
            hx_n++;
            state.hx_raw = raw;
            if (hx_tare_left > 0) {
                hx_tare_sum += raw;
                if (--hx_tare_left == 0) hx_tare = hx_tare_sum / HX_TARE_SAMPLES;
            }
            state.hx_units = (raw - hx_tare) / HX_SCALE;
        }
        bool hx_ok = last_hx && now - last_hx < HX_TIMEOUT_US;
        if (hx_ok != state.hx_ok) ESP_LOGI(TAG, "HX711 %s", hx_ok ? "found" : "not answering");
        state.hx_ok = hx_ok;

        if (++tick % 2 == 0) {          // every 20 ms
            if (state.motor_mode == MOTOR_POT) motor_follow_pot();
            int count = 0;
            pcnt_unit_get_count(enc, &count);
            state.enc_count = count;
            state.enc_ab = gpio_get_level(PIN_ENC_A) | gpio_get_level(PIN_ENC_B) << 1;
            if (tick % 100 == 0) {      // every second
                float dt = (now - rate_start) / 1e6f;
                state.enc_steps_s = (count - enc_last) / dt;
                state.hx_hz = hx_n / dt;
                enc_last = count;
                hx_n = 0;
                rate_start = now;
            }
        }
        xSemaphoreGive(lock);
    }
}

void gpioparts_start(void) {
    lock = xSemaphoreCreateMutex();
    state.motor_mode = MOTOR_API;
    state.motor_ccw = true;
    motor_load();
    motor_init();
    encoder_init();
    hx_init();
    us_init();
    xTaskCreate(gpio_task, "gpio", 3072, NULL, 5, NULL);
    ESP_LOGI(TAG, "motor in %s mode", (const char *[]){"direct", "api", "pot"}[state.motor_mode]);
}
