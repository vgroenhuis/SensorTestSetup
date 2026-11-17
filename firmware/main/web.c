#include "web.h"
#include "board.h"
#include "sensors.h"
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

typedef enum { TOPIC_STATUS, TOPIC_POT, TOPIC_MH, TOPIC_MCP3008, TOPIC_COUNT } topic_t;
static const char *const TOPIC_NAMES[TOPIC_COUNT] = {"status", "pot", "mh", "mcp3008"};
static const int TOPIC_PERIOD_MS[TOPIC_COUNT] = {500, 50, 50, 50};
#define TICK_MS 50

#define MAX_CLIENTS 6
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

static int status_json(char *out, size_t len, int fd, const sensors_t *s, int n_clients) {
    closer_demo_status_t st;
    closer_demo_get_status(&st);
    return snprintf(out, len,
                    "{\"t\":\"status\",\"fw\":\"%s\",\"host\":\"%s\",\"uptime_s\":%lld,\"heap\":%u,\"ip\":\"%s\","
                    "\"rssi\":%d,\"ssid\":\"%s\",\"clients\":%d,\"sample_hz\":%.1f,\"mcp3008\":%s,\"access\":\"%s\"}",
                    closer_demo_version(), closer_demo_name(), esp_timer_get_time() / 1000000,
                    (unsigned)heap_caps_get_free_size(MALLOC_CAP_DEFAULT), st.ip, st.rssi, st.ssid, n_clients,
                    s->rate_hz, s->mcp3008_ok ? "true" : "false", fd >= 0 ? closer_access_state(fd) : "none");
}

// Caller holds the lock.
static int topic_json(topic_t t, char *out, size_t len, int fd, const sensors_t *s) {
    const char *ok = s->mcp3008_ok ? "true" : "false";
    switch (t) {
    case TOPIC_STATUS:
        return status_json(out, len, fd, s, count_clients());
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
    static char buf[512];
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(TICK_MS));
        sensors_t s;
        sensors_get(&s);
        int64_t now = now_ms();
        xSemaphoreTake(lock, portMAX_DELAY);
        for (int i = 0; i < MAX_CLIENTS; i++) {
            client_t *c = &clients[i];
            for (int t = 0; t < TOPIC_COUNT && c->fd >= 0; t++) {
                if (!(c->topics & 1u << t) || now < c->due_ms[t]) continue;
                c->due_ms[t] = now + TOPIC_PERIOD_MS[t] - TICK_MS / 2;
                int n = topic_json(t, buf, sizeof buf, c->fd, &s);
                if (n > 0 && n < (int)sizeof buf && !send_text(c->fd, buf, n)) c->fd = -1;      // (gone)
            }
        }
        xSemaphoreGive(lock);
    }
}

// ------------------------------------------------------------------ handlers

static esp_err_t ws_handler(httpd_req_t *req) {
    if (req->method == HTTP_GET) return ESP_OK;          // the handshake
    char buf[200];
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

static esp_err_t state_get(httpd_req_t *req) {
    char buf[512];
    sensors_t s;
    sensors_get(&s);
    int n = status_json(buf, sizeof buf, -1, &s, web_clients());
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, buf, n);
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
        return httpd_resp_send(req, (const char *)WEB_FILES[i].start, WEB_FILES[i].end - WEB_FILES[i].start);
    }
    return httpd_resp_send_404(req);
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
    c.max_open_sockets = 8;
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
