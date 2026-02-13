#ifndef MOTOR_PWM_H
#define MOTOR_PWM_H

#include <stdint.h>
#include "pico/types.h"

typedef struct MotorPwm MotorPwm;

typedef struct {
    void (*coast)(MotorPwm *self);
    void (*brake)(MotorPwm *self);
    void (*set_forward_duty)(MotorPwm *self, uint8_t duty_percent);
    void (*set_reverse_duty)(MotorPwm *self, uint8_t duty_percent);
} MotorPwmOps;

struct MotorPwm {
    const char *name;
    uint in1_gpio;
    uint in2_gpio;
    uint slice_num;
    uint16_t wrap;
    float clkdiv;
    const MotorPwmOps *ops;
};

void motor_pwm_init(
    MotorPwm *motor,
    const char *name,
    uint in1_gpio,
    uint in2_gpio,
    uint32_t pwm_hz
);

void motor_pwm_coast(MotorPwm *motor);
void motor_pwm_brake(MotorPwm *motor);
void motor_pwm_set_forward_duty(MotorPwm *motor, uint8_t duty_percent);
void motor_pwm_set_reverse_duty(MotorPwm *motor, uint8_t duty_percent);

#endif
