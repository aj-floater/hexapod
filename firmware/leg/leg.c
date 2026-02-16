#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"

#include "adc_pot.h"
#include "motor_pwm.h"
#include "pio_uart_rx.h"
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
#define OPEN_LOOP_SAMPLE_PERIOD_MS 20u
#define OPEN_LOOP_PRE_STEP_MS 500u
#define OPEN_LOOP_DEFAULT_DUTY_PCT 60u
#define OPEN_LOOP_DEFAULT_STEP_MS 2000u
#define OPEN_LOOP_MIN_STEP_MS 100u
#define OPEN_LOOP_MAX_STEP_MS 10000u
#define CMD_BUFFER_LEN 64u
#define CMD_IDLE_FLUSH_MS 80u
#define STATUS_LED_GPIO 25u
#define RX_LED_PULSE_MS 40u
#define COMMAND_RX_GPIO 3u
#define COMMAND_BAUD 115200u

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

typedef struct {
    char data[CMD_BUFFER_LEN];
    uint32_t len;
    absolute_time_t flush_at;
} UartLineBuffer;

typedef struct {
    uint8_t duty_pct;
    uint32_t step_ms;
    bool reverse;
} OpenLoopStartCommand;

typedef struct {
    bool active;
    bool reverse;
    bool step_applied;
    uint8_t duty_pct;
    uint32_t step_ms;
    uint64_t started_at_us;
    absolute_time_t step_starts_at;
    absolute_time_t ends_at;
    Telemetry sample_timer;
} OpenLoopTest;

static AdcBank g_adc_bank;
static MotorBank g_motor_bank;
static bool g_rx_led_active;
static absolute_time_t g_rx_led_deadline;

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

static void init_status_led(void) {
    gpio_init(STATUS_LED_GPIO);
    gpio_set_dir(STATUS_LED_GPIO, GPIO_OUT);
    gpio_put(STATUS_LED_GPIO, 0);
    g_rx_led_active = false;
    g_rx_led_deadline = get_absolute_time();
}

static void rx_led_note_byte(void) {
    gpio_put(STATUS_LED_GPIO, 1);
    g_rx_led_active = true;
    g_rx_led_deadline = make_timeout_time_ms(RX_LED_PULSE_MS);
}

static void rx_led_tick(void) {
    if (!g_rx_led_active) {
        return;
    }
    if (time_reached(g_rx_led_deadline)) {
        gpio_put(STATUS_LED_GPIO, 0);
        g_rx_led_active = false;
    }
}

static uint32_t clamp_u32(uint32_t value, uint32_t min_value, uint32_t max_value) {
    if (value < min_value) {
        return min_value;
    }
    if (value > max_value) {
        return max_value;
    }
    return value;
}

static bool str_equals_ignore_case(const char *lhs, const char *rhs) {
    while (*lhs != '\0' && *rhs != '\0') {
        if (toupper((unsigned char)*lhs) != toupper((unsigned char)*rhs)) {
            return false;
        }
        lhs++;
        rhs++;
    }
    return *lhs == '\0' && *rhs == '\0';
}

static void normalize_command_line(const char *line, char *out_line, uint32_t out_size) {
    hard_assert(line != NULL);
    hard_assert(out_line != NULL);
    hard_assert(out_size > 0u);

    uint32_t out_len = 0u;
    bool previous_was_space = true;

    for (uint32_t i = 0u; line[i] != '\0' && out_len < (out_size - 1u); i++) {
        char ch = line[i];
        bool is_delimiter = (ch == ',') || isspace((unsigned char)ch);

        if (is_delimiter) {
            if (!previous_was_space) {
                out_line[out_len++] = ' ';
                previous_was_space = true;
            }
            continue;
        }

        out_line[out_len++] = ch;
        previous_was_space = false;
    }

    if (out_len > 0u && out_line[out_len - 1u] == ' ') {
        out_len--;
    }
    out_line[out_len] = '\0';
}

static bool parse_open_loop_start_command(const char *line, OpenLoopStartCommand *out_cmd) {
    char normalized[CMD_BUFFER_LEN] = {0};
    char command[16] = {0};
    unsigned int duty_pct = OPEN_LOOP_DEFAULT_DUTY_PCT;
    unsigned int step_ms = OPEN_LOOP_DEFAULT_STEP_MS;
    char direction = 'F';

    normalize_command_line(line, normalized, CMD_BUFFER_LEN);
    if (normalized[0] == '\0') {
        return false;
    }

    if (
        normalized[1] == '\0'
        && (normalized[0] == 'S' || normalized[0] == 's')
    ) {
        out_cmd->duty_pct = OPEN_LOOP_DEFAULT_DUTY_PCT;
        out_cmd->step_ms = OPEN_LOOP_DEFAULT_STEP_MS;
        out_cmd->reverse = false;
        return true;
    }

    int fields = sscanf(normalized, "%15s %u %u %c", command, &duty_pct, &step_ms, &direction);
    if (fields < 1) {
        return false;
    }
    if (!str_equals_ignore_case(command, "START") && !str_equals_ignore_case(command, "S")) {
        return false;
    }
    if (fields < 2) {
        duty_pct = OPEN_LOOP_DEFAULT_DUTY_PCT;
    }
    if (fields < 3) {
        step_ms = OPEN_LOOP_DEFAULT_STEP_MS;
    }
    if (fields < 4) {
        direction = 'F';
    }

    duty_pct = clamp_u32(duty_pct, 0u, 100u);
    step_ms = clamp_u32(step_ms, OPEN_LOOP_MIN_STEP_MS, OPEN_LOOP_MAX_STEP_MS);
    direction = (char)toupper((unsigned char)direction);
    if (direction != 'F' && direction != 'R') {
        return false;
    }

    out_cmd->duty_pct = (uint8_t)duty_pct;
    out_cmd->step_ms = (uint32_t)step_ms;
    out_cmd->reverse = direction == 'R';
    return true;
}

static bool uart_try_read_line(
    PioUartRx *command_rx,
    UartLineBuffer *buffer,
    char *out_line,
    uint32_t out_line_size
) {
    hard_assert(command_rx != NULL);
    hard_assert(buffer != NULL);
    hard_assert(out_line != NULL);
    hard_assert(out_line_size > 0u);

    uint8_t received_byte = 0u;
    while (pio_uart_rx_try_getc(command_rx, &received_byte)) {
        int ch = (int)received_byte;
        rx_led_note_byte();

        if (ch == '\r' || ch == '\n') {
            if (buffer->len > 0u) {
                uint32_t copy_len = buffer->len;
                if (copy_len >= out_line_size) {
                    copy_len = out_line_size - 1u;
                }
                memcpy(out_line, buffer->data, copy_len);
                out_line[copy_len] = '\0';
                buffer->len = 0u;
                return true;
            }
        } else if (ch == 8 || ch == 127) {
            if (buffer->len > 0u) {
                buffer->len--;
            }
            buffer->flush_at = make_timeout_time_ms(CMD_IDLE_FLUSH_MS);
        } else if (isprint((unsigned char)ch) && buffer->len < (CMD_BUFFER_LEN - 1u)) {
            buffer->data[buffer->len] = (char)ch;
            buffer->len++;
            buffer->flush_at = make_timeout_time_ms(CMD_IDLE_FLUSH_MS);
        }

    }

    if (buffer->len > 0u && time_reached(buffer->flush_at)) {
        uint32_t copy_len = buffer->len;
        if (copy_len >= out_line_size) {
            copy_len = out_line_size - 1u;
        }
        memcpy(out_line, buffer->data, copy_len);
        out_line[copy_len] = '\0';
        buffer->len = 0u;
        return true;
    }

    return false;
}

static void open_loop_test_start(
    OpenLoopTest *test,
    MotorPwm *motor_c,
    const OpenLoopStartCommand *command
) {
    hard_assert(test != NULL);
    hard_assert(motor_c != NULL);
    hard_assert(command != NULL);

    motor_pwm_coast(motor_c);

    test->active = true;
    test->reverse = command->reverse;
    test->step_applied = false;
    test->duty_pct = command->duty_pct;
    test->step_ms = command->step_ms;
    test->started_at_us = time_us_64();
    test->step_starts_at = make_timeout_time_ms(OPEN_LOOP_PRE_STEP_MS);
    test->ends_at = make_timeout_time_ms(OPEN_LOOP_PRE_STEP_MS + test->step_ms);
    telemetry_init(&test->sample_timer, OPEN_LOOP_SAMPLE_PERIOD_MS);
}

static void open_loop_test_stop(OpenLoopTest *test, MotorPwm *motor_c) {
    hard_assert(test != NULL);
    hard_assert(motor_c != NULL);

    motor_pwm_coast(motor_c);
    test->active = false;
}

static void open_loop_test_tick(OpenLoopTest *test, MotorPwm *motor_c, AdcPot *adc_c) {
    hard_assert(test != NULL);
    hard_assert(motor_c != NULL);
    hard_assert(adc_c != NULL);

    if (!test->active) {
        return;
    }

    if (!test->step_applied && time_reached(test->step_starts_at)) {
        if (test->reverse) {
            motor_pwm_set_reverse_duty(motor_c, test->duty_pct);
        } else {
            motor_pwm_set_forward_duty(motor_c, test->duty_pct);
        }
        test->step_applied = true;
    }

    if (time_reached(test->ends_at)) {
        printf("DONE\r\n");
        open_loop_test_stop(test, motor_c);
        return;
    }

    uint16_t adc_c_raw = 0u;
    uint64_t sample_us = 0u;
    if (!telemetry_try_sample_one(&test->sample_timer, adc_c, &adc_c_raw, &sample_us)) {
        return;
    }

    uint8_t ref_pwm_pct = test->step_applied ? test->duty_pct : 0u;
    uint16_t ref_step_adc = (uint16_t)(((uint32_t)ref_pwm_pct * ADC_POT_MAX_RAW) / 100u);
    uint32_t t_ms = (uint32_t)((sample_us - test->started_at_us) / 1000u);

    // VS Code Serial Plotter format.
    printf(
        ">ref_step_adc:%u,adc_c_raw:%u,ref_pwm_pct:%u,t_ms:%u\r\n",
        ref_step_adc,
        adc_c_raw,
        ref_pwm_pct,
        t_ms
    );
}

int main(void) {
    stdio_init_all();
    init_status_led();
    sleep_ms(1200u);
    init_adc_bank(&g_adc_bank);
    init_motor_bank(&g_motor_bank);

    PioUartRx command_rx = {0};
    if (!pio_uart_rx_init(&command_rx, pio0, COMMAND_RX_GPIO, COMMAND_BAUD)) {
        printf("ERR: PIO RX init failed\r\n");
        while (true) {
            rx_led_tick();
            tight_loop_contents();
        }
    }

    OpenLoopTest test = {0};
    UartLineBuffer command_buffer = {0};
    char command_line[CMD_BUFFER_LEN] = {0};
    command_buffer.flush_at = make_timeout_time_ms(CMD_IDLE_FLUSH_MS);

    printf("READY: send START,duty,step_ms,F|R or S\r\n");

    while (true) {
        if (!test.active && uart_try_read_line(
                &command_rx,
                &command_buffer,
                command_line,
                CMD_BUFFER_LEN
            )) {
            OpenLoopStartCommand command;
            printf("RX: %s\r\n", command_line);
            if (parse_open_loop_start_command(command_line, &command)) {
                printf(
                    "ACK: duty_pct=%u step_ms=%u dir=%c\r\n",
                    command.duty_pct,
                    command.step_ms,
                    command.reverse ? 'R' : 'F'
                );
                open_loop_test_start(&test, &g_motor_bank.c, &command);
            } else {
                printf("ERR: expected START,duty,step_ms,F|R or S\r\n");
            }
        }

        open_loop_test_tick(&test, &g_motor_bank.c, &g_adc_bank.c);
        rx_led_tick();
        tight_loop_contents();
    }
}
