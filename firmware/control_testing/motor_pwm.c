#include "motor_pwm.h"

#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "pico/stdlib.h"

// Constants
#define MOTOR_PWM_WRAP_DEFAULT 999u

// Clamps duty to a valid percentage.
static uint8_t motor_pwm_bound_duty(uint8_t duty_percent) {
    if (duty_percent > 100u) {
        return 100u;
    }

    return duty_percent;
}

// Converts duty percent into a PWM level.
static uint16_t motor_pwm_duty_to_level(const MotorPwm *motor, uint8_t duty_percent) {
    uint8_t bounded_duty = motor_pwm_bound_duty(duty_percent);
    return (uint16_t)(((uint32_t)bounded_duty * motor->wrap) / 100u);
}

// Configures one H-bridge PWM pair.
void motor_pwm_init(
    MotorPwm *motor,
    const char *name,
    uint in1_gpio,
    uint in2_gpio,
    uint32_t pwm_hz
) {
    uint in1_slice = 0u;
    uint in2_slice = 0u;
    uint32_t sys_hz = 0u;

    hard_assert(motor != NULL);
    hard_assert(pwm_hz > 0u);

    in1_slice = pwm_gpio_to_slice_num(in1_gpio);
    in2_slice = pwm_gpio_to_slice_num(in2_gpio);
    hard_assert(in1_slice == in2_slice);

    motor->name = name;
    motor->in1_gpio = in1_gpio;
    motor->in2_gpio = in2_gpio;
    motor->slice_num = in1_slice;
    motor->wrap = MOTOR_PWM_WRAP_DEFAULT;

    sys_hz = clock_get_hz(clk_sys);
    motor->clkdiv = (float)sys_hz / ((float)pwm_hz * (float)(motor->wrap + 1u));
    if (motor->clkdiv < 1.0f) {
        motor->clkdiv = 1.0f;
    }
    if (motor->clkdiv > 255.0f) {
        motor->clkdiv = 255.0f;
    }

    gpio_init(in1_gpio);
    gpio_set_dir(in1_gpio, GPIO_OUT);
    gpio_put(in1_gpio, 0);

    gpio_init(in2_gpio);
    gpio_set_dir(in2_gpio, GPIO_OUT);
    gpio_put(in2_gpio, 0);

    gpio_set_function(in1_gpio, GPIO_FUNC_PWM);
    gpio_set_function(in2_gpio, GPIO_FUNC_PWM);

    {
        pwm_config cfg = pwm_get_default_config();
        pwm_config_set_wrap(&cfg, motor->wrap);
        pwm_config_set_clkdiv(&cfg, motor->clkdiv);
        pwm_init(motor->slice_num, &cfg, true);
    }

    motor_pwm_coast(motor);
}

// Releases both motor outputs.
void motor_pwm_coast(MotorPwm *motor) {
    hard_assert(motor != NULL);

    pwm_set_gpio_level(motor->in1_gpio, 0u);
    pwm_set_gpio_level(motor->in2_gpio, 0u);
}

// Actively brakes the motor.
void motor_pwm_brake(MotorPwm *motor) {
    uint16_t high_level = 0u;

    hard_assert(motor != NULL);

    high_level = (uint16_t)(motor->wrap + 1u);
    pwm_set_gpio_level(motor->in1_gpio, high_level);
    pwm_set_gpio_level(motor->in2_gpio, high_level);
}

// Drives the motor forward.
void motor_pwm_set_forward_duty(MotorPwm *motor, uint8_t duty_percent) {
    hard_assert(motor != NULL);

    pwm_set_gpio_level(motor->in1_gpio, 0u);
    pwm_set_gpio_level(motor->in2_gpio, motor_pwm_duty_to_level(motor, duty_percent));
}

// Drives the motor in reverse.
void motor_pwm_set_reverse_duty(MotorPwm *motor, uint8_t duty_percent) {
    hard_assert(motor != NULL);

    pwm_set_gpio_level(motor->in1_gpio, motor_pwm_duty_to_level(motor, duty_percent));
    pwm_set_gpio_level(motor->in2_gpio, 0u);
}
