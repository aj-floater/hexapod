#include "debug_app.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"

#ifndef PICO_DEFAULT_LED_PIN
#error "debug-2 firmware requires PICO_DEFAULT_LED_PIN"
#endif

#ifndef PICO_DEFAULT_UART_TX_PIN
#error "debug-2 firmware requires PICO_DEFAULT_UART_TX_PIN"
#endif

typedef enum {
    DEBUG_PARAM_STATUS_LED_ON = 0,
    DEBUG_PARAM_TEST_U8,
    DEBUG_PARAM_TEST_F32,
    DEBUG_PARAM_VERBOSE,
    DEBUG_PARAM_COUNT,
} DebugParamId;

typedef struct {
    const char *name;
    DevlinkSerialScalarType type;
    bool has_bounds;
    DevlinkSerialValue default_value;
    DevlinkSerialValue min_value;
    DevlinkSerialValue max_value;
    DebugParamId id;
} DebugParamDescriptor;

typedef enum {
    DEBUG_LINE_NONE = 0,
    DEBUG_LINE_READY,
    DEBUG_LINE_OVERFLOW,
} DebugLineReadStatus;

#define DEBUG_DEVICE_NAME "debug"
#define DEBUG_BOARD_NAME "pico"
#define DEBUG_COMMAND_RX_GPIO 3u
#define DEBUG_COMMAND_BAUD 115200u
#define DEBUG_COMMAND_IDLE_FLUSH_MS 80u
#define DEBUG_STATS_PERIOD_MS 1000u
#define DEBUG_DIAGNOSTICS_LABEL "uart_tx_plaintext_only"

static const DebugParamDescriptor g_debug_params[DEBUG_PARAM_COUNT] = {
    {
        .name = "status_led.on",
        .type = DEVLINK_SERIAL_TYPE_BOOL,
        .has_bounds = false,
        .default_value = DEVLINK_SERIAL_VALUE_BOOL(false),
        .min_value = DEVLINK_SERIAL_VALUE_BOOL(false),
        .max_value = DEVLINK_SERIAL_VALUE_BOOL(true),
        .id = DEBUG_PARAM_STATUS_LED_ON,
    },
    {
        .name = "test.u8",
        .type = DEVLINK_SERIAL_TYPE_U8,
        .has_bounds = true,
        .default_value = DEVLINK_SERIAL_VALUE_U8(0u),
        .min_value = DEVLINK_SERIAL_VALUE_U8(0u),
        .max_value = DEVLINK_SERIAL_VALUE_U8(100u),
        .id = DEBUG_PARAM_TEST_U8,
    },
    {
        .name = "test.f32",
        .type = DEVLINK_SERIAL_TYPE_F32,
        .has_bounds = true,
        .default_value = DEVLINK_SERIAL_VALUE_F32(0.0f),
        .min_value = DEVLINK_SERIAL_VALUE_F32(0.0f),
        .max_value = DEVLINK_SERIAL_VALUE_F32(180.0f),
        .id = DEBUG_PARAM_TEST_F32,
    },
    {
        .name = "debug.verbose",
        .type = DEVLINK_SERIAL_TYPE_BOOL,
        .has_bounds = false,
        .default_value = DEVLINK_SERIAL_VALUE_BOOL(false),
        .min_value = DEVLINK_SERIAL_VALUE_BOOL(false),
        .max_value = DEVLINK_SERIAL_VALUE_BOOL(true),
        .id = DEBUG_PARAM_VERBOSE,
    },
};

static void debug_copy_string(char *dest, size_t dest_size, const char *src) {
    hard_assert(dest != NULL);
    hard_assert(dest_size > 0u);

    if (src == NULL) {
        dest[0] = '\0';
        return;
    }

    snprintf(dest, dest_size, "%s", src);
}

static const char *debug_parse_status_name(DevlinkSerialParseStatus status) {
    switch (status) {
        case DEVLINK_SERIAL_PARSE_OK:
            return "ok";
        case DEVLINK_SERIAL_PARSE_INVALID_JSON:
            return "invalid_json";
        case DEVLINK_SERIAL_PARSE_MISSING_FIELD:
            return "missing_field";
        case DEVLINK_SERIAL_PARSE_WRONG_TYPE:
            return "wrong_type";
        case DEVLINK_SERIAL_PARSE_UNSUPPORTED_VERSION:
            return "unsupported_version";
        case DEVLINK_SERIAL_PARSE_BUFFER_TOO_SMALL:
            return "buffer_too_small";
        default:
            return "unknown";
    }
}

static void debug_line_buffer_reset(DebugLineBuffer *buffer) {
    hard_assert(buffer != NULL);

    buffer->len = 0u;
    buffer->overflowed = false;
    buffer->flush_at = make_timeout_time_ms(DEBUG_COMMAND_IDLE_FLUSH_MS);
}

static DebugLineReadStatus debug_line_buffer_finalize(
    DebugApp *app,
    DebugLineBuffer *buffer,
    char *out_line,
    size_t out_line_size
) {
    size_t copy_len = 0u;

    hard_assert(app != NULL);
    hard_assert(buffer != NULL);
    hard_assert(out_line != NULL);
    hard_assert(out_line_size > 0u);

    if (buffer->overflowed) {
        app->counters.line_overflow_total += 1u;
        debug_line_buffer_reset(buffer);
        return DEBUG_LINE_OVERFLOW;
    }

    if (buffer->len == 0u) {
        return DEBUG_LINE_NONE;
    }

    copy_len = buffer->len;
    if (copy_len >= out_line_size) {
        copy_len = out_line_size - 1u;
    }

    memcpy(out_line, buffer->storage, copy_len);
    out_line[copy_len] = '\0';
    app->counters.line_ready_total += 1u;
    app->last_completed_line_length = buffer->len;
    debug_line_buffer_reset(buffer);
    return DEBUG_LINE_READY;
}

static DebugLineReadStatus debug_line_buffer_push(
    DebugApp *app,
    DebugLineBuffer *buffer,
    int ch,
    char *out_line,
    size_t out_line_size
) {
    hard_assert(app != NULL);
    hard_assert(buffer != NULL);
    hard_assert(out_line != NULL);
    hard_assert(out_line_size > 0u);

    if (ch == '\r' || ch == '\n') {
        return debug_line_buffer_finalize(app, buffer, out_line, out_line_size);
    }

    if (ch == 8 || ch == 127) {
        if (!buffer->overflowed && buffer->len > 0u) {
            buffer->len -= 1u;
        }
        buffer->flush_at = make_timeout_time_ms(DEBUG_COMMAND_IDLE_FLUSH_MS);
        return DEBUG_LINE_NONE;
    }

    if (ch < 32 || ch > 126) {
        app->counters.ignored_nonprintable_total += 1u;
        return DEBUG_LINE_NONE;
    }

    if (buffer->overflowed) {
        return DEBUG_LINE_NONE;
    }

    if (buffer->len >= (sizeof(buffer->storage) - 1u)) {
        buffer->overflowed = true;
        return DEBUG_LINE_NONE;
    }

    buffer->storage[buffer->len++] = (char)ch;
    buffer->flush_at = make_timeout_time_ms(DEBUG_COMMAND_IDLE_FLUSH_MS);
    return DEBUG_LINE_NONE;
}

static DebugLineReadStatus debug_line_buffer_flush_if_idle(
    DebugApp *app,
    DebugLineBuffer *buffer,
    char *out_line,
    size_t out_line_size
) {
    hard_assert(app != NULL);
    hard_assert(buffer != NULL);
    hard_assert(out_line != NULL);
    hard_assert(out_line_size > 0u);

    if ((buffer->len == 0u && !buffer->overflowed) || !time_reached(buffer->flush_at)) {
        return DEBUG_LINE_NONE;
    }

    return debug_line_buffer_finalize(app, buffer, out_line, out_line_size);
}

static const DebugParamDescriptor *debug_find_param(const char *name) {
    size_t i = 0u;

    hard_assert(name != NULL);

    for (i = 0u; i < DEBUG_PARAM_COUNT; ++i) {
        if (strcmp(g_debug_params[i].name, name) == 0) {
            return &g_debug_params[i];
        }
    }

    return NULL;
}

static bool debug_param_get_value(
    const DebugApp *app,
    const DebugParamDescriptor *param,
    DevlinkSerialValue *out_value
) {
    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_value != NULL);

    switch (param->id) {
        case DEBUG_PARAM_STATUS_LED_ON:
            *out_value = DEVLINK_SERIAL_VALUE_BOOL(app->status_led_on);
            return true;
        case DEBUG_PARAM_TEST_U8:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->test_u8);
            return true;
        case DEBUG_PARAM_TEST_F32:
            *out_value = DEVLINK_SERIAL_VALUE_F32(app->test_f32);
            return true;
        case DEBUG_PARAM_VERBOSE:
            *out_value = DEVLINK_SERIAL_VALUE_BOOL(app->debug_verbose);
            return true;
        default:
            return false;
    }
}

static bool debug_param_set_value(
    DebugApp *app,
    const DebugParamDescriptor *param,
    DevlinkSerialValue value
) {
    hard_assert(app != NULL);
    hard_assert(param != NULL);

    switch (param->id) {
        case DEBUG_PARAM_STATUS_LED_ON:
            app->status_led_on = value.bool_value;
            gpio_put(PICO_DEFAULT_LED_PIN, app->status_led_on);
            return true;
        case DEBUG_PARAM_TEST_U8:
            app->test_u8 = (uint8_t)value.u32_value;
            return true;
        case DEBUG_PARAM_TEST_F32:
            app->test_f32 = value.f32_value;
            return true;
        case DEBUG_PARAM_VERBOSE:
            app->debug_verbose = value.bool_value;
            return true;
        default:
            return false;
    }
}

static bool debug_value_out_of_bounds(
    const DebugParamDescriptor *param,
    DevlinkSerialValue value
) {
    hard_assert(param != NULL);

    if (!param->has_bounds) {
        return false;
    }

    switch (param->type) {
        case DEVLINK_SERIAL_TYPE_U8:
        case DEVLINK_SERIAL_TYPE_U16:
        case DEVLINK_SERIAL_TYPE_U32:
            return value.u32_value < param->min_value.u32_value || value.u32_value > param->max_value.u32_value;
        case DEVLINK_SERIAL_TYPE_F32:
            return value.f32_value < param->min_value.f32_value || value.f32_value > param->max_value.f32_value;
        default:
            return false;
    }
}

static bool debug_parse_param_value(
    const DebugParamDescriptor *param,
    const char *args_json,
    DevlinkSerialValue *out_value,
    const char **out_reason
) {
    int32_t int_value = 0;
    float float_value = 0.0f;

    hard_assert(param != NULL);
    hard_assert(args_json != NULL);
    hard_assert(out_value != NULL);
    hard_assert(out_reason != NULL);

    *out_reason = NULL;

    switch (param->type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            if (!devlink_serial_json_get_bool(args_json, "value", &out_value->bool_value)) {
                *out_reason = "wrong_type";
                return false;
            }
            return true;
        case DEVLINK_SERIAL_TYPE_U8:
            if (!devlink_serial_json_get_int32(args_json, "value", &int_value)) {
                *out_reason = "wrong_type";
                return false;
            }
            if (int_value < 0 || int_value > 255) {
                *out_reason = "out_of_range";
                return false;
            }
            out_value->u32_value = (uint32_t)int_value;
            break;
        case DEVLINK_SERIAL_TYPE_F32:
            if (!devlink_serial_json_get_float32(args_json, "value", &float_value)) {
                *out_reason = "wrong_type";
                return false;
            }
            if (!isfinite(float_value)) {
                *out_reason = "wrong_type";
                return false;
            }
            out_value->f32_value = float_value;
            break;
        default:
            *out_reason = "unsupported_type";
            return false;
    }

    if (debug_value_out_of_bounds(param, *out_value)) {
        *out_reason = "out_of_range";
        return false;
    }

    return true;
}

static void debug_format_value(
    DevlinkSerialScalarType type,
    DevlinkSerialValue value,
    char *buffer,
    size_t buffer_size
) {
    hard_assert(buffer != NULL);
    hard_assert(buffer_size > 0u);

    switch (type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            snprintf(buffer, buffer_size, "%s", value.bool_value ? "true" : "false");
            break;
        case DEVLINK_SERIAL_TYPE_U8:
        case DEVLINK_SERIAL_TYPE_U16:
        case DEVLINK_SERIAL_TYPE_U32:
            snprintf(buffer, buffer_size, "%lu", (unsigned long)value.u32_value);
            break;
        case DEVLINK_SERIAL_TYPE_I16:
        case DEVLINK_SERIAL_TYPE_I32:
            snprintf(buffer, buffer_size, "%ld", (long)value.i32_value);
            break;
        case DEVLINK_SERIAL_TYPE_F32:
            snprintf(buffer, buffer_size, "%.3f", (double)value.f32_value);
            break;
        default:
            snprintf(buffer, buffer_size, "unknown");
            break;
    }
}

static void debug_log_stats(const DebugApp *app, const char *tag) {
    hard_assert(app != NULL);
    hard_assert(tag != NULL);

    printf(
        "[%s] rx_bytes_total=%lu rx_ring_drops_total=%lu line_ready_total=%lu "
        "line_overflow_total=%lu ignored_nonprintable_total=%lu parse_ok_total=%lu "
        "parse_invalid_json_total=%lu parse_missing_field_total=%lu parse_wrong_type_total=%lu "
        "parse_unsupported_version_total=%lu parse_buffer_too_small_total=%lu wrong_device_total=%lu "
        "cmd_describe_total=%lu cmd_param_get_total=%lu cmd_param_set_total=%lu cmd_unknown_total=%lu "
        "param_set_success_total=%lu param_set_reject_total=%lu last_command_id=%lu "
        "last_command_name=%s last_target_device=%s last_param_name=%s last_parse_status=%s "
        "last_completed_line_length=%lu\n",
        tag,
        (unsigned long)app->counters.rx_bytes_total,
        (unsigned long)app->counters.rx_ring_drops_total,
        (unsigned long)app->counters.line_ready_total,
        (unsigned long)app->counters.line_overflow_total,
        (unsigned long)app->counters.ignored_nonprintable_total,
        (unsigned long)app->counters.parse_ok_total,
        (unsigned long)app->counters.parse_invalid_json_total,
        (unsigned long)app->counters.parse_missing_field_total,
        (unsigned long)app->counters.parse_wrong_type_total,
        (unsigned long)app->counters.parse_unsupported_version_total,
        (unsigned long)app->counters.parse_buffer_too_small_total,
        (unsigned long)app->counters.wrong_device_total,
        (unsigned long)app->counters.cmd_describe_total,
        (unsigned long)app->counters.cmd_param_get_total,
        (unsigned long)app->counters.cmd_param_set_total,
        (unsigned long)app->counters.cmd_unknown_total,
        (unsigned long)app->counters.param_set_success_total,
        (unsigned long)app->counters.param_set_reject_total,
        (unsigned long)app->last_command_id,
        app->last_command_name[0] != '\0' ? app->last_command_name : "-",
        app->last_target_device[0] != '\0' ? app->last_target_device : "-",
        app->last_param_name[0] != '\0' ? app->last_param_name : "-",
        app->last_parse_status[0] != '\0' ? app->last_parse_status : "-",
        (unsigned long)app->last_completed_line_length
    );
}

static void debug_log_boot(const DebugApp *app) {
    hard_assert(app != NULL);

    printf(
        "[boot] board=%s device=%s rx_pin=%u diag_tx_pin=%u baud=%u buffer=%u idle_flush_ms=%u "
        "stats_period_ms=%u diagnostics=%s init_ok=%s\n",
        DEBUG_BOARD_NAME,
        DEBUG_DEVICE_NAME,
        DEBUG_COMMAND_RX_GPIO,
        PICO_DEFAULT_UART_TX_PIN,
        DEBUG_COMMAND_BAUD,
        (unsigned int)sizeof(app->line_buffer.storage),
        DEBUG_COMMAND_IDLE_FLUSH_MS,
        DEBUG_STATS_PERIOD_MS,
        DEBUG_DIAGNOSTICS_LABEL,
        app->init_ok ? "true" : "false"
    );
}

static void debug_log_describe(void) {
    printf(
        "[describe] device=%s commands=device.describe,param.get,param.set,debug.snapshot,debug.reset_stats "
        "params=status_led.on:bool,test.u8:u8,test.f32:f32,debug.verbose:bool rx_pin=%u diag_tx_pin=%u "
        "baud=%u buffer=%u diagnostics=%s\n",
        DEBUG_DEVICE_NAME,
        DEBUG_COMMAND_RX_GPIO,
        PICO_DEFAULT_UART_TX_PIN,
        DEBUG_COMMAND_BAUD,
        (unsigned int)sizeof(((DebugApp *)0)->line_buffer.storage),
        DEBUG_DIAGNOSTICS_LABEL
    );
}

static void debug_log_parse_failure(const DebugApp *app, DevlinkSerialParseStatus status) {
    hard_assert(app != NULL);

    printf(
        "[parse] status=%s last_completed_line_length=%lu\n",
        debug_parse_status_name(status),
        (unsigned long)app->last_completed_line_length
    );
}

static void debug_log_raw_line(const char *line) {
    hard_assert(line != NULL);

    printf("[raw] line=\"");
    while (*line != '\0') {
        if (*line == '"' || *line == '\\') {
            putchar('\\');
        }
        putchar(*line);
        line++;
    }
    printf("\"\n");
}

static void debug_log_snapshot(const DebugApp *app) {
    hard_assert(app != NULL);

    debug_log_stats(app, "snapshot");
    printf(
        "[snapshot] status_led_on=%s test_u8=%u test_f32=%.3f debug_verbose=%s\n",
        app->status_led_on ? "true" : "false",
        app->test_u8,
        (double)app->test_f32,
        app->debug_verbose ? "true" : "false"
    );
}

static void debug_log_cmd_result(
    const DevlinkSerialCommand *command,
    const char *result,
    const char *detail_key,
    const char *detail_value
) {
    hard_assert(command != NULL);
    hard_assert(result != NULL);

    printf(
        "[cmd] id=%lu name=%s device=%s result=%s",
        (unsigned long)command->id,
        command->name,
        command->device,
        result
    );
    if (detail_key != NULL && detail_value != NULL) {
        printf(" %s=%s", detail_key, detail_value);
    }
    printf("\n");
}

static void debug_reset_observability(DebugApp *app) {
    bool verbose = false;

    hard_assert(app != NULL);

    verbose = app->debug_verbose;
    memset(&app->counters, 0, sizeof(app->counters));
    app->last_command_id = 0u;
    app->last_completed_line_length = 0u;
    app->last_command_name[0] = '\0';
    app->last_target_device[0] = '\0';
    app->last_param_name[0] = '\0';
    debug_copy_string(app->last_parse_status, sizeof(app->last_parse_status), "none");
    app->debug_verbose = verbose;
    app->next_stats_at = make_timeout_time_ms(DEBUG_STATS_PERIOD_MS);
}

static void debug_handle_param_get(DebugApp *app, const DevlinkSerialCommand *command) {
    char param_name[48] = {0};
    const DebugParamDescriptor *param = NULL;
    DevlinkSerialValue value = {0};
    char value_buffer[32] = {0};

    app->counters.cmd_param_get_total += 1u;

    if (!devlink_serial_json_get_string(command->args_json, "param", param_name, sizeof(param_name))) {
        debug_log_cmd_result(command, "error", "reason", "missing_param");
        return;
    }

    debug_copy_string(app->last_param_name, sizeof(app->last_param_name), param_name);
    param = debug_find_param(param_name);
    if (param == NULL) {
        debug_log_cmd_result(command, "error", "reason", "unknown_param");
        return;
    }

    if (!debug_param_get_value(app, param, &value)) {
        debug_log_cmd_result(command, "error", "reason", "param_read_failed");
        return;
    }

    debug_format_value(param->type, value, value_buffer, sizeof(value_buffer));
    debug_log_cmd_result(command, "ok", "value", value_buffer);
}

static void debug_handle_param_set(DebugApp *app, const DevlinkSerialCommand *command) {
    char param_name[48] = {0};
    const DebugParamDescriptor *param = NULL;
    DevlinkSerialValue value = {0};
    const char *reason = NULL;
    char value_buffer[32] = {0};

    app->counters.cmd_param_set_total += 1u;

    if (!devlink_serial_json_get_string(command->args_json, "param", param_name, sizeof(param_name))) {
        app->counters.param_set_reject_total += 1u;
        debug_log_cmd_result(command, "error", "reason", "missing_param");
        return;
    }

    debug_copy_string(app->last_param_name, sizeof(app->last_param_name), param_name);
    param = debug_find_param(param_name);
    if (param == NULL) {
        app->counters.param_set_reject_total += 1u;
        debug_log_cmd_result(command, "error", "reason", "unknown_param");
        return;
    }

    if (!debug_parse_param_value(param, command->args_json, &value, &reason)) {
        app->counters.param_set_reject_total += 1u;
        debug_log_cmd_result(command, "error", "reason", reason);
        return;
    }

    if (!debug_param_set_value(app, param, value)) {
        app->counters.param_set_reject_total += 1u;
        debug_log_cmd_result(command, "error", "reason", "param_write_failed");
        return;
    }

    app->counters.param_set_success_total += 1u;
    debug_format_value(param->type, value, value_buffer, sizeof(value_buffer));
    debug_log_cmd_result(command, "ok", "value", value_buffer);
}

static void debug_handle_line(DebugApp *app, const char *line) {
    DevlinkSerialCommand command = {0};
    DevlinkSerialParseStatus parse_status = DEVLINK_SERIAL_PARSE_OK;

    hard_assert(app != NULL);
    hard_assert(line != NULL);

    if (app->debug_verbose) {
        debug_log_raw_line(line);
    }

    parse_status = devlink_serial_parse_command(line, &command);
    debug_copy_string(app->last_parse_status, sizeof(app->last_parse_status), debug_parse_status_name(parse_status));

    switch (parse_status) {
        case DEVLINK_SERIAL_PARSE_OK:
            app->counters.parse_ok_total += 1u;
            break;
        case DEVLINK_SERIAL_PARSE_INVALID_JSON:
            app->counters.parse_invalid_json_total += 1u;
            break;
        case DEVLINK_SERIAL_PARSE_MISSING_FIELD:
            app->counters.parse_missing_field_total += 1u;
            break;
        case DEVLINK_SERIAL_PARSE_WRONG_TYPE:
            app->counters.parse_wrong_type_total += 1u;
            break;
        case DEVLINK_SERIAL_PARSE_UNSUPPORTED_VERSION:
            app->counters.parse_unsupported_version_total += 1u;
            break;
        case DEVLINK_SERIAL_PARSE_BUFFER_TOO_SMALL:
            app->counters.parse_buffer_too_small_total += 1u;
            break;
        default:
            break;
    }

    if (parse_status != DEVLINK_SERIAL_PARSE_OK) {
        debug_log_parse_failure(app, parse_status);
        return;
    }

    app->last_command_id = command.id;
    debug_copy_string(app->last_command_name, sizeof(app->last_command_name), command.name);
    debug_copy_string(app->last_target_device, sizeof(app->last_target_device), command.device);

    if (strcmp(command.name, "device.describe") == 0) {
        if (strcmp(command.device, "*") != 0 && strcmp(command.device, DEBUG_DEVICE_NAME) != 0) {
            app->counters.wrong_device_total += 1u;
            debug_log_cmd_result(&command, "error", "reason", "wrong_device");
            return;
        }

        app->counters.cmd_describe_total += 1u;
        debug_log_describe();
        debug_log_cmd_result(&command, "ok", "detail", "described");
        return;
    }

    if (strcmp(command.device, DEBUG_DEVICE_NAME) != 0) {
        app->counters.wrong_device_total += 1u;
        debug_log_cmd_result(&command, "error", "reason", "wrong_device");
        return;
    }

    if (strcmp(command.name, "param.get") == 0) {
        debug_handle_param_get(app, &command);
        return;
    }

    if (strcmp(command.name, "param.set") == 0) {
        debug_handle_param_set(app, &command);
        return;
    }

    if (strcmp(command.name, "debug.snapshot") == 0) {
        debug_log_snapshot(app);
        debug_log_cmd_result(&command, "ok", "detail", "snapshot");
        return;
    }

    if (strcmp(command.name, "debug.reset_stats") == 0) {
        debug_reset_observability(app);
        debug_log_cmd_result(&command, "ok", "detail", "stats_reset");
        return;
    }

    app->counters.cmd_unknown_total += 1u;
    debug_log_cmd_result(&command, "error", "reason", "unknown_command");
}

static void debug_poll_commands(DebugApp *app) {
    char line[256] = {0};
    uint8_t received_byte = 0u;
    uint32_t dropped_count = 0u;

    hard_assert(app != NULL);

    if (!app->init_ok) {
        return;
    }

    while (pio_uart_rx_try_getc(&app->command_rx, &received_byte)) {
        DebugLineReadStatus status = DEBUG_LINE_NONE;

        app->counters.rx_bytes_total += 1u;
        status = debug_line_buffer_push(app, &app->line_buffer, (int)received_byte, line, sizeof(line));
        if (status == DEBUG_LINE_READY) {
            debug_handle_line(app, line);
        }
    }

    if (debug_line_buffer_flush_if_idle(app, &app->line_buffer, line, sizeof(line)) == DEBUG_LINE_READY) {
        debug_handle_line(app, line);
    }

    dropped_count = pio_uart_rx_take_dropped_count(&app->command_rx);
    if (dropped_count > 0u) {
        app->counters.rx_ring_drops_total += dropped_count;
    }
}

static void debug_emit_periodic_stats(DebugApp *app) {
    hard_assert(app != NULL);

    if (!time_reached(app->next_stats_at)) {
        return;
    }

    debug_log_stats(app, "stats");
    app->next_stats_at = make_timeout_time_ms(DEBUG_STATS_PERIOD_MS);
}

void debug_app_init(DebugApp *app) {
    hard_assert(app != NULL);

    memset(app, 0, sizeof(*app));

    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);

    app->status_led_on = false;
    app->debug_verbose = false;
    app->test_u8 = 0u;
    app->test_f32 = 0.0f;
    gpio_put(PICO_DEFAULT_LED_PIN, app->status_led_on);

    debug_line_buffer_reset(&app->line_buffer);
    app->next_stats_at = make_timeout_time_ms(DEBUG_STATS_PERIOD_MS);
    debug_copy_string(app->last_parse_status, sizeof(app->last_parse_status), "none");

    app->init_ok = pio_uart_rx_init(&app->command_rx, pio0, DEBUG_COMMAND_RX_GPIO, DEBUG_COMMAND_BAUD);
    debug_log_boot(app);
    if (!app->init_ok) {
        printf("[boot] status=error reason=pio_uart_rx_init_failed\n");
    }
}

void debug_app_poll(DebugApp *app) {
    hard_assert(app != NULL);

    debug_poll_commands(app);
    debug_emit_periodic_stats(app);
}
