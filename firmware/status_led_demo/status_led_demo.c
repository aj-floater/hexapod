#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "pico/stdlib.h"
#include "pico/time.h"

#include "devlink_serial.h"
#include "pio_uart_rx.h"

#define STATUS_LED_GPIO 25u
#define CMD_BUFFER_LEN 256u
#define CMD_IDLE_FLUSH_MS 80u
#define SAMPLE_PERIOD_MS 250u
#define TIMING_SAMPLE_DEFAULT_MS 50u
#define TIMING_SAMPLE_MIN_MS 10u
#define TIMING_SAMPLE_MAX_MS 1000u
#define STATS_SAMPLE_DEFAULT_MS 500u
#define STATS_SAMPLE_MIN_MS 100u
#define STATS_SAMPLE_MAX_MS 5000u
#define BLINK_PERIOD_DEFAULT_MS 250u
#define BLINK_PERIOD_MIN_MS 10u
#define BLINK_PERIOD_MAX_MS 2000u
#define COMMAND_RX_GPIO 3u
#define COMMAND_BAUD 115200u

enum {
    PARAM_LED_ENABLED = 0,
    PARAM_BLINK_ENABLED,
    PARAM_BLINK_PERIOD_MS,
    PARAM_TIMING_SAMPLE_MS,
    PARAM_STATS_SAMPLE_MS,
};

typedef struct {
    bool led_enabled;
    bool blink_enabled;
    uint32_t blink_period_ms;
    uint32_t timing_sample_ms;
    uint32_t stats_sample_ms;
    bool led_output_high;
    uint32_t state_sample_seq;
    uint32_t timing_sample_seq;
    uint32_t stats_sample_seq;
    uint32_t toggle_count;
    uint32_t command_count;
    absolute_time_t boot_at;
    absolute_time_t phase_started_at;
    absolute_time_t next_blink_at;
    absolute_time_t next_state_sample_at;
    absolute_time_t next_timing_sample_at;
    absolute_time_t next_stats_sample_at;
} StatusLedAppContext;

static DevlinkSerialCommandStatus handle_led_toggle(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static bool status_led_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
);
static bool status_led_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
);

static const DevlinkSerialStreamFieldDescriptor g_status_led_state_stream_fields[] = {
    {"led_enabled", DEVLINK_SERIAL_TYPE_BOOL, "state"},
    {"output_high", DEVLINK_SERIAL_TYPE_BOOL, "state"},
    {"blink_enabled", DEVLINK_SERIAL_TYPE_BOOL, "state"},
    {"blink_period_ms", DEVLINK_SERIAL_TYPE_U32, "ms"},
};

static const DevlinkSerialStreamFieldDescriptor g_status_led_timing_stream_fields[] = {
    {"phase_elapsed_ms", DEVLINK_SERIAL_TYPE_U32, "ms"},
    {"time_to_toggle_ms", DEVLINK_SERIAL_TYPE_U32, "ms"},
    {"blink_period_ms", DEVLINK_SERIAL_TYPE_U32, "ms"},
};

static const DevlinkSerialStreamFieldDescriptor g_status_led_stats_stream_fields[] = {
    {"toggle_count", DEVLINK_SERIAL_TYPE_U32, "count"},
    {"command_count", DEVLINK_SERIAL_TYPE_U32, "count"},
    {"uptime_ms", DEVLINK_SERIAL_TYPE_U32, "ms"},
};

static const DevlinkSerialStreamDescriptor g_status_led_streams[] = {
    {"status_led.state", g_status_led_state_stream_fields, count_of(g_status_led_state_stream_fields)},
    {"status_led.timing", g_status_led_timing_stream_fields, count_of(g_status_led_timing_stream_fields)},
    {"status_led.stats", g_status_led_stats_stream_fields, count_of(g_status_led_stats_stream_fields)},
};

static const DevlinkSerialParamDescriptor g_status_led_params[] = {
    {
        "led.enabled",
        DEVLINK_SERIAL_TYPE_BOOL,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_BOOL(true),
        false,
        DEVLINK_SERIAL_VALUE_BOOL(false),
        DEVLINK_SERIAL_VALUE_BOOL(true),
        PARAM_LED_ENABLED,
    },
    {
        "blink.enabled",
        DEVLINK_SERIAL_TYPE_BOOL,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_BOOL(true),
        false,
        DEVLINK_SERIAL_VALUE_BOOL(false),
        DEVLINK_SERIAL_VALUE_BOOL(true),
        PARAM_BLINK_ENABLED,
    },
    {
        "blink.period_ms",
        DEVLINK_SERIAL_TYPE_U32,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U32(BLINK_PERIOD_DEFAULT_MS),
        true,
        DEVLINK_SERIAL_VALUE_U32(BLINK_PERIOD_MIN_MS),
        DEVLINK_SERIAL_VALUE_U32(BLINK_PERIOD_MAX_MS),
        PARAM_BLINK_PERIOD_MS,
    },
    {
        "telemetry.timing_sample_ms",
        DEVLINK_SERIAL_TYPE_U32,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U32(TIMING_SAMPLE_DEFAULT_MS),
        true,
        DEVLINK_SERIAL_VALUE_U32(TIMING_SAMPLE_MIN_MS),
        DEVLINK_SERIAL_VALUE_U32(TIMING_SAMPLE_MAX_MS),
        PARAM_TIMING_SAMPLE_MS,
    },
    {
        "telemetry.stats_sample_ms",
        DEVLINK_SERIAL_TYPE_U32,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U32(STATS_SAMPLE_DEFAULT_MS),
        true,
        DEVLINK_SERIAL_VALUE_U32(STATS_SAMPLE_MIN_MS),
        DEVLINK_SERIAL_VALUE_U32(STATS_SAMPLE_MAX_MS),
        PARAM_STATS_SAMPLE_MS,
    },
};

static const DevlinkSerialCommandDescriptor g_status_led_commands[] = {
    {"led.toggle", NULL, 0u, handle_led_toggle, "led.toggled", "info"},
};

static const DevlinkSerialDeviceDescriptor g_status_led_device = {
    .device = "status_led",
    .firmware = "0.2.0",
    .commands = g_status_led_commands,
    .command_count = count_of(g_status_led_commands),
    .streams = g_status_led_streams,
    .stream_count = count_of(g_status_led_streams),
    .params = g_status_led_params,
    .param_count = count_of(g_status_led_params),
    .param_getter = status_led_param_get,
    .param_setter = status_led_param_set,
};

static void status_led_apply_output(const StatusLedAppContext *app) {
    hard_assert(app != NULL);
    gpio_put(STATUS_LED_GPIO, app->led_enabled && app->led_output_high);
}

static void status_led_log_value_change(const char *name, const char *value_text) {
    char message[96] = {0};
    int written = 0;

    hard_assert(name != NULL);
    hard_assert(value_text != NULL);

    written = snprintf(message, sizeof(message), "%s=%s", name, value_text);
    if (written < 0 || (size_t)written >= sizeof(message)) {
        devlink_serial_print_log(&g_status_led_device, "info", name);
        return;
    }
    devlink_serial_print_log(&g_status_led_device, "info", message);
}

static void status_led_init(StatusLedAppContext *app) {
    absolute_time_t now = get_absolute_time();

    hard_assert(app != NULL);

    gpio_init(STATUS_LED_GPIO);
    gpio_set_dir(STATUS_LED_GPIO, GPIO_OUT);

    app->led_enabled = true;
    app->blink_enabled = true;
    app->blink_period_ms = BLINK_PERIOD_DEFAULT_MS;
    app->timing_sample_ms = TIMING_SAMPLE_DEFAULT_MS;
    app->stats_sample_ms = STATS_SAMPLE_DEFAULT_MS;
    app->led_output_high = true;
    app->state_sample_seq = 0u;
    app->timing_sample_seq = 0u;
    app->stats_sample_seq = 0u;
    app->toggle_count = 0u;
    app->command_count = 0u;
    app->boot_at = now;
    app->phase_started_at = now;
    app->next_blink_at = delayed_by_ms(now, app->blink_period_ms);
    app->next_state_sample_at = now;
    app->next_timing_sample_at = now;
    app->next_stats_sample_at = now;
    status_led_apply_output(app);
}

static uint32_t status_led_uptime_ms(const StatusLedAppContext *app) {
    int64_t elapsed_us = 0;

    hard_assert(app != NULL);

    elapsed_us = absolute_time_diff_us(app->boot_at, get_absolute_time());
    if (elapsed_us <= 0) {
        return 0u;
    }
    return (uint32_t)(elapsed_us / 1000);
}

static uint32_t status_led_phase_elapsed_ms(const StatusLedAppContext *app) {
    int64_t elapsed_us = 0;

    hard_assert(app != NULL);

    elapsed_us = absolute_time_diff_us(app->phase_started_at, get_absolute_time());
    if (elapsed_us <= 0) {
        return 0u;
    }
    return (uint32_t)(elapsed_us / 1000);
}

static uint32_t status_led_time_to_toggle_ms(const StatusLedAppContext *app) {
    int64_t remaining_us = 0;

    hard_assert(app != NULL);

    if (!app->blink_enabled) {
        return 0u;
    }

    remaining_us = absolute_time_diff_us(get_absolute_time(), app->next_blink_at);
    if (remaining_us <= 0) {
        return 0u;
    }
    return (uint32_t)((remaining_us + 999) / 1000);
}

static void status_led_reset_blink_timer(StatusLedAppContext *app, absolute_time_t now) {
    hard_assert(app != NULL);
    app->phase_started_at = now;
    app->next_blink_at = delayed_by_ms(now, app->blink_period_ms);
}

static void status_led_reset_sample_timer(absolute_time_t *deadline, uint32_t delay_ms) {
    hard_assert(deadline != NULL);
    *deadline = delayed_by_ms(get_absolute_time(), delay_ms);
}

static void status_led_emit_state_sample(StatusLedAppContext *app) {
    DevlinkSerialValue values[count_of(g_status_led_state_stream_fields)];

    hard_assert(app != NULL);

    values[0] = DEVLINK_SERIAL_VALUE_BOOL(app->led_enabled);
    values[1] = DEVLINK_SERIAL_VALUE_BOOL(app->led_enabled && app->led_output_high);
    values[2] = DEVLINK_SERIAL_VALUE_BOOL(app->blink_enabled);
    values[3] = DEVLINK_SERIAL_VALUE_U32(app->blink_period_ms);
    devlink_serial_print_sample(
        &g_status_led_device,
        &g_status_led_streams[0],
        app->state_sample_seq++,
        time_us_64(),
        values
    );
}

static void status_led_emit_timing_sample(StatusLedAppContext *app) {
    DevlinkSerialValue values[count_of(g_status_led_timing_stream_fields)];

    hard_assert(app != NULL);

    values[0] = DEVLINK_SERIAL_VALUE_U32(status_led_phase_elapsed_ms(app));
    values[1] = DEVLINK_SERIAL_VALUE_U32(status_led_time_to_toggle_ms(app));
    values[2] = DEVLINK_SERIAL_VALUE_U32(app->blink_period_ms);
    devlink_serial_print_sample(
        &g_status_led_device,
        &g_status_led_streams[1],
        app->timing_sample_seq++,
        time_us_64(),
        values
    );
}

static void status_led_emit_stats_sample(StatusLedAppContext *app) {
    DevlinkSerialValue values[count_of(g_status_led_stats_stream_fields)];

    hard_assert(app != NULL);

    values[0] = DEVLINK_SERIAL_VALUE_U32(app->toggle_count);
    values[1] = DEVLINK_SERIAL_VALUE_U32(app->command_count);
    values[2] = DEVLINK_SERIAL_VALUE_U32(status_led_uptime_ms(app));
    devlink_serial_print_sample(
        &g_status_led_device,
        &g_status_led_streams[2],
        app->stats_sample_seq++,
        time_us_64(),
        values
    );
}

static void status_led_tick(StatusLedAppContext *app) {
    absolute_time_t now = get_absolute_time();

    hard_assert(app != NULL);

    if (app->blink_enabled && time_reached(app->next_blink_at)) {
        app->led_output_high = !app->led_output_high;
        app->toggle_count += 1u;
        status_led_apply_output(app);
        status_led_reset_blink_timer(app, now);
    } else if (!app->blink_enabled) {
        if (!app->led_output_high) {
            app->led_output_high = true;
            app->toggle_count += 1u;
            app->phase_started_at = now;
            status_led_apply_output(app);
        }
    }

    if (time_reached(app->next_state_sample_at)) {
        status_led_emit_state_sample(app);
        status_led_reset_sample_timer(&app->next_state_sample_at, SAMPLE_PERIOD_MS);
    }
    if (time_reached(app->next_timing_sample_at)) {
        status_led_emit_timing_sample(app);
        status_led_reset_sample_timer(&app->next_timing_sample_at, app->timing_sample_ms);
    }
    if (time_reached(app->next_stats_sample_at)) {
        status_led_emit_stats_sample(app);
        status_led_reset_sample_timer(&app->next_stats_sample_at, app->stats_sample_ms);
    }
}

static void poll_command_input(
    PioUartRx *command_rx,
    DevlinkSerialLineBuffer *line_buffer,
    StatusLedAppContext *app,
    char *command_line,
    size_t command_line_size
) {
    uint8_t received_byte = 0u;

    while (pio_uart_rx_try_getc(command_rx, &received_byte)) {
        DevlinkSerialLineReadStatus read_status = devlink_serial_line_buffer_push(
            line_buffer,
            (int)received_byte,
            command_line,
            command_line_size
        );

        if (read_status == DEVLINK_SERIAL_LINE_READY) {
            app->command_count += 1u;
            devlink_serial_handle_command_line(&g_status_led_device, app, command_line);
        } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
            devlink_serial_print_event(&g_status_led_device, "protocol.line_too_long", "error");
        }
    }

    {
        DevlinkSerialLineReadStatus read_status = devlink_serial_line_buffer_flush_if_idle(
            line_buffer,
            command_line,
            command_line_size
        );

        if (read_status == DEVLINK_SERIAL_LINE_READY) {
            app->command_count += 1u;
            devlink_serial_handle_command_line(&g_status_led_device, app, command_line);
        } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
            devlink_serial_print_event(&g_status_led_device, "protocol.line_too_long", "error");
        }
    }
}

static bool command_input_pending(
    const PioUartRx *command_rx,
    const DevlinkSerialLineBuffer *line_buffer
) {
    hard_assert(command_rx != NULL);
    hard_assert(line_buffer != NULL);

    return pio_uart_rx_has_pending(command_rx) || line_buffer->len > 0u || line_buffer->overflowed;
}

static bool status_led_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
) {
    StatusLedAppContext *app = (StatusLedAppContext *)context;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_value != NULL);

    switch ((int)param->user_data) {
        case PARAM_LED_ENABLED:
            *out_value = DEVLINK_SERIAL_VALUE_BOOL(app->led_enabled);
            return true;
        case PARAM_BLINK_ENABLED:
            *out_value = DEVLINK_SERIAL_VALUE_BOOL(app->blink_enabled);
            return true;
        case PARAM_BLINK_PERIOD_MS:
            *out_value = DEVLINK_SERIAL_VALUE_U32(app->blink_period_ms);
            return true;
        case PARAM_TIMING_SAMPLE_MS:
            *out_value = DEVLINK_SERIAL_VALUE_U32(app->timing_sample_ms);
            return true;
        case PARAM_STATS_SAMPLE_MS:
            *out_value = DEVLINK_SERIAL_VALUE_U32(app->stats_sample_ms);
            return true;
        default:
            return false;
    }
}

static bool status_led_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
) {
    StatusLedAppContext *app = (StatusLedAppContext *)context;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    *out_error_code = NULL;
    *out_error_message = NULL;

    switch ((int)param->user_data) {
        case PARAM_LED_ENABLED:
            app->led_enabled = value.bool_value;
            status_led_apply_output(app);
            status_led_log_value_change("led.enabled", value.bool_value ? "true" : "false");
            return true;
        case PARAM_BLINK_ENABLED:
            app->blink_enabled = value.bool_value;
            app->led_output_high = true;
            app->phase_started_at = get_absolute_time();
            status_led_apply_output(app);
            status_led_reset_blink_timer(app, get_absolute_time());
            status_led_log_value_change("blink.enabled", value.bool_value ? "true" : "false");
            return true;
        case PARAM_BLINK_PERIOD_MS:
            app->blink_period_ms = value.u32_value;
            status_led_reset_blink_timer(app, get_absolute_time());
            {
                char value_text[16] = {0};
                snprintf(value_text, sizeof(value_text), "%lu", (unsigned long)value.u32_value);
                status_led_log_value_change("blink.period_ms", value_text);
            }
            return true;
        case PARAM_TIMING_SAMPLE_MS:
            app->timing_sample_ms = value.u32_value;
            status_led_reset_sample_timer(&app->next_timing_sample_at, app->timing_sample_ms);
            {
                char value_text[16] = {0};
                snprintf(value_text, sizeof(value_text), "%lu", (unsigned long)value.u32_value);
                status_led_log_value_change("telemetry.timing_sample_ms", value_text);
            }
            return true;
        case PARAM_STATS_SAMPLE_MS:
            app->stats_sample_ms = value.u32_value;
            status_led_reset_sample_timer(&app->next_stats_sample_at, app->stats_sample_ms);
            {
                char value_text[16] = {0};
                snprintf(value_text, sizeof(value_text), "%lu", (unsigned long)value.u32_value);
                status_led_log_value_change("telemetry.stats_sample_ms", value_text);
            }
            return true;
        default:
            *out_error_code = "unknown_param";
            *out_error_message = "unknown parameter";
            return false;
    }
}

static DevlinkSerialCommandStatus handle_led_toggle(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    StatusLedAppContext *app = (StatusLedAppContext *)context;
    int written = 0;

    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;

    app->led_enabled = !app->led_enabled;
    status_led_apply_output(app);
    devlink_serial_print_log(&g_status_led_device, "info", "led.toggle");

    written = snprintf(
        out_result_json,
        out_result_json_size,
        "{\"led_enabled\":%s}",
        app->led_enabled ? "true" : "false"
    );
    if (written < 0 || (size_t)written >= out_result_json_size) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }

    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

int main(void) {
    PioUartRx command_rx = {0};
    StatusLedAppContext app = {0};
    DevlinkSerialLineBuffer command_buffer = {0};
    char command_storage[CMD_BUFFER_LEN] = {0};
    char command_line[CMD_BUFFER_LEN] = {0};

    stdio_init_all();
    sleep_ms(200u);
    status_led_init(&app);

    if (!pio_uart_rx_init(&command_rx, pio0, COMMAND_RX_GPIO, COMMAND_BAUD)) {
        devlink_serial_print_log(&g_status_led_device, "error", "pio rx init failed");
        while (true) {
            status_led_tick(&app);
            tight_loop_contents();
        }
    }

    devlink_serial_line_buffer_init(
        &command_buffer,
        command_storage,
        sizeof(command_storage),
        CMD_IDLE_FLUSH_MS
    );

    devlink_serial_print_discovery(&g_status_led_device);
    devlink_serial_print_log(&g_status_led_device, "info", "status_led ready");
    devlink_serial_print_event(&g_status_led_device, "device.ready", "info");

    while (true) {
        poll_command_input(
            &command_rx,
            &command_buffer,
            &app,
            command_line,
            sizeof(command_line)
        );
        if (!command_input_pending(&command_rx, &command_buffer)) {
            status_led_tick(&app);
        }
        tight_loop_contents();
    }
}
