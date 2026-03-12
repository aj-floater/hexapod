#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "pico/time.h"

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
#define POSITION_CONTROLLER_UPDATE_MS 5u
#define POSITION_PLOT_SAMPLE_MS 20u
#define POSITION_STEP_DELAY_MS 1000u
#define POSITION_HOLD_RUN_TIME_MS 10000u
#define POSITION_SETPOINT_ADC 2600u
#define POSITION_HOLD_DEADBAND_ADC 60u
#define POSITION_P_MIN_OUTPUT_PCT 20u
#define POSITION_P_MAX_OUTPUT_PCT 60u
// P controller output = min_output + |position error| / POSITION_P_ERROR_TO_OUTPUT_DIVISOR.
#define POSITION_P_ERROR_TO_OUTPUT_DIVISOR 16u
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
    bool start;
    bool stop;
} PositionCommand;

typedef struct {
    bool active;
    bool hold_enabled;
    uint16_t baseline_target_adc;
    uint16_t active_target_adc;
    uint16_t latest_position_adc;
    int16_t telemetry_drive_pct;
    uint64_t started_at_us;
    absolute_time_t next_control_at;
    absolute_time_t hold_starts_at;
    absolute_time_t ends_at;
    Telemetry sample_timer;
} PositionHoldDemo;

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

static bool parse_position_command(const char *line, PositionCommand *out_cmd) {
    char normalized[CMD_BUFFER_LEN] = {0};
    char command[16] = {0};

    hard_assert(line != NULL);
    hard_assert(out_cmd != NULL);

    out_cmd->start = false;
    out_cmd->stop = false;

    normalize_command_line(line, normalized, CMD_BUFFER_LEN);
    if (normalized[0] == '\0') {
        return false;
    }

    if (normalized[1] == '\0' && (normalized[0] == 'S' || normalized[0] == 's')) {
        out_cmd->start = true;
        return true;
    }
    if (normalized[1] == '\0' && (normalized[0] == 'X' || normalized[0] == 'x')) {
        out_cmd->stop = true;
        return true;
    }

    int fields = sscanf(normalized, "%15s", command);
    if (fields != 1) {
        return false;
    }

    if (str_equals_ignore_case(command, "START") || str_equals_ignore_case(command, "S")) {
        out_cmd->start = true;
        return true;
    }
    if (str_equals_ignore_case(command, "STOP") || str_equals_ignore_case(command, "X")) {
        out_cmd->stop = true;
        return true;
    }

    return false;
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

static uint16_t position_compute_drive_duty(uint16_t error_magnitude) {
    uint16_t duty_pct = (uint16_t)(
        POSITION_P_MIN_OUTPUT_PCT + (error_magnitude / POSITION_P_ERROR_TO_OUTPUT_DIVISOR)
    );
    if (duty_pct > POSITION_P_MAX_OUTPUT_PCT) {
        return POSITION_P_MAX_OUTPUT_PCT;
    }
    return duty_pct;
}

static void position_hold_demo_stop(PositionHoldDemo *demo, MotorPwm *motor_c, AdcPot *adc_c) {
    hard_assert(demo != NULL);
    hard_assert(motor_c != NULL);
    hard_assert(adc_c != NULL);

    demo->latest_position_adc = adc_pot_read_raw(adc_c);
    demo->baseline_target_adc = demo->latest_position_adc;
    demo->active_target_adc = demo->latest_position_adc;
    demo->telemetry_drive_pct = 0;
    demo->hold_enabled = false;
    demo->active = false;
    motor_pwm_brake(motor_c);
}

static void position_hold_demo_start(PositionHoldDemo *demo, MotorPwm *motor_c, AdcPot *adc_c) {
    hard_assert(demo != NULL);
    hard_assert(motor_c != NULL);
    hard_assert(adc_c != NULL);

    uint16_t initial_position_adc = adc_pot_read_raw(adc_c);

    motor_pwm_coast(motor_c);
    demo->active = true;
    demo->hold_enabled = false;
    demo->baseline_target_adc = initial_position_adc;
    demo->active_target_adc = initial_position_adc;
    demo->latest_position_adc = initial_position_adc;
    demo->telemetry_drive_pct = 0;
    demo->started_at_us = time_us_64();
    demo->next_control_at = get_absolute_time();
    demo->hold_starts_at = make_timeout_time_ms(POSITION_STEP_DELAY_MS);
    demo->ends_at = make_timeout_time_ms(POSITION_HOLD_RUN_TIME_MS);
    telemetry_init(&demo->sample_timer, POSITION_PLOT_SAMPLE_MS);
}

static void position_hold_demo_tick(PositionHoldDemo *demo, MotorPwm *motor_c, AdcPot *adc_c) {
    hard_assert(demo != NULL);
    hard_assert(motor_c != NULL);
    hard_assert(adc_c != NULL);

    if (!demo->active) {
        return;
    }

    if (time_reached(demo->ends_at)) {
        printf("DONE\r\n");
        position_hold_demo_stop(demo, motor_c, adc_c);
        return;
    }

    if (time_reached(demo->next_control_at)) {
        demo->latest_position_adc = adc_pot_read_raw(adc_c);

                if (!demo->hold_enabled && time_reached(demo->hold_starts_at)) {
                    demo->hold_enabled = true;
                    demo->active_target_adc = POSITION_SETPOINT_ADC;
                }

        if (!demo->hold_enabled) {
            demo->active_target_adc = demo->baseline_target_adc;
            demo->telemetry_drive_pct = 0;
            motor_pwm_coast(motor_c);
        } else {
            int32_t error = (int32_t)demo->active_target_adc - (int32_t)demo->latest_position_adc;
            uint32_t error_magnitude = (error >= 0) ? (uint32_t)error : (uint32_t)(-error);

            if (error_magnitude <= POSITION_HOLD_DEADBAND_ADC) {
                demo->telemetry_drive_pct = 0;
                motor_pwm_brake(motor_c);
            } else {
                uint16_t duty_pct = position_compute_drive_duty((uint16_t)error_magnitude);
                if (error > 0) {
                    motor_pwm_set_forward_duty(motor_c, (uint8_t)duty_pct);
                    demo->telemetry_drive_pct = (int16_t)duty_pct;
                } else {
                    motor_pwm_set_reverse_duty(motor_c, (uint8_t)duty_pct);
                    demo->telemetry_drive_pct = (int16_t)(-((int16_t)duty_pct));
                }
            }
        }

        demo->next_control_at = make_timeout_time_ms(POSITION_CONTROLLER_UPDATE_MS);
    }

    uint16_t adc_c_raw = 0u;
    uint64_t sample_us = 0u;
    if (!telemetry_try_sample_one(&demo->sample_timer, adc_c, &adc_c_raw, &sample_us)) {
        return;
    }

    uint32_t t_ms = (uint32_t)((sample_us - demo->started_at_us) / 1000u);
    printf(
        ">setpoint_adc:%u,measured_adc:%u,control_output_pct:%d,t_ms:%u\r\n",
        demo->active_target_adc,
        adc_c_raw,
        demo->telemetry_drive_pct,
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

    PositionHoldDemo demo = {0};
    UartLineBuffer command_buffer = {0};
    char command_line[CMD_BUFFER_LEN] = {0};
    command_buffer.flush_at = make_timeout_time_ms(CMD_IDLE_FLUSH_MS);

    position_hold_demo_start(&demo, &g_motor_bank.c, &g_adc_bank.c);
    printf("READY: send START|S or STOP|X\r\n");

    while (true) {
        if (uart_try_read_line(
                &command_rx,
                &command_buffer,
                command_line,
                CMD_BUFFER_LEN
            )) {
            PositionCommand command;
            printf("RX: %s\r\n", command_line);
            if (parse_position_command(command_line, &command)) {
                if (command.start) {
                    printf("ACK: START setpoint_adc=%u\r\n", POSITION_SETPOINT_ADC);
                    position_hold_demo_start(&demo, &g_motor_bank.c, &g_adc_bank.c);
                } else if (command.stop) {
                    printf("ACK: STOP\r\n");
                    position_hold_demo_stop(&demo, &g_motor_bank.c, &g_adc_bank.c);
                }
            } else {
                printf("ERR: expected START|S or STOP|X\r\n");
            }
        }

        position_hold_demo_tick(&demo, &g_motor_bank.c, &g_adc_bank.c);
        rx_led_tick();
        tight_loop_contents();
    }
}
