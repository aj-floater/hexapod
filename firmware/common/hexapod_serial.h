#ifndef HEXAPOD_SERIAL_H
#define HEXAPOD_SERIAL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HEXAPOD_SERIAL_PROTOCOL "hexapod.serial"
#define HEXAPOD_SERIAL_VERSION 1u
#define HEXAPOD_SERIAL_DEVICE_MAX_LEN 32u
#define HEXAPOD_SERIAL_COMMAND_MAX_LEN 48u
#define HEXAPOD_SERIAL_ARGS_MAX_LEN 160u

typedef struct {
    uint32_t version;
    uint32_t id;
    char device[HEXAPOD_SERIAL_DEVICE_MAX_LEN];
    char name[HEXAPOD_SERIAL_COMMAND_MAX_LEN];
    char args_json[HEXAPOD_SERIAL_ARGS_MAX_LEN];
} HexapodSerialCommand;

typedef enum {
    HEXAPOD_SERIAL_PARSE_OK = 0,
    HEXAPOD_SERIAL_PARSE_INVALID_JSON,
    HEXAPOD_SERIAL_PARSE_MISSING_FIELD,
    HEXAPOD_SERIAL_PARSE_WRONG_TYPE,
    HEXAPOD_SERIAL_PARSE_UNSUPPORTED_VERSION,
    HEXAPOD_SERIAL_PARSE_BUFFER_TOO_SMALL
} HexapodSerialParseStatus;

void hexapod_serial_print_hello(const char *device, const char *firmware);
void hexapod_serial_print_event(const char *device, const char *name, const char *severity);
void hexapod_serial_print_log(const char *device, const char *level, const char *msg);
void hexapod_serial_print_resp_ok(const char *device, uint32_t id);
void hexapod_serial_print_resp_error(
    const char *device,
    uint32_t id,
    const char *code,
    const char *message
);

HexapodSerialParseStatus hexapod_serial_parse_command(
    const char *line,
    HexapodSerialCommand *out_command
);

bool hexapod_serial_json_get_string(
    const char *json_object,
    const char *key,
    char *out_value,
    size_t out_value_size
);

bool hexapod_serial_json_get_int32(const char *json_object, const char *key, int32_t *out_value);

#endif
