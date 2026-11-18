// The parts on plain GPIO pins: the L298N motor driver, the motor's quadrature encoder, the HC-SR04 ultrasonic sensor
// and the HX711 load cell amplifier.
//
// Nothing here waits on a part: the encoder is counted by the PCNT peripheral, the ultrasonic echo is timed by a pin
// interrupt, and the HX711 is only read once it says a sample is ready. A part that doesn't answer shows "ok":false.
//
// Motor modes:
//   direct  IN1 and IN2 set by hand (both low: coasting; both high: braking)
//   api     a speed -1..1 (PWM on one input, the other low)
//   pot     follows the potentiometer (MCP3008 channel 7): 1.65 V stop, 0 V full reverse, 3.3 V full forward
// The mode and which way "forward" turns are kept in NVS. Pot mode runs without anyone in control, so the setup
// shows something at power-on; in direct and api mode the motor stops when control ends (gpioparts_stop).
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum { MOTOR_DIRECT, MOTOR_API, MOTOR_POT } motor_mode_t;

typedef struct {
    motor_mode_t motor_mode;
    bool motor_ccw;             // "forward" is counterclockwise (as the PlatformIO firmware's default)
    bool in1, in2;              // direct mode
    float speed;                // -1..1: what the motor gets now (any mode)

    int32_t enc_count;          // quadrature steps (4 per encoder line)
    uint8_t enc_ab;             // bit 0: A, bit 1: B
    float enc_steps_s;

    bool us_ok;                 // an echo within range
    float us_mm;
    float us_hz;

    bool hx_ok;
    float hx_units;             // (raw - tare) / 7050, as the PlatformIO firmware ("grams" there)
    int32_t hx_raw;
    float hx_hz;
} gpioparts_t;

void gpioparts_start(void);
void gpioparts_get(gpioparts_t *out);

bool gpioparts_motor_mode(motor_mode_t mode);
bool gpioparts_motor_ccw(bool ccw);
bool gpioparts_motor_direct(bool in1, bool in2);   // switches to direct mode
bool gpioparts_motor_speed(float speed);           // -1..1; switches to api mode
void gpioparts_stop(void);                         // control ended: stop unless in pot mode
void gpioparts_encoder_zero(void);
bool gpioparts_loadcell_tare(void);
