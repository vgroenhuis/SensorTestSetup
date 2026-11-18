// The I2C bus: MCP23017 (16 GPIO), PCA9685 (16 PWM/servo outputs), and two WF100DPZ pressure sensors behind a
// TCA9548 multiplexer (channels 0 and 1, both at 0x6D).
//
// One task reads the inputs about 50 times a second into a snapshot (i2cbus_get). Outputs are written straight away by
// the setters. A part that doesn't answer is marked absent and is looked for again every second; when an MCP23017
// or PCA9685 comes back (re-plugged, power glitch) it gets its settings again.
// Settings (MCP23017 directions/pull-ups/outputs, PWM frequency and channel modes, pressure zero offsets) are kept in
// NVS, so the setup is the same after power-on.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define PWM_CHANNELS        16
#define PRESSURE_SENSORS    2

typedef struct {
    uint8_t mode_a, pullup_a, mode_b, pullup_b;     // mode bit 1: input (the MCP23017's IODIR)
    uint8_t out_a, out_b;
} mcp23017_cfg_t;

typedef enum { PWM_SERVO, PWM_RAW } pwm_mode_t;

typedef struct {
    pwm_mode_t mode;
    uint16_t min_us, max_us;    // servo: the pulse for 0 and for 1
} pwm_channel_cfg_t;

typedef struct {
    bool mcp_ok;
    uint8_t gpio_a, gpio_b;     // the pins' levels
    mcp23017_cfg_t mcp;

    bool pca_ok;
    float pwm_hz;
    pwm_channel_cfg_t pwm[PWM_CHANNELS];
    int16_t pwm_us[PWM_CHANNELS];       // servo pulse, or -1
    float pwm_duty[PWM_CHANNELS];       // 0..1 (both modes); -1: off (never set since power-on)

    bool tca_ok;
    bool pressure_ok[PRESSURE_SENSORS];
    float pressure_bar[PRESSURE_SENSORS];  // gauge pressure, zero offset applied
    float pressure_hz;
} i2cbus_t;

void i2cbus_start(void);
void i2cbus_get(i2cbus_t *out);

// Setters: false (and nothing changes) when the part is absent or a value is out of range.
bool i2cbus_mcp_set(const mcp23017_cfg_t *cfg);
bool i2cbus_pwm_set_us(int ch, int us);             // 100..5000 us
bool i2cbus_pwm_set_value(int ch, float v);         // 0..1: servo between min and max, raw: duty cycle
bool i2cbus_pwm_off(int ch);
bool i2cbus_pwm_set_cfg(int ch, const pwm_channel_cfg_t *cfg);
bool i2cbus_pwm_set_hz(float hz);                   // 24..1500
bool i2cbus_pressure_zero(int sensor);              // the current reading becomes 0
