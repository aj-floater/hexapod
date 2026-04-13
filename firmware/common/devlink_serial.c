#include "devlink_serial.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "pico/stdlib.h"

static const char *skip_ws(const char *cursor) {
    while (*cursor != '\0' && isspace((unsigned char)*cursor)) {
        cursor++;
    }
    return cursor;
}

static bool copy_json_string(const char *cursor, char *out_value, size_t out_value_size) {
    size_t out_len = 0u;

    if (cursor == NULL || out_value == NULL || out_value_size == 0u || *cursor != '"') {
        return false;
    }

    cursor++;
    while (*cursor != '\0') {
        char ch = *cursor++;
        if (ch == '"') {
            out_value[out_len] = '\0';
            return true;
        }
        if (ch == '\\') {
            char escaped = *cursor++;
            if (escaped == '\0') {
                return false;
            }
            switch (escaped) {
                case '"':
                case '\\':
                case '/':
                    ch = escaped;
                    break;
                case 'b':
                    ch = '\b';
                    break;
                case 'f':
                    ch = '\f';
                    break;
                case 'n':
                    ch = '\n';
                    break;
                case 'r':
                    ch = '\r';
                    break;
                case 't':
                    ch = '\t';
                    break;
                default:
                    return false;
            }
        }
        if (out_len + 1u >= out_value_size) {
            return false;
        }
        out_value[out_len++] = ch;
    }

    return false;
}

static const char *skip_json_string(const char *cursor) {
    hard_assert(cursor != NULL);
    hard_assert(*cursor == '"');

    cursor++;
    while (*cursor != '\0') {
        if (*cursor == '\\') {
            cursor++;
            if (*cursor == '\0') {
                return NULL;
            }
        } else if (*cursor == '"') {
            return cursor + 1;
        }
        cursor++;
    }

    return NULL;
}

static const char *skip_json_value(const char *cursor);

static const char *skip_json_compound(const char *cursor, char open_ch, char close_ch) {
    int depth = 0;

    hard_assert(cursor != NULL);
    hard_assert(*cursor == open_ch);

    while (*cursor != '\0') {
        if (*cursor == '"') {
            cursor = skip_json_string(cursor);
            if (cursor == NULL) {
                return NULL;
            }
            continue;
        }
        if (*cursor == open_ch) {
            depth++;
        } else if (*cursor == close_ch) {
            depth--;
            if (depth == 0) {
                return cursor + 1;
            }
        }
        cursor++;
    }

    return NULL;
}

static const char *skip_json_value(const char *cursor) {
    cursor = skip_ws(cursor);
    if (*cursor == '\0') {
        return NULL;
    }

    switch (*cursor) {
        case '"':
            return skip_json_string(cursor);
        case '{':
            return skip_json_compound(cursor, '{', '}');
        case '[':
            return skip_json_compound(cursor, '[', ']');
        default:
            while (*cursor != '\0' && *cursor != ',' && *cursor != '}' && *cursor != ']') {
                cursor++;
            }
            return cursor;
    }
}

static const char *find_object_key_value(const char *json_object, const char *key) {
    char parsed_key[DEVLINK_SERIAL_COMMAND_MAX_LEN] = {0};
    const char *cursor = skip_ws(json_object);

    if (cursor == NULL || key == NULL || *cursor != '{') {
        return NULL;
    }

    cursor++;

    while (true) {
        cursor = skip_ws(cursor);
        if (*cursor == '}') {
            return NULL;
        }
        if (*cursor != '"') {
            return NULL;
        }

        if (!copy_json_string(cursor, parsed_key, sizeof(parsed_key))) {
            return NULL;
        }

        cursor = skip_json_string(cursor);
        if (cursor == NULL) {
            return NULL;
        }

        cursor = skip_ws(cursor);
        if (*cursor != ':') {
            return NULL;
        }
        cursor = skip_ws(cursor + 1);

        if (strcmp(parsed_key, key) == 0) {
            return cursor;
        }

        cursor = skip_json_value(cursor);
        if (cursor == NULL) {
            return NULL;
        }

        cursor = skip_ws(cursor);
        if (*cursor == ',') {
            cursor++;
            continue;
        }
        if (*cursor == '}') {
            return NULL;
        }
        return NULL;
    }
}

static bool copy_json_object(const char *cursor, char *out_json, size_t out_json_size) {
    const char *end = skip_json_value(cursor);
    size_t copy_len = 0u;

    if (cursor == NULL || out_json == NULL || out_json_size == 0u || *cursor != '{' || end == NULL) {
        return false;
    }

    copy_len = (size_t)(end - cursor);
    if (copy_len + 1u > out_json_size) {
        return false;
    }

    memcpy(out_json, cursor, copy_len);
    out_json[copy_len] = '\0';
    return true;
}

static bool parse_bool_value(const char *cursor, bool *out_value) {
    cursor = skip_ws(cursor);
    if (strncmp(cursor, "true", 4) == 0) {
        cursor = skip_ws(cursor + 4);
        if (*cursor != ',' && *cursor != '}' && *cursor != ']') {
            return false;
        }
        *out_value = true;
        return true;
    }
    if (strncmp(cursor, "false", 5) == 0) {
        cursor = skip_ws(cursor + 5);
        if (*cursor != ',' && *cursor != '}' && *cursor != ']') {
            return false;
        }
        *out_value = false;
        return true;
    }
    return false;
}

static bool parse_int32_value(const char *cursor, int32_t *out_value) {
    char *end = NULL;
    long parsed = 0l;

    if (cursor == NULL || out_value == NULL) {
        return false;
    }

    cursor = skip_ws(cursor);
    parsed = strtol(cursor, &end, 10);
    if (end == cursor) {
        return false;
    }
    end = (char *)skip_ws(end);
    if (*end != ',' && *end != '}' && *end != ']') {
        return false;
    }

    *out_value = (int32_t)parsed;
    return true;
}

static bool parse_uint32_value(const char *cursor, uint32_t *out_value) {
    int32_t signed_value = 0;

    if (!parse_int32_value(cursor, &signed_value) || signed_value < 0) {
        return false;
    }

    *out_value = (uint32_t)signed_value;
    return true;
}

static bool parse_float32_value(const char *cursor, float *out_value) {
    char *end = NULL;
    float parsed = 0.0f;

    if (cursor == NULL || out_value == NULL) {
        return false;
    }

    cursor = skip_ws(cursor);
    parsed = strtof(cursor, &end);
    if (end == cursor) {
        return false;
    }
    end = (char *)skip_ws(end);
    if (*end != ',' && *end != '}' && *end != ']') {
        return false;
    }

    *out_value = parsed;
    return true;
}

static const char *scalar_type_to_string(DevlinkSerialScalarType type) {
    switch (type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            return "bool";
        case DEVLINK_SERIAL_TYPE_U8:
            return "u8";
        case DEVLINK_SERIAL_TYPE_U16:
            return "u16";
        case DEVLINK_SERIAL_TYPE_U32:
            return "u32";
        case DEVLINK_SERIAL_TYPE_I16:
            return "i16";
        case DEVLINK_SERIAL_TYPE_I32:
            return "i32";
        case DEVLINK_SERIAL_TYPE_F32:
            return "f32";
        default:
            return "unknown";
    }
}

static const char *access_to_string(DevlinkSerialAccess access) {
    return (access == DEVLINK_SERIAL_ACCESS_RW) ? "rw" : "ro";
}

static const char *sample_format_to_string(DevlinkSerialSampleFormat format) {
    return (format == DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY) ? "binary" : "json";
}

static const char *device_default_sample_format(const DevlinkSerialDeviceDescriptor *device) {
    if (device->stream_count == 0u) {
        return "json";
    }
    return sample_format_to_string(device->streams[0].sample_format);
}

static void print_float32_value(float value) {
    char buffer[32] = {0};
    size_t len = 0u;

    snprintf(buffer, sizeof(buffer), "%.3f", (double)value);
    len = strlen(buffer);

    while (len > 0u && buffer[len - 1u] == '0') {
        buffer[--len] = '\0';
    }
    if (len > 0u && buffer[len - 1u] == '.') {
        buffer[len++] = '0';
        buffer[len] = '\0';
    }

    printf("%s", buffer);
}

static void print_scalar_value(DevlinkSerialScalarType type, DevlinkSerialValue value) {
    switch (type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            printf(value.bool_value ? "true" : "false");
            break;
        case DEVLINK_SERIAL_TYPE_U8:
        case DEVLINK_SERIAL_TYPE_U16:
        case DEVLINK_SERIAL_TYPE_U32:
            printf("%lu", (unsigned long)value.u32_value);
            break;
        case DEVLINK_SERIAL_TYPE_I16:
        case DEVLINK_SERIAL_TYPE_I32:
            printf("%ld", (long)value.i32_value);
            break;
        case DEVLINK_SERIAL_TYPE_F32:
            print_float32_value(value.f32_value);
            break;
        default:
            printf("null");
            break;
    }
}

static void print_le_u16(uint16_t value) {
    putchar_raw((int)(value & 0xffu));
    putchar_raw((int)((value >> 8u) & 0xffu));
}

static void print_le_u32(uint32_t value) {
    putchar_raw((int)(value & 0xffu));
    putchar_raw((int)((value >> 8u) & 0xffu));
    putchar_raw((int)((value >> 16u) & 0xffu));
    putchar_raw((int)((value >> 24u) & 0xffu));
}

static void print_le_u64(uint64_t value) {
    for (size_t shift = 0u; shift < 64u; shift += 8u) {
        putchar_raw((int)((value >> shift) & 0xffu));
    }
}

static void print_binary_scalar_value(DevlinkSerialScalarType type, DevlinkSerialValue value) {
    union {
        float f32;
        uint32_t u32;
    } f32_bits = {0};

    switch (type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            putchar_raw(value.bool_value ? 1 : 0);
            break;
        case DEVLINK_SERIAL_TYPE_U8:
            putchar_raw((int)((uint8_t)value.u32_value));
            break;
        case DEVLINK_SERIAL_TYPE_U16:
            print_le_u16((uint16_t)value.u32_value);
            break;
        case DEVLINK_SERIAL_TYPE_U32:
            print_le_u32(value.u32_value);
            break;
        case DEVLINK_SERIAL_TYPE_I16:
            print_le_u16((uint16_t)(int16_t)value.i32_value);
            break;
        case DEVLINK_SERIAL_TYPE_I32:
            print_le_u32((uint32_t)value.i32_value);
            break;
        case DEVLINK_SERIAL_TYPE_F32:
            f32_bits.f32 = value.f32_value;
            print_le_u32(f32_bits.u32);
            break;
        default:
            break;
    }
}

static bool value_fits_type(DevlinkSerialScalarType type, DevlinkSerialValue value) {
    switch (type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            return true;
        case DEVLINK_SERIAL_TYPE_U8:
            return value.u32_value <= UINT8_MAX;
        case DEVLINK_SERIAL_TYPE_U16:
            return value.u32_value <= UINT16_MAX;
        case DEVLINK_SERIAL_TYPE_U32:
            return true;
        case DEVLINK_SERIAL_TYPE_I16:
            return value.i32_value >= INT16_MIN && value.i32_value <= INT16_MAX;
        case DEVLINK_SERIAL_TYPE_I32:
            return true;
        case DEVLINK_SERIAL_TYPE_F32:
            return true;
        default:
            return false;
    }
}

static bool values_equal(DevlinkSerialScalarType type, DevlinkSerialValue lhs, DevlinkSerialValue rhs) {
    switch (type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            return lhs.bool_value == rhs.bool_value;
        case DEVLINK_SERIAL_TYPE_U8:
        case DEVLINK_SERIAL_TYPE_U16:
        case DEVLINK_SERIAL_TYPE_U32:
            return lhs.u32_value == rhs.u32_value;
        case DEVLINK_SERIAL_TYPE_I16:
        case DEVLINK_SERIAL_TYPE_I32:
            return lhs.i32_value == rhs.i32_value;
        case DEVLINK_SERIAL_TYPE_F32:
            return lhs.f32_value == rhs.f32_value;
        default:
            return false;
    }
}

static bool value_out_of_bounds(const DevlinkSerialParamDescriptor *param, DevlinkSerialValue value) {
    if (!param->has_bounds) {
        return false;
    }

    switch (param->type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            return false;
        case DEVLINK_SERIAL_TYPE_U8:
        case DEVLINK_SERIAL_TYPE_U16:
        case DEVLINK_SERIAL_TYPE_U32:
            return value.u32_value < param->min_value.u32_value || value.u32_value > param->max_value.u32_value;
        case DEVLINK_SERIAL_TYPE_I16:
        case DEVLINK_SERIAL_TYPE_I32:
            return value.i32_value < param->min_value.i32_value || value.i32_value > param->max_value.i32_value;
        case DEVLINK_SERIAL_TYPE_F32:
            return value.f32_value < param->min_value.f32_value || value.f32_value > param->max_value.f32_value;
        default:
            return true;
    }
}

static const DevlinkSerialParamDescriptor *find_param_descriptor(
    const DevlinkSerialDeviceDescriptor *device,
    const char *param_name
) {
    for (size_t i = 0u; i < device->param_count; i++) {
        const DevlinkSerialParamDescriptor *param = &device->params[i];
        if (strcmp(param->name, param_name) == 0) {
            return param;
        }
    }
    return NULL;
}

static const DevlinkSerialCommandDescriptor *find_command_descriptor(
    const DevlinkSerialDeviceDescriptor *device,
    const char *command_name
) {
    for (size_t i = 0u; i < device->command_count; i++) {
        const DevlinkSerialCommandDescriptor *command = &device->commands[i];
        if (strcmp(command->name, command_name) == 0) {
            return command;
        }
    }
    return NULL;
}

static bool device_supports_params(const DevlinkSerialDeviceDescriptor *device) {
    return device->param_count > 0u && device->param_getter != NULL;
}

static bool device_supports_param_set(const DevlinkSerialDeviceDescriptor *device) {
    if (!device_supports_params(device) || device->param_setter == NULL) {
        return false;
    }

    for (size_t i = 0u; i < device->param_count; i++) {
        if (device->params[i].access == DEVLINK_SERIAL_ACCESS_RW) {
            return true;
        }
    }
    return false;
}

static bool parse_value_for_type(
    const char *json_object,
    const char *key,
    DevlinkSerialScalarType type,
    DevlinkSerialValue *out_value
) {
    int32_t int_value = 0;
    uint32_t uint_value = 0u;
    float float_value = 0.0f;

    switch (type) {
        case DEVLINK_SERIAL_TYPE_BOOL:
            return devlink_serial_json_get_bool(json_object, key, &out_value->bool_value);
        case DEVLINK_SERIAL_TYPE_U8:
        case DEVLINK_SERIAL_TYPE_U16:
        case DEVLINK_SERIAL_TYPE_U32:
            if (!devlink_serial_json_get_int32(json_object, key, &int_value) || int_value < 0) {
                return false;
            }
            uint_value = (uint32_t)int_value;
            out_value->u32_value = uint_value;
            return value_fits_type(type, *out_value);
        case DEVLINK_SERIAL_TYPE_I16:
        case DEVLINK_SERIAL_TYPE_I32:
            if (!devlink_serial_json_get_int32(json_object, key, &int_value)) {
                return false;
            }
            out_value->i32_value = int_value;
            return value_fits_type(type, *out_value);
        case DEVLINK_SERIAL_TYPE_F32:
            if (!devlink_serial_json_get_float32(json_object, key, &float_value)) {
                return false;
            }
            out_value->f32_value = float_value;
            return value_fits_type(type, *out_value);
        default:
            return false;
    }
}

static void print_param_result(
    const DevlinkSerialDeviceDescriptor *device,
    uint32_t id,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value
) {
    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":true,"
        "\"result\":{\"param\":\"%s\",\"value\":",
        DEVLINK_SERIAL_VERSION,
        device->device,
        (unsigned long)id,
        param->name
    );
    print_scalar_value(param->type, value);
    printf("}}\r\n");
}

static void print_param_list_result(
    const DevlinkSerialDeviceDescriptor *device,
    uint32_t id,
    void *context
) {
    bool first = true;

    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":true,\"result\":{\"params\":[",
        DEVLINK_SERIAL_VERSION,
        device->device,
        (unsigned long)id
    );

    for (size_t i = 0u; i < device->param_count; i++) {
        DevlinkSerialValue value = {0};
        const DevlinkSerialParamDescriptor *param = &device->params[i];

        if (!device->param_getter(context, param, &value)) {
            continue;
        }

        if (!first) {
            printf(",");
        }

        printf("{\"name\":\"%s\",\"value\":", param->name);
        print_scalar_value(param->type, value);
        printf("}");
        first = false;
    }

    printf("]}}\r\n");
}

static bool handle_param_command(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command
) {
    char param_name[48] = {0};
    const DevlinkSerialParamDescriptor *param = NULL;
    DevlinkSerialValue value = {0};
    const char *error_code = NULL;
    const char *error_message = NULL;

    if (!device_supports_params(device)) {
        return false;
    }

    if (strcmp(command->name, "param.list") == 0) {
        print_param_list_result(device, command->id, context);
        return true;
    }

    if (strcmp(command->name, "param.get") == 0) {
        if (!devlink_serial_json_get_string(command->args_json, "param", param_name, sizeof(param_name))) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "invalid_args",
                "param argument required"
            );
            return true;
        }

        param = find_param_descriptor(device, param_name);
        if (param == NULL) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "unknown_param",
                "parameter not found"
            );
            return true;
        }

        if (!device->param_getter(context, param, &value)) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "param_read_failed",
                "parameter read failed"
            );
            return true;
        }

        print_param_result(device, command->id, param, value);
        return true;
    }

    if (strcmp(command->name, "param.set") == 0) {
        if (!device_supports_param_set(device)) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "unknown_command",
                "command not supported"
            );
            return true;
        }

        if (!devlink_serial_json_get_string(command->args_json, "param", param_name, sizeof(param_name))) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "invalid_args",
                "param argument required"
            );
            return true;
        }

        param = find_param_descriptor(device, param_name);
        if (param == NULL) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "unknown_param",
                "parameter not found"
            );
            return true;
        }

        if (param->access != DEVLINK_SERIAL_ACCESS_RW) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "read_only_param",
                "parameter is read only"
            );
            return true;
        }

        if (!parse_value_for_type(command->args_json, "value", param->type, &value)) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "invalid_args",
                "param value has the wrong type"
            );
            return true;
        }

        if (value_out_of_bounds(param, value)) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "value_out_of_range",
                "param value outside allowed range"
            );
            return true;
        }

        if (!device->param_setter(context, param, value, &error_code, &error_message)) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                (error_code != NULL) ? error_code : "param_write_failed",
                (error_message != NULL) ? error_message : "parameter write failed"
            );
            return true;
        }

        if (!device->param_getter(context, param, &value)) {
            devlink_serial_print_resp_error(
                device,
                command->id,
                "param_read_failed",
                "parameter read failed"
            );
            return true;
        }

        print_param_result(device, command->id, param, value);
        return true;
    }

    return false;
}

static bool handle_builtin_command(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command
) {
    if (strcmp(command->name, "device.describe") == 0) {
        devlink_serial_print_discovery(device);
        devlink_serial_print_resp_ok(device, command->id);
        return true;
    }

    return handle_param_command(device, context, command);
}

void devlink_serial_line_buffer_init(
    DevlinkSerialLineBuffer *buffer,
    char *storage,
    size_t storage_size,
    uint32_t idle_flush_ms
) {
    hard_assert(buffer != NULL);
    hard_assert(storage != NULL);
    hard_assert(storage_size > 1u);
    hard_assert(idle_flush_ms > 0u);

    buffer->storage = storage;
    buffer->storage_size = storage_size;
    buffer->idle_flush_ms = idle_flush_ms;
    devlink_serial_line_buffer_reset(buffer);
}

void devlink_serial_line_buffer_reset(DevlinkSerialLineBuffer *buffer) {
    hard_assert(buffer != NULL);

    buffer->len = 0u;
    buffer->overflowed = false;
    buffer->flush_at = make_timeout_time_ms(buffer->idle_flush_ms);
}

static DevlinkSerialLineReadStatus line_buffer_finalize(
    DevlinkSerialLineBuffer *buffer,
    char *out_line,
    size_t out_line_size
) {
    size_t copy_len = 0u;

    if (buffer->overflowed) {
        devlink_serial_line_buffer_reset(buffer);
        return DEVLINK_SERIAL_LINE_OVERFLOW;
    }

    if (buffer->len == 0u) {
        return DEVLINK_SERIAL_LINE_NONE;
    }

    copy_len = buffer->len;
    if (copy_len >= out_line_size) {
        copy_len = out_line_size - 1u;
    }

    memcpy(out_line, buffer->storage, copy_len);
    out_line[copy_len] = '\0';
    devlink_serial_line_buffer_reset(buffer);
    return DEVLINK_SERIAL_LINE_READY;
}

DevlinkSerialLineReadStatus devlink_serial_line_buffer_push(
    DevlinkSerialLineBuffer *buffer,
    int ch,
    char *out_line,
    size_t out_line_size
) {
    hard_assert(buffer != NULL);
    hard_assert(out_line != NULL);
    hard_assert(out_line_size > 0u);

    if (ch == '\r' || ch == '\n') {
        return line_buffer_finalize(buffer, out_line, out_line_size);
    }

    if (ch == 8 || ch == 127) {
        if (!buffer->overflowed && buffer->len > 0u) {
            buffer->len--;
        }
        buffer->flush_at = make_timeout_time_ms(buffer->idle_flush_ms);
        return DEVLINK_SERIAL_LINE_NONE;
    }

    if (ch < 32 || ch > 126) {
        return DEVLINK_SERIAL_LINE_NONE;
    }

    if (buffer->overflowed) {
        return DEVLINK_SERIAL_LINE_NONE;
    }

    if (buffer->len >= (buffer->storage_size - 1u)) {
        buffer->overflowed = true;
        return DEVLINK_SERIAL_LINE_NONE;
    }

    buffer->storage[buffer->len++] = (char)ch;
    buffer->flush_at = make_timeout_time_ms(buffer->idle_flush_ms);
    return DEVLINK_SERIAL_LINE_NONE;
}

DevlinkSerialLineReadStatus devlink_serial_line_buffer_flush_if_idle(
    DevlinkSerialLineBuffer *buffer,
    char *out_line,
    size_t out_line_size
) {
    hard_assert(buffer != NULL);
    hard_assert(out_line != NULL);
    hard_assert(out_line_size > 0u);

    if ((buffer->len == 0u && !buffer->overflowed) || !time_reached(buffer->flush_at)) {
        return DEVLINK_SERIAL_LINE_NONE;
    }

    return line_buffer_finalize(buffer, out_line, out_line_size);
}

void devlink_serial_print_hello(const DevlinkSerialDeviceDescriptor *device) {
    printf(
        "{\"type\":\"hello\",\"version\":%u,\"device\":\"%s\",\"protocol\":\"%s\",\"firmware\":\"%s\"}\r\n",
        DEVLINK_SERIAL_VERSION,
        device->device,
        DEVLINK_SERIAL_PROTOCOL,
        device->firmware
    );
}

void devlink_serial_print_capabilities(const DevlinkSerialDeviceDescriptor *device) {
    printf(
        "{\"type\":\"capabilities\",\"version\":%u,\"device\":\"%s\",\"commands\":[",
        DEVLINK_SERIAL_VERSION,
        device->device
    );

    for (size_t i = 0u; i < device->command_count; i++) {
        const DevlinkSerialCommandDescriptor *command = &device->commands[i];
        printf("{\"name\":\"%s\",\"args\":[", command->name);
        for (size_t arg_index = 0u; arg_index < command->arg_count; arg_index++) {
            const DevlinkSerialCommandArgDescriptor *arg = &command->args[arg_index];
            printf(
                "{\"name\":\"%s\",\"type\":\"%s\",\"required\":%s}%s",
                arg->name,
                arg->type,
                arg->required ? "true" : "false",
                (arg_index + 1u == command->arg_count) ? "" : ","
            );
        }
        printf("]},");
    }

    printf("{\"name\":\"device.describe\",\"args\":[]}");

    if (device_supports_params(device)) {
        printf(",");
    }

    if (device_supports_params(device)) {
        printf("{\"name\":\"param.list\",\"args\":[]},");
        printf("{\"name\":\"param.get\",\"args\":[{\"name\":\"param\",\"type\":\"string\",\"required\":true}]}");
        if (device_supports_param_set(device)) {
            printf(
                ",{\"name\":\"param.set\",\"args\":["
                "{\"name\":\"param\",\"type\":\"string\",\"required\":true},"
                "{\"name\":\"value\",\"type\":\"integer\",\"required\":true}"
                "]}"
            );
        }
    }

    printf("],\"streams\":[");
    for (size_t i = 0u; i < device->stream_count; i++) {
        const DevlinkSerialStreamDescriptor *stream = &device->streams[i];
        printf(
            "{\"name\":\"%s\",\"id\":%u,\"sample_format\":\"%s\",\"fields\":[",
            stream->name,
            (unsigned int)stream->id,
            sample_format_to_string(stream->sample_format)
        );
        for (size_t field_index = 0u; field_index < stream->field_count; field_index++) {
            const DevlinkSerialStreamFieldDescriptor *field = &stream->fields[field_index];
            printf(
                "{\"name\":\"%s\",\"type\":\"%s\",\"unit\":\"%s\"}%s",
                field->name,
                scalar_type_to_string(field->type),
                field->unit,
                (field_index + 1u == stream->field_count) ? "" : ","
            );
        }
        printf("]}%s", (i + 1u == device->stream_count) ? "" : ",");
    }

    printf(
        "],\"telemetry\":{\"sample_formats\":[\"json\",\"binary\"],\"default_sample_format\":\"%s\"},"
        "\"params\":["
        ,
        device_default_sample_format(device)
    );
    for (size_t i = 0u; i < device->param_count; i++) {
        const DevlinkSerialParamDescriptor *param = &device->params[i];
        printf(
            "{\"name\":\"%s\",\"type\":\"%s\",\"access\":\"%s\",\"default\":",
            param->name,
            scalar_type_to_string(param->type),
            access_to_string(param->access)
        );
        print_scalar_value(param->type, param->default_value);
        if (param->has_bounds) {
            printf(",\"min\":");
            print_scalar_value(param->type, param->min_value);
            printf(",\"max\":");
            print_scalar_value(param->type, param->max_value);
        }
        printf("}%s", (i + 1u == device->param_count) ? "" : ",");
    }
    printf("]}\r\n");
}

void devlink_serial_print_discovery(const DevlinkSerialDeviceDescriptor *device) {
    devlink_serial_print_hello(device);
    devlink_serial_print_capabilities(device);
}

void devlink_serial_print_event(
    const DevlinkSerialDeviceDescriptor *device,
    const char *name,
    const char *severity
) {
    printf(
        "{\"type\":\"event\",\"version\":%u,\"device\":\"%s\",\"name\":\"%s\",\"severity\":\"%s\"}\r\n",
        DEVLINK_SERIAL_VERSION,
        device->device,
        name,
        severity
    );
}

void devlink_serial_print_log(
    const DevlinkSerialDeviceDescriptor *device,
    const char *level,
    const char *msg
) {
    printf(
        "{\"type\":\"log\",\"version\":%u,\"device\":\"%s\",\"level\":\"%s\",\"msg\":\"%s\"}\r\n",
        DEVLINK_SERIAL_VERSION,
        device->device,
        level,
        msg
    );
}

void devlink_serial_print_resp_ok(const DevlinkSerialDeviceDescriptor *device, uint32_t id) {
    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":true}\r\n",
        DEVLINK_SERIAL_VERSION,
        device->device,
        (unsigned long)id
    );
}

void devlink_serial_print_resp_error(
    const DevlinkSerialDeviceDescriptor *device,
    uint32_t id,
    const char *code,
    const char *message
) {
    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":false,"
        "\"error\":{\"code\":\"%s\",\"message\":\"%s\"}}\r\n",
        DEVLINK_SERIAL_VERSION,
        device->device,
        (unsigned long)id,
        code,
        message
    );
}

void devlink_serial_print_resp_result_json(
    const DevlinkSerialDeviceDescriptor *device,
    uint32_t id,
    const char *result_json
) {
    if (result_json == NULL || *result_json == '\0') {
        result_json = "{}";
    }

    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":true,\"result\":%s}\r\n",
        DEVLINK_SERIAL_VERSION,
        device->device,
        (unsigned long)id,
        result_json
    );
}

void devlink_serial_print_sample(
    const DevlinkSerialDeviceDescriptor *device,
    const DevlinkSerialStreamDescriptor *stream,
    uint32_t seq,
    uint64_t t_us,
    const DevlinkSerialValue *values
) {
    if (stream->sample_format == DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY) {
        putchar_raw(0xa5);
        putchar_raw((int)DEVLINK_SERIAL_VERSION);
        putchar_raw((int)stream->id);
        print_le_u32(seq);
        print_le_u64(t_us);
        for (size_t i = 0u; i < stream->field_count; i++) {
            print_binary_scalar_value(stream->fields[i].type, values[i]);
        }
        printf("\r\n");
        return;
    }

    printf(
        "{\"type\":\"sample\",\"version\":%u,\"device\":\"%s\",\"stream\":\"%s\",\"seq\":%lu,"
        "\"t_us\":%llu,\"data\":{",
        DEVLINK_SERIAL_VERSION,
        device->device,
        stream->name,
        (unsigned long)seq,
        (unsigned long long)t_us
    );

    for (size_t i = 0u; i < stream->field_count; i++) {
        const DevlinkSerialStreamFieldDescriptor *field = &stream->fields[i];
        printf("\"%s\":", field->name);
        print_scalar_value(field->type, values[i]);
        if (i + 1u != stream->field_count) {
            printf(",");
        }
    }

    printf("}}\r\n");
}

void devlink_serial_print_parse_error(
    const DevlinkSerialDeviceDescriptor *device,
    DevlinkSerialParseStatus status
) {
    switch (status) {
        case DEVLINK_SERIAL_PARSE_INVALID_JSON:
            devlink_serial_print_event(device, "protocol.invalid_json", "error");
            break;
        case DEVLINK_SERIAL_PARSE_MISSING_FIELD:
        case DEVLINK_SERIAL_PARSE_WRONG_TYPE:
            devlink_serial_print_event(device, "protocol.invalid_command", "error");
            break;
        case DEVLINK_SERIAL_PARSE_UNSUPPORTED_VERSION:
            devlink_serial_print_event(device, "protocol.unsupported_version", "error");
            break;
        case DEVLINK_SERIAL_PARSE_BUFFER_TOO_SMALL:
            devlink_serial_print_event(device, "protocol.command_too_large", "error");
            break;
        case DEVLINK_SERIAL_PARSE_OK:
        default:
            break;
    }
}

DevlinkSerialParseStatus devlink_serial_parse_command(
    const char *line,
    DevlinkSerialCommand *out_command
) {
    const char *type_value = NULL;
    const char *version_value = NULL;
    const char *device_value = NULL;
    const char *id_value = NULL;
    const char *name_value = NULL;
    const char *args_value = NULL;
    char type_name[16] = {0};

    if (line == NULL || out_command == NULL) {
        return DEVLINK_SERIAL_PARSE_INVALID_JSON;
    }
    if (*skip_ws(line) != '{') {
        return DEVLINK_SERIAL_PARSE_INVALID_JSON;
    }

    memset(out_command, 0, sizeof(*out_command));

    type_value = find_object_key_value(line, "type");
    version_value = find_object_key_value(line, "version");
    device_value = find_object_key_value(line, "device");
    id_value = find_object_key_value(line, "id");
    name_value = find_object_key_value(line, "name");
    args_value = find_object_key_value(line, "args");

    if (type_value == NULL || version_value == NULL || device_value == NULL ||
        id_value == NULL || name_value == NULL || args_value == NULL) {
        return DEVLINK_SERIAL_PARSE_MISSING_FIELD;
    }

    if (!copy_json_string(type_value, type_name, sizeof(type_name))) {
        return DEVLINK_SERIAL_PARSE_WRONG_TYPE;
    }
    if (strcmp(type_name, "cmd") != 0) {
        return DEVLINK_SERIAL_PARSE_WRONG_TYPE;
    }
    if (!parse_uint32_value(version_value, &out_command->version)) {
        return DEVLINK_SERIAL_PARSE_WRONG_TYPE;
    }
    if (out_command->version != DEVLINK_SERIAL_VERSION) {
        return DEVLINK_SERIAL_PARSE_UNSUPPORTED_VERSION;
    }
    if (!parse_uint32_value(id_value, &out_command->id)) {
        return DEVLINK_SERIAL_PARSE_WRONG_TYPE;
    }
    if (!copy_json_string(device_value, out_command->device, sizeof(out_command->device))) {
        return DEVLINK_SERIAL_PARSE_BUFFER_TOO_SMALL;
    }
    if (!copy_json_string(name_value, out_command->name, sizeof(out_command->name))) {
        return DEVLINK_SERIAL_PARSE_BUFFER_TOO_SMALL;
    }
    if (!copy_json_object(args_value, out_command->args_json, sizeof(out_command->args_json))) {
        return DEVLINK_SERIAL_PARSE_BUFFER_TOO_SMALL;
    }

    return DEVLINK_SERIAL_PARSE_OK;
}

void devlink_serial_handle_command_line(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const char *line
) {
    DevlinkSerialCommand command = {0};
    DevlinkSerialParseStatus parse_status = devlink_serial_parse_command(line, &command);
    const DevlinkSerialCommandDescriptor *command_descriptor = NULL;
    char result_json[DEVLINK_SERIAL_RESULT_MAX_LEN] = {0};
    const char *error_code = NULL;
    const char *error_message = NULL;
    DevlinkSerialCommandStatus command_status = DEVLINK_SERIAL_COMMAND_ERROR;

    if (parse_status != DEVLINK_SERIAL_PARSE_OK) {
        devlink_serial_print_parse_error(device, parse_status);
        return;
    }

    if (
        strcmp(command.device, device->device) != 0 &&
        !(strcmp(command.name, "device.describe") == 0 && strcmp(command.device, "*") == 0)
    ) {
        devlink_serial_print_resp_error(
            device,
            command.id,
            "wrong_device",
            "command addressed to a different device"
        );
        return;
    }

    if (handle_builtin_command(device, context, &command)) {
        return;
    }

    command_descriptor = find_command_descriptor(device, command.name);
    if (command_descriptor == NULL || command_descriptor->handler == NULL) {
        devlink_serial_print_resp_error(
            device,
            command.id,
            "unknown_command",
            "command not supported"
        );
        return;
    }

    command_status = command_descriptor->handler(
        device,
        context,
        &command,
        result_json,
        sizeof(result_json),
        &error_code,
        &error_message
    );

    switch (command_status) {
        case DEVLINK_SERIAL_COMMAND_OK:
            devlink_serial_print_resp_ok(device, command.id);
            if (command_descriptor->success_event_name != NULL) {
                devlink_serial_print_event(
                    device,
                    command_descriptor->success_event_name,
                    (command_descriptor->success_event_severity != NULL)
                        ? command_descriptor->success_event_severity
                        : "info"
                );
            }
            break;
        case DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT:
            devlink_serial_print_resp_result_json(device, command.id, result_json);
            if (command_descriptor->success_event_name != NULL) {
                devlink_serial_print_event(
                    device,
                    command_descriptor->success_event_name,
                    (command_descriptor->success_event_severity != NULL)
                        ? command_descriptor->success_event_severity
                        : "info"
                );
            }
            break;
        case DEVLINK_SERIAL_COMMAND_ERROR:
        default:
            devlink_serial_print_resp_error(
                device,
                command.id,
                (error_code != NULL) ? error_code : "command_failed",
                (error_message != NULL) ? error_message : "command failed"
            );
            break;
    }
}

bool devlink_serial_json_get_string(
    const char *json_object,
    const char *key,
    char *out_value,
    size_t out_value_size
) {
    const char *value = find_object_key_value(json_object, key);

    if (value == NULL) {
        return false;
    }

    return copy_json_string(value, out_value, out_value_size);
}

bool devlink_serial_json_get_bool(const char *json_object, const char *key, bool *out_value) {
    const char *value = find_object_key_value(json_object, key);

    if (value == NULL) {
        return false;
    }

    return parse_bool_value(value, out_value);
}

bool devlink_serial_json_get_int32(const char *json_object, const char *key, int32_t *out_value) {
    const char *value = find_object_key_value(json_object, key);

    if (value == NULL) {
        return false;
    }

    return parse_int32_value(value, out_value);
}

bool devlink_serial_json_get_float32(const char *json_object, const char *key, float *out_value) {
    const char *value = find_object_key_value(json_object, key);

    if (value == NULL) {
        return false;
    }

    return parse_float32_value(value, out_value);
}
