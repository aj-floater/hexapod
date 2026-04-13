#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "pico/stdlib.h"
#include "pico/time.h"

#include "adc_input.h"
#include "servo.h"
#include "devlink_serial.h"
#include "leg_pins.h"
#include "pio_uart_rx.h"

#ifndef PICO_DEFAULT_LED_PIN
#error "control_testing requires PICO_DEFAULT_LED_PIN"
#endif

#define COMMAND_RX_GPIO 3u
#define COMMAND_BAUD 115200u
#define COMMAND_BUFFER_LEN 256u
#define COMMAND_IDLE_FLUSH_MS 80u
#define PID_PERIOD_US 1000
#define TELEMETRY_PERIOD_MS 40u
#define CONTROL_TESTING_SERVO_COUNT 3u
#define CONTROL_TESTING_SERVO_USER_DATA_BASE ((uintptr_t)0x100u)
#define CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS 50u
#define CONTROL_TESTING_TEACH_SAMPLE_CAPACITY 200u

enum {
    CONTROL_TESTING_SERVO_A = 0,
    CONTROL_TESTING_SERVO_B,
    CONTROL_TESTING_SERVO_C,
};

enum {
    CONTROL_TESTING_STREAM_ADC = 0,
    CONTROL_TESTING_STREAM_ADC_AVG,
    CONTROL_TESTING_STREAM_ADC_LP,
    CONTROL_TESTING_STREAM_ANGLE_AVG,
    CONTROL_TESTING_STREAM_ANGLE_LP,
    CONTROL_TESTING_STREAM_MOTOR,
    CONTROL_TESTING_STREAM_HOLD,
    CONTROL_TESTING_STREAM_COUNT,
};

enum {
    CONTROL_TESTING_APP_PARAM_STATUS_LED_ON = 0,
};

enum {
    CONTROL_TESTING_SERVO_PARAM_FILTER_ALPHA_PCT = 0,
    CONTROL_TESTING_SERVO_PARAM_MOTOR_STATE,
    CONTROL_TESTING_SERVO_PARAM_MOTOR_DRIVE_PCT,
    CONTROL_TESTING_SERVO_PARAM_CONTROL_MODE,
    CONTROL_TESTING_SERVO_PARAM_HOLD_TARGET_DEG,
    CONTROL_TESTING_SERVO_PARAM_HOLD_DEADBAND_DEG,
    CONTROL_TESTING_SERVO_PARAM_HOLD_P_GAIN,
    CONTROL_TESTING_SERVO_PARAM_HOLD_I_GAIN,
    CONTROL_TESTING_SERVO_PARAM_HOLD_D_GAIN,
    CONTROL_TESTING_SERVO_PARAM_HOLD_MAX_DUTY,
    CONTROL_TESTING_SERVO_PARAM_COUNT,
};

#define CONTROL_TESTING_SERVO_USER_DATA(servo_index, param_id) \
    (CONTROL_TESTING_SERVO_USER_DATA_BASE + (((uintptr_t)(servo_index)) << 4u) + (uintptr_t)(param_id))

#define CONTROL_TESTING_SERVO_PARAM_SET(letter, servo_index, control_default) \
    { \
        "servo." #letter ".filter.alpha_pct", \
        DEVLINK_SERIAL_TYPE_U8, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_U8(SERVO_FILTER_ALPHA_DEFAULT_PCT), \
        true, \
        DEVLINK_SERIAL_VALUE_U8(SERVO_FILTER_ALPHA_MIN_PCT), \
        DEVLINK_SERIAL_VALUE_U8(SERVO_FILTER_ALPHA_MAX_PCT), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_FILTER_ALPHA_PCT), \
    }, \
    { \
        "servo." #letter ".motor.state", \
        DEVLINK_SERIAL_TYPE_U8, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_U8(SERVO_MOTOR_STATE_COAST), \
        true, \
        DEVLINK_SERIAL_VALUE_U8(SERVO_MOTOR_STATE_COAST), \
        DEVLINK_SERIAL_VALUE_U8(SERVO_MOTOR_STATE_REVERSE), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_MOTOR_STATE), \
    }, \
    { \
        "servo." #letter ".motor.drive_pct", \
        DEVLINK_SERIAL_TYPE_U8, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_U8(0u), \
        true, \
        DEVLINK_SERIAL_VALUE_U8(0u), \
        DEVLINK_SERIAL_VALUE_U8(100u), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_MOTOR_DRIVE_PCT), \
    }, \
    { \
        "servo." #letter ".control.mode", \
        DEVLINK_SERIAL_TYPE_U8, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_U8(control_default), \
        true, \
        DEVLINK_SERIAL_VALUE_U8(CONTROL_MODE_MANUAL), \
        DEVLINK_SERIAL_VALUE_U8(CONTROL_MODE_HOLD), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_CONTROL_MODE), \
    }, \
    { \
        "servo." #letter ".hold.target_deg", \
        DEVLINK_SERIAL_TYPE_F32, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_TARGET_DEFAULT), \
        true, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_TARGET_MIN), \
        DEVLINK_SERIAL_VALUE_F32(HOLD_TARGET_MAX), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_HOLD_TARGET_DEG), \
    }, \
    { \
        "servo." #letter ".hold.deadband_deg", \
        DEVLINK_SERIAL_TYPE_F32, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_DEADBAND_DEFAULT), \
        true, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_DEADBAND_MIN), \
        DEVLINK_SERIAL_VALUE_F32(HOLD_DEADBAND_MAX), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_HOLD_DEADBAND_DEG), \
    }, \
    { \
        "servo." #letter ".hold.p_gain", \
        DEVLINK_SERIAL_TYPE_F32, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_P_GAIN_DEFAULT), \
        true, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_P_GAIN_MIN), \
        DEVLINK_SERIAL_VALUE_F32(HOLD_P_GAIN_MAX), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_HOLD_P_GAIN), \
    }, \
    { \
        "servo." #letter ".hold.i_gain", \
        DEVLINK_SERIAL_TYPE_F32, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_I_GAIN_DEFAULT), \
        true, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_I_GAIN_MIN), \
        DEVLINK_SERIAL_VALUE_F32(HOLD_I_GAIN_MAX), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_HOLD_I_GAIN), \
    }, \
    { \
        "servo." #letter ".hold.d_gain", \
        DEVLINK_SERIAL_TYPE_F32, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_D_GAIN_DEFAULT), \
        true, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_D_GAIN_MIN), \
        DEVLINK_SERIAL_VALUE_F32(HOLD_D_GAIN_MAX), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_HOLD_D_GAIN), \
    }, \
    { \
        "servo." #letter ".hold.max_duty", \
        DEVLINK_SERIAL_TYPE_U8, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_U8(HOLD_MAX_DUTY_DEFAULT), \
        true, \
        DEVLINK_SERIAL_VALUE_U8(0u), \
        DEVLINK_SERIAL_VALUE_U8(100u), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_HOLD_MAX_DUTY), \
    }

typedef enum {
    CONTROL_TESTING_COMMAND_STATE_CUSTOM = 0,
    CONTROL_TESTING_COMMAND_STATE_LINK_BC,
    CONTROL_TESTING_COMMAND_STATE_ALL_HOLD,
    CONTROL_TESTING_COMMAND_STATE_ALL_MANUAL,
} ControlTestingCommandState;

typedef struct {
    int16_t servo_angle_deg_tenths[CONTROL_TESTING_SERVO_COUNT];
} ControlTestingTeachSample;

typedef enum {
    CONTROL_TESTING_TEACH_MODE_IDLE = 0,
    CONTROL_TESTING_TEACH_MODE_RECORDING,
    CONTROL_TESTING_TEACH_MODE_RECORDED,
    CONTROL_TESTING_TEACH_MODE_PLAYING,
} ControlTestingTeachMode;

typedef struct {
    ControlTestingTeachMode mode;
    bool waiting_for_alignment;
    bool playback_interpolate;
    uint16_t sample_count;
    uint16_t playback_index;
    absolute_time_t playback_segment_started_at;
    absolute_time_t next_sample_at;
    ControlTestingTeachSample samples[CONTROL_TESTING_TEACH_SAMPLE_CAPACITY];
} ControlTestingTeachState;

typedef struct {
    bool status_led_on;
    ControlTestingCommandState command_state;
    Servo servos[CONTROL_TESTING_SERVO_COUNT];
    ControlTestingTeachState teach;
    repeating_timer_t pid_timer;
    absolute_time_t next_telemetry_at;
    uint32_t stream_sample_seq[CONTROL_TESTING_STREAM_COUNT];
} ControlTestingApp;

static bool control_testing_pid_callback(repeating_timer_t *rt);
static void control_testing_pid_tick(ControlTestingApp *app);
static void control_testing_emit_telemetry(ControlTestingApp *app);
static void control_testing_consume_command_byte(
    DevlinkSerialLineBuffer *line_buffer,
    ControlTestingApp *app,
    int received_byte,
    char *command_line,
    size_t command_line_size
);
static void control_testing_flush_command_buffer(
    DevlinkSerialLineBuffer *line_buffer,
    ControlTestingApp *app,
    char *command_line,
    size_t command_line_size
);
static void control_testing_apply_servo_bc_link(ControlTestingApp *app);
static void control_testing_set_command_state(
    ControlTestingApp *app,
    ControlTestingCommandState state
);
static const char *control_testing_command_state_name(ControlTestingCommandState state);
static const char *control_testing_teach_mode_name(ControlTestingTeachMode mode);
static bool control_testing_write_command_state_result(
    char *out_result_json,
    size_t out_result_json_size,
    ControlTestingCommandState state
);
static bool control_testing_write_teach_status_result(
    char *out_result_json,
    size_t out_result_json_size,
    const ControlTestingApp *app
);
static void control_testing_stop_playback(ControlTestingApp *app);
static void control_testing_cancel_playback_for_override(ControlTestingApp *app);
static void control_testing_start_recording(ControlTestingApp *app);
static void control_testing_stop_recording(ControlTestingApp *app);
static bool control_testing_start_playback(
    ControlTestingApp *app,
    const char **out_error_code,
    const char **out_error_message
);
static void control_testing_capture_teach_sample(ControlTestingApp *app);
static void control_testing_apply_teach_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSample *sample
);
static void control_testing_apply_interpolated_teach_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSample *start_sample,
    const ControlTestingTeachSample *end_sample,
    uint32_t elapsed_ms
);
static void control_testing_update_teach(ControlTestingApp *app);
static DevlinkSerialCommandStatus handle_cmd_mode_link_bc(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_mode_all_hold(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_mode_all_manual(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_record_start(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_record_stop(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_play_start(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_play_stop(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_status(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_play_interpolate_on(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_play_interpolate_off(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static bool control_testing_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
);
static bool control_testing_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
);

static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_fields[] = {
    {"adc_a_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
    {"adc_b_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
    {"adc_c_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_avg_fields[] = {
    {"adc_a_avg_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
    {"adc_b_avg_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
    {"adc_c_avg_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_lp_fields[] = {
    {"adc_a_lp_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
    {"adc_b_lp_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
    {"adc_c_lp_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_angle_avg_fields[] = {
    {"adc_a_avg_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"adc_b_avg_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"adc_c_avg_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_angle_lp_fields[] = {
    {"adc_a_lp_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"adc_b_lp_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"adc_c_lp_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_motor_fields[] = {
    {"motor_a_state", DEVLINK_SERIAL_TYPE_U8, "state"},
    {"motor_a_drive_pct", DEVLINK_SERIAL_TYPE_U8, "pct"},
    {"motor_b_state", DEVLINK_SERIAL_TYPE_U8, "state"},
    {"motor_b_drive_pct", DEVLINK_SERIAL_TYPE_U8, "pct"},
    {"motor_c_state", DEVLINK_SERIAL_TYPE_U8, "state"},
    {"motor_c_drive_pct", DEVLINK_SERIAL_TYPE_U8, "pct"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_hold_fields[] = {
    {"hold_a_target_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_a_actual_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_a_error_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_a_output_pct", DEVLINK_SERIAL_TYPE_I16, "pct"},
    {"hold_b_target_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_b_actual_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_b_error_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_b_output_pct", DEVLINK_SERIAL_TYPE_I16, "pct"},
    {"hold_c_target_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_c_actual_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_c_error_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_c_output_pct", DEVLINK_SERIAL_TYPE_I16, "pct"},
};

static const DevlinkSerialStreamDescriptor g_control_testing_streams[] = {
    {
        "control_testing.adc",
        g_control_testing_adc_fields,
        count_of(g_control_testing_adc_fields),
        CONTROL_TESTING_STREAM_ADC,
        DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY,
    },
    {
        "control_testing.adc_avg",
        g_control_testing_adc_avg_fields,
        count_of(g_control_testing_adc_avg_fields),
        CONTROL_TESTING_STREAM_ADC_AVG,
        DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY,
    },
    {
        "control_testing.adc_lp",
        g_control_testing_adc_lp_fields,
        count_of(g_control_testing_adc_lp_fields),
        CONTROL_TESTING_STREAM_ADC_LP,
        DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY,
    },
    {
        "control_testing.angle_avg",
        g_control_testing_angle_avg_fields,
        count_of(g_control_testing_angle_avg_fields),
        CONTROL_TESTING_STREAM_ANGLE_AVG,
        DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY,
    },
    {
        "control_testing.angle_lp",
        g_control_testing_angle_lp_fields,
        count_of(g_control_testing_angle_lp_fields),
        CONTROL_TESTING_STREAM_ANGLE_LP,
        DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY,
    },
    {
        "control_testing.motor",
        g_control_testing_motor_fields,
        count_of(g_control_testing_motor_fields),
        CONTROL_TESTING_STREAM_MOTOR,
        DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY,
    },
    {
        "control_testing.hold",
        g_control_testing_hold_fields,
        count_of(g_control_testing_hold_fields),
        CONTROL_TESTING_STREAM_HOLD,
        DEVLINK_SERIAL_SAMPLE_FORMAT_BINARY,
    },
};

static const DevlinkSerialParamDescriptor g_control_testing_params[] = {
    {
        "status_led.on",
        DEVLINK_SERIAL_TYPE_BOOL,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_BOOL(false),
        false,
        DEVLINK_SERIAL_VALUE_BOOL(false),
        DEVLINK_SERIAL_VALUE_BOOL(true),
        CONTROL_TESTING_APP_PARAM_STATUS_LED_ON,
    },
    CONTROL_TESTING_SERVO_PARAM_SET(a, CONTROL_TESTING_SERVO_A, CONTROL_MODE_MANUAL),
    CONTROL_TESTING_SERVO_PARAM_SET(b, CONTROL_TESTING_SERVO_B, CONTROL_MODE_MANUAL),
    CONTROL_TESTING_SERVO_PARAM_SET(c, CONTROL_TESTING_SERVO_C, CONTROL_MODE_MANUAL),
};

static const ServoCalibrationPoint g_control_testing_calibration_points[] = {
    {0u, 3943u},
    {10u, 3746u},
    {20u, 3575u},
    {30u, 3386u},
    {40u, 3199u},
    {50u, 3006u},
    {60u, 2811u},
    {70u, 2602u},
    {80u, 2396u},
    {90u, 2192u},
    {100u, 1977u},
    {110u, 1761u},
    {120u, 1560u},
    {130u, 1366u},
    {140u, 1148u},
    {150u, 950u},
    {160u, 707u},
    {170u, 509u},
    {180u, 285u},
};

static const ServoConfig g_control_testing_servo_configs[CONTROL_TESTING_SERVO_COUNT] = {
    {
        'a',
        "motor_a",
        LEG_POT_A_GPIO,
        LEG_MOTOR_A_IN1_GPIO,
        LEG_MOTOR_A_IN2_GPIO,
        CONTROL_MODE_MANUAL,
        g_control_testing_calibration_points,
        count_of(g_control_testing_calibration_points),
    },
    {
        'b',
        "motor_b",
        LEG_POT_C_GPIO,
        LEG_MOTOR_C_IN1_GPIO,
        LEG_MOTOR_C_IN2_GPIO,
        CONTROL_MODE_MANUAL,
        g_control_testing_calibration_points,
        count_of(g_control_testing_calibration_points),
    },
    {
        'c',
        "motor_c",
        LEG_POT_B_GPIO,
        LEG_MOTOR_B_IN1_GPIO,
        LEG_MOTOR_B_IN2_GPIO,
        CONTROL_MODE_MANUAL,
        g_control_testing_calibration_points,
        count_of(g_control_testing_calibration_points),
    },
};

static const DevlinkSerialCommandDescriptor g_control_testing_commands[] = {
    {
        .name = "servo.mode.link_bc",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_mode_link_bc,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "servo.mode.all_hold",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_mode_all_hold,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "servo.mode.all_manual",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_mode_all_manual,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.record.start",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_record_start,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.record.stop",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_record_stop,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.play.start",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_play_start,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.play.stop",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_play_stop,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.status",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_status,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.play.interpolate.on",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_play_interpolate_on,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.play.interpolate.off",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_play_interpolate_off,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
};

static const DevlinkSerialDeviceDescriptor g_control_testing_device = {
    .device = "control_testing",
    .firmware = "0.9.0",
    .commands = g_control_testing_commands,
    .command_count = count_of(g_control_testing_commands),
    .streams = g_control_testing_streams,
    .stream_count = count_of(g_control_testing_streams),
    .params = g_control_testing_params,
    .param_count = count_of(g_control_testing_params),
    .param_getter = control_testing_param_get,
    .param_setter = control_testing_param_set,
};

// Returns one mutable servo slot.
static Servo *control_testing_get_servo(ControlTestingApp *app, uint8_t servo_index) {
    hard_assert(app != NULL);

    if (servo_index >= CONTROL_TESTING_SERVO_COUNT) {
        return NULL;
    }
    return &app->servos[servo_index];
}

// Returns one read-only servo slot.
static const Servo *control_testing_get_servo_const(
    const ControlTestingApp *app,
    uint8_t servo_index
) {
    hard_assert(app != NULL);

    if (servo_index >= CONTROL_TESTING_SERVO_COUNT) {
        return NULL;
    }
    return &app->servos[servo_index];
}

// Decodes a servo parameter token.
static bool control_testing_decode_servo_user_data(
    uintptr_t user_data,
    uint8_t *out_servo_index,
    uint8_t *out_param_id
) {
    uint8_t servo_index = 0u;
    uint8_t param_id = 0u;

    hard_assert(out_servo_index != NULL);
    hard_assert(out_param_id != NULL);

    if (user_data < CONTROL_TESTING_SERVO_USER_DATA_BASE) {
        return false;
    }

    servo_index = (uint8_t)((user_data - CONTROL_TESTING_SERVO_USER_DATA_BASE) >> 4u);
    param_id = (uint8_t)((user_data - CONTROL_TESTING_SERVO_USER_DATA_BASE) & 0x0fu);

    if (servo_index >= CONTROL_TESTING_SERVO_COUNT || param_id >= CONTROL_TESTING_SERVO_PARAM_COUNT) {
        return false;
    }

    *out_servo_index = servo_index;
    *out_param_id = param_id;
    return true;
}

// Updates the status LED output.
static void control_testing_apply_status_led(const ControlTestingApp *app) {
    hard_assert(app != NULL);
    gpio_put(PICO_DEFAULT_LED_PIN, app->status_led_on);
}

// Initializes app state and timers.
static void control_testing_init(ControlTestingApp *app) {
    absolute_time_t now = get_absolute_time();
    bool pid_timer_registered = false;

    hard_assert(app != NULL);

    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);

    adc_input_system_init();

    app->status_led_on = false;
    app->command_state = CONTROL_TESTING_COMMAND_STATE_ALL_MANUAL;
    app->teach.mode = CONTROL_TESTING_TEACH_MODE_IDLE;
    app->teach.waiting_for_alignment = false;
    app->teach.playback_interpolate = false;
    app->teach.sample_count = 0u;
    app->teach.playback_index = 0u;
    app->teach.playback_segment_started_at = now;
    app->teach.next_sample_at = now;
    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        servo_init(&app->servos[servo_index], &g_control_testing_servo_configs[servo_index]);
    }
    app->next_telemetry_at = now;

    control_testing_apply_status_led(app);
    control_testing_pid_tick(app);

    pid_timer_registered = add_repeating_timer_us(
        -((int64_t)PID_PERIOD_US),
        control_testing_pid_callback,
        app,
        &app->pid_timer
    );
    hard_assert(pid_timer_registered);
}

// Converts angle tenths to float degrees.
static float control_testing_deg_tenths_to_f32(int16_t deg_tenths) {
    return (float)deg_tenths / (float)SERVO_TENTHS_PER_DEG;
}

// Clamps one hold target to the supported public range.
static float control_testing_clamp_hold_target_deg(float target_deg) {
    if (target_deg < HOLD_TARGET_MIN) {
        return HOLD_TARGET_MIN;
    }
    if (target_deg > HOLD_TARGET_MAX) {
        return HOLD_TARGET_MAX;
    }
    return target_deg;
}

// Mirrors servo B's measured position into servo C's hold target.
static void control_testing_apply_servo_bc_link(ControlTestingApp *app) {
    const Servo *servo_b = NULL;
    Servo *servo_c = NULL;
    float servo_b_angle_lp_deg = 0.0f; // 

    hard_assert(app != NULL);

    servo_b = control_testing_get_servo_const(app, CONTROL_TESTING_SERVO_B);
    servo_c = control_testing_get_servo(app, CONTROL_TESTING_SERVO_C);
    hard_assert(servo_b != NULL);
    hard_assert(servo_c != NULL);

    servo_b_angle_lp_deg = control_testing_deg_tenths_to_f32(
        servo_b->telemetry.angle_lp_deg_tenths
    );
    servo_c->settings.hold_target_deg = control_testing_clamp_hold_target_deg(servo_b_angle_lp_deg);
}

// Applies one of the high-level device command states.
static void control_testing_set_command_state(
    ControlTestingApp *app,
    ControlTestingCommandState state
) {
    hard_assert(app != NULL);

    if (app->teach.mode == CONTROL_TESTING_TEACH_MODE_PLAYING) {
        control_testing_cancel_playback_for_override(app);
    }

    app->command_state = state;

    switch (state) {
        case CONTROL_TESTING_COMMAND_STATE_LINK_BC:
            servo_set_control_mode(&app->servos[CONTROL_TESTING_SERVO_A], CONTROL_MODE_MANUAL);
            servo_set_control_mode(&app->servos[CONTROL_TESTING_SERVO_B], CONTROL_MODE_MANUAL);
            servo_set_control_mode(&app->servos[CONTROL_TESTING_SERVO_C], CONTROL_MODE_HOLD);
            control_testing_apply_servo_bc_link(app);
            return;
        case CONTROL_TESTING_COMMAND_STATE_ALL_HOLD:
            for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
                servo_set_control_mode(&app->servos[servo_index], CONTROL_MODE_HOLD);
            }
            return;
        case CONTROL_TESTING_COMMAND_STATE_ALL_MANUAL:
            for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
                servo_set_control_mode(&app->servos[servo_index], CONTROL_MODE_MANUAL);
            }
            return;
        case CONTROL_TESTING_COMMAND_STATE_CUSTOM:
        default:
            return;
    }
}

// Returns a stable name for the active command state.
static const char *control_testing_command_state_name(ControlTestingCommandState state) {
    switch (state) {
        case CONTROL_TESTING_COMMAND_STATE_LINK_BC:
            return "link_bc";
        case CONTROL_TESTING_COMMAND_STATE_ALL_HOLD:
            return "all_hold";
        case CONTROL_TESTING_COMMAND_STATE_ALL_MANUAL:
            return "all_manual";
        case CONTROL_TESTING_COMMAND_STATE_CUSTOM:
        default:
            return "custom";
    }
}

// Returns a stable name for the teach engine state.
static const char *control_testing_teach_mode_name(ControlTestingTeachMode mode) {
    switch (mode) {
        case CONTROL_TESTING_TEACH_MODE_RECORDING:
            return "recording";
        case CONTROL_TESTING_TEACH_MODE_RECORDED:
            return "recorded";
        case CONTROL_TESTING_TEACH_MODE_PLAYING:
            return "playing";
        case CONTROL_TESTING_TEACH_MODE_IDLE:
        default:
            return "idle";
    }
}

// Formats the active command state for command responses.
static bool control_testing_write_command_state_result(
    char *out_result_json,
    size_t out_result_json_size,
    ControlTestingCommandState state
) {
    int written = 0;

    hard_assert(out_result_json != NULL);

    written = snprintf(
        out_result_json,
        out_result_json_size,
        "{\"state\":\"%s\"}",
        control_testing_command_state_name(state)
    );
    return written >= 0 && (size_t)written < out_result_json_size;
}

// Formats one teach status response for command handlers.
static bool control_testing_write_teach_status_result(
    char *out_result_json,
    size_t out_result_json_size,
    const ControlTestingApp *app
) {
    uint32_t duration_ms = 0u;
    int written = 0;

    hard_assert(out_result_json != NULL);
    hard_assert(app != NULL);

    duration_ms = (uint32_t)app->teach.sample_count * CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS;
    written = snprintf(
        out_result_json,
        out_result_json_size,
        "{\"mode\":\"%s\",\"samples\":%u,\"capacity\":%u,\"duration_ms\":%lu,"
        "\"playback_index\":%u,\"waiting_for_alignment\":%s,\"interpolate\":%s}",
        control_testing_teach_mode_name(app->teach.mode),
        (unsigned int)app->teach.sample_count,
        (unsigned int)CONTROL_TESTING_TEACH_SAMPLE_CAPACITY,
        (unsigned long)duration_ms,
        (unsigned int)app->teach.playback_index,
        app->teach.waiting_for_alignment ? "true" : "false",
        app->teach.playback_interpolate ? "true" : "false"
    );
    return written >= 0 && (size_t)written < out_result_json_size;
}

// Stops active playback and keeps current clip loaded.
static void control_testing_stop_playback(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->teach.mode != CONTROL_TESTING_TEACH_MODE_PLAYING) {
        return;
    }

    app->teach.mode = (app->teach.sample_count > 0u)
        ? CONTROL_TESTING_TEACH_MODE_RECORDED
        : CONTROL_TESTING_TEACH_MODE_IDLE;
    app->teach.waiting_for_alignment = false;
    app->teach.playback_index = 0u;
    app->teach.playback_segment_started_at = get_absolute_time();
}

// Stops playback before an external command overrides servo behavior.
static void control_testing_cancel_playback_for_override(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->teach.mode != CONTROL_TESTING_TEACH_MODE_PLAYING) {
        return;
    }

    control_testing_stop_playback(app);
    app->command_state = CONTROL_TESTING_COMMAND_STATE_CUSTOM;
}

// Starts a fresh teach recording.
static void control_testing_start_recording(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->teach.mode == CONTROL_TESTING_TEACH_MODE_PLAYING) {
        control_testing_stop_playback(app);
    }

    app->teach.mode = CONTROL_TESTING_TEACH_MODE_RECORDING;
    app->teach.waiting_for_alignment = false;
    app->teach.sample_count = 0u;
    app->teach.playback_index = 0u;
    app->teach.playback_segment_started_at = get_absolute_time();
    app->teach.next_sample_at = get_absolute_time();
    app->command_state = CONTROL_TESTING_COMMAND_STATE_CUSTOM;
}

// Stops recording and keeps captured clip available.
static void control_testing_stop_recording(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->teach.mode != CONTROL_TESTING_TEACH_MODE_RECORDING) {
        return;
    }

    app->teach.mode = (app->teach.sample_count > 0u)
        ? CONTROL_TESTING_TEACH_MODE_RECORDED
        : CONTROL_TESTING_TEACH_MODE_IDLE;
    app->teach.waiting_for_alignment = false;
    app->teach.playback_index = 0u;
    app->teach.playback_segment_started_at = get_absolute_time();
}

// Applies one recorded pose to all hold targets.
static void control_testing_apply_teach_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSample *sample
) {
    hard_assert(app != NULL);
    hard_assert(sample != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        app->servos[servo_index].settings.hold_target_deg = control_testing_clamp_hold_target_deg(
            control_testing_deg_tenths_to_f32(sample->servo_angle_deg_tenths[servo_index])
        );
    }
}

// Blends hold targets between two recorded poses over one sample interval.
static void control_testing_apply_interpolated_teach_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSample *start_sample,
    const ControlTestingTeachSample *end_sample,
    uint32_t elapsed_ms
) {
    float t = 0.0f;

    hard_assert(app != NULL);
    hard_assert(start_sample != NULL);
    hard_assert(end_sample != NULL);

    if (elapsed_ms >= CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS) {
        t = 1.0f;
    } else {
        t = (float)elapsed_ms / (float)CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS;
    }

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        float start_deg = control_testing_deg_tenths_to_f32(
            start_sample->servo_angle_deg_tenths[servo_index]
        );
        float end_deg = control_testing_deg_tenths_to_f32(
            end_sample->servo_angle_deg_tenths[servo_index]
        );
        float interpolated_deg = start_deg + ((end_deg - start_deg) * t);

        app->servos[servo_index].settings.hold_target_deg =
            control_testing_clamp_hold_target_deg(interpolated_deg);
    }
}

// Captures one teach sample from filtered measured servo angles.
static void control_testing_capture_teach_sample(ControlTestingApp *app) {
    ControlTestingTeachSample *sample = NULL;

    hard_assert(app != NULL);

    if (app->teach.sample_count >= CONTROL_TESTING_TEACH_SAMPLE_CAPACITY) {
        control_testing_stop_recording(app);
        return;
    }

    sample = &app->teach.samples[app->teach.sample_count];
    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        sample->servo_angle_deg_tenths[servo_index] = app->servos[servo_index].telemetry.angle_lp_deg_tenths;
    }
    app->teach.sample_count++;

    if (app->teach.sample_count >= CONTROL_TESTING_TEACH_SAMPLE_CAPACITY) {
        control_testing_stop_recording(app);
    }
}

// Starts playback immediately from recorded first sample.
static bool control_testing_start_playback(
    ControlTestingApp *app,
    const char **out_error_code,
    const char **out_error_message
) {
    hard_assert(app != NULL);
    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    if (app->teach.sample_count == 0u) {
        *out_error_code = "no_recording";
        *out_error_message = "no taught motion available";
        return false;
    }

    if (app->teach.mode == CONTROL_TESTING_TEACH_MODE_RECORDING) {
        control_testing_stop_recording(app);
    }

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        app->servos[servo_index].settings.hold_target_deg = control_testing_clamp_hold_target_deg(
            control_testing_deg_tenths_to_f32(app->servos[servo_index].telemetry.angle_lp_deg_tenths)
        );
        servo_set_control_mode(&app->servos[servo_index], CONTROL_MODE_HOLD);
    }

    app->teach.mode = CONTROL_TESTING_TEACH_MODE_PLAYING;
    app->teach.waiting_for_alignment = false;
    app->teach.playback_index = 0u;
    app->teach.playback_segment_started_at = get_absolute_time();
    control_testing_apply_teach_sample(app, &app->teach.samples[0]);
    app->teach.next_sample_at = make_timeout_time_ms(CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS);
    app->command_state = CONTROL_TESTING_COMMAND_STATE_CUSTOM;
    return true;
}

// Advances record or playback state machine.
static void control_testing_update_teach(ControlTestingApp *app) {
    absolute_time_t now = get_absolute_time();

    hard_assert(app != NULL);

    if (app->teach.mode == CONTROL_TESTING_TEACH_MODE_RECORDING) {
        if (time_reached(app->teach.next_sample_at)) {
            control_testing_capture_teach_sample(app);
            app->teach.next_sample_at = make_timeout_time_ms(CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS);
        }
        return;
    }

    if (app->teach.mode != CONTROL_TESTING_TEACH_MODE_PLAYING) {
        return;
    }

    if (app->teach.playback_interpolate && app->teach.playback_index + 1u < app->teach.sample_count) {
        int64_t elapsed_us = absolute_time_diff_us(app->teach.playback_segment_started_at, now);
        uint32_t elapsed_ms = 0u;

        if (elapsed_us > 0) {
            elapsed_ms = (uint32_t)(elapsed_us / 1000);
        }
        control_testing_apply_interpolated_teach_sample(
            app,
            &app->teach.samples[app->teach.playback_index],
            &app->teach.samples[app->teach.playback_index + 1u],
            elapsed_ms
        );
    }

    if (!time_reached(app->teach.next_sample_at)) {
        return;
    }

    app->teach.playback_index++;

    if (app->teach.playback_index >= app->teach.sample_count) {
        control_testing_stop_playback(app);
        return;
    }

    app->teach.playback_segment_started_at = now;
    control_testing_apply_teach_sample(app, &app->teach.samples[app->teach.playback_index]);

    if (app->teach.playback_index + 1u >= app->teach.sample_count) {
        control_testing_stop_playback(app);
        return;
    }

    app->teach.next_sample_at = make_timeout_time_ms(CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS);
}

// Returns the current parameter value.
static bool control_testing_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    const Servo *servo = NULL;
    uint8_t servo_index = 0u;
    uint8_t local_param_id = 0u;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_value != NULL);

    if (param->user_data == CONTROL_TESTING_APP_PARAM_STATUS_LED_ON) {
        *out_value = DEVLINK_SERIAL_VALUE_BOOL(app->status_led_on);
        return true;
    }
    if (!control_testing_decode_servo_user_data(param->user_data, &servo_index, &local_param_id)) {
        return false;
    }

    servo = control_testing_get_servo_const(app, servo_index);
    hard_assert(servo != NULL);

    switch (local_param_id) {
        case CONTROL_TESTING_SERVO_PARAM_FILTER_ALPHA_PCT:
            *out_value = DEVLINK_SERIAL_VALUE_U8(servo->settings.filter_alpha_pct);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_MOTOR_STATE:
            *out_value = DEVLINK_SERIAL_VALUE_U8(servo->telemetry.motor_state);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_MOTOR_DRIVE_PCT:
            *out_value = DEVLINK_SERIAL_VALUE_U8(servo->telemetry.motor_drive_pct);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_CONTROL_MODE:
            *out_value = DEVLINK_SERIAL_VALUE_U8(servo->control_mode);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_TARGET_DEG:
            *out_value = DEVLINK_SERIAL_VALUE_F32(servo->settings.hold_target_deg);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_DEADBAND_DEG:
            *out_value = DEVLINK_SERIAL_VALUE_F32(servo->settings.hold_deadband_deg);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_P_GAIN:
            *out_value = DEVLINK_SERIAL_VALUE_F32(servo->settings.hold_p_gain);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_I_GAIN:
            *out_value = DEVLINK_SERIAL_VALUE_F32(servo->settings.hold_i_gain);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_D_GAIN:
            *out_value = DEVLINK_SERIAL_VALUE_F32(servo->settings.hold_d_gain);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_MAX_DUTY:
            *out_value = DEVLINK_SERIAL_VALUE_U8(servo->settings.hold_max_duty);
            return true;
        default:
            return false;
    }
}

// Applies a parameter update.
static bool control_testing_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    Servo *servo = NULL;
    uint8_t servo_index = 0u;
    uint8_t local_param_id = 0u;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    *out_error_code = NULL;
    *out_error_message = NULL;

    if (param->user_data == CONTROL_TESTING_APP_PARAM_STATUS_LED_ON) {
        app->status_led_on = value.bool_value;
        control_testing_apply_status_led(app);
        return true;
    }
    if (!control_testing_decode_servo_user_data(param->user_data, &servo_index, &local_param_id)) {
        *out_error_code = "unknown_param";
        *out_error_message = "unknown parameter";
        return false;
    }

    if (app->teach.mode == CONTROL_TESTING_TEACH_MODE_PLAYING) {
        control_testing_cancel_playback_for_override(app);
    }

    servo = control_testing_get_servo(app, servo_index);
    hard_assert(servo != NULL);

    switch (local_param_id) {
        case CONTROL_TESTING_SERVO_PARAM_FILTER_ALPHA_PCT:
            servo->settings.filter_alpha_pct = (uint8_t)value.u32_value;
            return true;
        case CONTROL_TESTING_SERVO_PARAM_MOTOR_STATE:
            servo_set_motor_state(servo, (uint8_t)value.u32_value);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_MOTOR_DRIVE_PCT:
            servo_set_motor_drive_pct(servo, (uint8_t)value.u32_value);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_CONTROL_MODE:
            servo_set_control_mode(servo, (uint8_t)value.u32_value);
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_TARGET_DEG:
            servo->settings.hold_target_deg = value.f32_value;
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_DEADBAND_DEG:
            servo->settings.hold_deadband_deg = value.f32_value;
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_P_GAIN:
            servo->settings.hold_p_gain = value.f32_value;
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_I_GAIN:
            servo->settings.hold_i_gain = value.f32_value;
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_D_GAIN:
            servo->settings.hold_d_gain = value.f32_value;
            return true;
        case CONTROL_TESTING_SERVO_PARAM_HOLD_MAX_DUTY:
            servo->settings.hold_max_duty = (uint8_t)value.u32_value;
            return true;
        default:
            *out_error_code = "unknown_param";
            *out_error_message = "unknown parameter";
            return false;
    }
}

// Puts the device into BC-link mode. Later mode commands replace this state.
static DevlinkSerialCommandStatus handle_cmd_mode_link_bc(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;

    control_testing_set_command_state(app, CONTROL_TESTING_COMMAND_STATE_LINK_BC);
    if (!control_testing_write_command_state_result(
            out_result_json,
            out_result_json_size,
            app->command_state
        )) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Sets every servo to hold mode.
static DevlinkSerialCommandStatus handle_cmd_mode_all_hold(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;
    control_testing_set_command_state(app, CONTROL_TESTING_COMMAND_STATE_ALL_HOLD);
    if (!control_testing_write_command_state_result(
            out_result_json,
            out_result_json_size,
            app->command_state
        )) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Sets every servo to manual mode.
static DevlinkSerialCommandStatus handle_cmd_mode_all_manual(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;
    control_testing_set_command_state(app, CONTROL_TESTING_COMMAND_STATE_ALL_MANUAL);
    if (!control_testing_write_command_state_result(
            out_result_json,
            out_result_json_size,
            app->command_state
        )) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Starts a new teach recording buffer.
static DevlinkSerialCommandStatus handle_cmd_teach_record_start(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;

    control_testing_start_recording(app);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Stops active recording and keeps clip available.
static DevlinkSerialCommandStatus handle_cmd_teach_record_stop(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;

    control_testing_stop_recording(app);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Starts teach playback from recorded samples.
static DevlinkSerialCommandStatus handle_cmd_teach_play_start(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;

    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    *out_error_code = NULL;
    *out_error_message = NULL;

    if (!control_testing_start_playback(app, out_error_code, out_error_message)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Stops teach playback without clearing clip.
static DevlinkSerialCommandStatus handle_cmd_teach_play_stop(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;

    control_testing_stop_playback(app);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Reports current teach engine state.
static DevlinkSerialCommandStatus handle_cmd_teach_status(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;

    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Enables interpolation between recorded playback poses.
static DevlinkSerialCommandStatus handle_cmd_teach_play_interpolate_on(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;

    app->teach.playback_interpolate = true;
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Disables interpolation between recorded playback poses.
static DevlinkSerialCommandStatus handle_cmd_teach_play_interpolate_off(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;
    (void)device;
    (void)command;
    (void)out_error_code;
    (void)out_error_message;

    app->teach.playback_interpolate = false;
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Ticks all servos once.
static void control_testing_pid_tick(ControlTestingApp *app) {
    hard_assert(app != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        servo_tick(&app->servos[servo_index]);
    }

    if (app->command_state == CONTROL_TESTING_COMMAND_STATE_LINK_BC) {
        control_testing_apply_servo_bc_link(app);
    }
}

// Emits one grouped telemetry frame.
static void control_testing_emit_telemetry(ControlTestingApp *app) {
    uint64_t sample_time_us = time_us_64();
    DevlinkSerialValue adc_values[count_of(g_control_testing_adc_fields)];
    DevlinkSerialValue adc_avg_values[count_of(g_control_testing_adc_avg_fields)];
    DevlinkSerialValue adc_lp_values[count_of(g_control_testing_adc_lp_fields)];
    DevlinkSerialValue angle_avg_values[count_of(g_control_testing_angle_avg_fields)];
    DevlinkSerialValue angle_lp_values[count_of(g_control_testing_angle_lp_fields)];
    DevlinkSerialValue motor_values[count_of(g_control_testing_motor_fields)];
    DevlinkSerialValue hold_values[count_of(g_control_testing_hold_fields)];

    hard_assert(app != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        const Servo *servo = &app->servos[servo_index];
        float actual_deg = control_testing_deg_tenths_to_f32(servo->telemetry.angle_lp_deg_tenths);

        adc_values[servo_index] = DEVLINK_SERIAL_VALUE_U16(servo->telemetry.adc_raw);
        adc_avg_values[servo_index] = DEVLINK_SERIAL_VALUE_U16(servo->telemetry.adc_avg_raw);
        adc_lp_values[servo_index] = DEVLINK_SERIAL_VALUE_U16(servo->telemetry.adc_lp_raw);
        angle_avg_values[servo_index] = DEVLINK_SERIAL_VALUE_F32(
            control_testing_deg_tenths_to_f32(servo->telemetry.angle_avg_deg_tenths)
        );
        angle_lp_values[servo_index] = DEVLINK_SERIAL_VALUE_F32(actual_deg);
        motor_values[servo_index * 2u] = DEVLINK_SERIAL_VALUE_U8(servo->telemetry.motor_state);
        motor_values[(servo_index * 2u) + 1u] = DEVLINK_SERIAL_VALUE_U8(servo->telemetry.motor_drive_pct);
        hold_values[servo_index * 4u] = DEVLINK_SERIAL_VALUE_F32(servo->settings.hold_target_deg);
        hold_values[(servo_index * 4u) + 1u] = DEVLINK_SERIAL_VALUE_F32(actual_deg);
        hold_values[(servo_index * 4u) + 2u] = DEVLINK_SERIAL_VALUE_F32(
            servo->settings.hold_target_deg - actual_deg
        );
        hold_values[(servo_index * 4u) + 3u] = DEVLINK_SERIAL_VALUE_I16(servo->telemetry.hold_output_pct);
    }

    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[CONTROL_TESTING_STREAM_ADC],
        app->stream_sample_seq[CONTROL_TESTING_STREAM_ADC]++,
        sample_time_us,
        adc_values
    );
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[CONTROL_TESTING_STREAM_ADC_AVG],
        app->stream_sample_seq[CONTROL_TESTING_STREAM_ADC_AVG]++,
        sample_time_us,
        adc_avg_values
    );
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[CONTROL_TESTING_STREAM_ADC_LP],
        app->stream_sample_seq[CONTROL_TESTING_STREAM_ADC_LP]++,
        sample_time_us,
        adc_lp_values
    );
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[CONTROL_TESTING_STREAM_ANGLE_AVG],
        app->stream_sample_seq[CONTROL_TESTING_STREAM_ANGLE_AVG]++,
        sample_time_us,
        angle_avg_values
    );
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[CONTROL_TESTING_STREAM_ANGLE_LP],
        app->stream_sample_seq[CONTROL_TESTING_STREAM_ANGLE_LP]++,
        sample_time_us,
        angle_lp_values
    );
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[CONTROL_TESTING_STREAM_MOTOR],
        app->stream_sample_seq[CONTROL_TESTING_STREAM_MOTOR]++,
        sample_time_us,
        motor_values
    );
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[CONTROL_TESTING_STREAM_HOLD],
        app->stream_sample_seq[CONTROL_TESTING_STREAM_HOLD]++,
        sample_time_us,
        hold_values
    );
}

// Dispatches one timer interrupt tick.
static bool control_testing_pid_callback(repeating_timer_t *rt) {
    control_testing_pid_tick((ControlTestingApp *)rt->user_data);
    return true;
}

// Emits telemetry when its deadline expires.
static void control_testing_tick(ControlTestingApp *app) {
    hard_assert(app != NULL);

    control_testing_update_teach(app);

    if (time_reached(app->next_telemetry_at)) {
        control_testing_emit_telemetry(app);
        app->next_telemetry_at = make_timeout_time_ms(TELEMETRY_PERIOD_MS);
    }
}

// Processes pending devlink command bytes.
static void control_testing_poll_commands(
    PioUartRx *command_rx,
    DevlinkSerialLineBuffer *line_buffer,
    ControlTestingApp *app,
    char *command_line,
    size_t command_line_size
) {
    uint8_t received_byte = 0u;

    hard_assert(command_rx != NULL);
    hard_assert(line_buffer != NULL);
    hard_assert(app != NULL);
    hard_assert(command_line != NULL);

    while (pio_uart_rx_try_getc(command_rx, &received_byte)) {
        control_testing_consume_command_byte(
            line_buffer,
            app,
            (int)received_byte,
            command_line,
            command_line_size
        );
    }

    control_testing_flush_command_buffer(
        line_buffer,
        app,
        command_line,
        command_line_size
    );

    if (pio_uart_rx_take_dropped_count(command_rx) > 0u) {
        devlink_serial_print_event(&g_control_testing_device, "protocol.rx_overflow", "error");
    }
}

// Pushes one command byte into a line buffer and dispatches complete lines.
static void control_testing_consume_command_byte(
    DevlinkSerialLineBuffer *line_buffer,
    ControlTestingApp *app,
    int received_byte,
    char *command_line,
    size_t command_line_size
) {
    DevlinkSerialLineReadStatus read_status = DEVLINK_SERIAL_LINE_NONE;

    hard_assert(line_buffer != NULL);
    hard_assert(app != NULL);
    hard_assert(command_line != NULL);

    read_status = devlink_serial_line_buffer_push(
            line_buffer,
            received_byte,
            command_line,
            command_line_size
        );

    if (read_status == DEVLINK_SERIAL_LINE_READY) {
        devlink_serial_handle_command_line(&g_control_testing_device, app, command_line);
    } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
        devlink_serial_print_event(&g_control_testing_device, "protocol.line_too_long", "error");
    }
}

// Flushes one line buffer after idle timeout.
static void control_testing_flush_command_buffer(
    DevlinkSerialLineBuffer *line_buffer,
    ControlTestingApp *app,
    char *command_line,
    size_t command_line_size
) {
    DevlinkSerialLineReadStatus read_status = DEVLINK_SERIAL_LINE_NONE;

    hard_assert(line_buffer != NULL);
    hard_assert(app != NULL);
    hard_assert(command_line != NULL);

    read_status = devlink_serial_line_buffer_flush_if_idle(
        line_buffer,
        command_line,
        command_line_size
    );

    if (read_status == DEVLINK_SERIAL_LINE_READY) {
        devlink_serial_handle_command_line(&g_control_testing_device, app, command_line);
    } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
        devlink_serial_print_event(&g_control_testing_device, "protocol.line_too_long", "error");
    }
}

// Starts the control testing firmware.
int main(void) {
    PioUartRx command_rx = {0};
    ControlTestingApp app = {0};
    DevlinkSerialLineBuffer command_buffer = {0};
    char command_storage[COMMAND_BUFFER_LEN] = {0};
    char command_line[COMMAND_BUFFER_LEN] = {0};

    stdio_init_all();
    sleep_ms(200u);

    control_testing_init(&app);

    gpio_pull_up(COMMAND_RX_GPIO);

    if (!pio_uart_rx_init(&command_rx, pio0, COMMAND_RX_GPIO, COMMAND_BAUD)) {
        devlink_serial_print_log(&g_control_testing_device, "error", "pio rx init failed");
        while (true) {
            tight_loop_contents();
        }
    }

    devlink_serial_line_buffer_init(
        &command_buffer,
        command_storage,
        sizeof(command_storage),
        COMMAND_IDLE_FLUSH_MS
    );

    devlink_serial_print_discovery(&g_control_testing_device);
    devlink_serial_print_log(&g_control_testing_device, "info", "control_testing ready");
    devlink_serial_print_event(&g_control_testing_device, "device.ready", "info");

    while (true) {
        control_testing_poll_commands(
            &command_rx,
            &command_buffer,
            &app,
            command_line,
            sizeof(command_line)
        );
        control_testing_tick(&app);
        tight_loop_contents();
    }
}
