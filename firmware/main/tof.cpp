#include "tof.h"
extern "C" {
#include "i2cbus.h"
}
#include "vl53l7cx_class.h"

#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"

static const char *TAG = "tof";

#define ADDR_VL53L7CX       0x29
#define RETRY_MS            5000        // looking again for a sensor that isn't there
#define STALE_MS            2000        // no frame for this long while ranging: start it again

typedef struct {
    uint8_t side, filter;
    uint16_t max_mm;
} tof_cfg_t;

static SemaphoreHandle_t lock;
static tof_t state;
static tof_cfg_t cfg = {8, 1, 350};     // (as the PlatformIO firmware: 8x8, filter on at 350 mm)
static bool side_changed;
static VL53L7CX *sensor;
static VL53L7CX_ResultsData results;

static int64_t now_ms(void) { return esp_timer_get_time() / 1000; }

void tof_get(tof_t *out) {
    if (!lock) {
        memset(out, 0, sizeof *out);
        return;
    }
    xSemaphoreTake(lock, portMAX_DELAY);
    *out = state;
    xSemaphoreGive(lock);
}

static void save(void) {
    nvs_handle_t h;
    if (nvs_open("sensortest", NVS_READWRITE, &h) != ESP_OK) return;
    if (nvs_set_blob(h, "tof", &cfg, sizeof cfg) != ESP_OK || nvs_commit(h) != ESP_OK) ESP_LOGW(TAG, "can't save");
    nvs_close(h);
}

static void load(void) {
    nvs_handle_t h;
    tof_cfg_t c;
    size_t n = sizeof c;
    if (nvs_open("sensortest", NVS_READONLY, &h) != ESP_OK) return;
    if (nvs_get_blob(h, "tof", &c, &n) == ESP_OK && n == sizeof c && (c.side == 4 || c.side == 8)) cfg = c;
    nvs_close(h);
}

bool tof_set_resolution(int side) {
    if (side != 4 && side != 8) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    if (cfg.side != side) {
        cfg.side = side;
        side_changed = true;
        save();
    }
    xSemaphoreGive(lock);
    return true;
}

bool tof_set_filter(bool enabled, int max_mm) {
    if (max_mm < 20 || max_mm > 4000) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    cfg.filter = enabled;
    cfg.max_mm = max_mm;
    state.filter = enabled;
    state.max_mm = max_mm;
    save();
    xSemaphoreGive(lock);
    return true;
}

static uint8_t resolution(int side) { return side == 8 ? VL53L7CX_RESOLUTION_8X8 : VL53L7CX_RESOLUTION_4X4; }
static uint8_t frequency(int side) { return side == 8 ? 15 : 60; }

// Resolution, frequency and continuous mode, then ranging. (The frequency is limited by the resolution, so the
// resolution goes first.)
static bool configure(int side) {
    return sensor->vl53l7cx_set_resolution(resolution(side)) == VL53L7CX_STATUS_OK &&
           sensor->vl53l7cx_set_ranging_frequency_hz(frequency(side)) == VL53L7CX_STATUS_OK &&
           sensor->vl53l7cx_set_ranging_mode(VL53L7CX_RANGING_MODE_CONTINUOUS) == VL53L7CX_STATUS_OK &&
           sensor->vl53l7cx_start_ranging() == VL53L7CX_STATUS_OK;
}

static bool start(int side) {
    if (i2c_master_probe(i2cbus_bus(), ADDR_VL53L7CX, 20) != ESP_OK) return false;
    ESP_LOGI(TAG, "VL53L7CX found: loading its firmware");
    int64_t t = now_ms();
    if (sensor->init_sensor() != VL53L7CX_STATUS_OK) {
        ESP_LOGW(TAG, "init failed");
        return false;
    }
    if (!configure(side)) {
        ESP_LOGW(TAG, "configuring failed");
        return false;
    }
    ESP_LOGI(TAG, "ranging at %dx%d (start-up %lld ms)", side, side, now_ms() - t);
    return true;
}

// Caller holds the lock: the frame into the snapshot, with the filter applied.
static void take_frame(int side) {
    int zones = side * side;
    state.side = side;
    for (int z = 0; z < zones; z++) {
        int i = z * VL53L7CX_NB_TARGET_PER_ZONE;
        int16_t d = results.distance_mm[i];
        uint8_t s = results.target_status[i];
        uint8_t n = results.nb_target_detected[z];
        if (n && (s == 5 || s == 9)) {
            if (d <= 0) s = TOF_STATUS_NON_POSITIVE;
            else if (cfg.filter && d > cfg.max_mm) s = TOF_STATUS_TOO_FAR;
        }
        state.distance_mm[z] = d;
        state.status[z] = s;
        state.targets[z] = n;
    }
    state.frames++;
}

static void tof_task(void *arg) {
    bool running = false, said_absent = false;
    int side = 0;
    int64_t retry = 0, last_frame = 0, rate_start = now_ms();
    uint32_t rate_frames = 0;
    for (;;) {
        vTaskDelay(1);          // (10 ms; a frame comes every 17 ms at 60 Hz)
        int64_t now = now_ms();

        xSemaphoreTake(lock, portMAX_DELAY);
        int want = cfg.side;
        bool change = side_changed;
        side_changed = false;
        xSemaphoreGive(lock);

        if (!running) {
            if (now < retry) continue;
            retry = now + RETRY_MS;
            running = start(want);
            if (!running && !said_absent) ESP_LOGI(TAG, "no VL53L7CX (looking again every %d s)", RETRY_MS / 1000);
            said_absent = !running;
            side = want;
            last_frame = now_ms();
            continue;
        }

        if (change && want != side) {
            bool ok = sensor->vl53l7cx_stop_ranging() == VL53L7CX_STATUS_OK && configure(want);
            ESP_LOGI(TAG, "resolution %dx%d%s", want, want, ok ? "" : ": failed, starting again");
            side = want;
            running = ok;
            last_frame = now;
            if (!ok) continue;
        }

        uint8_t ready = 0;
        if (sensor->vl53l7cx_check_data_ready(&ready) == VL53L7CX_STATUS_OK && ready &&
            sensor->vl53l7cx_get_ranging_data(&results) == VL53L7CX_STATUS_OK) {
            last_frame = now;
            rate_frames++;
            xSemaphoreTake(lock, portMAX_DELAY);
            state.ok = true;
            take_frame(side);
            xSemaphoreGive(lock);
        } else if (now - last_frame > STALE_MS) {
            ESP_LOGW(TAG, "no frames for %d s: starting it again", STALE_MS / 1000);
            running = false;
            retry = 0;
            xSemaphoreTake(lock, portMAX_DELAY);
            state.ok = false;
            xSemaphoreGive(lock);
        }

        if (now - rate_start >= 1000) {
            xSemaphoreTake(lock, portMAX_DELAY);
            state.hz = rate_frames * 1000.0f / (now - rate_start);
            xSemaphoreGive(lock);
            rate_frames = 0;
            rate_start = now;
        }
    }
}

void tof_start(void) {
    lock = xSemaphoreCreateMutex();
    load();
    state.side = cfg.side;
    state.filter = cfg.filter;
    state.max_mm = cfg.max_mm;
    i2c_device_config_t dc = {};
    dc.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dc.device_address = ADDR_VL53L7CX;
    dc.scl_speed_hz = 400000;
    i2c_master_dev_handle_t dev;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(i2cbus_bus(), &dc, &dev));
    sensor = new VL53L7CX(dev);
    xTaskCreate(tof_task, "tof", 4096, NULL, 4, NULL);
}
