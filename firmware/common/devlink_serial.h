#ifndef DEVLINK_SERIAL_H
#define DEVLINK_SERIAL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "pico/time.h"

#define DEVLINK_SERIAL_PROTOCOL "devlink"
#define DEVLINK_SERIAL_VERSION 1u
#define DEVLINK_SERIAL_DEVICE_MAX_LEN 32u
#define DEVLINK_SERIAL_COMMAND_MAX_LEN 48u
#define DEVLINK_SERIAL_ARGS_MAX_LEN 160u
#define DEVLINK_SERIAL_RESULT_MAX_LEN 192u

typedef struct {
    uint32_t version;
    uint32_t id;
    char device[DEVLINK_SERIAL_DEVICE_MAX_LEN];
    char name[DEVLINK_SERIAL_COMMAND_MAX_LEN];
    char args_json[DEVLINK_SERIAL_ARGS_MAX_LEN];
} DevlinkSerialCommand;

typedef enum {
    DEVLINK_SERIAL_PARSE_OK = 0,
    DEVLINK_SERIAL_PARSE_INVALID_JSON,
    DEVLINK_SERIAL_PARSE_MISSING_FIELD,
    DEVLINK_SERIAL_PARSE_WRONG_TYPE,
    DEVLINK_SERIAL_PARSE_UNSUPPORTED_VERSION,
    DEVLINK_SERIAL_PARSE_BUFFER_TOO_SMALL
} DevlinkSerialParseStatus;

typedef enum {
    DEVLINK_SERIAL_LINE_NONE = 0,
    DEVLINK_SERIAL_LINE_READY,
    DEVLINK_SERIAL_LINE_OVERFLOW
} DevlinkSerialLineReadStatus;

typedef struct {
    char *storage;
    size_t storage_size;
    size_t len;
    bool overflowed;
    uint32_t idle_flush_ms;
    absolute_time_t flush_at;
} DevlinkSerialLineBuffer;

typedef enum {
    DEVLINK_SERIAL_TYPE_BOOL = 0,
    DEVLINK_SERIAL_TYPE_U8,
    DEVLINK_SERIAL_TYPE_U16,
    DEVLINK_SERIAL_TYPE_U32,
    DEVLINK_SERIAL_TYPE_I16,
    DEVLINK_SERIAL_TYPE_I32,
    DEVLINK_SERIAL_TYPE_F32
} DevlinkSerialScalarType;

typedef enum {
    DEVLINK_SERIAL_ACCESS_RO = 0,
    DEVLINK_SERIAL_ACCESS_RW
} DevlinkSerialAccess;

typedef union {
    bool bool_value;
    uint32_t u32_value;
    int32_t i32_value;
    float f32_value;
} DevlinkSerialValue;

#define DEVLINK_SERIAL_VALUE_BOOL(v) ((DevlinkSerialValue){.bool_value = (v)})
#define DEVLINK_SERIAL_VALUE_U8(v) ((DevlinkSerialValue){.u32_value = (uint32_t)(uint8_t)(v)})
#define DEVLINK_SERIAL_VALUE_U16(v) ((DevlinkSerialValue){.u32_value = (uint32_t)(uint16_t)(v)})
#define DEVLINK_SERIAL_VALUE_U32(v) ((DevlinkSerialValue){.u32_value = (uint32_t)(v)})
#define DEVLINK_SERIAL_VALUE_I16(v) ((DevlinkSerialValue){.i32_value = (int32_t)(int16_t)(v)})
#define DEVLINK_SERIAL_VALUE_I32(v) ((DevlinkSerialValue){.i32_value = (int32_t)(v)})
#define DEVLINK_SERIAL_VALUE_F32(v) ((DevlinkSerialValue){.f32_value = (float)(v)})

typedef struct {
    const char *name;
    const char *type;
    bool required;
} DevlinkSerialCommandArgDescriptor;

typedef struct {
    const char *name;
    DevlinkSerialScalarType type;
    const char *unit;
} DevlinkSerialStreamFieldDescriptor;

typedef enum {
    DEVLINK_SERIAL_SAMPLE_FORMAT_JSON = 0,
    DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY
} DevlinkSerialSampleFormat;

typedef struct {
    const char *name;
    const DevlinkSerialStreamFieldDescriptor *fields;
    size_t field_count;
    uint8_t id;
    DevlinkSerialSampleFormat sample_format;
} DevlinkSerialStreamDescriptor;

typedef struct {
    const char *name;
    DevlinkSerialScalarType type;
    DevlinkSerialAccess access;
    DevlinkSerialValue default_value;
    bool has_bounds;
    DevlinkSerialValue min_value;
    DevlinkSerialValue max_value;
    uintptr_t user_data;
} DevlinkSerialParamDescriptor;

typedef struct DevlinkSerialDeviceDescriptor DevlinkSerialDeviceDescriptor;

typedef enum {
    DEVLINK_SERIAL_COMMAND_OK = 0,
    DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT,
    DEVLINK_SERIAL_COMMAND_ERROR
} DevlinkSerialCommandStatus;

typedef DevlinkSerialCommandStatus (*DevlinkSerialCommandHandler)(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);

typedef bool (*DevlinkSerialParamGetter)(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
);

typedef bool (*DevlinkSerialParamSetter)(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
);

typedef struct {
    const char *name;
    const DevlinkSerialCommandArgDescriptor *args;
    size_t arg_count;
    DevlinkSerialCommandHandler handler;
    const char *success_event_name;
    const char *success_event_severity;
} DevlinkSerialCommandDescriptor;

struct DevlinkSerialDeviceDescriptor {
    const char *device;
    const char *firmware;
    const DevlinkSerialCommandDescriptor *commands;
    size_t command_count;
    const DevlinkSerialStreamDescriptor *streams;
    size_t stream_count;
    const DevlinkSerialParamDescriptor *params;
    size_t param_count;
    DevlinkSerialParamGetter param_getter;
    DevlinkSerialParamSetter param_setter;
};

void devlink_serial_line_buffer_init(
    DevlinkSerialLineBuffer *buffer,
    char *storage,
    size_t storage_size,
    uint32_t idle_flush_ms
);
void devlink_serial_line_buffer_reset(DevlinkSerialLineBuffer *buffer);
DevlinkSerialLineReadStatus devlink_serial_line_buffer_push(
    DevlinkSerialLineBuffer *buffer,
    int ch,
    char *out_line,
    size_t out_line_size
);
DevlinkSerialLineReadStatus devlink_serial_line_buffer_flush_if_idle(
    DevlinkSerialLineBuffer *buffer,
    char *out_line,
    size_t out_line_size
);

void devlink_serial_print_hello(const DevlinkSerialDeviceDescriptor *device);
void devlink_serial_print_capabilities(const DevlinkSerialDeviceDescriptor *device);
void devlink_serial_print_discovery(const DevlinkSerialDeviceDescriptor *device);
void devlink_serial_print_event(
    const DevlinkSerialDeviceDescriptor *device,
    const char *name,
    const char *severity
);
void devlink_serial_print_log(
    const DevlinkSerialDeviceDescriptor *device,
    const char *level,
    const char *msg
);
void devlink_serial_print_resp_ok(const DevlinkSerialDeviceDescriptor *device, uint32_t id);
void devlink_serial_print_resp_error(
    const DevlinkSerialDeviceDescriptor *device,
    uint32_t id,
    const char *code,
    const char *message
);
void devlink_serial_print_resp_result_json(
    const DevlinkSerialDeviceDescriptor *device,
    uint32_t id,
    const char *result_json
);
void devlink_serial_print_sample(
    const DevlinkSerialDeviceDescriptor *device,
    const DevlinkSerialStreamDescriptor *stream,
    uint32_t seq,
    uint64_t t_us,
    const DevlinkSerialValue *values
);
void devlink_serial_print_parse_error(
    const DevlinkSerialDeviceDescriptor *device,
    DevlinkSerialParseStatus status
);
void devlink_serial_handle_command_line(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const char *line
);

DevlinkSerialParseStatus devlink_serial_parse_command(
    const char *line,
    DevlinkSerialCommand *out_command
);

bool devlink_serial_json_get_string(
    const char *json_object,
    const char *key,
    char *out_value,
    size_t out_value_size
);
bool devlink_serial_json_get_bool(const char *json_object, const char *key, bool *out_value);
bool devlink_serial_json_get_int32(const char *json_object, const char *key, int32_t *out_value);
bool devlink_serial_json_get_float32(const char *json_object, const char *key, float *out_value);

#endif
