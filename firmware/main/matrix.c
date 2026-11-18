#include "matrix.h"
#include "board.h"
#include "sensors.h"
#include "i2cbus.h"
#include "gpioparts.h"
#include "tof.h"

#include <math.h>
#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"

static const char *TAG = "matrix";

const char *const MATRIX_IN_NAMES[IN_COUNT] = {"mcp3008", "mcp_a", "mcp_b", "pressure", "ultrasonic", "tof", "loadcell",
                                               "encoder"};
const char *const MATRIX_OUT_NAMES[OUT_COUNT] = {"servo", "motor", "mcp_a", "mcp_b"};

static SemaphoreHandle_t lock;
static matrix_route_t routes[MATRIX_ROUTES];
static matrix_live_t live[MATRIX_ROUTES];
static float last_out[MATRIX_ROUTES];     // what the route last sent (NAN: nothing yet), so unchanged values aren't sent

static void save(void) {
    nvs_handle_t h;
    if (nvs_open("sensortest", NVS_READWRITE, &h) != ESP_OK) return;
    if (nvs_set_blob(h, "matrix", routes, sizeof routes) != ESP_OK || nvs_commit(h) != ESP_OK) ESP_LOGW(TAG, "can't save");
    nvs_close(h);
}

static void load(void) {
    nvs_handle_t h;
    size_t n = sizeof routes;
    if (nvs_open("sensortest", NVS_READONLY, &h) != ESP_OK) return;
    if (nvs_get_blob(h, "matrix", routes, &n) != ESP_OK || n != sizeof routes) memset(routes, 0, sizeof routes);
    nvs_close(h);
    int count = 0;
    for (int i = 0; i < MATRIX_ROUTES; i++) count += routes[i].used;
    ESP_LOGI(TAG, "%d route%s", count, count == 1 ? "" : "s");
}

void matrix_get(matrix_route_t r[MATRIX_ROUTES], matrix_live_t l[MATRIX_ROUTES]) {
    xSemaphoreTake(lock, portMAX_DELAY);
    memcpy(r, routes, sizeof routes);
    memcpy(l, live, sizeof live);
    xSemaphoreGive(lock);
}

static bool valid(const matrix_route_t *r) {
    static const uint8_t in_channels[IN_COUNT] = {8, 8, 8, PRESSURE_SENSORS, 1, TOF_ZONES_MAX + 1, 1, 1};
    static const uint8_t out_channels[OUT_COUNT] = {PWM_CHANNELS, 1, 8, 8};
    return r->in < IN_COUNT && r->in_ch < in_channels[r->in] && r->out < OUT_COUNT && r->out_ch < out_channels[r->out] &&
           isfinite(r->in_min) && isfinite(r->in_max) && r->in_min != r->in_max && r->threshold >= 0 &&
           r->threshold <= 1;
}

int matrix_set(int id, const matrix_route_t *route) {
    if (!valid(route) || id < -1 || id >= MATRIX_ROUTES) return -1;
    xSemaphoreTake(lock, portMAX_DELAY);
    if (id < 0)
        for (int i = 0; i < MATRIX_ROUTES && id < 0; i++)
            if (!routes[i].used) id = i;
    if (id >= 0) {
        routes[id] = *route;
        routes[id].used = true;
        routes[id].name[sizeof routes[id].name - 1] = 0;
        last_out[id] = NAN;
        save();
    }
    xSemaphoreGive(lock);
    return id;
}

bool matrix_delete(int id) {
    if (id < 0 || id >= MATRIX_ROUTES) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    bool ok = routes[id].used;
    memset(&routes[id], 0, sizeof routes[id]);
    memset(&live[id], 0, sizeof live[id]);
    if (ok) save();
    xSemaphoreGive(lock);
    return ok;
}

void matrix_clear(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    memset(routes, 0, sizeof routes);
    memset(live, 0, sizeof live);
    save();
    xSemaphoreGive(lock);
}

typedef struct {
    sensors_t s;
    i2cbus_t b;
    gpioparts_t g;
    tof_t t;
} inputs_t;

// The input in its own unit; false when its part doesn't answer.
static bool read_input(const matrix_route_t *r, const inputs_t *x, float *out) {
    switch (r->in) {
    case IN_MCP3008:
        *out = x->s.mcp3008_v[r->in_ch];
        return x->s.mcp3008_ok;
    case IN_MCP_A:
    case IN_MCP_B:
        *out = (r->in == IN_MCP_A ? x->b.gpio_a : x->b.gpio_b) >> r->in_ch & 1;
        return x->b.mcp_ok;
    case IN_PRESSURE:
        *out = x->b.pressure_bar[r->in_ch];
        return x->b.pressure_ok[r->in_ch];
    case IN_ULTRASONIC:
        *out = x->g.us_mm;
        return x->g.us_ok;
    case IN_TOF: {
        if (!x->t.ok) return false;
        int zones = x->t.side * x->t.side, best = -1;
        for (int z = 0; z < zones; z++) {
            bool ok = x->t.targets[z] && (x->t.status[z] == 5 || x->t.status[z] == 9);
            if (r->in_ch < TOF_ZONES_MAX ? z == r->in_ch && ok : ok && (best < 0 ||
                                                                         x->t.distance_mm[z] < x->t.distance_mm[best]))
                best = z;
        }
        if (best < 0) return false;
        *out = x->t.distance_mm[best];
        return true;
    }
    case IN_LOADCELL:
        *out = x->g.hx_units;
        return x->g.hx_ok;
    case IN_ENCODER:
        *out = x->g.enc_count;
        return true;
    default:
        return false;
    }
}

static void drive(int i, const matrix_route_t *r, float v, const inputs_t *x) {
    switch (r->out) {
    case OUT_SERVO:
        if (isnan(last_out[i]) || fabsf(v - last_out[i]) >= 0.002f) {
            if (i2cbus_pwm_set_value(r->out_ch, v)) last_out[i] = v;
        }
        break;
    case OUT_MOTOR:
        if (x->g.motor_mode == MOTOR_API && (isnan(last_out[i]) || fabsf(v - last_out[i]) >= 0.002f ||
                                             fabsf(x->g.speed - (v * 2 - 1)) > 0.01f)) {
            if (gpioparts_motor_speed(v * 2 - 1)) last_out[i] = v;
        }
        break;
    case OUT_MCP_A:
    case OUT_MCP_B: {
        bool level = v >= r->threshold;
        uint8_t now = (r->out == OUT_MCP_A ? x->b.mcp.out_a : x->b.mcp.out_b) >> r->out_ch & 1;
        if (now != level) i2cbus_mcp_output(r->out == OUT_MCP_B, r->out_ch, level);
        break;
    }
    }
}

static void matrix_task(void *arg) {
    static inputs_t x;
    static matrix_route_t r[MATRIX_ROUTES];
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(20));
        xSemaphoreTake(lock, portMAX_DELAY);
        memcpy(r, routes, sizeof routes);
        xSemaphoreGive(lock);
        bool any = false;
        for (int i = 0; i < MATRIX_ROUTES; i++) any |= r[i].used;      // (disabled ones still show their input)
        if (!any) continue;
        sensors_get(&x.s);
        i2cbus_get(&x.b);
        gpioparts_get(&x.g);
        tof_get(&x.t);
        for (int i = 0; i < MATRIX_ROUTES; i++) {
            if (!r[i].used) continue;
            float raw = 0;
            bool ok = read_input(&r[i], &x, &raw);
            float v = (raw - r[i].in_min) / (r[i].in_max - r[i].in_min);
            v = v < 0 ? 0 : v > 1 ? 1 : v;
            if (r[i].invert) v = 1 - v;
            if (ok && r[i].enabled) drive(i, &r[i], v, &x);
            xSemaphoreTake(lock, portMAX_DELAY);
            if (routes[i].used) live[i] = (matrix_live_t){ok, raw, v};
            xSemaphoreGive(lock);
        }
    }
}

void matrix_start(void) {
    lock = xSemaphoreCreateMutex();
    for (int i = 0; i < MATRIX_ROUTES; i++) last_out[i] = NAN;
    load();
    xTaskCreate(matrix_task, "matrix", 4096, NULL, 3, NULL);
}
