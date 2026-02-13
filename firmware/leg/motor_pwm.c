#include "motor_pwm.h"

#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "pico/stdlib.h"

#define PWM_WRAP_DEFAULT 999u

static uint8_t normalize_duty(uint8_t duty_percent) {
    if (duty_percent > 100u) {
        return 100u;
    }
    return duty_percent;
}

static uint16_t duty_to_level(const MotorPwm *motor, uint8_t duty_percent) {
    uint8_t normalized = normalize_duty(duty_percent);
    return (uint16_t)(((uint32_t)normalized * motor->wrap) / 100u);
}

static void motor_pwm_coast_impl(MotorPwm *self) {
    pwm_set_gpio_level(self->in1_gpio, 0u);
    pwm_set_gpio_level(self->in2_gpio, 0u);
}

static void motor_pwm_brake_impl(MotorPwm *self) {
    uint16_t high_level = (uint16_t)(self->wrap + 1u);
    pwm_set_gpio_level(self->in1_gpio, high_level);
    pwm_set_gpio_level(self->in2_gpio, high_level);
}

static void motor_pwm_set_forward_duty_impl(MotorPwm *self, uint8_t duty_percent) {
    pwm_set_gpio_level(self->in1_gpio, duty_to_level(self, duty_percent));
    pwm_set_gpio_level(self->in2_gpio, 0u);
}

static void motor_pwm_set_reverse_duty_impl(MotorPwm *self, uint8_t duty_percent) {
    pwm_set_gpio_level(self->in1_gpio, 0u);
    pwm_set_gpio_level(self->in2_gpio, duty_to_level(self, duty_percent));
}

static const MotorPwmOps k_motor_pwm_ops = {
    .coast = motor_pwm_coast_impl,
    .brake = motor_pwm_brake_impl,
    .set_forward_duty = motor_pwm_set_forward_duty_impl,
    .set_reverse_duty = motor_pwm_set_reverse_duty_impl,
};

void motor_pwm_init(
    MotorPwm *motor,
    const char *name,
    uint in1_gpio,
    uint in2_gpio,
    uint32_t pwm_hz
) {
    hard_assert(motor != NULL);
    hard_assert(pwm_hz > 0u);

    uint in1_slice = pwm_gpio_to_slice_num(in1_gpio);
    uint in2_slice = pwm_gpio_to_slice_num(in2_gpio);
    hard_assert(in1_slice == in2_slice);

    motor->name = name;
    motor->in1_gpio = in1_gpio;
    motor->in2_gpio = in2_gpio;
    motor->slice_num = in1_slice;
    motor->wrap = PWM_WRAP_DEFAULT;
    motor->ops = &k_motor_pwm_ops;

    uint32_t sys_hz = clock_get_hz(clk_sys);
    float clkdiv = (float)sys_hz / ((float)pwm_hz * (float)(motor->wrap + 1u));
    if (clkdiv < 1.0f) {
        clkdiv = 1.0f;
    }
    if (clkdiv > 255.0f) {
        clkdiv = 255.0f;
    }
    motor->clkdiv = clkdiv;

    gpio_init(in1_gpio);
    gpio_set_dir(in1_gpio, GPIO_OUT);
    gpio_put(in1_gpio, 0);

    gpio_init(in2_gpio);
    gpio_set_dir(in2_gpio, GPIO_OUT);
    gpio_put(in2_gpio, 0);

    gpio_set_function(in1_gpio, GPIO_FUNC_PWM);
    gpio_set_function(in2_gpio, GPIO_FUNC_PWM);

    pwm_config cfg = pwm_get_default_config();
    pwm_config_set_wrap(&cfg, motor->wrap);
    pwm_config_set_clkdiv(&cfg, motor->clkdiv);
    pwm_init(motor->slice_num, &cfg, true);

    motor_pwm_coast(motor);
}

void motor_pwm_coast(MotorPwm *motor) {
    hard_assert(motor != NULL);
    motor->ops->coast(motor);
}

void motor_pwm_brake(MotorPwm *motor) {
    hard_assert(motor != NULL);
    motor->ops->brake(motor);
}

void motor_pwm_set_forward_duty(MotorPwm *motor, uint8_t duty_percent) {
    hard_assert(motor != NULL);
    motor->ops->set_forward_duty(motor, duty_percent);
}

void motor_pwm_set_reverse_duty(MotorPwm *motor, uint8_t duty_percent) {
    hard_assert(motor != NULL);
    motor->ops->set_reverse_duty(motor, duty_percent);
}
