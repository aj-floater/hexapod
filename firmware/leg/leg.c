#include <stdio.h>

#include "pico/stdlib.h"

#include "adc_pot.h"
#include "motor_pwm.h"
#include "telemetry.h"

// Potentiometer ADC mapping (servo angle feedback).
#define POT_A_GPIO 26
#define POT_B_GPIO 27
#define POT_C_GPIO 28

// DRV8837 IN1/IN2 mapping.
#define MOTOR_A_IN1_GPIO 18
#define MOTOR_A_IN2_GPIO 19
#define MOTOR_B_IN1_GPIO 12
#define MOTOR_B_IN2_GPIO 13
#define MOTOR_C_IN1_GPIO 22
#define MOTOR_C_IN2_GPIO 23

#define MOTOR_PWM_HZ 20000u
#define ADC_LOG_PERIOD_MS 20u

typedef struct {
    AdcPot a;
    AdcPot b;
    AdcPot c;
} AdcBank;

typedef struct {
    MotorPwm a;
    MotorPwm b;
    MotorPwm c;
} MotorBank;

static AdcBank g_adc_bank;
static MotorBank g_motor_bank;

static void init_adc_bank(AdcBank *bank) {
    adc_pot_system_init();
    adc_pot_init(&bank->a, "adc_a", POT_A_GPIO);
    adc_pot_init(&bank->b, "adc_b", POT_B_GPIO);
    adc_pot_init(&bank->c, "adc_c", POT_C_GPIO);
}

static void init_motor_bank(MotorBank *bank) {
    motor_pwm_init(&bank->a, "motor_a", MOTOR_A_IN1_GPIO, MOTOR_A_IN2_GPIO, MOTOR_PWM_HZ);
    motor_pwm_init(&bank->b, "motor_b", MOTOR_B_IN1_GPIO, MOTOR_B_IN2_GPIO, MOTOR_PWM_HZ);
    motor_pwm_init(&bank->c, "motor_c", MOTOR_C_IN1_GPIO, MOTOR_C_IN2_GPIO, MOTOR_PWM_HZ);

    motor_pwm_coast(&bank->a);
    motor_pwm_coast(&bank->b);
    motor_pwm_coast(&bank->c);
}

int main(void) {
    stdio_init_all();
    init_adc_bank(&g_adc_bank);
    init_motor_bank(&g_motor_bank);

    Telemetry telemetry;
    telemetry_init(&telemetry, ADC_LOG_PERIOD_MS);

    while (true) {
        TelemetrySample sample;

        if (telemetry_try_sample_three(
                &telemetry,
                &g_adc_bank.a,
                &g_adc_bank.b,
                &g_adc_bank.c,
                &sample
            )) {
            telemetry_print_plotter_line(&sample);
        }

        tight_loop_contents();
    }
}
