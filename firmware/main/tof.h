// The VL53L7CX time-of-flight sensor (I2C 0x29): distances in a 4x4 (up to 60 Hz) or 8x8 (up to 15 Hz) grid over a
// 60 x 60 degree field of view, with ST's driver (components/vl53l7cx).
//
// Its own task starts it (ST's driver uploads ~84 kB of firmware into the sensor, a few seconds) and reads every
// frame into a snapshot. Not found, or it stops answering: looked for again every 5 s, so it can be plugged in later.
// The resolution and the distance filter are kept in NVS.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TOF_ZONES_MAX 64

// Zone status (ST's target_status), and the filter's own codes. 5 and 9 are valid ranges.
#define TOF_STATUS_NON_POSITIVE  17     // valid, but 0 mm or less
#define TOF_STATUS_TOO_FAR       18     // valid, but beyond the filter's maximum

typedef struct {
    bool ok;                    // the sensor is ranging
    uint8_t side;               // 4 or 8
    float hz;                   // frames per second
    uint32_t frames;
    bool filter;                // distances beyond max_mm count as invalid
    uint16_t max_mm;
    int16_t distance_mm[TOF_ZONES_MAX];
    uint8_t status[TOF_ZONES_MAX];
    uint8_t targets[TOF_ZONES_MAX];     // targets detected in the zone (0: none)
} tof_t;

void tof_start(void);
void tof_get(tof_t *out);
bool tof_set_resolution(int side);              // 4 or 8 (applied by the task, a moment later)
bool tof_set_filter(bool enabled, int max_mm);  // max_mm 20..4000

#ifdef __cplusplus
}
#endif
