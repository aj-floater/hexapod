#include "hexapod_serial.h"

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
    char parsed_key[HEXAPOD_SERIAL_COMMAND_MAX_LEN] = {0};
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

static bool parse_uint32_value(const char *cursor, uint32_t *out_value) {
    char *end = NULL;
    unsigned long parsed = 0ul;

    if (cursor == NULL || out_value == NULL) {
        return false;
    }

    cursor = skip_ws(cursor);
    parsed = strtoul(cursor, &end, 10);
    if (end == cursor) {
        return false;
    }
    end = (char *)skip_ws(end);
    if (*end != ',' && *end != '}' && *end != ']') {
        return false;
    }

    *out_value = (uint32_t)parsed;
    return true;
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

void hexapod_serial_print_hello(const char *device, const char *firmware) {
    printf(
        "{\"type\":\"hello\",\"version\":%u,\"device\":\"%s\",\"protocol\":\"%s\",\"firmware\":\"%s\"}\r\n",
        HEXAPOD_SERIAL_VERSION,
        device,
        HEXAPOD_SERIAL_PROTOCOL,
        firmware
    );
}

void hexapod_serial_print_event(const char *device, const char *name, const char *severity) {
    printf(
        "{\"type\":\"event\",\"version\":%u,\"device\":\"%s\",\"name\":\"%s\",\"severity\":\"%s\"}\r\n",
        HEXAPOD_SERIAL_VERSION,
        device,
        name,
        severity
    );
}

void hexapod_serial_print_log(const char *device, const char *level, const char *msg) {
    printf(
        "{\"type\":\"log\",\"version\":%u,\"device\":\"%s\",\"level\":\"%s\",\"msg\":\"%s\"}\r\n",
        HEXAPOD_SERIAL_VERSION,
        device,
        level,
        msg
    );
}

void hexapod_serial_print_resp_ok(const char *device, uint32_t id) {
    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":true}\r\n",
        HEXAPOD_SERIAL_VERSION,
        device,
        (unsigned long)id
    );
}

void hexapod_serial_print_resp_error(
    const char *device,
    uint32_t id,
    const char *code,
    const char *message
) {
    printf(
        "{\"type\":\"resp\",\"version\":%u,\"device\":\"%s\",\"id\":%lu,\"ok\":false,"
        "\"error\":{\"code\":\"%s\",\"message\":\"%s\"}}\r\n",
        HEXAPOD_SERIAL_VERSION,
        device,
        (unsigned long)id,
        code,
        message
    );
}

HexapodSerialParseStatus hexapod_serial_parse_command(
    const char *line,
    HexapodSerialCommand *out_command
) {
    const char *type_value = NULL;
    const char *version_value = NULL;
    const char *device_value = NULL;
    const char *id_value = NULL;
    const char *name_value = NULL;
    const char *args_value = NULL;
    char type_name[16] = {0};

    if (line == NULL || out_command == NULL) {
        return HEXAPOD_SERIAL_PARSE_INVALID_JSON;
    }
    if (*skip_ws(line) != '{') {
        return HEXAPOD_SERIAL_PARSE_INVALID_JSON;
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
        return HEXAPOD_SERIAL_PARSE_MISSING_FIELD;
    }

    if (!copy_json_string(type_value, type_name, sizeof(type_name))) {
        return HEXAPOD_SERIAL_PARSE_WRONG_TYPE;
    }
    if (strcmp(type_name, "cmd") != 0) {
        return HEXAPOD_SERIAL_PARSE_WRONG_TYPE;
    }
    if (!parse_uint32_value(version_value, &out_command->version)) {
        return HEXAPOD_SERIAL_PARSE_WRONG_TYPE;
    }
    if (out_command->version != HEXAPOD_SERIAL_VERSION) {
        return HEXAPOD_SERIAL_PARSE_UNSUPPORTED_VERSION;
    }
    if (!parse_uint32_value(id_value, &out_command->id)) {
        return HEXAPOD_SERIAL_PARSE_WRONG_TYPE;
    }
    if (!copy_json_string(device_value, out_command->device, sizeof(out_command->device))) {
        return HEXAPOD_SERIAL_PARSE_BUFFER_TOO_SMALL;
    }
    if (!copy_json_string(name_value, out_command->name, sizeof(out_command->name))) {
        return HEXAPOD_SERIAL_PARSE_BUFFER_TOO_SMALL;
    }
    if (!copy_json_object(args_value, out_command->args_json, sizeof(out_command->args_json))) {
        return HEXAPOD_SERIAL_PARSE_BUFFER_TOO_SMALL;
    }

    return HEXAPOD_SERIAL_PARSE_OK;
}

bool hexapod_serial_json_get_string(
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

bool hexapod_serial_json_get_int32(const char *json_object, const char *key, int32_t *out_value) {
    const char *value = find_object_key_value(json_object, key);

    if (value == NULL) {
        return false;
    }

    return parse_int32_value(value, out_value);
}
