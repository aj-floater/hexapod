#ifndef DEBUG_APP_H
#define DEBUG_APP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "devlink_serial.h"
#include "pio_uart_rx.h"
#include "pico/time.h"

typedef struct {
    size_t len;
    bool overflowed;
    absolute_time_t flush_at;
    char storage[256];
} DebugLineBuffer;

typedef struct {
    uint32_t rx_bytes_total;
    uint32_t rx_ring_drops_total;
    uint32_t line_ready_total;
    uint32_t line_overflow_total;
    uint32_t ignored_nonprintable_total;
    uint32_t parse_ok_total;
    uint32_t parse_invalid_json_total;
    uint32_t parse_missing_field_total;
    uint32_t parse_wrong_type_total;
    uint32_t parse_unsupported_version_total;
    uint32_t parse_buffer_too_small_total;
    uint32_t wrong_device_total;
    uint32_t cmd_describe_total;
    uint32_t cmd_param_get_total;
    uint32_t cmd_param_set_total;
    uint32_t cmd_unknown_total;
    uint32_t param_set_success_total;
    uint32_t param_set_reject_total;
} DebugCounters;

typedef struct {
    PioUartRx command_rx;
    DebugLineBuffer line_buffer;
    DebugCounters counters;
    absolute_time_t next_stats_at;
    bool status_led_on;
    bool debug_verbose;
    uint8_t test_u8;
    float test_f32;
    uint32_t last_command_id;
    size_t last_completed_line_length;
    char last_command_name[DEVLINK_SERIAL_COMMAND_MAX_LEN];
    char last_target_device[DEVLINK_SERIAL_DEVICE_MAX_LEN];
    char last_param_name[48];
    char last_parse_status[32];
    bool init_ok;
} DebugApp;

void debug_app_init(DebugApp *app);
void debug_app_poll(DebugApp *app);

#endif
