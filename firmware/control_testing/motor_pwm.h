#ifndef MOTOR_PWM_H
#define MOTOR_PWM_H

#include <stdint.h>

#include "pico/types.h"

// Types
typedef struct {
    const char *name;
    uint in1_gpio;
    uint in2_gpio;
    uint slice_num;
    uint16_t wrap;
    float clkdiv;
} MotorPwm;

// Setup
void motor_pwm_init(
    MotorPwm *motor,
    const char *name,
    uint in1_gpio,
    uint in2_gpio,
    uint32_t pwm_hz
);

// Stop
void motor_pwm_coast(MotorPwm *motor);
void motor_pwm_brake(MotorPwm *motor);

// Drive
void motor_pwm_set_forward_duty(MotorPwm *motor, uint8_t duty_percent);
void motor_pwm_set_reverse_duty(MotorPwm *motor, uint8_t duty_percent);

#endif
