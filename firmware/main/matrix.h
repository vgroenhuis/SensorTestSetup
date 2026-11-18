// The input-output matrix: routes from a sensor to an actuator, run 50 times a second without anyone in control (like
// the motor's pot mode), so a route shows something at power-on. Changing the routes needs control.
//
// A route reads its input, scales in_min..in_max to 0..1 (clamped; invert: 1 - x), and drives its output:
//   servo      PCA9685 channel: 0..1 between the channel's min and max (or its duty cycle in raw mode)
//   motor      speed -1..1 (0.5: stop); only while the motor is in speed mode, so it never fights the other modes
//   mcp_a/b    MCP23017 output pin: high at or above the threshold (pins that are inputs are left alone)
// An input that doesn't answer leaves its output as it is. Routes are kept in NVS.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define MATRIX_ROUTES 12

typedef enum {
    IN_MCP3008,         // ch 0..7, volts
    IN_MCP_A,           // ch 0..7, 0/1
    IN_MCP_B,
    IN_PRESSURE,        // ch 0..1, bar
    IN_ULTRASONIC,      // mm
    IN_TOF,             // ch 0..63: a zone; 64: the nearest valid zone; mm
    IN_LOADCELL,        // the load cell page's units
    IN_ENCODER,         // counts
    IN_COUNT
} matrix_in_t;

typedef enum { OUT_SERVO, OUT_MOTOR, OUT_MCP_A, OUT_MCP_B, OUT_COUNT } matrix_out_t;

typedef struct {
    bool used, enabled, invert;
    uint8_t in, in_ch, out, out_ch;
    float in_min, in_max;
    float threshold;            // digital outputs
    char name[24];
} matrix_route_t;

typedef struct {
    bool in_ok;                 // the input answered
    float in_raw;               // in its own unit
    float value;                // 0..1 after scaling and inverting
} matrix_live_t;

extern const char *const MATRIX_IN_NAMES[IN_COUNT];
extern const char *const MATRIX_OUT_NAMES[OUT_COUNT];

void matrix_start(void);
void matrix_get(matrix_route_t routes[MATRIX_ROUTES], matrix_live_t live[MATRIX_ROUTES]);
int matrix_set(int id, const matrix_route_t *route);   // id -1: a new route; returns its id, or -1
bool matrix_delete(int id);
void matrix_clear(void);
