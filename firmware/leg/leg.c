#include <stdbool.h>
#include <stdint.h>

#include "pico/stdlib.h"
#include "pico/time.h"

#include "adc_pot.h"
#include "devlink_serial.h"
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
#define POSITION_P_ERROR_TO_OUTPUT_DIVISOR 16u
#define CMD_BUFFER_LEN 256u
#define CMD_IDLE_FLUSH_MS 80u
#define STATUS_LED_GPIO 25u
#define RX_LED_PULSE_MS 40u
#define COMMAND_RX_GPIO 3u
#define COMMAND_BAUD 115200u
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
    uint16_t setpoint_adc;
    uint16_t deadband_adc;
    uint8_t min_output_pct;
    uint8_t max_output_pct;
    uint16_t error_to_output_divisor;
} PositionControlConfig;

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

typedef struct {
    PositionControlConfig config;
    PositionHoldDemo demo;
} LegAppContext;

enum {
    PARAM_SETPOINT_ADC = 0,
    PARAM_DEADBAND_ADC,
    PARAM_MIN_OUTPUT_PCT,
    PARAM_MAX_OUTPUT_PCT,
    PARAM_ERROR_TO_OUTPUT_DIVISOR,
};

static AdcBank g_adc_bank;
static MotorBank g_motor_bank;
static bool g_rx_led_active;
static absolute_time_t g_rx_led_deadline;

static DevlinkSerialCommandStatus handle_demo_start(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_demo_stop(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static bool leg_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
);
static bool leg_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
);

static const DevlinkSerialStreamFieldDescriptor g_position_stream_fields[] = {
    {"setpoint_adc", DEVLINK_SERIAL_TYPE_U16, "adc"},
    {"measured_adc", DEVLINK_SERIAL_TYPE_U16, "adc"},
    {"control_output_pct", DEVLINK_SERIAL_TYPE_I16, "pct"},
};

static const DevlinkSerialStreamDescriptor g_leg_streams[] = {
    {STREAM_POSITION, g_position_stream_fields, count_of(g_position_stream_fields)},
};

static const DevlinkSerialParamDescriptor g_leg_params[] = {
    {
        "control.setpoint_adc",
        DEVLINK_SERIAL_TYPE_U16,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U16(POSITION_SETPOINT_ADC),
        true,
        DEVLINK_SERIAL_VALUE_U16(0),
        DEVLINK_SERIAL_VALUE_U16(ADC_POT_MAX_RAW),
        PARAM_SETPOINT_ADC,
    },
    {
        "control.deadband_adc",
        DEVLINK_SERIAL_TYPE_U16,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U16(POSITION_HOLD_DEADBAND_ADC),
        true,
        DEVLINK_SERIAL_VALUE_U16(0),
        DEVLINK_SERIAL_VALUE_U16(ADC_POT_MAX_RAW),
        PARAM_DEADBAND_ADC,
    },
    {
        "control.min_output_pct",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(POSITION_P_MIN_OUTPUT_PCT),
        true,
        DEVLINK_SERIAL_VALUE_U8(0),
        DEVLINK_SERIAL_VALUE_U8(100),
        PARAM_MIN_OUTPUT_PCT,
    },
    {
        "control.max_output_pct",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(POSITION_P_MAX_OUTPUT_PCT),
        true,
        DEVLINK_SERIAL_VALUE_U8(0),
        DEVLINK_SERIAL_VALUE_U8(100),
        PARAM_MAX_OUTPUT_PCT,
    },
    {
        "control.error_to_output_divisor",
        DEVLINK_SERIAL_TYPE_U16,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U16(POSITION_P_ERROR_TO_OUTPUT_DIVISOR),
        true,
        DEVLINK_SERIAL_VALUE_U16(1),
        DEVLINK_SERIAL_VALUE_U16(ADC_POT_MAX_RAW),
        PARAM_ERROR_TO_OUTPUT_DIVISOR,
    },
};

static const DevlinkSerialCommandDescriptor g_leg_commands[] = {
    {"demo.start", NULL, 0u, handle_demo_start, "demo.started", "info"},
    {"demo.stop", NULL, 0u, handle_demo_stop, "demo.stopped", "info"},
};

static const DevlinkSerialDeviceDescriptor g_leg_device = {
    .device = "leg",
    .firmware = "0.1.0",
    .commands = g_leg_commands,
    .command_count = count_of(g_leg_commands),
    .streams = g_leg_streams,
    .stream_count = count_of(g_leg_streams),
    .params = g_leg_params,
    .param_count = count_of(g_leg_params),
    .param_getter = leg_param_get,
    .param_setter = leg_param_set,
};

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

static void position_control_config_init_defaults(PositionControlConfig *config) {
    hard_assert(config != NULL);

    config->setpoint_adc = POSITION_SETPOINT_ADC;
    config->deadband_adc = POSITION_HOLD_DEADBAND_ADC;
    config->min_output_pct = POSITION_P_MIN_OUTPUT_PCT;
    config->max_output_pct = POSITION_P_MAX_OUTPUT_PCT;
    config->error_to_output_divisor = POSITION_P_ERROR_TO_OUTPUT_DIVISOR;
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
    LegAppContext *app,
    MotorPwm *motor_c,
    AdcPot *adc_c
) {
    DevlinkSerialValue values[count_of(g_position_stream_fields)];
    PositionHoldDemo *demo = &app->demo;
    const PositionControlConfig *config = &app->config;
    uint16_t adc_c_raw = 0u;
    uint64_t sample_us = 0u;

    if (!demo->active) {
        return;
    }

    if (time_reached(demo->ends_at)) {
        devlink_serial_print_event(&g_leg_device, "demo.done", "info");
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

    if (!telemetry_try_sample_one(&demo->sample_timer, adc_c, &adc_c_raw, &sample_us)) {
        return;
    }

    values[0] = DEVLINK_SERIAL_VALUE_U16(demo->active_target_adc);
    values[1] = DEVLINK_SERIAL_VALUE_U16(adc_c_raw);
    values[2] = DEVLINK_SERIAL_VALUE_I16(demo->telemetry_drive_pct);
    devlink_serial_print_sample(
        &g_leg_device,
        &g_leg_streams[0],
        demo->sample_seq++,
        sample_us,
        values
    );
}

static bool leg_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
) {
    LegAppContext *app = (LegAppContext *)context;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_value != NULL);

    switch ((int)param->user_data) {
        case PARAM_SETPOINT_ADC:
            *out_value = DEVLINK_SERIAL_VALUE_U16(app->config.setpoint_adc);
            return true;
        case PARAM_DEADBAND_ADC:
            *out_value = DEVLINK_SERIAL_VALUE_U16(app->config.deadband_adc);
            return true;
        case PARAM_MIN_OUTPUT_PCT:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->config.min_output_pct);
            return true;
        case PARAM_MAX_OUTPUT_PCT:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->config.max_output_pct);
            return true;
        case PARAM_ERROR_TO_OUTPUT_DIVISOR:
            *out_value = DEVLINK_SERIAL_VALUE_U16(app->config.error_to_output_divisor);
            return true;
        default:
            return false;
    }
}

static bool leg_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
) {
    LegAppContext *app = (LegAppContext *)context;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    *out_error_code = NULL;
    *out_error_message = NULL;

    switch ((int)param->user_data) {
        case PARAM_SETPOINT_ADC:
            app->config.setpoint_adc = (uint16_t)value.u32_value;
            return true;
        case PARAM_DEADBAND_ADC:
            app->config.deadband_adc = (uint16_t)value.u32_value;
            return true;
        case PARAM_MIN_OUTPUT_PCT:
            if (value.u32_value > app->config.max_output_pct) {
                *out_error_code = "value_out_of_range";
                *out_error_message = "min_output_pct must be <= max_output_pct";
                return false;
            }
            app->config.min_output_pct = (uint8_t)value.u32_value;
            return true;
        case PARAM_MAX_OUTPUT_PCT:
            if (value.u32_value < app->config.min_output_pct) {
                *out_error_code = "value_out_of_range";
                *out_error_message = "max_output_pct must be >= min_output_pct";
                return false;
            }
            app->config.max_output_pct = (uint8_t)value.u32_value;
            return true;
        case PARAM_ERROR_TO_OUTPUT_DIVISOR:
            app->config.error_to_output_divisor = (uint16_t)value.u32_value;
            return true;
        default:
            *out_error_code = "unknown_param";
            *out_error_message = "unknown parameter";
            return false;
    }
}

static DevlinkSerialCommandStatus handle_demo_start(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    LegAppContext *app = (LegAppContext *)context;

    (void)device;
    (void)command;
    (void)out_result_json;
    (void)out_result_json_size;
    (void)out_error_code;
    (void)out_error_message;

    position_hold_demo_start(&app->demo, &g_motor_bank.c, &g_adc_bank.c);
    return DEVLINK_SERIAL_COMMAND_OK;
}

static DevlinkSerialCommandStatus handle_demo_stop(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    LegAppContext *app = (LegAppContext *)context;

    (void)device;
    (void)command;
    (void)out_result_json;
    (void)out_result_json_size;
    (void)out_error_code;
    (void)out_error_message;

    position_hold_demo_stop(&app->demo, &g_motor_bank.c, &g_adc_bank.c);
    return DEVLINK_SERIAL_COMMAND_OK;
}

static void poll_command_input(
    PioUartRx *command_rx,
    DevlinkSerialLineBuffer *line_buffer,
    LegAppContext *app,
    char *command_line,
    size_t command_line_size
) {
    uint8_t received_byte = 0u;

    while (pio_uart_rx_try_getc(command_rx, &received_byte)) {
        DevlinkSerialLineReadStatus read_status = DEVLINK_SERIAL_LINE_NONE;

        rx_led_note_byte();
        read_status = devlink_serial_line_buffer_push(
            line_buffer,
            (int)received_byte,
            command_line,
            command_line_size
        );

        if (read_status == DEVLINK_SERIAL_LINE_READY) {
            devlink_serial_handle_command_line(&g_leg_device, app, command_line);
        } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
            devlink_serial_print_event(&g_leg_device, "protocol.line_too_long", "error");
        }
    }

    {
        DevlinkSerialLineReadStatus read_status = devlink_serial_line_buffer_flush_if_idle(
            line_buffer,
            command_line,
            command_line_size
        );

        if (read_status == DEVLINK_SERIAL_LINE_READY) {
            devlink_serial_handle_command_line(&g_leg_device, app, command_line);
        } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
            devlink_serial_print_event(&g_leg_device, "protocol.line_too_long", "error");
        }
    }
}

int main(void) {
    PioUartRx command_rx = {0};
    LegAppContext app = {0};
    DevlinkSerialLineBuffer command_buffer = {0};
    char command_line[CMD_BUFFER_LEN] = {0};

    stdio_init_all();
    init_status_led();
    sleep_ms(1200u);
    init_adc_bank(&g_adc_bank);
    init_motor_bank(&g_motor_bank);

    if (!pio_uart_rx_init(&command_rx, pio0, COMMAND_RX_GPIO, COMMAND_BAUD)) {
        devlink_serial_print_log(&g_leg_device, "error", "pio rx init failed");
        while (true) {
            rx_led_tick();
            tight_loop_contents();
        }
    }

    position_control_config_init_defaults(&app.config);
    devlink_serial_line_buffer_init(
        &command_buffer,
        command_line,
        sizeof(command_line),
        CMD_IDLE_FLUSH_MS
    );

    devlink_serial_print_discovery(&g_leg_device);
    devlink_serial_print_event(&g_leg_device, "device.ready", "info");

    position_hold_demo_start(&app.demo, &g_motor_bank.c, &g_adc_bank.c);
    devlink_serial_print_event(&g_leg_device, "demo.started", "info");

    while (true) {
        poll_command_input(
            &command_rx,
            &command_buffer,
            &app,
            command_line,
            sizeof(command_line)
        );
        position_hold_demo_tick(&app, &g_motor_bank.c, &g_adc_bank.c);
        rx_led_tick();
        tight_loop_contents();
    }
}
