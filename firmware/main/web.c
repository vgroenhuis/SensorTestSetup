#include "web.h"
#include "board.h"
#include "sensors.h"
#include "i2cbus.h"
#include "gpioparts.h"
#include "tof.h"
#include "matrix.h"
#include "closer_access.h"
#include "closer_demo.h"
#include "closer_udp.h"
#include "closer_wifi_web.h"
#include "web_table.h"

#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include "cJSON.h"
#include "esp_heap_caps.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

static const char *TAG = "web";

typedef enum {
    TOPIC_STATUS, TOPIC_POT, TOPIC_MH, TOPIC_MCP3008, TOPIC_MCP23017, TOPIC_PRESSURE, TOPIC_PWM,
    TOPIC_MOTOR, TOPIC_ENCODER, TOPIC_ULTRASONIC, TOPIC_LOADCELL, TOPIC_TOF, TOPIC_MATRIX, TOPIC_COUNT
} topic_t;
static const char *const TOPIC_NAMES[TOPIC_COUNT] = {"status", "pot", "mh", "mcp3008", "mcp23017", "pressure", "pwm",
                                                     "motor", "encoder", "ultrasonic", "loadcell", "tof", "matrix"};
static const int TOPIC_PERIOD_MS[TOPIC_COUNT] = {500, 50, 50, 50, 50, 50, 250, 100, 50, 50, 50, 50, 250};
#define TICK_MS 50

#define MAX_CLIENTS 12
typedef struct {
    int fd;                     // -1: free
    uint32_t topics;            // bit per topic_t
    int64_t due_ms[TOPIC_COUNT];
} client_t;

static httpd_handle_t server;
static client_t clients[MAX_CLIENTS];
static SemaphoreHandle_t lock;      // clients[] and sending (the stream task and the server task both send)

static int64_t now_ms(void) { return esp_timer_get_time() / 1000; }

// ------------------------------------------------------------------ clients

static client_t *client_find(int fd, bool add) {
    client_t *free_slot = NULL;
    for (int i = 0; i < MAX_CLIENTS; i++) {
        if (clients[i].fd == fd) return &clients[i];
        if (clients[i].fd < 0 && !free_slot) free_slot = &clients[i];
    }
    if (!add || !free_slot) return NULL;
    *free_slot = (client_t){.fd = fd};
    return free_slot;
}

static void client_subscribe(int fd, uint32_t topics) {
    xSemaphoreTake(lock, portMAX_DELAY);
    client_t *c = client_find(fd, true);
    if (c) {
        c->topics = topics;
        for (int t = 0; t < TOPIC_COUNT; t++) c->due_ms[t] = 0;
    } else {
        ESP_LOGW(TAG, "more than %d WebSocket clients: fd %d gets nothing", MAX_CLIENTS, fd);
    }
    xSemaphoreGive(lock);
}

static void client_gone(int fd) {
    xSemaphoreTake(lock, portMAX_DELAY);
    client_t *c = client_find(fd, false);
    if (c) c->fd = -1;
    xSemaphoreGive(lock);
}

// Caller holds the lock.
static int count_clients(void) {
    int n = 0;
    for (int i = 0; i < MAX_CLIENTS; i++) n += clients[i].fd >= 0 && clients[i].topics;
    return n;
}

int web_clients(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    int n = count_clients();
    xSemaphoreGive(lock);
    return n;
}

// Caller holds the lock.
static bool send_text(int fd, const char *s, size_t n) {
    httpd_ws_frame_t f = {.type = HTTPD_WS_TYPE_TEXT, .payload = (uint8_t *)s, .len = n};
    return httpd_ws_get_fd_info(server, fd) == HTTPD_WS_CLIENT_WEBSOCKET &&
           httpd_ws_send_frame_async(server, fd, &f) == ESP_OK;
}

// ------------------------------------------------------------------ topic messages

#define TF(b) ((b) ? "true" : "false")

typedef struct {
    sensors_t s;
    i2cbus_t b;
    gpioparts_t g;
    tof_t tof;
} snapshot_t;

static void snapshot(snapshot_t *x) {
    sensors_get(&x->s);
    i2cbus_get(&x->b);
    gpioparts_get(&x->g);
    tof_get(&x->tof);
}

// {"t":"tof","ok":..,"side":8,"hz":..,"frame":n,"filter":..,"max_mm":..,"d":[mm..],"s":[status..],"n":[targets..]},
// zones row by row as the sensor gives them.
static int tof_json(char *out, size_t len, const tof_t *t) {
    int zones = t->side * t->side;
    int n = snprintf(out, len, "{\"t\":\"tof\",\"ok\":%s,\"side\":%u,\"hz\":%.1f,\"frame\":%lu,\"filter\":%s,"
                     "\"max_mm\":%u,\"d\":[", TF(t->ok), t->side, t->hz, (unsigned long)t->frames, TF(t->filter),
                     t->max_mm);
    for (int z = 0; z < zones && n < (int)len; z++) n += snprintf(out + n, len - n, "%s%d", z ? "," : "", t->distance_mm[z]);
    if (n < (int)len) n += snprintf(out + n, len - n, "],\"s\":[");
    for (int z = 0; z < zones && n < (int)len; z++) n += snprintf(out + n, len - n, "%s%u", z ? "," : "", t->status[z]);
    if (n < (int)len) n += snprintf(out + n, len - n, "],\"n\":[");
    for (int z = 0; z < zones && n < (int)len; z++) n += snprintf(out + n, len - n, "%s%u", z ? "," : "", t->targets[z]);
    if (n < (int)len) n += snprintf(out + n, len - n, "]}");
    return n;
}

// {"t":"matrix","in":[names],"out":[names],"routes":[{"id":0,"name":..,"enabled":..,"in":..,"in_ch":..,"in_min":..,
// "in_max":..,"invert":..,"out":..,"out_ch":..,"threshold":..,"ok":..,"raw":..,"value":..},...]}
static int matrix_json(char *out, size_t len) {
    static matrix_route_t r[MATRIX_ROUTES];
    static matrix_live_t l[MATRIX_ROUTES];
    matrix_get(r, l);
    int n = snprintf(out, len, "{\"t\":\"matrix\",\"routes\":[");
    bool first = true;
    for (int i = 0; i < MATRIX_ROUTES && n < (int)len; i++) {
        if (!r[i].used) continue;
        n += snprintf(out + n, len - n,
                      "%s{\"id\":%d,\"name\":\"%s\",\"enabled\":%s,\"in\":\"%s\",\"in_ch\":%u,\"in_min\":%g,"
                      "\"in_max\":%g,\"invert\":%s,\"out\":\"%s\",\"out_ch\":%u,\"threshold\":%g,\"ok\":%s,"
                      "\"raw\":%.3f,\"value\":%.3f}",
                      first ? "" : ",", i, r[i].name, TF(r[i].enabled), MATRIX_IN_NAMES[r[i].in], r[i].in_ch, r[i].in_min,
                      r[i].in_max, TF(r[i].invert), MATRIX_OUT_NAMES[r[i].out], r[i].out_ch, r[i].threshold,
                      TF(l[i].in_ok), l[i].in_raw, l[i].value);
        first = false;
    }
    if (n < (int)len) n += snprintf(out + n, len - n, "]}");
    return n;
}

static int num(const cJSON *o, const char *key, int dflt);

static int name_index(const char *const names[], int count, const cJSON *v) {
    for (int i = 0; i < count && cJSON_IsString(v); i++)
        if (strcmp(v->valuestring, names[i]) == 0) return i;
    return -1;
}

static double dnum(const cJSON *o, const char *key, double dflt) {
    const cJSON *v = cJSON_GetObjectItem(o, key);
    return cJSON_IsNumber(v) ? v->valuedouble : dflt;
}

// {"set":{route, "id" for an existing one}} | {"delete":id} | {"clear":1}
static bool matrix_command(const cJSON *v) {
    const cJSON *x;
    if ((x = cJSON_GetObjectItem(v, "set")) && cJSON_IsObject(x)) {
        matrix_route_t r = {0};
        int in = name_index(MATRIX_IN_NAMES, IN_COUNT, cJSON_GetObjectItem(x, "in"));
        int out = name_index(MATRIX_OUT_NAMES, OUT_COUNT, cJSON_GetObjectItem(x, "out"));
        if (in < 0 || out < 0) return false;
        r.in = in;
        r.out = out;
        r.in_ch = num(x, "in_ch", 0);
        r.out_ch = num(x, "out_ch", 0);
        r.in_min = dnum(x, "in_min", 0);
        r.in_max = dnum(x, "in_max", 1);
        r.threshold = dnum(x, "threshold", 0.5);
        r.enabled = !cJSON_IsFalse(cJSON_GetObjectItem(x, "enabled"));
        r.invert = cJSON_IsTrue(cJSON_GetObjectItem(x, "invert"));
        const cJSON *name = cJSON_GetObjectItem(x, "name");
        if (cJSON_IsString(name)) {
            // (printable ASCII without quotes or backslashes: it goes into JSON as it is)
            size_t k = 0;
            for (const char *c = name->valuestring; *c && k < sizeof r.name - 1; c++)
                r.name[k++] = (*c >= 32 && *c < 127 && *c != '"' && *c != 0x5C) ? *c : '_';   // (0x5C: backslash)
        }
        return matrix_set(num(x, "id", -1), &r) >= 0;
    }
    if (cJSON_IsNumber(x = cJSON_GetObjectItem(v, "delete"))) return matrix_delete(x->valueint);
    if (cJSON_GetObjectItem(v, "clear")) {
        matrix_clear();
        return true;
    }
    return false;
}

static const char *const MOTOR_MODES[] = {"direct", "api", "pot"};

static int status_json(char *out, size_t len, int fd, const snapshot_t *x, int n_clients) {
    const sensors_t *s = &x->s;
    const i2cbus_t *b = &x->b;
    closer_demo_status_t st;
    closer_demo_get_status(&st);
    char code[12], link[8];
    int code_s = closer_access_code(code, sizeof code, link, sizeof link);
    return snprintf(out, len,
                    "{\"t\":\"status\",\"fw\":\"%s\",\"host\":\"%s\",\"uptime_s\":%lld,\"heap\":%u,\"ip\":\"%s\","
                    "\"rssi\":%d,\"ssid\":\"%s\",\"clients\":%d,\"sample_hz\":%.1f,\"parts\":{\"mcp3008\":%s,"
                    "\"mcp23017\":%s,\"pca9685\":%s,\"tca9548\":%s,\"pressure0\":%s,\"pressure1\":%s,"
                    "\"hx711\":%s,\"ultrasonic\":%s,\"vl53l7cx\":%s},\"access\":\"%s\",\"code\":%d}",
                    closer_demo_version(), closer_demo_name(), esp_timer_get_time() / 1000000,
                    (unsigned)heap_caps_get_free_size(MALLOC_CAP_DEFAULT), st.ip, st.rssi, st.ssid, n_clients,
                    s->rate_hz, TF(s->mcp3008_ok), TF(b->mcp_ok), TF(b->pca_ok), TF(b->tca_ok), TF(b->pressure_ok[0]),
                    TF(b->pressure_ok[1]), TF(x->g.hx_ok), TF(x->g.us_ok), TF(x->tof.ok), fd >= 0 ? closer_access_state(fd) : "none",
                    code_s);
}

static int pwm_json(char *out, size_t len, const i2cbus_t *b) {
    int n = snprintf(out, len, "{\"t\":\"pwm\",\"ok\":%s,\"hz\":%.2f,\"ch\":[", TF(b->pca_ok), b->pwm_hz);
    for (int ch = 0; ch < PWM_CHANNELS && n < (int)len; ch++) {
        const pwm_channel_cfg_t *c = &b->pwm[ch];
        n += snprintf(out + n, len - n, "%s{\"mode\":\"%s\",\"min\":%u,\"max\":%u,\"us\":%d,\"duty\":%.4f}",
                      ch ? "," : "", c->mode == PWM_SERVO ? "servo" : "raw", c->min_us, c->max_us, b->pwm_us[ch],
                      b->pwm_duty[ch]);
    }
    if (n < (int)len) n += snprintf(out + n, len - n, "]}");
    return n;
}

// Caller holds the lock.
static int topic_json(topic_t t, char *out, size_t len, int fd, const snapshot_t *x) {
    const sensors_t *s = &x->s;
    const i2cbus_t *b = &x->b;
    const gpioparts_t *g = &x->g;
    const char *ok = TF(s->mcp3008_ok);
    switch (t) {
    case TOPIC_STATUS:
        return status_json(out, len, fd, x, count_clients());
    case TOPIC_MOTOR:
        return snprintf(out, len,
                        "{\"t\":\"motor\",\"mode\":\"%s\",\"forward\":\"%s\",\"in1\":%s,\"in2\":%s,\"speed\":%.3f,"
                        "\"pot\":%.3f,\"pot_ok\":%s}",
                        MOTOR_MODES[g->motor_mode], g->motor_ccw ? "ccw" : "cw", TF(g->in1), TF(g->in2), g->speed,
                        s->mcp3008_v[MCP3008_CH_POT], ok);
    case TOPIC_ENCODER:
        return snprintf(out, len, "{\"t\":\"encoder\",\"encoderCount\":%ld,\"encABBits\":%u,\"stepsPerSecond\":%.1f}",
                        (long)g->enc_count, g->enc_ab, g->enc_steps_s);
    case TOPIC_ULTRASONIC:
        return snprintf(out, len, "{\"t\":\"ultrasonic\",\"ok\":%s,\"distanceMm\":%.1f,\"hz\":%.1f}", TF(g->us_ok),
                        g->us_mm, g->us_hz);
    case TOPIC_MATRIX:
        return matrix_json(out, len);
    case TOPIC_TOF:
        return tof_json(out, len, &x->tof);
    case TOPIC_LOADCELL:
        return snprintf(out, len, "{\"t\":\"loadcell\",\"ok\":%s,\"grams\":%.2f,\"raw\":%ld,\"hz\":%.1f}", TF(g->hx_ok),
                        g->hx_units, (long)g->hx_raw, g->hx_hz);
    case TOPIC_MCP23017: {
        const mcp23017_cfg_t *c = &b->mcp;
        return snprintf(out, len,
                        "{\"t\":\"mcp23017\",\"ok\":%s,\"a\":%u,\"b\":%u,\"cfg\":{\"modeA\":%u,\"pullupA\":%u,"
                        "\"outputA\":%u,\"modeB\":%u,\"pullupB\":%u,\"outputB\":%u}}",
                        TF(b->mcp_ok), b->gpio_a, b->gpio_b, c->mode_a, c->pullup_a, c->out_a, c->mode_b,
                        c->pullup_b, c->out_b);
    }
    case TOPIC_PRESSURE:
        return snprintf(out, len, "{\"t\":\"pressure\",\"ok\":[%s,%s],\"bar\":[%.4f,%.4f],\"hz\":%.1f}",
                        TF(b->pressure_ok[0]), TF(b->pressure_ok[1]), b->pressure_bar[0], b->pressure_bar[1],
                        b->pressure_hz);
    case TOPIC_PWM:
        return pwm_json(out, len, b);
    case TOPIC_POT:
        return snprintf(out, len, "{\"t\":\"pot\",\"ok\":%s,\"voltage\":%.3f}", ok, s->mcp3008_v[MCP3008_CH_POT]);
    case TOPIC_MH:
        return snprintf(out, len, "{\"t\":\"mh\",\"ok\":%s,\"voltage\":%.3f}", ok, s->mcp3008_v[MCP3008_CH_MH]);
    case TOPIC_MCP3008: {
        int n = snprintf(out, len, "{\"t\":\"mcp3008\",\"ok\":%s,\"channels\":[", ok);
        for (int ch = 0; ch < 8 && n < (int)len; ch++) n += snprintf(out + n, len - n, "%s%.3f", ch ? "," : "", s->mcp3008_v[ch]);
        if (n < (int)len) n += snprintf(out + n, len - n, "]}");
        return n;
    }
    default:
        return 0;
    }
}

static void stream_task(void *arg) {
    static char buf[4096];         // (the largest: the matrix with 12 routes)
    static snapshot_t x;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(TICK_MS));
        snapshot(&x);
        int64_t now = now_ms();
        xSemaphoreTake(lock, portMAX_DELAY);
        for (int i = 0; i < MAX_CLIENTS; i++) {
            client_t *c = &clients[i];
            for (int t = 0; t < TOPIC_COUNT && c->fd >= 0; t++) {
                if (!(c->topics & 1u << t) || now < c->due_ms[t]) continue;
                c->due_ms[t] = now + TOPIC_PERIOD_MS[t] - TICK_MS / 2;
                int n = topic_json(t, buf, sizeof buf, c->fd, &x);
                if (n > 0 && n < (int)sizeof buf && !send_text(c->fd, buf, n)) c->fd = -1;      // (gone)
            }
        }
        xSemaphoreGive(lock);
    }
}

// ------------------------------------------------------------------ handlers

static int num(const cJSON *o, const char *key, int dflt) {
    const cJSON *v = cJSON_GetObjectItem(o, key);
    return cJSON_IsNumber(v) ? v->valueint : dflt;
}

// A command that changes something: only from the client in control. The reply says what happened.
static int command(int fd, cJSON *j, char *reply, size_t len) {
    const char *what = NULL;
    bool ok = false;
    cJSON *v;
    if ((v = cJSON_GetObjectItem(j, "mcp23017")) && cJSON_IsObject(v)) {
        what = "mcp23017";
        i2cbus_t b;
        i2cbus_get(&b);
        mcp23017_cfg_t c = {num(v, "modeA", b.mcp.mode_a), num(v, "pullupA", b.mcp.pullup_a),
                            num(v, "modeB", b.mcp.mode_b), num(v, "pullupB", b.mcp.pullup_b),
                            num(v, "outputA", b.mcp.out_a), num(v, "outputB", b.mcp.out_b)};
        if (closer_access_has(fd)) ok = i2cbus_mcp_set(&c);
    } else if ((v = cJSON_GetObjectItem(j, "pwm")) && cJSON_IsObject(v)) {
        what = "pwm";
        int ch = num(v, "ch", -1);
        cJSON *x;
        if (!closer_access_has(fd)) {
        } else if (cJSON_IsNumber(x = cJSON_GetObjectItem(v, "us"))) {
            ok = i2cbus_pwm_set_us(ch, x->valueint);
        } else if (cJSON_IsNumber(x = cJSON_GetObjectItem(v, "value"))) {
            ok = i2cbus_pwm_set_value(ch, (float)x->valuedouble);
        } else if (cJSON_GetObjectItem(v, "off")) {
            ok = i2cbus_pwm_off(ch);
        }
    } else if ((v = cJSON_GetObjectItem(j, "pwm_cfg")) && cJSON_IsObject(v)) {
        what = "pwm_cfg";
        cJSON *m = cJSON_GetObjectItem(v, "mode");
        pwm_channel_cfg_t c = {.mode = cJSON_IsString(m) && strcmp(m->valuestring, "raw") == 0 ? PWM_RAW : PWM_SERVO,
                               .min_us = num(v, "min", 500), .max_us = num(v, "max", 2500)};
        if (closer_access_has(fd)) ok = i2cbus_pwm_set_cfg(num(v, "ch", -1), &c);
    } else if (cJSON_IsNumber(v = cJSON_GetObjectItem(j, "pwm_hz"))) {
        what = "pwm_hz";
        if (closer_access_has(fd)) ok = i2cbus_pwm_set_hz((float)v->valuedouble);
    } else if (cJSON_IsNumber(v = cJSON_GetObjectItem(j, "pressure_zero"))) {
        what = "pressure_zero";
        if (closer_access_has(fd)) ok = i2cbus_pressure_zero(v->valueint);
    } else if ((v = cJSON_GetObjectItem(j, "motor")) && cJSON_IsObject(v)) {
        what = "motor";
        cJSON *x;
        if (!closer_access_has(fd)) {
        } else if (cJSON_IsString(x = cJSON_GetObjectItem(v, "mode"))) {
            for (int m = 0; m < 3; m++)
                if (strcmp(x->valuestring, MOTOR_MODES[m]) == 0) ok = gpioparts_motor_mode(m);
        } else if (cJSON_IsString(x = cJSON_GetObjectItem(v, "forward"))) {
            ok = gpioparts_motor_ccw(strcmp(x->valuestring, "cw") != 0);
        } else if (cJSON_IsNumber(x = cJSON_GetObjectItem(v, "speed"))) {
            ok = gpioparts_motor_speed((float)x->valuedouble);
        } else if (cJSON_GetObjectItem(v, "in1") || cJSON_GetObjectItem(v, "in2")) {
            ok = gpioparts_motor_direct(cJSON_IsTrue(cJSON_GetObjectItem(v, "in1")),
                                        cJSON_IsTrue(cJSON_GetObjectItem(v, "in2")));
        }
    } else if (cJSON_GetObjectItem(j, "encoder_zero")) {
        what = "encoder_zero";
        if (closer_access_has(fd)) {
            gpioparts_encoder_zero();
            ok = true;
        }
    } else if ((v = cJSON_GetObjectItem(j, "matrix")) && cJSON_IsObject(v)) {
        what = "matrix";
        if (closer_access_has(fd)) ok = matrix_command(v);
    } else if ((v = cJSON_GetObjectItem(j, "tof")) && cJSON_IsObject(v)) {
        what = "tof";
        if (closer_access_has(fd)) {
            tof_t t;
            tof_get(&t);
            cJSON *f = cJSON_GetObjectItem(v, "filter");
            ok = (!cJSON_GetObjectItem(v, "side") || tof_set_resolution(num(v, "side", 0))) &&
                 ((!f && !cJSON_GetObjectItem(v, "max_mm")) ||
                  tof_set_filter(f ? cJSON_IsTrue(f) : t.filter, num(v, "max_mm", t.max_mm)));
        }
    } else if (cJSON_GetObjectItem(j, "loadcell_tare")) {
        what = "loadcell_tare";
        if (closer_access_has(fd)) ok = gpioparts_loadcell_tare();
    }
    if (!what) return 0;
    if (!closer_access_has(fd)) return snprintf(reply, len, "{\"need\":1,\"cmd\":\"%s\"}", what);
    closer_access_used(fd);
    return snprintf(reply, len, "{\"cmd\":\"%s\",\"ok\":%s}", what, TF(ok));
}

static esp_err_t ws_handler(httpd_req_t *req) {
    if (req->method == HTTP_GET) return ESP_OK;          // the handshake
    char buf[400];
    httpd_ws_frame_t frame = {.type = HTTPD_WS_TYPE_TEXT, .payload = (uint8_t *)buf};
    esp_err_t err = httpd_ws_recv_frame(req, &frame, sizeof buf - 1);
    if (err != ESP_OK) return err;
    int fd = httpd_req_to_sockfd(req);
    if (frame.type == HTTPD_WS_TYPE_CLOSE) {
        client_gone(fd);
        closer_access_gone(fd);
        return ESP_OK;
    }
    if (frame.type != HTTPD_WS_TYPE_TEXT) return ESP_OK;
    buf[frame.len] = 0;

    char reply[160];
    int n = 0;
    if (strcmp(buf, "stream") == 0) {
        client_subscribe(fd, 1u << TOPIC_STATUS);
    } else if (strncmp(buf, "ping:", 5) == 0) {
        n = snprintf(reply, sizeof reply, "pong:%s", buf + 5);
    } else if (closer_access_message(fd, buf, reply, sizeof reply)) {
        n = strlen(reply);
    } else {
        cJSON *j = cJSON_Parse(buf);
        cJSON *sub = j ? cJSON_GetObjectItem(j, "sub") : NULL;
        if (cJSON_IsArray(sub)) {
            uint32_t topics = 0;
            cJSON *item;
            cJSON_ArrayForEach(item, sub) {
                for (int t = 0; t < TOPIC_COUNT && cJSON_IsString(item); t++)
                    if (strcmp(item->valuestring, TOPIC_NAMES[t]) == 0) topics |= 1u << t;
            }
            client_subscribe(fd, topics);
        } else if (j) {
            n = command(fd, j, reply, sizeof reply);
        }
        cJSON_Delete(j);
    }
    if (n > 0 && n < (int)sizeof reply) {
        xSemaphoreTake(lock, portMAX_DELAY);
        send_text(fd, reply, n);
        xSemaphoreGive(lock);
    }
    return ESP_OK;
}

// A file or a single request: the connection closes after it. Left open (keep-alive), the connections of every page
// load would fill the server's slots, and when they're full it closes the least recently used one: often a page's
// WebSocket ("Disconnected, retrying..."), especially through the lab demos proxy.
static esp_err_t send_and_close(httpd_req_t *req, const char *body, size_t len) {
    httpd_resp_set_hdr(req, "Connection", "close");
    esp_err_t e = httpd_resp_send(req, body, len);
    httpd_sess_trigger_close(req->handle, httpd_req_to_sockfd(req));
    return e;
}

static esp_err_t state_get(httpd_req_t *req) {
    char buf[700];
    static snapshot_t x;            // (only the server task gets here)
    snapshot(&x);
    int n = status_json(buf, sizeof buf, -1, &x, web_clients());
    httpd_resp_set_type(req, "application/json");
    return send_and_close(req, buf, n);
}

// Every other GET: a file from web/ (gzipped in the firmware); "/" is index.html.
static esp_err_t file_get(httpd_req_t *req) {
    char path[64];
    size_t n = strcspn(req->uri, "?#");
    if (n >= sizeof path) return httpd_resp_send_404(req);
    memcpy(path, req->uri, n);
    path[n] = 0;
    if (strcmp(path, "/") == 0) strcpy(path, "/index.html");
    for (size_t i = 0; i < sizeof WEB_FILES / sizeof WEB_FILES[0]; i++) {
        if (strcmp(WEB_FILES[i].path, path) != 0) continue;
        httpd_resp_set_type(req, WEB_FILES[i].type);
        httpd_resp_set_hdr(req, "Content-Encoding", "gzip");
        httpd_resp_set_hdr(req, "Cache-Control", "no-cache");
        return send_and_close(req, (const char *)WEB_FILES[i].start, WEB_FILES[i].end - WEB_FILES[i].start);
    }
    httpd_resp_set_hdr(req, "Connection", "close");
    esp_err_t e = httpd_resp_send_404(req);
    httpd_sess_trigger_close(req->handle, httpd_req_to_sockfd(req));
    return e;
}

static void on_close(httpd_handle_t hd, int fd) {
    client_gone(fd);
    closer_access_gone(fd);
    close(fd);
}

void web_start(void) {
    lock = xSemaphoreCreateMutex();
    for (int i = 0; i < MAX_CLIENTS; i++) clients[i].fd = -1;

    httpd_config_t c = HTTPD_DEFAULT_CONFIG();
    c.lru_purge_enable = true;
    c.stack_size = 6144;
    c.max_open_sockets = 16;        // (CONFIG_LWIP_MAX_SOCKETS 24, less the server's own 3 and the rest's 5)
    c.max_uri_handlers = 16;        // (9 in use: 3 here, 3 for the Wi-Fi settings page, 3 for the UDP test)
    c.send_wait_timeout = 2;        // a stalled viewer must not hold the others up for long
    c.close_fn = on_close;
    c.uri_match_fn = httpd_uri_match_wildcard;
    ESP_ERROR_CHECK(httpd_start(&server, &c));

    httpd_uri_t uris[] = {
        {.uri = "/ws", .method = HTTP_GET, .handler = ws_handler, .is_websocket = true},
        {.uri = "/api/state", .method = HTTP_GET, .handler = state_get},
    };
    for (int i = 0; i < sizeof uris / sizeof uris[0]; i++) httpd_register_uri_handler(server, &uris[i]);
    closer_wifi_web_register(server);       // /wifi: networks, band, access point, roaming
    closer_udp_register(server);            // /udp: round trips to the CloSer server
    // Last: handlers are matched in the order they were registered.
    httpd_uri_t files = {.uri = "/*", .method = HTTP_GET, .handler = file_get};
    httpd_register_uri_handler(server, &files);

    xTaskCreate(stream_task, "ws-stream", 4096, NULL, 4, NULL);
}
