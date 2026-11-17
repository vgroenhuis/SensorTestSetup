// Laid out like the other lab demos' displays (BesBot, LynXP, SpaceMouse, HandTool):
//
//   SensorTest                     [Wi-Fi]      <- header: name and firmware version in turn (3 s each)
//   ------------------------------------------
//   iotroam                     ch36 -56dBm     <- network (scrolls if too long), channel and signal
//   192.168.0.37                                <- address, the largest font that fits
//   ------------------------------------------
//   Pot 1.65 V   MH 0.42 V                      <- footer from the app
//
// and while a control code is shown: the code as big as it fits, with a bar for the time left. u8g2 draws off-screen;
// five times a second the 128-byte pages that changed go out over SPI. SPI can't tell whether a panel is there, so
// the controller is set up again every 30 s (a panel plugged in later, or one that browned out, comes back).
#include "display.h"
#include "board.h"
#include "closer_access.h"
#include "closer_demo.h"
#include "u8g2.h"

#include <stdio.h>
#include <string.h>
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "display";

#define W 128
#define H 64
#define PAGES (H / 8)
#define TITLE "SensorTest"

static spi_device_handle_t dev;
static u8g2_t u8g2;
static uint8_t sent[PAGES][W];
static bool sent_valid;
static display_footer_fn footer_fn;

static int64_t now_ms(void) { return esp_timer_get_time() / 1000; }

// ------------------------------------------------------------------ the controller

// D/C low: command bytes; high: display data. Set just before each transaction starts.
static void IRAM_ATTR pre_cb(spi_transaction_t *t) { gpio_set_level(PIN_OLED_DC, (int)t->user); }

static esp_err_t send(const uint8_t *b, size_t n, int data) {
    spi_transaction_t t = {.length = n * 8, .tx_buffer = b, .user = (void *)data};
    return spi_device_polling_transmit(dev, &t);
}

static void flush(void) {
    const uint8_t *fb = u8g2_GetBufferPtr(&u8g2);
    for (int p = 0; p < PAGES; p++) {
        const uint8_t *page = fb + p * W;
        if (sent_valid && memcmp(page, sent[p], W) == 0) continue;
        uint8_t c[3] = {0xB0 | p, 0x00, 0x10};          // page p, column 0
        if (send(c, sizeof c, 0) != ESP_OK || send(page, W, 1) != ESP_OK) {
            sent_valid = false;
            return;
        }
        memcpy(sent[p], page, W);
    }
    sent_valid = true;
}

static void setup_panel(void) {
    static const uint8_t seq[] = {
        0xD5, 0x80,              // clock
        0xA8, 0x3F,              // 64 rows
        0xD3, 0x00, 0x40,        // no offset, start line 0
        0x8D, 0x14,              // charge pump on
        0x20, 0x02,              // page addressing
        0xA1, 0xC8,              // the usual way up
        0xDA, 0x12,              // COM pins
        0x81, 0x7F,              // contrast
        0xD9, 0xF1, 0xDB, 0x40,  // pre-charge, VCOMH
        0xA4, 0xA6,              // show the RAM, not inverted
        0xAF,                    // on
    };
    send(seq, sizeof seq, 0);
    sent_valid = false;          // (the RAM may have been lost: send every page again)
}

// ------------------------------------------------------------------ drawing helpers (as in BesBot)

static void text(int x, int y, const uint8_t *font, const char *s) {
    u8g2_SetFont(&u8g2, font);
    u8g2_DrawStr(&u8g2, x, y, s);
}

static int width(const uint8_t *font, const char *s) {
    u8g2_SetFont(&u8g2, font);
    return u8g2_GetStrWidth(&u8g2, s);
}

static void text_right(int x_right, int y, const uint8_t *font, const char *s) { text(x_right - width(font, s), y, font, s); }
static void text_center(int y, const uint8_t *font, const char *s) { text((W - width(font, s)) / 2, y, font, s); }

static const uint8_t *pick_font(const uint8_t *const *fonts, size_t n, const char *s, int max_width) {
    for (size_t i = 0; i < n; i++)
        if (width(fonts[i], s) <= max_width) return fonts[i];
    return fonts[n - 1];
}

// Text in a band of the given width that scrolls back and forth when it doesn't fit.
typedef struct { char text[64]; int64_t start_ms; } marquee_t;

static void band(marquee_t *m, const uint8_t *font, const char *s, int baseline, int band_width) {
    if (strncmp(m->text, s, sizeof m->text - 1) != 0) {
        strlcpy(m->text, s, sizeof m->text);
        m->start_ms = now_ms();
    }
    int tw = width(font, s);
    if (tw <= band_width) {
        u8g2_DrawStr(&u8g2, 0, baseline, s);
        return;
    }
    const int HOLD_MS = 1500, PX_PER_S = 30;
    int overflow = tw - band_width, scroll_ms = overflow * 1000 / PX_PER_S;
    int t = (int)((now_ms() - m->start_ms) % (HOLD_MS + scroll_ms + HOLD_MS));
    int offset = t < HOLD_MS ? 0 : t < HOLD_MS + scroll_ms ? (t - HOLD_MS) * PX_PER_S / 1000 : overflow;
    u8g2_SetClipWindow(&u8g2, 0, baseline - u8g2_GetAscent(&u8g2), band_width, baseline - u8g2_GetDescent(&u8g2) + 1);
    u8g2_DrawStr(&u8g2, -offset, baseline, s);
    u8g2_SetMaxClipWindow(&u8g2);
}

static void wifi_icon(int x, int y, int rssi) {
    int bars = rssi == 0 ? 0 : rssi > -55 ? 4 : rssi > -65 ? 3 : rssi > -75 ? 2 : 1;
    for (int i = 0; i < 4; i++) {
        int h = 3 + 2 * i;
        if (i < bars) u8g2_DrawBox(&u8g2, x + 3 * i, y - h, 2, h);
        else u8g2_DrawPixel(&u8g2, x + 3 * i, y - 1);
    }
    if (!bars) {
        u8g2_DrawLine(&u8g2, x + 6, y - 9, x + 11, y - 4);
        u8g2_DrawLine(&u8g2, x + 11, y - 9, x + 6, y - 4);
    }
}

// Word-wrapped text; returns the number of lines used.
static int wrapped(int x, int y, int line_h, int max_width, int max_lines, const uint8_t *font, const char *s) {
    char line[48];
    int lines = 0;
    u8g2_SetFont(&u8g2, font);
    while (*s && lines < max_lines) {
        size_t best = 0, n = 0;
        while (s[n]) {
            size_t m = n;
            while (s[m] && s[m] != ' ') m++;
            size_t k = m < sizeof line - 1 ? m : sizeof line - 1;
            memcpy(line, s, k);
            line[k] = 0;
            if (best && u8g2_GetStrWidth(&u8g2, line) > max_width) break;
            best = k;
            if (!s[m]) break;
            n = m + 1;
        }
        if (!best) best = strlen(s) < sizeof line - 1 ? strlen(s) : sizeof line - 1;
        memcpy(line, s, best);
        line[best] = 0;
        u8g2_DrawStr(&u8g2, x, y + lines * line_h, line);
        lines++;
        s += best;
        while (*s == ' ') s++;
    }
    return lines;
}

// ------------------------------------------------------------------ the screens

static const uint8_t *const IP_FONTS[] = {u8g2_font_logisoso24_tn, u8g2_font_logisoso22_tn, u8g2_font_logisoso20_tn,
                                          u8g2_font_logisoso18_tn, u8g2_font_logisoso16_tn, u8g2_font_fub14_tn,
                                          u8g2_font_fub11_tn};
static const uint8_t *const CODE_FONTS[] = {u8g2_font_logisoso42_tn, u8g2_font_logisoso38_tn, u8g2_font_logisoso24_tn,
                                            u8g2_font_logisoso16_tn};
static marquee_t network_band;

static void header(const char *title, const closer_demo_status_t *st, bool version) {
    if (version && now_ms() / 3000 % 2) text(0, 9, u8g2_font_helvR08_tr, closer_demo_version());
    else text(0, 9, u8g2_font_helvB08_tr, title);
    wifi_icon(115, 9, st->connected ? (st->rssi ? st->rssi : -60) : 0);
    u8g2_DrawHLine(&u8g2, 0, 11, W);
}

static void footer(void) {
    char s[48] = "";
    if (footer_fn) footer_fn(s, sizeof s);
    u8g2_DrawHLine(&u8g2, 0, 50, W);
    text_center(62, u8g2_font_helvB08_tr, s);
}

static void connected_screen(const closer_demo_status_t *st) {
    char s[32];
    snprintf(s, sizeof s, "ch%d %d dBm", st->channel, st->rssi);
    int sw = st->rssi ? width(u8g2_font_helvR08_tr, s) : 0;
    if (sw) text_right(W, 22, u8g2_font_helvR08_tr, s);
    u8g2_SetFont(&u8g2, u8g2_font_helvR08_tr);
    band(&network_band, u8g2_font_helvR08_tr, st->ssid, 22, W - sw - 6);
    const uint8_t *f = pick_font(IP_FONTS, sizeof IP_FONTS / sizeof IP_FONTS[0], st->ip, W);
    text_center(46, f, st->ip);
}

static void offline_screen(const closer_demo_status_t *st, int tick) {
    char line[64], detail[48] = "";
    bool busy = strncmp(st->wifi, "Searching", 9) == 0 || strncmp(st->wifi, "Getting", 7) == 0 ||
                strncmp(st->wifi, "Starting", 8) == 0 || strncmp(st->wifi, "Joining", 7) == 0 ||
                strncmp(st->wifi, "Looking", 7) == 0;
    snprintf(line, sizeof line, "%s%.*s", st->wifi[0] ? st->wifi : "No Wi-Fi settings", busy ? tick / 3 % 4 : 0, "...");
    int lines = wrapped(0, 24, 11, W - 1, 2, u8g2_font_helvB08_tr, line);
    if (st->attempts > 1) snprintf(detail, sizeof detail, "attempt %d", st->attempts);
    text(0, 24 + lines * 11, u8g2_font_5x8_tr, detail);
}

static void code_screen(const char *code, int left, const closer_demo_status_t *st) {
    char s[16];
    header("Control code", st, false);
    snprintf(s, sizeof s, "%d s", left);
    text_right(110, 9, u8g2_font_helvR08_tr, s);
    const uint8_t *f = pick_font(CODE_FONTS, sizeof CODE_FONTS / sizeof CODE_FONTS[0], code, W);
    text_center(56, f, code);
    int bar = (W - 4) * (left > 60 ? 60 : left) / 60;
    u8g2_DrawRFrame(&u8g2, 0, 58, W, 6, 2);
    if (bar > 0) u8g2_DrawBox(&u8g2, 2, 60, bar, 2);
}

static void draw(int tick) {
    closer_demo_status_t st;
    closer_demo_get_status(&st);
    char code[12];
    int left = closer_access_code(code, sizeof code, NULL, 0);

    u8g2_ClearBuffer(&u8g2);
    if (st.updating) {
        header(TITLE, &st, true);
        text_center(27, u8g2_font_helvB10_tr, "Updating firmware");
        snprintf(code, sizeof code, "%d %%", st.update_pct);
        text_center(41, u8g2_font_helvB10_tr, code);
        u8g2_DrawRFrame(&u8g2, 0, 45, W, 6, 2);
        if (st.update_pct > 0) u8g2_DrawBox(&u8g2, 2, 47, (W - 4) * st.update_pct / 100, 2);
        text_center(62, u8g2_font_6x10_tr, "Don't switch off");
    } else if (st.update_error[0] && st.update_failed_s >= 0 && st.update_failed_s < 60) {
        header("Update failed", &st, false);
        wrapped(0, 24, 10, W - 1, 4, u8g2_font_6x10_tr, st.update_error);
    } else if (left > 0) {
        code_screen(code, left, &st);
    } else {
        header(TITLE, &st, true);
        if (st.connected) connected_screen(&st);
        else offline_screen(&st, tick);
        footer();
    }
}

static void display_task(void *arg) {
    for (int tick = 0;; tick++) {
        if (tick % 150 == 0) setup_panel();
        draw(tick);
        flush();
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}

void display_start(spi_host_device_t host, display_footer_fn footer) {
    footer_fn = footer;
    gpio_config_t dc = {.pin_bit_mask = 1ULL << PIN_OLED_DC, .mode = GPIO_MODE_OUTPUT};
    gpio_config(&dc);
    spi_device_interface_config_t devcfg = {.clock_speed_hz = 8 * 1000 * 1000, .mode = 0, .spics_io_num = PIN_OLED_CS,
                                            .queue_size = 1, .pre_cb = pre_cb};
    if (spi_bus_add_device(host, &devcfg, &dev) != ESP_OK) {
        ESP_LOGE(TAG, "can't add the display to the SPI bus");
        return;
    }
    u8g2_Setup_ssd1306_128x64_noname_f(&u8g2, U8G2_R0, u8x8_dummy_cb, u8x8_dummy_cb);    // (off-screen only)
    u8g2_SetFontMode(&u8g2, 1);
    xTaskCreate(display_task, "display", 4096, NULL, 2, NULL);
}
