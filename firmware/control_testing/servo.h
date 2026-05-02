#ifndef SERVO_H
#define SERVO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "pico/types.h"

#include "adc_input.h"
#include "motor_pwm.h"
#include "position_hold.h"

#define SERVO_FILTER_ALPHA_DEFAULT_PCT 40u
#define SERVO_FILTER_ALPHA_MIN_PCT 1u
#define SERVO_FILTER_ALPHA_MAX_PCT 100u
#define SERVO_TENTHS_PER_DEG 10u

#define SERVO_MOTOR_STATE_COAST 0u
#define SERVO_MOTOR_STATE_BRAKE 1u
#define SERVO_MOTOR_STATE_FORWARD 2u
#define SERVO_MOTOR_STATE_REVERSE 3u

typedef struct {
    uint16_t deg;
    uint16_t raw;
} ServoCalibrationPoint;

typedef struct {
    char id;
    const char *motor_name;
    uint adc_gpio;
    uint motor_in1_gpio;
    uint motor_in2_gpio;
    uint8_t default_control_mode;
    float default_hold_p_gain;
    float default_hold_i_gain;
    float default_hold_d_gain;
    float min_angle_deg;
    float max_angle_deg;
    const ServoCalibrationPoint *calibration_points;
    size_t calibration_point_count;
} ServoConfig;

typedef struct {
    uint8_t filter_alpha_pct;
    float hold_target_deg;
    float hold_deadband_deg;
    float hold_p_gain;
    float hold_i_gain;
    float hold_d_gain;
    uint8_t hold_max_duty;
} ServoSettings;

typedef struct {
    uint16_t adc_raw;
    uint16_t adc_avg_raw;
    uint16_t adc_lp_raw;
    int16_t angle_avg_deg_tenths;
    int16_t angle_lp_deg_tenths;
    uint8_t motor_state;
    uint8_t motor_drive_pct;
    int16_t hold_output_pct;
} ServoTelemetry;

typedef struct {
    char id;
    AdcInput adc;
    MotorPwm motor;
    bool adc_lp_ready;
    bool boundary_override_active;
    bool boundary_override_low_side;
    uint8_t control_mode;
    uint8_t manual_motor_state;
    uint8_t manual_motor_drive_pct;
    ServoSettings settings;
    ServoTelemetry telemetry;
    PositionHoldState hold_state;
    PositionHoldState boundary_hold_state;
    float min_angle_deg;
    float max_angle_deg;
    const ServoCalibrationPoint *calibration_points;
    size_t calibration_point_count;
} Servo;

void servo_init(
    Servo *servo,
    const ServoConfig *config
);
void servo_tick(Servo *servo);
void servo_set_control_mode(Servo *servo, uint8_t mode);
void servo_set_motor_state(Servo *servo, uint8_t state);
void servo_set_motor_drive_pct(Servo *servo, uint8_t pct);
float servo_clamp_target_deg(const Servo *servo, float target_deg);

#endif
