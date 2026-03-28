#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "pico/time.h"

#include "adc_pot.h"
#include "hexapod_serial.h"
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
#define CMD_BUFFER_LEN 256u
#define CMD_IDLE_FLUSH_MS 80u
#define STATUS_LED_GPIO 25u
#define RX_LED_PULSE_MS 40u
#define COMMAND_RX_GPIO 3u
#define COMMAND_BAUD 115200u
#define DEVICE_ID "leg"
#define FIRMWARE_VERSION "0.1.0"
#define STREAM_POSITION "leg.position"

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
    bool overflowed;
    absolute_time_t flush_at;
} UartLineBuffer;

typedef struct {
    uint16_t setpoint_adc;
    uint16_t deadband_adc;
    uint8_t min_output_pct;
    uint8_t max_output_pct;
    uint16_t error_to_output_divisor;
} PositionControlConfig;

typedef struct {
    const char *name;
    const char *type;
    const char *access;
    int32_t default_value;
    int32_t min_value;
    int32_t max_value;
} ParamMetadata;

typedef enum {
    UART_READ_NONE = 0,
    UART_READ_LINE,
    UART_READ_OVERFLOW
} UartReadStatus;

typedef struct {
    bool active;
    bool hold_enabled;
    uint16_t baseline_target_adc;
    uint16_t active_target_adc;
    uint16_t latest_position_adc;
    int16_t telemetry_drive_pct;
    uint32_t sample_seq;
    uint64_t started_at_us;
    absolute_time_t next_control_at;
    absolute_time_t hold_starts_at;
    absolute_time_t ends_at;
    Telemetry sample_timer;
} PositionHoldDemo;

enum {
    PARAM_SETPOINT_ADC = 0,
    PARAM_DEADBAND_ADC,
    PARAM_MIN_OUTPUT_PCT,
    PARAM_MAX_OUTPUT_PCT,
    PARAM_ERROR_TO_OUTPUT_DIVISOR,
    PARAM_COUNT
};

static const ParamMetadata g_param_metadata[PARAM_COUNT] = {
    {"control.setpoint_adc", "u16", "rw", POSITION_SETPOINT_ADC, 0, ADC_POT_MAX_RAW},
    {"control.deadband_adc", "u16", "rw", POSITION_HOLD_DEADBAND_ADC, 0, ADC_POT_MAX_RAW},
    {"control.min_output_pct", "u8", "rw", POSITION_P_MIN_OUTPUT_PCT, 0, 100},
    {"control.max_output_pct", "u8", "rw", POSITION_P_MAX_OUTPUT_PCT, 0, 100},
    {
        "control.error_to_output_divisor",
        "u16",
        "rw",
        POSITION_P_ERROR_TO_OUTPUT_DIVISOR,
        1,
        ADC_POT_MAX_RAW
    },
};

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

static void uart_line_buffer_reset(UartLineBuffer *buffer) {
    hard_assert(buffer != NULL);

    buffer->len = 0u;
    buffer->overflowed = false;
    buffer->flush_at = make_timeout_time_ms(CMD_IDLE_FLUSH_MS);
}

static UartReadStatus uart_try_read_line(
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
            if (buffer->overflowed) {
                uart_line_buffer_reset(buffer);
                return UART_READ_OVERFLOW;
            }
            if (buffer->len > 0u) {
                uint32_t copy_len = buffer->len;
                if (copy_len >= out_line_size) {
                    copy_len = out_line_size - 1u;
                }
                memcpy(out_line, buffer->data, copy_len);
                out_line[copy_len] = '\0';
                uart_line_buffer_reset(buffer);
                return UART_READ_LINE;
            }
            continue;
        }

        if (ch == 8 || ch == 127) {
            if (!buffer->overflowed && buffer->len > 0u) {
                buffer->len--;
            }
            buffer->flush_at = make_timeout_time_ms(CMD_IDLE_FLUSH_MS);
            continue;
        }

        if (ch < 32 || ch > 126) {
            continue;
        }

        if (buffer->overflowed) {
            continue;
        }

        if (buffer->len >= (CMD_BUFFER_LEN - 1u)) {
            buffer->overflowed = true;
            continue;
        }

        buffer->data[buffer->len++] = (char)ch;
        buffer->flush_at = make_timeout_time_ms(CMD_IDLE_FLUSH_MS);
    }

    if ((buffer->len > 0u || buffer->overflowed) && time_reached(buffer->flush_at)) {
        if (buffer->overflowed) {
            uart_line_buffer_reset(buffer);
            return UART_READ_OVERFLOW;
        }

        uint32_t copy_len = buffer->len;
        if (copy_len >= out_line_size) {
            copy_len = out_line_size - 1u;
        }
        memcpy(out_line, buffer->data, copy_len);
        out_line[copy_len] = '\0';
        uart_line_buffer_reset(buffer);
        return UART_READ_LINE;
    }

    return UART_READ_NONE;
}

static void position_control_config_init_defaults(PositionControlConfig *config) {
    hard_assert(config != NULL);

    config->setpoint_adc = POSITION_SETPOINT_ADC;
    config->deadband_adc = POSITION_HOLD_DEADBAND_ADC;
    config->min_output_pct = POSITION_P_MIN_OUTPUT_PCT;
    config->max_output_pct = POSITION_P_MAX_OUTPUT_PCT;
    config->error_to_output_divisor = POSITION_P_ERROR_TO_OUTPUT_DIVISOR;
}

static int find_param_index(const char *param_name) {
    hard_assert(param_name != NULL);

    for (int i = 0; i < PARAM_COUNT; i++) {
        if (strcmp(param_name, g_param_metadata[i].name) == 0) {
            return i;
        }
    }

    return -1;
}

static int32_t read_param_value_by_index(const PositionControlConfig *config, int param_index) {
    hard_assert(config != NULL);

    switch (param_index) {
        case PARAM_SETPOINT_ADC:
            return config->setpoint_adc;
        case PARAM_DEADBAND_ADC:
            return config->deadband_adc;
        case PARAM_MIN_OUTPUT_PCT:
            return config->min_output_pct;
        case PARAM_MAX_OUTPUT_PCT:
            return config->max_output_pct;
        case PARAM_ERROR_TO_OUTPUT_DIVISOR:
            return config->error_to_output_divisor;
        default:
            return 0;
    }
}

static bool set_param_value_by_index(
    PositionControlConfig *config,
    int param_index,
    int32_t value,
    const char **out_error_code,
    const char **out_error_message
) {
    hard_assert(config != NULL);
    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    *out_error_code = NULL;
    *out_error_message = NULL;

    if (value < g_param_metadata[param_index].min_value || value > g_param_metadata[param_index].max_value) {
        *out_error_code = "value_out_of_range";
        *out_error_message = "param value outside allowed range";
        return false;
    }

    switch (param_index) {
        case PARAM_SETPOINT_ADC:
            config->setpoint_adc = (uint16_t)value;
            return true;
        case PARAM_DEADBAND_ADC:
            config->deadband_adc = (uint16_t)value;
            return true;
        case PARAM_MIN_OUTPUT_PCT:
            if (value > config->max_output_pct) {
                *out_error_code = "value_out_of_range";
                *out_error_message = "min_output_pct must be <= max_output_pct";
                return false;
            }
            config->min_output_pct = (uint8_t)value;
            return true;
        case PARAM_MAX_OUTPUT_PCT:
            if (value < config->min_output_pct) {
                *out_error_code = "value_out_of_range";
                *out_error_message = "max_output_pct must be >= min_output_pct";
                return false;
            }
            config->max_output_pct = (uint8_t)value;
            return true;
        case PARAM_ERROR_TO_OUTPUT_DIVISOR:
            config->error_to_output_divisor = (uint16_t)value;
            return true;
        default:
            *out_error_code = "unknown_param";
            *out_error_message = "unknown parameter";
            return false;
    }
}

static void print_capabilities(void) {
    printf(
        "{\"type\":\"capabilities\",\"version\":%u,\"device\":\"%s\",\"commands\":[",
        HEXAPOD_SERIAL_VERSION,
        DEVICE_ID
    );
    printf("{\"name\":\"demo.start\",\"args\":[]},");
    printf("{\"name\":\"demo.stop\",\"args\":[]},");
    printf("{\"name\":\"param.list\",\"args\":[]},");
    printf("{\"name\":\"param.get\",\"args\":[{\"name\":\"param\",\"type\":\"string\",\"required\":true}]},");
    printf(
        "{\"name\":\"param.set\",\"args\":["
        "{\"name\":\"param\",\"type\":\"string\",\"required\":true},"
        "{\"name\":\"value\",\"type\":\"integer\",\"required\":true}"
        "]}"
    );
    printf("],\"streams\":[");
    printf(
        "{\"name\":\"%s\",\"fields\":["
        "{\"name\":\"setpoint_adc\",\"type\":\"u16\",\"unit\":\"adc\"},"
        "{\"name\":\"measured_adc\",\"type\":\"u16\",\"unit\":\"adc\"},"
        "{\"name\":\"control_output_pct\",\"type\":\"i16\",\"unit\":\"pct\"}"
        "]}",
        STREAM_POSITION
    );
    printf("],\"params\":[");
    for (int i = 0; i < PARAM_COUNT; i++) {
        const ParamMetadata *metadata = &g_param_metadata[i];
        printf(
            "{\"name\":\"%s\",\"type\":\"%s\",\"access\":\"%s\",\"default\":%ld,\"min\":%ld,\"max\":%ld}%s",
            metadata->name,
            metadata->type,
            metadata->access,
            (long)metadata->default_value,
            (long)metadata->min_value,
            (long)metadata->max_value,
            (i + 1 == PARAM_COUNT) ? "" : ","
        );
    }
    printf("]}\r\n");
}

static void print_param_result(uint32_t id, const char *param_name, int32_t value) {
    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":true,"
        "\"result\":{\"param\":\"%s\",\"value\":%ld}}\r\n",
        HEXAPOD_SERIAL_VERSION,
        DEVICE_ID,
        (unsigned long)id,
        param_name,
        (long)value
    );
}

static void print_param_list_result(uint32_t id, const PositionControlConfig *config) {
    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":true,\"result\":{\"params\":[",
        HEXAPOD_SERIAL_VERSION,
        DEVICE_ID,
        (unsigned long)id
    );
    for (int i = 0; i < PARAM_COUNT; i++) {
        printf(
            "{\"name\":\"%s\",\"value\":%ld}%s",
            g_param_metadata[i].name,
            (long)read_param_value_by_index(config, i),
            (i + 1 == PARAM_COUNT) ? "" : ","
        );
    }
    printf("]}}\r\n");
}

static uint16_t position_compute_drive_duty(
    const PositionControlConfig *config,
    uint16_t error_magnitude
) {
    uint16_t duty_pct = (uint16_t)(
        config->min_output_pct + (error_magnitude / config->error_to_output_divisor)
    );

    if (duty_pct > config->max_output_pct) {
        return config->max_output_pct;
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
    demo->sample_seq = 0u;
    demo->started_at_us = time_us_64();
    demo->next_control_at = get_absolute_time();
    demo->hold_starts_at = make_timeout_time_ms(POSITION_STEP_DELAY_MS);
    demo->ends_at = make_timeout_time_ms(POSITION_HOLD_RUN_TIME_MS);
    telemetry_init(&demo->sample_timer, POSITION_PLOT_SAMPLE_MS);
}

static void position_hold_demo_tick(
    PositionHoldDemo *demo,
    MotorPwm *motor_c,
    AdcPot *adc_c,
    const PositionControlConfig *config
) {
    hard_assert(demo != NULL);
    hard_assert(motor_c != NULL);
    hard_assert(adc_c != NULL);
    hard_assert(config != NULL);

    if (!demo->active) {
        return;
    }

    if (time_reached(demo->ends_at)) {
        hexapod_serial_print_event(DEVICE_ID, "demo.done", "info");
        position_hold_demo_stop(demo, motor_c, adc_c);
        return;
    }

    if (time_reached(demo->next_control_at)) {
        demo->latest_position_adc = adc_pot_read_raw(adc_c);

        if (!demo->hold_enabled && time_reached(demo->hold_starts_at)) {
            demo->hold_enabled = true;
            demo->active_target_adc = config->setpoint_adc;
        }

        if (!demo->hold_enabled) {
            demo->active_target_adc = demo->baseline_target_adc;
            demo->telemetry_drive_pct = 0;
            motor_pwm_coast(motor_c);
        } else {
            int32_t error = (int32_t)config->setpoint_adc - (int32_t)demo->latest_position_adc;
            uint32_t error_magnitude = (error >= 0) ? (uint32_t)error : (uint32_t)(-error);

            demo->active_target_adc = config->setpoint_adc;
            if (error_magnitude <= config->deadband_adc) {
                demo->telemetry_drive_pct = 0;
                motor_pwm_brake(motor_c);
            } else {
                uint16_t duty_pct = position_compute_drive_duty(config, (uint16_t)error_magnitude);
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

    printf(
        "{\"type\":\"sample\",\"version\":%u,\"device\":\"%s\",\"stream\":\"%s\",\"seq\":%lu,"
        "\"t_us\":%llu,\"data\":{\"setpoint_adc\":%u,\"measured_adc\":%u,\"control_output_pct\":%d}}\r\n",
        HEXAPOD_SERIAL_VERSION,
        DEVICE_ID,
        STREAM_POSITION,
        (unsigned long)demo->sample_seq++,
        (unsigned long long)sample_us,
        demo->active_target_adc,
        adc_c_raw,
        demo->telemetry_drive_pct
    );
}

static void emit_parse_error(HexapodSerialParseStatus status) {
    switch (status) {
        case HEXAPOD_SERIAL_PARSE_INVALID_JSON:
            hexapod_serial_print_event(DEVICE_ID, "protocol.invalid_json", "error");
            break;
        case HEXAPOD_SERIAL_PARSE_MISSING_FIELD:
        case HEXAPOD_SERIAL_PARSE_WRONG_TYPE:
            hexapod_serial_print_event(DEVICE_ID, "protocol.invalid_command", "error");
            break;
        case HEXAPOD_SERIAL_PARSE_UNSUPPORTED_VERSION:
            hexapod_serial_print_event(DEVICE_ID, "protocol.unsupported_version", "error");
            break;
        case HEXAPOD_SERIAL_PARSE_BUFFER_TOO_SMALL:
            hexapod_serial_print_event(DEVICE_ID, "protocol.command_too_large", "error");
            break;
        case HEXAPOD_SERIAL_PARSE_OK:
        default:
            break;
    }
}

static void handle_protocol_command(
    const HexapodSerialCommand *command,
    PositionHoldDemo *demo,
    MotorPwm *motor_c,
    AdcPot *adc_c,
    PositionControlConfig *config
) {
    hard_assert(command != NULL);
    hard_assert(demo != NULL);
    hard_assert(motor_c != NULL);
    hard_assert(adc_c != NULL);
    hard_assert(config != NULL);

    if (strcmp(command->device, DEVICE_ID) != 0) {
        hexapod_serial_print_resp_error(
            DEVICE_ID,
            command->id,
            "wrong_device",
            "command addressed to a different device"
        );
        return;
    }

    if (strcmp(command->name, "demo.start") == 0) {
        position_hold_demo_start(demo, motor_c, adc_c);
        hexapod_serial_print_resp_ok(DEVICE_ID, command->id);
        hexapod_serial_print_event(DEVICE_ID, "demo.started", "info");
        return;
    }

    if (strcmp(command->name, "demo.stop") == 0) {
        position_hold_demo_stop(demo, motor_c, adc_c);
        hexapod_serial_print_resp_ok(DEVICE_ID, command->id);
        hexapod_serial_print_event(DEVICE_ID, "demo.stopped", "info");
        return;
    }

    if (strcmp(command->name, "param.list") == 0) {
        print_param_list_result(command->id, config);
        return;
    }

    if (strcmp(command->name, "param.get") == 0) {
        char param_name[48] = {0};
        int param_index = -1;

        if (!hexapod_serial_json_get_string(command->args_json, "param", param_name, sizeof(param_name))) {
            hexapod_serial_print_resp_error(
                DEVICE_ID,
                command->id,
                "invalid_args",
                "param argument required"
            );
            return;
        }

        param_index = find_param_index(param_name);
        if (param_index < 0) {
            hexapod_serial_print_resp_error(
                DEVICE_ID,
                command->id,
                "unknown_param",
                "parameter not found"
            );
            return;
        }

        print_param_result(command->id, param_name, read_param_value_by_index(config, param_index));
        return;
    }

    if (strcmp(command->name, "param.set") == 0) {
        char param_name[48] = {0};
        int32_t value = 0;
        int param_index = -1;
        const char *error_code = NULL;
        const char *error_message = NULL;

        if (!hexapod_serial_json_get_string(command->args_json, "param", param_name, sizeof(param_name)) ||
            !hexapod_serial_json_get_int32(command->args_json, "value", &value)) {
            hexapod_serial_print_resp_error(
                DEVICE_ID,
                command->id,
                "invalid_args",
                "param and integer value required"
            );
            return;
        }

        param_index = find_param_index(param_name);
        if (param_index < 0) {
            hexapod_serial_print_resp_error(
                DEVICE_ID,
                command->id,
                "unknown_param",
                "parameter not found"
            );
            return;
        }

        if (!set_param_value_by_index(config, param_index, value, &error_code, &error_message)) {
            hexapod_serial_print_resp_error(DEVICE_ID, command->id, error_code, error_message);
            return;
        }

        print_param_result(command->id, param_name, read_param_value_by_index(config, param_index));
        return;
    }

    hexapod_serial_print_resp_error(DEVICE_ID, command->id, "unknown_command", "command not supported");
}

int main(void) {
    stdio_init_all();
    init_status_led();
    sleep_ms(1200u);
    init_adc_bank(&g_adc_bank);
    init_motor_bank(&g_motor_bank);

    PioUartRx command_rx = {0};
    if (!pio_uart_rx_init(&command_rx, pio0, COMMAND_RX_GPIO, COMMAND_BAUD)) {
        hexapod_serial_print_log(DEVICE_ID, "error", "pio rx init failed");
        while (true) {
            rx_led_tick();
            tight_loop_contents();
        }
    }

    PositionControlConfig config = {0};
    PositionHoldDemo demo = {0};
    UartLineBuffer command_buffer = {0};
    char command_line[CMD_BUFFER_LEN] = {0};

    position_control_config_init_defaults(&config);
    uart_line_buffer_reset(&command_buffer);

    hexapod_serial_print_hello(DEVICE_ID, FIRMWARE_VERSION);
    print_capabilities();
    hexapod_serial_print_event(DEVICE_ID, "device.ready", "info");

    position_hold_demo_start(&demo, &g_motor_bank.c, &g_adc_bank.c);
    hexapod_serial_print_event(DEVICE_ID, "demo.started", "info");

    while (true) {
        UartReadStatus read_status = uart_try_read_line(
            &command_rx,
            &command_buffer,
            command_line,
            CMD_BUFFER_LEN
        );

        if (read_status == UART_READ_OVERFLOW) {
            hexapod_serial_print_event(DEVICE_ID, "protocol.line_too_long", "error");
        } else if (read_status == UART_READ_LINE) {
            HexapodSerialCommand command = {0};
            HexapodSerialParseStatus parse_status = hexapod_serial_parse_command(command_line, &command);

            if (parse_status == HEXAPOD_SERIAL_PARSE_OK) {
                handle_protocol_command(
                    &command,
                    &demo,
                    &g_motor_bank.c,
                    &g_adc_bank.c,
                    &config
                );
            } else {
                emit_parse_error(parse_status);
            }
        }

        position_hold_demo_tick(&demo, &g_motor_bank.c, &g_adc_bank.c, &config);
        rx_led_tick();
        tight_loop_contents();
    }
}
