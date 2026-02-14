#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "pico/multicore.h"
#include "pico/stdlib.h"
#include "pico/time.h"
#include "pico/util/queue.h"

#include "adc_pot.h"
#include "motor_pwm.h"

// Generated template examples retained for later use:
// #include "hardware/i2c.h"
// #include "hardware/uart.h"
//
// // I2C defines
// #define I2C_PORT i2c0
// #define I2C_SDA 8
// #define I2C_SCL 9
//
// // UART defines
// #define UART_ID uart1
// #define BAUD_RATE 115200
// #define UART_TX_PIN 4
// #define UART_RX_PIN 5

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
#define MAX_ON_TIME_MS 600u
#define TEST_ON_MS 400u
#define TEST_OFF_MS 1000u
#define TEST_DUTY_MIN 60u
#define TEST_DUTY_MAX 100u
#define TEST_DUTY_STEP 5u
#define ADC_LOG_PERIOD_MS 20u
#define TELEMETRY_QUEUE_DEPTH 64u
#define RUN_REVERSE_TEST 0

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

typedef enum {
    MOTOR_PHASE_ON,
    MOTOR_PHASE_OFF,
} MotorPhase;

typedef struct {
    bool reverse;
    MotorPhase phase;
    uint8_t duty_current;
    uint8_t duty_min;
    uint8_t duty_max;
    uint8_t duty_step;
    uint32_t on_ms;
    uint32_t off_ms;
    uint8_t telemetry_duty;
    absolute_time_t phase_deadline;
} MotorCTestTask;

typedef struct {
    uint32_t period_ms;
    absolute_time_t next_sample_at;
} TelemetryTask;

typedef struct {
    uint16_t adc_a;
    uint16_t adc_b;
    uint16_t adc_c;
    uint8_t duty_step;
    uint64_t time_us;
} TelemetrySample;

static AdcBank g_adc_bank;
static MotorBank g_motor_bank;
static queue_t g_telemetry_queue;

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

static uint32_t clamp_on_time_ms(uint32_t on_ms) {
    if (on_ms > MAX_ON_TIME_MS) {
        return MAX_ON_TIME_MS;
    }
    return on_ms;
}

static void motor_c_test_task_init(MotorCTestTask *task, bool reverse) {
    task->reverse = reverse;
    task->phase = MOTOR_PHASE_ON;
    task->duty_min = TEST_DUTY_MIN;
    task->duty_max = TEST_DUTY_MAX;
    task->duty_step = TEST_DUTY_STEP;
    task->duty_current = task->duty_min;
    task->on_ms = clamp_on_time_ms(TEST_ON_MS);
    task->off_ms = TEST_OFF_MS;
    task->telemetry_duty = 0u;
    task->phase_deadline = get_absolute_time();
}

static void motor_c_test_task_tick(MotorCTestTask *task, MotorBank *motors) {
    if (!time_reached(task->phase_deadline)) {
        return;
    }

    if (task->phase == MOTOR_PHASE_ON) {
        if (task->reverse) {
            motor_pwm_set_reverse_duty(&motors->c, task->duty_current);
        } else {
            motor_pwm_set_forward_duty(&motors->c, task->duty_current);
        }

        task->telemetry_duty = task->duty_current;
        task->phase = MOTOR_PHASE_OFF;
        task->phase_deadline = make_timeout_time_ms(task->on_ms);
        return;
    }

    motor_pwm_coast(&motors->c);
    task->telemetry_duty = 0u;

    if ((uint16_t)task->duty_current + (uint16_t)task->duty_step <= (uint16_t)task->duty_max) {
        task->duty_current = (uint8_t)(task->duty_current + task->duty_step);
    } else {
        task->duty_current = task->duty_min;
    }

    task->phase = MOTOR_PHASE_ON;
    task->phase_deadline = make_timeout_time_ms(task->off_ms);
}

static void telemetry_task_init(TelemetryTask *task, uint32_t period_ms) {
    task->period_ms = period_ms;
    task->next_sample_at = get_absolute_time();
}

static void telemetry_task_tick(TelemetryTask *task, AdcBank *adc_bank, uint8_t duty_step) {
    if (!time_reached(task->next_sample_at)) {
        return;
    }

    TelemetrySample sample;
    sample.adc_a = adc_pot_read_raw(&adc_bank->a);
    sample.adc_b = adc_pot_read_raw(&adc_bank->b);
    sample.adc_c = adc_pot_read_raw(&adc_bank->c);
    sample.duty_step = duty_step;
    sample.time_us = time_us_64();

    // Control loop never blocks on telemetry I/O.
    (void)queue_try_add(&g_telemetry_queue, &sample);

    task->next_sample_at = make_timeout_time_ms(task->period_ms);
}

static void core1_control_main(void) {
    MotorCTestTask motor_c_task;
    TelemetryTask telemetry_task;

#if RUN_REVERSE_TEST
    motor_c_test_task_init(&motor_c_task, true);
#else
    motor_c_test_task_init(&motor_c_task, false);
#endif
    telemetry_task_init(&telemetry_task, ADC_LOG_PERIOD_MS);

    while (true) {
        motor_c_test_task_tick(&motor_c_task, &g_motor_bank);
        telemetry_task_tick(&telemetry_task, &g_adc_bank, motor_c_task.telemetry_duty);
        tight_loop_contents();
    }
}

int main(void) {
    stdio_init_all();
    init_adc_bank(&g_adc_bank);
    init_motor_bank(&g_motor_bank);
    queue_init(&g_telemetry_queue, sizeof(TelemetrySample), TELEMETRY_QUEUE_DEPTH);

    multicore_launch_core1(core1_control_main);

    while (true) {
        TelemetrySample sample;
        queue_remove_blocking(&g_telemetry_queue, &sample);

        // VS Code Serial Plotter format.
        printf(
            ">adc_a_gpio26:%u,adc_b_gpio27:%u,adc_c_gpio28:%u,duty_step:%u,time_us:%llu\r\n",
            sample.adc_a,
            sample.adc_b,
            sample.adc_c,
            sample.duty_step,
            (unsigned long long)sample.time_us
        );
    }
}
