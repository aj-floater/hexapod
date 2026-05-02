#include <math.h>
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
#define CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_P_GAIN 20.0f
#define CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_I_GAIN 0.2f
#define CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_D_GAIN 200.0f
#define CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_P_GAIN 30.0f
#define CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_I_GAIN 0.3f
#define CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_D_GAIN 300.0f
#define CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_P_GAIN 30.0f
#define CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_I_GAIN 0.3f
#define CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_D_GAIN 300.0f
#define CONTROL_TESTING_GAIT_UPDATE_PERIOD_MS 20u
#define CONTROL_TESTING_GAIT_PATH_SAMPLE_COUNT 100u
#define CONTROL_TESTING_GAIT_SPEED_MODE_COUNT 4u
#define CONTROL_TESTING_GAIT_TRANSITION_SAMPLE_COUNT 40u

#define CONTROL_TESTING_GAIT_PI_F 3.14159265358979323846f
#define CONTROL_TESTING_GAIT_IK_COS_TOLERANCE 1e-5f
#define CONTROL_TESTING_GAIT_IK_POSITION_TOLERANCE_MM 0.5f
#define CONTROL_TESTING_GAIT_PATH_STANCE_RATIO 0.60f
#define CONTROL_TESTING_GAIT_PATH_HALF_WIDTH_MM 25.0f
#define CONTROL_TESTING_GAIT_PATH_STANCE_Y_MM 130.0f
#define CONTROL_TESTING_GAIT_PATH_STANCE_Z_MM -98.0f
#define CONTROL_TESTING_GAIT_PATH_SWING_Y_ARC_MM 15.0f
#define CONTROL_TESTING_GAIT_PATH_SWING_Z_LIFT_MM 50.0f
#define CONTROL_TESTING_GAIT_LINK_1_MM 36.0f
#define CONTROL_TESTING_GAIT_LINK_2_MM 62.0f
#define CONTROL_TESTING_GAIT_LINK_3_MM 87.0f

static const float g_control_testing_gait_cycle_time_s[CONTROL_TESTING_GAIT_SPEED_MODE_COUNT] = {
    2.0f,
    1.5f,
    1.0f,
    0.75f,
};
static const float g_control_testing_gait_assembly_pose_deg[CONTROL_TESTING_SERVO_COUNT] = {
    90.0f,
    82.0f,
    91.0f,
};

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
    CONTROL_TESTING_APP_PARAM_GAIT_SPEED_MODE,
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

#define CONTROL_TESTING_SERVO_PARAM_SET(letter, servo_index, control_default, p_default, i_default, d_default) \
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
        DEVLINK_SERIAL_VALUE_F32(p_default), \
        true, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_P_GAIN_MIN), \
        DEVLINK_SERIAL_VALUE_F32(HOLD_P_GAIN_MAX), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_HOLD_P_GAIN), \
    }, \
    { \
        "servo." #letter ".hold.i_gain", \
        DEVLINK_SERIAL_TYPE_F32, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_F32(i_default), \
        true, \
        DEVLINK_SERIAL_VALUE_F32(HOLD_I_GAIN_MIN), \
        DEVLINK_SERIAL_VALUE_F32(HOLD_I_GAIN_MAX), \
        CONTROL_TESTING_SERVO_USER_DATA(servo_index, CONTROL_TESTING_SERVO_PARAM_HOLD_I_GAIN), \
    }, \
    { \
        "servo." #letter ".hold.d_gain", \
        DEVLINK_SERIAL_TYPE_F32, \
        DEVLINK_SERIAL_ACCESS_RW, \
        DEVLINK_SERIAL_VALUE_F32(d_default), \
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

typedef enum {
    CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_STEP = 0,
    CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_LINEAR,
    CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_SMOOTH,
} ControlTestingTeachPlaybackProfile;

typedef struct {
    float position_deg[CONTROL_TESTING_SERVO_COUNT];
    float velocity_deg_per_s[CONTROL_TESTING_SERVO_COUNT];
    float acceleration_deg_per_s2[CONTROL_TESTING_SERVO_COUNT];
} ControlTestingTeachSmoothSample;

typedef struct {
    ControlTestingTeachMode mode;
    bool waiting_for_alignment;
    ControlTestingTeachPlaybackProfile playback_requested_profile;
    ControlTestingTeachPlaybackProfile playback_active_profile;
    bool playback_repeat;
    uint16_t sample_count;
    uint16_t playback_index;
    absolute_time_t playback_segment_started_at;
    absolute_time_t next_sample_at;
    ControlTestingTeachSample samples[CONTROL_TESTING_TEACH_SAMPLE_CAPACITY];
    ControlTestingTeachSmoothSample smooth_samples[CONTROL_TESTING_TEACH_SAMPLE_CAPACITY];
} ControlTestingTeachState;

typedef struct {
    float x_mm;
    float y_mm;
    float z_mm;
    float phase_u;
    uint8_t sample_index;
} ControlTestingGaitPathTarget;

typedef enum {
    CONTROL_TESTING_GAIT_MODE_IDLE = 0,
    CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_PATH,
    CONTROL_TESTING_GAIT_MODE_RUNNING,
    CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_ASSEMBLY,
} ControlTestingGaitMode;

typedef struct {
    ControlTestingGaitMode mode;
    uint8_t speed_mode;
    float phase_u;
    float current_pose_deg[CONTROL_TESTING_SERVO_COUNT];
    float segment_start_pose_deg[CONTROL_TESTING_SERVO_COUNT];
    float segment_target_pose_deg[CONTROL_TESTING_SERVO_COUNT];
    float reference_pose_deg[CONTROL_TESTING_SERVO_COUNT];
    uint16_t transition_total_samples;
    uint16_t transition_sample_index;
} ControlTestingGaitState;

typedef struct {
    bool status_led_on;
    ControlTestingCommandState command_state;
    Servo servos[CONTROL_TESTING_SERVO_COUNT];
    ControlTestingTeachState teach;
    ControlTestingGaitState gait;
    repeating_timer_t pid_timer;
    absolute_time_t next_gait_at;
    absolute_time_t next_telemetry_at;
    uint32_t stream_sample_seq[CONTROL_TESTING_STREAM_COUNT];
} ControlTestingApp;

static float control_testing_wrap_angle_deg(float angle_deg);
static float control_testing_wrap_phase_u(float phase_u);
static float control_testing_pose_distance_sq(
    const float left[CONTROL_TESTING_SERVO_COUNT],
    const float right[CONTROL_TESTING_SERVO_COUNT]
);
static void control_testing_copy_pose(
    float dest[CONTROL_TESTING_SERVO_COUNT],
    const float source[CONTROL_TESTING_SERVO_COUNT]
);
static void control_testing_capture_measured_pose(
    const ControlTestingApp *app,
    float out_pose_deg[CONTROL_TESTING_SERVO_COUNT]
);
static void control_testing_gait_apply_hold_pose(
    ControlTestingApp *app,
    const float pose_deg[CONTROL_TESTING_SERVO_COUNT]
);
static const char *control_testing_gait_mode_name(ControlTestingGaitMode mode);
static uint32_t control_testing_gait_cycle_time_ms(uint8_t speed_mode);
static float control_testing_gait_cycle_time_s(uint8_t speed_mode);
static void control_testing_gait_compute_path_target(
    float phase_u,
    ControlTestingGaitPathTarget *target
);
static bool control_testing_gait_solve_ik(
    const ControlTestingApp *app,
    float x_mm,
    float y_mm,
    float z_mm,
    const float reference_pose_deg[CONTROL_TESTING_SERVO_COUNT],
    float solved_pose_deg[CONTROL_TESTING_SERVO_COUNT]
);
static void control_testing_gait_begin_transition(
    ControlTestingApp *app,
    ControlTestingGaitMode mode,
    const float target_pose_deg[CONTROL_TESTING_SERVO_COUNT]
);
static void control_testing_cancel_gait_for_override(ControlTestingApp *app);
static void control_testing_cancel_teach_for_gait(ControlTestingApp *app);
static bool control_testing_start_gait(
    ControlTestingApp *app,
    const char **out_error_code,
    const char **out_error_message
);
static void control_testing_pause_gait(ControlTestingApp *app);
static void control_testing_update_gait(ControlTestingApp *app);
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
static const char *control_testing_teach_playback_profile_name(
    ControlTestingTeachPlaybackProfile profile
);
static ControlTestingTeachPlaybackProfile control_testing_current_teach_playback_profile(
    const ControlTestingApp *app
);
static bool control_testing_write_gait_status_result(
    char *out_result_json,
    size_t out_result_json_size,
    const ControlTestingApp *app
);
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
static void control_testing_capture_current_pose_as_hold_targets(ControlTestingApp *app);
static void control_testing_stop_playback(ControlTestingApp *app);
static void control_testing_cancel_playback_for_override(ControlTestingApp *app);
static void control_testing_start_recording(ControlTestingApp *app);
static void control_testing_stop_recording(ControlTestingApp *app);
static bool control_testing_start_playback(
    ControlTestingApp *app,
    bool repeat,
    const char **out_error_code,
    const char **out_error_message
);
static void control_testing_set_playback_profile(
    ControlTestingApp *app,
    ControlTestingTeachPlaybackProfile profile
);
static void control_testing_prepare_playback_profile(ControlTestingApp *app);
static void control_testing_prepare_smooth_samples(
    ControlTestingApp *app,
    const ControlTestingTeachSample *samples,
    uint16_t sample_count,
    ControlTestingTeachSmoothSample *smooth_samples,
    bool wrap
);
static void control_testing_capture_teach_sample(ControlTestingApp *app);
static void control_testing_apply_teach_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSample *sample
);
static void control_testing_apply_playback_sample(
    ControlTestingApp *app,
    uint16_t sample_index
);
static void control_testing_apply_interpolated_teach_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSample *start_sample,
    const ControlTestingTeachSample *end_sample,
    uint32_t elapsed_ms
);
static void control_testing_prepare_smooth_playback(ControlTestingApp *app);
static uint16_t control_testing_wrap_sample_index(int32_t sample_index, uint16_t sample_count);
static uint16_t control_testing_mirror_sample_index(int32_t sample_index, uint16_t sample_count);
static float control_testing_get_sample_angle_deg(
    const ControlTestingTeachSample *samples,
    uint16_t sample_count,
    int32_t sample_index,
    size_t servo_index,
    bool wrap
);
static bool control_testing_playback_has_interpolated_segment(const ControlTestingApp *app);
static uint16_t control_testing_playback_segment_end_index(const ControlTestingApp *app);
static float control_testing_evaluate_quintic_hermite_segment(
    float start_pos_deg,
    float start_vel_deg_per_s,
    float start_accel_deg_per_s2,
    float end_pos_deg,
    float end_vel_deg_per_s,
    float end_accel_deg_per_s2,
    uint32_t elapsed_ms
);
static void control_testing_apply_smooth_playback_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSmoothSample *smooth_samples,
    uint16_t sample_count,
    uint16_t sample_index
);
static void control_testing_apply_smooth_playback_segment(
    ControlTestingApp *app,
    const ControlTestingTeachSmoothSample *smooth_samples,
    uint16_t sample_count,
    uint16_t start_index,
    uint16_t end_index,
    uint32_t elapsed_ms
);
static void control_testing_apply_playback_segment_target(
    ControlTestingApp *app,
    absolute_time_t now
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
static DevlinkSerialCommandStatus handle_cmd_teach_play_repeat(
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
static DevlinkSerialCommandStatus handle_cmd_teach_play_profile_step(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_play_profile_linear(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_teach_play_profile_smooth(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_gait_play(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_gait_pause(
    const DevlinkSerialDeviceDescriptor *device,
    void *context,
    const DevlinkSerialCommand *command,
    char *out_result_json,
    size_t out_result_json_size,
    const char **out_error_code,
    const char **out_error_message
);
static DevlinkSerialCommandStatus handle_cmd_gait_status(
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
    {
        "gait.speed_mode",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(0u),
        true,
        DEVLINK_SERIAL_VALUE_U8(0u),
        DEVLINK_SERIAL_VALUE_U8(CONTROL_TESTING_GAIT_SPEED_MODE_COUNT - 1u),
        CONTROL_TESTING_APP_PARAM_GAIT_SPEED_MODE,
    },
    CONTROL_TESTING_SERVO_PARAM_SET(
        a,
        CONTROL_TESTING_SERVO_A,
        CONTROL_MODE_MANUAL,
        CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_P_GAIN,
        CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_I_GAIN,
        CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_D_GAIN
    ),
    CONTROL_TESTING_SERVO_PARAM_SET(
        b,
        CONTROL_TESTING_SERVO_B,
        CONTROL_MODE_MANUAL,
        CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_P_GAIN,
        CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_I_GAIN,
        CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_D_GAIN
    ),
    CONTROL_TESTING_SERVO_PARAM_SET(
        c,
        CONTROL_TESTING_SERVO_C,
        CONTROL_MODE_MANUAL,
        CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_P_GAIN,
        CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_I_GAIN,
        CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_D_GAIN
    ),
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
        .id = 'a',
        .motor_name = "motor_a",
        .adc_gpio = LEG_POT_A_GPIO,
        .motor_in1_gpio = LEG_MOTOR_A_IN1_GPIO,
        .motor_in2_gpio = LEG_MOTOR_A_IN2_GPIO,
        .default_control_mode = CONTROL_MODE_MANUAL,
        .default_hold_p_gain = CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_P_GAIN,
        .default_hold_i_gain = CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_I_GAIN,
        .default_hold_d_gain = CONTROL_TESTING_SERVO_A_DEFAULT_HOLD_D_GAIN,
        .min_angle_deg = 40.0f,
        .max_angle_deg = 140.0f,
        .calibration_points = g_control_testing_calibration_points,
        .calibration_point_count = count_of(g_control_testing_calibration_points),
    },
    {
        .id = 'b',
        .motor_name = "motor_b",
        .adc_gpio = LEG_POT_C_GPIO,
        .motor_in1_gpio = LEG_MOTOR_C_IN1_GPIO,
        .motor_in2_gpio = LEG_MOTOR_C_IN2_GPIO,
        .default_control_mode = CONTROL_MODE_MANUAL,
        .default_hold_p_gain = CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_P_GAIN,
        .default_hold_i_gain = CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_I_GAIN,
        .default_hold_d_gain = CONTROL_TESTING_SERVO_B_DEFAULT_HOLD_D_GAIN,
        .min_angle_deg = 30.0f,
        .max_angle_deg = 130.0f,
        .calibration_points = g_control_testing_calibration_points,
        .calibration_point_count = count_of(g_control_testing_calibration_points),
    },
    {
        .id = 'c',
        .motor_name = "motor_c",
        .adc_gpio = LEG_POT_B_GPIO,
        .motor_in1_gpio = LEG_MOTOR_B_IN1_GPIO,
        .motor_in2_gpio = LEG_MOTOR_B_IN2_GPIO,
        .default_control_mode = CONTROL_MODE_MANUAL,
        .default_hold_p_gain = CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_P_GAIN,
        .default_hold_i_gain = CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_I_GAIN,
        .default_hold_d_gain = CONTROL_TESTING_SERVO_C_DEFAULT_HOLD_D_GAIN,
        .min_angle_deg = 20.0f,
        .max_angle_deg = 170.0f,
        .calibration_points = g_control_testing_calibration_points,
        .calibration_point_count = count_of(g_control_testing_calibration_points),
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
        .name = "teach.play.repeat",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_play_repeat,
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
    {
        .name = "teach.play.profile.step",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_play_profile_step,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.play.profile.linear",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_play_profile_linear,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "teach.play.profile.smooth",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_teach_play_profile_smooth,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "gait.play",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_gait_play,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "gait.pause",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_gait_pause,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
    {
        .name = "gait.status",
        .args = NULL,
        .arg_count = 0u,
        .handler = handle_cmd_gait_status,
        .success_event_name = NULL,
        .success_event_severity = NULL,
    },
};

static const DevlinkSerialDeviceDescriptor g_control_testing_device = {
    .device = "control_testing",
    .firmware = "0.10.0",
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

// Wraps one raw angle into the [-180, 180) range.
static float control_testing_wrap_angle_deg(float angle_deg) {
    while (angle_deg >= 180.0f) {
        angle_deg -= 360.0f;
    }
    while (angle_deg < -180.0f) {
        angle_deg += 360.0f;
    }
    return angle_deg;
}

// Wraps one gait phase into the [0, 1) range.
static float control_testing_wrap_phase_u(float phase_u) {
    while (phase_u >= 1.0f) {
        phase_u -= 1.0f;
    }
    while (phase_u < 0.0f) {
        phase_u += 1.0f;
    }
    return phase_u;
}

// Computes squared distance between two raw-servo poses.
static float control_testing_pose_distance_sq(
    const float left[CONTROL_TESTING_SERVO_COUNT],
    const float right[CONTROL_TESTING_SERVO_COUNT]
) {
    float distance_sq = 0.0f;

    hard_assert(left != NULL);
    hard_assert(right != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        float delta = left[servo_index] - right[servo_index];
        distance_sq += delta * delta;
    }
    return distance_sq;
}

// Copies one raw-servo pose.
static void control_testing_copy_pose(
    float dest[CONTROL_TESTING_SERVO_COUNT],
    const float source[CONTROL_TESTING_SERVO_COUNT]
) {
    hard_assert(dest != NULL);
    hard_assert(source != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        dest[servo_index] = source[servo_index];
    }
}

// Returns a stable name for the active gait mode.
static const char *control_testing_gait_mode_name(ControlTestingGaitMode mode) {
    switch (mode) {
        case CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_PATH:
            return "transition_to_path";
        case CONTROL_TESTING_GAIT_MODE_RUNNING:
            return "running";
        case CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_ASSEMBLY:
            return "transition_to_assembly";
        case CONTROL_TESTING_GAIT_MODE_IDLE:
        default:
            return "idle";
    }
}

// Returns the configured cycle time for one gait speed mode.
static uint32_t control_testing_gait_cycle_time_ms(uint8_t speed_mode) {
    hard_assert(speed_mode < CONTROL_TESTING_GAIT_SPEED_MODE_COUNT);
    return (uint32_t)(g_control_testing_gait_cycle_time_s[speed_mode] * 1000.0f + 0.5f);
}

// Returns the configured cycle time in seconds for one gait speed mode.
static float control_testing_gait_cycle_time_s(uint8_t speed_mode) {
    hard_assert(speed_mode < CONTROL_TESTING_GAIT_SPEED_MODE_COUNT);
    return g_control_testing_gait_cycle_time_s[speed_mode];
}

// Computes one canonical gait path sample.
static void control_testing_gait_compute_path_target(
    float phase_u,
    ControlTestingGaitPathTarget *target
) {
    float wrapped_phase_u = 0.0f;

    hard_assert(target != NULL);

    wrapped_phase_u = control_testing_wrap_phase_u(phase_u);
    target->phase_u = wrapped_phase_u;
    target->sample_index = (uint8_t)(
        ((uint32_t)(wrapped_phase_u * (float)CONTROL_TESTING_GAIT_PATH_SAMPLE_COUNT))
        % CONTROL_TESTING_GAIT_PATH_SAMPLE_COUNT
    );

    if (wrapped_phase_u <= CONTROL_TESTING_GAIT_PATH_STANCE_RATIO) {
        float stance_phase = wrapped_phase_u / CONTROL_TESTING_GAIT_PATH_STANCE_RATIO;

        target->x_mm = CONTROL_TESTING_GAIT_PATH_HALF_WIDTH_MM
            - (2.0f * CONTROL_TESTING_GAIT_PATH_HALF_WIDTH_MM * stance_phase);
        target->y_mm = CONTROL_TESTING_GAIT_PATH_STANCE_Y_MM;
        target->z_mm = CONTROL_TESTING_GAIT_PATH_STANCE_Z_MM;
        return;
    }

    {
        float swing_phase = (wrapped_phase_u - CONTROL_TESTING_GAIT_PATH_STANCE_RATIO)
            / (1.0f - CONTROL_TESTING_GAIT_PATH_STANCE_RATIO);
        float swing_arc = sinf(CONTROL_TESTING_GAIT_PI_F * swing_phase);

        target->x_mm = -CONTROL_TESTING_GAIT_PATH_HALF_WIDTH_MM
            + (2.0f * CONTROL_TESTING_GAIT_PATH_HALF_WIDTH_MM * swing_phase);
        target->y_mm = CONTROL_TESTING_GAIT_PATH_STANCE_Y_MM
            + (CONTROL_TESTING_GAIT_PATH_SWING_Y_ARC_MM * swing_arc);
        target->z_mm = CONTROL_TESTING_GAIT_PATH_STANCE_Z_MM
            + (CONTROL_TESTING_GAIT_PATH_SWING_Z_LIFT_MM * swing_arc);
    }
}

// Solves raw-servo DH IK and keeps branch continuity using the prior reference pose.
static bool control_testing_gait_solve_ik(
    const ControlTestingApp *app,
    float x_mm,
    float y_mm,
    float z_mm,
    const float reference_pose_deg[CONTROL_TESTING_SERVO_COUNT],
    float solved_pose_deg[CONTROL_TESTING_SERVO_COUNT]
) {
    float radial_distance_mm = hypotf(x_mm, y_mm);
    float base_heading_deg = atan2f(y_mm, x_mm) * (180.0f / CONTROL_TESTING_GAIT_PI_F);
    float vertical_target_mm = -z_mm;
    float best_pose_deg[CONTROL_TESTING_SERVO_COUNT] = {0.0f, 0.0f, 0.0f};
    float best_distance_sq = 0.0f;
    bool found_solution = false;

    hard_assert(app != NULL);
    hard_assert(reference_pose_deg != NULL);
    hard_assert(solved_pose_deg != NULL);

    for (size_t branch_index = 0u; branch_index < 2u; branch_index++) {
        float signed_radius_mm = (branch_index == 0u) ? radial_distance_mm : -radial_distance_mm;
        float theta1_deg = control_testing_wrap_angle_deg(
            (branch_index == 0u) ? base_heading_deg : (base_heading_deg + 180.0f)
        );
        float planar_x_mm = signed_radius_mm - CONTROL_TESTING_GAIT_LINK_1_MM;
        float cos_kappa = ((planar_x_mm * planar_x_mm) + (vertical_target_mm * vertical_target_mm)
            - (CONTROL_TESTING_GAIT_LINK_2_MM * CONTROL_TESTING_GAIT_LINK_2_MM)
            - (CONTROL_TESTING_GAIT_LINK_3_MM * CONTROL_TESTING_GAIT_LINK_3_MM))
            / (2.0f * CONTROL_TESTING_GAIT_LINK_2_MM * CONTROL_TESTING_GAIT_LINK_3_MM);

        if (cos_kappa < -1.0f - CONTROL_TESTING_GAIT_IK_COS_TOLERANCE
            || cos_kappa > 1.0f + CONTROL_TESTING_GAIT_IK_COS_TOLERANCE) {
            continue;
        }

        if (cos_kappa < -1.0f) {
            cos_kappa = -1.0f;
        } else if (cos_kappa > 1.0f) {
            cos_kappa = 1.0f;
        }

        {
            float kappa_abs_deg = acosf(cos_kappa) * (180.0f / CONTROL_TESTING_GAIT_PI_F);

            for (size_t kappa_index = 0u; kappa_index < 2u; kappa_index++) {
                float kappa_deg = (kappa_index == 0u) ? kappa_abs_deg : -kappa_abs_deg;
                float kappa_rad = kappa_deg * (CONTROL_TESTING_GAIT_PI_F / 180.0f);
                float beta_rad = atan2f(vertical_target_mm, planar_x_mm)
                    - atan2f(
                        CONTROL_TESTING_GAIT_LINK_3_MM * sinf(kappa_rad),
                        CONTROL_TESTING_GAIT_LINK_2_MM
                            + (CONTROL_TESTING_GAIT_LINK_3_MM * cosf(kappa_rad))
                    );
                float candidate_pose_deg[CONTROL_TESTING_SERVO_COUNT] = {
                    control_testing_wrap_angle_deg(theta1_deg),
                    (beta_rad * (180.0f / CONTROL_TESTING_GAIT_PI_F)) + 90.0f,
                    kappa_deg + 20.0f,
                };
                float candidate_xyz_mm[CONTROL_TESTING_SERVO_COUNT];
                float theta1_rad = candidate_pose_deg[0] * (CONTROL_TESTING_GAIT_PI_F / 180.0f);
                float beta_candidate_rad = (candidate_pose_deg[1] - 90.0f)
                    * (CONTROL_TESTING_GAIT_PI_F / 180.0f);
                float kappa_candidate_rad = (candidate_pose_deg[2] - 20.0f)
                    * (CONTROL_TESTING_GAIT_PI_F / 180.0f);
                float signed_radius_candidate_mm = CONTROL_TESTING_GAIT_LINK_1_MM
                    + (CONTROL_TESTING_GAIT_LINK_2_MM * cosf(beta_candidate_rad))
                    + (CONTROL_TESTING_GAIT_LINK_3_MM * cosf(beta_candidate_rad + kappa_candidate_rad));
                bool within_limits = true;

                for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
                    const Servo *servo = control_testing_get_servo_const(app, (uint8_t)servo_index);

                    hard_assert(servo != NULL);
                    if (candidate_pose_deg[servo_index] < servo->min_angle_deg - 1e-3f
                        || candidate_pose_deg[servo_index] > servo->max_angle_deg + 1e-3f) {
                        within_limits = false;
                        break;
                    }
                }
                if (!within_limits) {
                    continue;
                }

                candidate_xyz_mm[0] = signed_radius_candidate_mm * cosf(theta1_rad);
                candidate_xyz_mm[1] = signed_radius_candidate_mm * sinf(theta1_rad);
                candidate_xyz_mm[2] = -(
                    (CONTROL_TESTING_GAIT_LINK_2_MM * sinf(beta_candidate_rad))
                    + (CONTROL_TESTING_GAIT_LINK_3_MM * sinf(beta_candidate_rad + kappa_candidate_rad))
                );
                if (fabsf(candidate_xyz_mm[0] - x_mm) > CONTROL_TESTING_GAIT_IK_POSITION_TOLERANCE_MM
                    || fabsf(candidate_xyz_mm[1] - y_mm) > CONTROL_TESTING_GAIT_IK_POSITION_TOLERANCE_MM
                    || fabsf(candidate_xyz_mm[2] - z_mm) > CONTROL_TESTING_GAIT_IK_POSITION_TOLERANCE_MM) {
                    continue;
                }

                if (!found_solution
                    || control_testing_pose_distance_sq(candidate_pose_deg, reference_pose_deg) < best_distance_sq) {
                    control_testing_copy_pose(best_pose_deg, candidate_pose_deg);
                    best_distance_sq = control_testing_pose_distance_sq(best_pose_deg, reference_pose_deg);
                    found_solution = true;
                }
            }
        }
    }

    if (!found_solution) {
        return false;
    }

    control_testing_copy_pose(solved_pose_deg, best_pose_deg);
    return true;
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
    app->teach.playback_requested_profile = CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_STEP;
    app->teach.playback_active_profile = CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_STEP;
    app->teach.playback_repeat = false;
    app->teach.sample_count = 0u;
    app->teach.playback_index = 0u;
    app->teach.playback_segment_started_at = now;
    app->teach.next_sample_at = now;
    app->gait.mode = CONTROL_TESTING_GAIT_MODE_IDLE;
    app->gait.speed_mode = 0u;
    app->gait.phase_u = 0.0f;
    control_testing_copy_pose(app->gait.current_pose_deg, g_control_testing_gait_assembly_pose_deg);
    control_testing_copy_pose(app->gait.segment_start_pose_deg, g_control_testing_gait_assembly_pose_deg);
    control_testing_copy_pose(app->gait.segment_target_pose_deg, g_control_testing_gait_assembly_pose_deg);
    control_testing_copy_pose(app->gait.reference_pose_deg, g_control_testing_gait_assembly_pose_deg);
    app->gait.transition_total_samples = 0u;
    app->gait.transition_sample_index = 0u;
    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        servo_init(&app->servos[servo_index], &g_control_testing_servo_configs[servo_index]);
    }
    app->next_gait_at = now;
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

// Clamps one hold target to the public and servo-safe range.
static float control_testing_clamp_servo_hold_target_deg(const Servo *servo, float target_deg) {
    hard_assert(servo != NULL);

    return servo_clamp_target_deg(servo, control_testing_clamp_hold_target_deg(target_deg));
}

// Captures the current measured raw-servo pose from filtered telemetry.
static void control_testing_capture_measured_pose(
    const ControlTestingApp *app,
    float out_pose_deg[CONTROL_TESTING_SERVO_COUNT]
) {
    hard_assert(app != NULL);
    hard_assert(out_pose_deg != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        out_pose_deg[servo_index] = control_testing_deg_tenths_to_f32(
            app->servos[servo_index].telemetry.angle_lp_deg_tenths
        );
    }
}

// Applies one raw-servo pose through the existing hold-target clamp path.
static void control_testing_gait_apply_hold_pose(
    ControlTestingApp *app,
    const float pose_deg[CONTROL_TESTING_SERVO_COUNT]
) {
    hard_assert(app != NULL);
    hard_assert(pose_deg != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        Servo *servo = control_testing_get_servo(app, (uint8_t)servo_index);
        float target_deg = 0.0f;

        hard_assert(servo != NULL);
        target_deg = control_testing_clamp_hold_target_deg(pose_deg[servo_index]);
        target_deg = servo_clamp_target_deg(servo, target_deg);
        servo->settings.hold_target_deg = target_deg;
        if (servo->control_mode != CONTROL_MODE_HOLD) {
            servo_set_control_mode(servo, CONTROL_MODE_HOLD);
        }
        app->gait.current_pose_deg[servo_index] = target_deg;
    }
}

// Mirrors servo B's measured position into servo C's hold target.
static void control_testing_apply_servo_bc_link(ControlTestingApp *app) {
    const Servo *servo_b = NULL;
    Servo *servo_c = NULL;
    float servo_b_angle_lp_deg = 0.0f;

    hard_assert(app != NULL);

    servo_b = control_testing_get_servo_const(app, CONTROL_TESTING_SERVO_B);
    servo_c = control_testing_get_servo(app, CONTROL_TESTING_SERVO_C);
    hard_assert(servo_b != NULL);
    hard_assert(servo_c != NULL);

    servo_b_angle_lp_deg = control_testing_deg_tenths_to_f32(
        servo_b->telemetry.angle_lp_deg_tenths
    );
    servo_c->settings.hold_target_deg = control_testing_clamp_servo_hold_target_deg(
        servo_c,
        servo_b_angle_lp_deg
    );
}

// Applies one of the high-level device command states.
static void control_testing_set_command_state(
    ControlTestingApp *app,
    ControlTestingCommandState state
) {
    hard_assert(app != NULL);

    control_testing_cancel_gait_for_override(app);
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
            control_testing_capture_current_pose_as_hold_targets(app);
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

// Returns a stable name for the active teach playback profile.
static const char *control_testing_teach_playback_profile_name(
    ControlTestingTeachPlaybackProfile profile
) {
    switch (profile) {
        case CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_LINEAR:
            return "linear";
        case CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_SMOOTH:
            return "smooth";
        case CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_STEP:
        default:
            return "step";
    }
}

// Returns the effective playback profile for status and runtime logic.
static ControlTestingTeachPlaybackProfile control_testing_current_teach_playback_profile(
    const ControlTestingApp *app
) {
    hard_assert(app != NULL);

    if (app->teach.mode == CONTROL_TESTING_TEACH_MODE_PLAYING) {
        return app->teach.playback_active_profile;
    }
    return app->teach.playback_requested_profile;
}

// Formats one gait status response for command handlers.
static bool control_testing_write_gait_status_result(
    char *out_result_json,
    size_t out_result_json_size,
    const ControlTestingApp *app
) {
    ControlTestingGaitPathTarget target = {0};
    int written = 0;

    hard_assert(out_result_json != NULL);
    hard_assert(app != NULL);

    control_testing_gait_compute_path_target(app->gait.phase_u, &target);
    written = snprintf(
        out_result_json,
        out_result_json_size,
        "{\"mode\":\"%s\",\"speed_mode\":%u,\"cycle_time_ms\":%lu,\"phase_u\":%.6f,"
        "\"sample_index\":%u,\"command_state\":\"%s\",\"teach_mode\":\"%s\"}",
        control_testing_gait_mode_name(app->gait.mode),
        (unsigned int)app->gait.speed_mode,
        (unsigned long)control_testing_gait_cycle_time_ms(app->gait.speed_mode),
        (double)app->gait.phase_u,
        (unsigned int)target.sample_index,
        control_testing_command_state_name(app->command_state),
        control_testing_teach_mode_name(app->teach.mode)
    );
    return written >= 0 && (size_t)written < out_result_json_size;
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
    ControlTestingTeachPlaybackProfile playback_profile = CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_STEP;
    uint32_t duration_ms = 0u;
    int written = 0;

    hard_assert(out_result_json != NULL);
    hard_assert(app != NULL);

    playback_profile = control_testing_current_teach_playback_profile(app);
    duration_ms = (uint32_t)app->teach.sample_count * CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS;
    written = snprintf(
        out_result_json,
        out_result_json_size,
        "{\"mode\":\"%s\",\"samples\":%u,\"capacity\":%u,\"duration_ms\":%lu,"
        "\"playback_index\":%u,\"waiting_for_alignment\":%s,\"playback_profile\":\"%s\","
        "\"interpolate\":%s,\"repeat\":%s}",
        control_testing_teach_mode_name(app->teach.mode),
        (unsigned int)app->teach.sample_count,
        (unsigned int)CONTROL_TESTING_TEACH_SAMPLE_CAPACITY,
        (unsigned long)duration_ms,
        (unsigned int)app->teach.playback_index,
        app->teach.waiting_for_alignment ? "true" : "false",
        control_testing_teach_playback_profile_name(playback_profile),
        playback_profile == CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_LINEAR ? "true" : "false",
        app->teach.playback_repeat ? "true" : "false"
    );
    return written >= 0 && (size_t)written < out_result_json_size;
}

// Latches the current measured pose into the hold targets before enabling hold mode.
static void control_testing_capture_current_pose_as_hold_targets(ControlTestingApp *app) {
    hard_assert(app != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        app->servos[servo_index].settings.hold_target_deg = control_testing_clamp_servo_hold_target_deg(
            &app->servos[servo_index],
            control_testing_deg_tenths_to_f32(app->servos[servo_index].telemetry.angle_lp_deg_tenths)
        );
    }
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
    app->teach.playback_repeat = false;
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
    app->teach.playback_repeat = false;
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

// Wraps a sample index across the recorded clip.
static uint16_t control_testing_wrap_sample_index(int32_t sample_index, uint16_t sample_count) {
    int32_t wrapped_index = 0;

    hard_assert(sample_count > 0u);

    wrapped_index = sample_index % (int32_t)sample_count;
    if (wrapped_index < 0) {
        wrapped_index += (int32_t)sample_count;
    }
    return (uint16_t)wrapped_index;
}

// Mirrors a sample index at the clip boundaries.
static uint16_t control_testing_mirror_sample_index(int32_t sample_index, uint16_t sample_count) {
    int32_t last_index = 0;

    hard_assert(sample_count > 0u);

    if (sample_count == 1u) {
        return 0u;
    }

    last_index = (int32_t)sample_count - 1;
    while (sample_index < 0 || sample_index > last_index) {
        if (sample_index < 0) {
            sample_index = -sample_index;
        }
        if (sample_index > last_index) {
            sample_index = last_index - (sample_index - last_index);
        }
    }
    return (uint16_t)sample_index;
}

// Reads one sample angle in degrees with mirrored or wrapped edges.
static float control_testing_get_sample_angle_deg(
    const ControlTestingTeachSample *samples,
    uint16_t sample_count,
    int32_t sample_index,
    size_t servo_index,
    bool wrap
) {
    uint16_t resolved_index = 0u;

    hard_assert(samples != NULL);
    hard_assert(servo_index < CONTROL_TESTING_SERVO_COUNT);
    hard_assert(sample_count > 0u);

    resolved_index = wrap
        ? control_testing_wrap_sample_index(sample_index, sample_count)
        : control_testing_mirror_sample_index(sample_index, sample_count);
    return control_testing_deg_tenths_to_f32(samples[resolved_index].servo_angle_deg_tenths[servo_index]);
}

// Generates smooth playback waypoints for a fixed-sample clip.
static void control_testing_prepare_smooth_samples(
    ControlTestingApp *app,
    const ControlTestingTeachSample *samples,
    uint16_t sample_count,
    ControlTestingTeachSmoothSample *smooth_samples,
    bool wrap
) {
    static const float g_sg_coefficients[5] = {-3.0f, 12.0f, 17.0f, 12.0f, -3.0f};
    const float dt_s = (float)CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS / 1000.0f;
    const float dt_sq_s = dt_s * dt_s;

    hard_assert(app != NULL);
    hard_assert(samples != NULL);
    hard_assert(smooth_samples != NULL);
    hard_assert(sample_count >= 3u);

    for (uint16_t sample_index = 0u; sample_index < sample_count; sample_index++) {
        for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
            float smoothed_position_deg = 0.0f;

            if (!wrap && (sample_index == 0u || sample_index + 1u >= sample_count)) {
                smoothed_position_deg = control_testing_deg_tenths_to_f32(
                    samples[sample_index].servo_angle_deg_tenths[servo_index]
                );
            } else {
                for (int32_t offset = -2; offset <= 2; offset++) {
                    smoothed_position_deg += g_sg_coefficients[offset + 2]
                        * control_testing_get_sample_angle_deg(
                            samples,
                            sample_count,
                            (int32_t)sample_index + offset,
                            servo_index,
                            wrap
                        );
                }
                smoothed_position_deg /= 35.0f;
            }

            smooth_samples[sample_index].position_deg[servo_index] =
                control_testing_clamp_servo_hold_target_deg(
                    &app->servos[servo_index],
                    smoothed_position_deg
                );
        }
    }

    for (uint16_t sample_index = 0u; sample_index < sample_count; sample_index++) {
        for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
            float velocity_deg_per_s = 0.0f;
            float acceleration_deg_per_s2 = 0.0f;

            if (!wrap && (sample_index == 0u || sample_index + 1u >= sample_count)) {
                smooth_samples[sample_index].velocity_deg_per_s[servo_index] = 0.0f;
                smooth_samples[sample_index].acceleration_deg_per_s2[servo_index] = 0.0f;
                continue;
            }

            uint16_t prev_index = wrap
                ? control_testing_wrap_sample_index((int32_t)sample_index - 1, sample_count)
                : (uint16_t)(sample_index - 1u);
            uint16_t next_index = wrap
                ? control_testing_wrap_sample_index((int32_t)sample_index + 1, sample_count)
                : (uint16_t)(sample_index + 1u);
            float prev_position_deg = smooth_samples[prev_index].position_deg[servo_index];
            float current_position_deg = smooth_samples[sample_index].position_deg[servo_index];
            float next_position_deg = smooth_samples[next_index].position_deg[servo_index];
            float left_delta_deg = current_position_deg - prev_position_deg;
            float right_delta_deg = next_position_deg - current_position_deg;

            velocity_deg_per_s = (next_position_deg - prev_position_deg) / (2.0f * dt_s);
            if ((left_delta_deg * right_delta_deg) <= 0.0f) {
                velocity_deg_per_s = 0.0f;
            }

            acceleration_deg_per_s2 =
                (next_position_deg - (2.0f * current_position_deg) + prev_position_deg) / dt_sq_s;

            smooth_samples[sample_index].velocity_deg_per_s[servo_index] = velocity_deg_per_s;
            smooth_samples[sample_index].acceleration_deg_per_s2[servo_index] = acceleration_deg_per_s2;
        }
    }
}

// Generates smooth playback waypoints for the current recorded clip.
static void control_testing_prepare_smooth_playback(ControlTestingApp *app) {
    hard_assert(app != NULL);
    hard_assert(app->teach.sample_count >= 3u);

    control_testing_prepare_smooth_samples(
        app,
        app->teach.samples,
        app->teach.sample_count,
        app->teach.smooth_samples,
        app->teach.playback_repeat
    );
}

// Resolves the effective playback profile and prepares any derived state.
static void control_testing_prepare_playback_profile(ControlTestingApp *app) {
    hard_assert(app != NULL);

    app->teach.playback_active_profile = app->teach.playback_requested_profile;
    if (
        app->teach.playback_active_profile == CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_SMOOTH
        && app->teach.sample_count < 3u
    ) {
        app->teach.playback_active_profile = CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_LINEAR;
    }

    if (app->teach.playback_active_profile == CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_SMOOTH) {
        control_testing_prepare_smooth_playback(app);
    }
}

// Updates the selected playback profile and applies it immediately if playback is running.
static void control_testing_set_playback_profile(
    ControlTestingApp *app,
    ControlTestingTeachPlaybackProfile profile
) {
    absolute_time_t now = get_absolute_time();

    hard_assert(app != NULL);

    app->teach.playback_requested_profile = profile;
    app->teach.playback_active_profile = profile;

    if (app->teach.mode != CONTROL_TESTING_TEACH_MODE_PLAYING) {
        return;
    }

    control_testing_prepare_playback_profile(app);
    control_testing_apply_playback_sample(app, app->teach.playback_index);
    control_testing_apply_playback_segment_target(app, now);
}

// Applies one recorded pose to all hold targets.
static void control_testing_apply_teach_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSample *sample
) {
    hard_assert(app != NULL);
    hard_assert(sample != NULL);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        app->servos[servo_index].settings.hold_target_deg = control_testing_clamp_servo_hold_target_deg(
            &app->servos[servo_index],
            control_testing_deg_tenths_to_f32(sample->servo_angle_deg_tenths[servo_index])
        );
    }
}

// Applies the effective playback sample for the active playback profile.
static void control_testing_apply_playback_sample(
    ControlTestingApp *app,
    uint16_t sample_index
) {
    hard_assert(app != NULL);
    hard_assert(sample_index < app->teach.sample_count);

    if (app->teach.playback_active_profile != CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_SMOOTH) {
        control_testing_apply_teach_sample(app, &app->teach.samples[sample_index]);
        return;
    }

    control_testing_apply_smooth_playback_sample(
        app,
        app->teach.smooth_samples,
        app->teach.sample_count,
        sample_index
    );
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
            control_testing_clamp_servo_hold_target_deg(&app->servos[servo_index], interpolated_deg);
    }
}

// Returns whether the current playback sample has a segment to evaluate.
static bool control_testing_playback_has_interpolated_segment(const ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->teach.playback_active_profile == CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_STEP) {
        return false;
    }
    if (app->teach.sample_count == 0u) {
        return false;
    }
    if (
        app->teach.playback_active_profile == CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_SMOOTH
        && app->teach.playback_repeat
    ) {
        return true;
    }
    return app->teach.playback_index + 1u < app->teach.sample_count;
}

// Returns the end sample index for the active playback segment.
static uint16_t control_testing_playback_segment_end_index(const ControlTestingApp *app) {
    hard_assert(app != NULL);
    hard_assert(control_testing_playback_has_interpolated_segment(app));

    if (
        app->teach.playback_active_profile == CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_SMOOTH
        && app->teach.playback_repeat
        && app->teach.playback_index + 1u >= app->teach.sample_count
    ) {
        return 0u;
    }
    return app->teach.playback_index + 1u;
}

// Evaluates one quintic Hermite segment over a fixed teach sample interval.
static float control_testing_evaluate_quintic_hermite_segment(
    float start_pos_deg,
    float start_vel_deg_per_s,
    float start_accel_deg_per_s2,
    float end_pos_deg,
    float end_vel_deg_per_s,
    float end_accel_deg_per_s2,
    uint32_t elapsed_ms
) {
    const float segment_duration_s = (float)CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS / 1000.0f;
    float u = 0.0f;
    float u2 = 0.0f;
    float u3 = 0.0f;
    float u4 = 0.0f;
    float u5 = 0.0f;
    float h0 = 0.0f;
    float h1 = 0.0f;
    float h2 = 0.0f;
    float h3 = 0.0f;
    float h4 = 0.0f;
    float h5 = 0.0f;

    if (elapsed_ms >= CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS) {
        u = 1.0f;
    } else {
        u = (float)elapsed_ms / (float)CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS;
    }

    u2 = u * u;
    u3 = u2 * u;
    u4 = u3 * u;
    u5 = u4 * u;

    h0 = 1.0f - (10.0f * u3) + (15.0f * u4) - (6.0f * u5);
    h1 = u - (6.0f * u3) + (8.0f * u4) - (3.0f * u5);
    h2 = (0.5f * u2) - (1.5f * u3) + (1.5f * u4) - (0.5f * u5);
    h3 = (10.0f * u3) - (15.0f * u4) + (6.0f * u5);
    h4 = (-4.0f * u3) + (7.0f * u4) - (3.0f * u5);
    h5 = (0.5f * u3) - u4 + (0.5f * u5);

    return (h0 * start_pos_deg)
        + (h1 * segment_duration_s * start_vel_deg_per_s)
        + (h2 * segment_duration_s * segment_duration_s * start_accel_deg_per_s2)
        + (h3 * end_pos_deg)
        + (h4 * segment_duration_s * end_vel_deg_per_s)
        + (h5 * segment_duration_s * segment_duration_s * end_accel_deg_per_s2);
}

// Applies one smoothed sample to all hold targets.
static void control_testing_apply_smooth_playback_sample(
    ControlTestingApp *app,
    const ControlTestingTeachSmoothSample *smooth_samples,
    uint16_t sample_count,
    uint16_t sample_index
) {
    hard_assert(app != NULL);
    hard_assert(smooth_samples != NULL);
    hard_assert(sample_index < sample_count);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        app->servos[servo_index].settings.hold_target_deg = control_testing_clamp_servo_hold_target_deg(
            &app->servos[servo_index],
            smooth_samples[sample_index].position_deg[servo_index]
        );
    }
}

// Blends hold targets across one smooth playback segment.
static void control_testing_apply_smooth_playback_segment(
    ControlTestingApp *app,
    const ControlTestingTeachSmoothSample *smooth_samples,
    uint16_t sample_count,
    uint16_t start_index,
    uint16_t end_index,
    uint32_t elapsed_ms
) {
    hard_assert(app != NULL);
    hard_assert(smooth_samples != NULL);
    hard_assert(start_index < sample_count);
    hard_assert(end_index < sample_count);

    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        float interpolated_deg = control_testing_evaluate_quintic_hermite_segment(
            smooth_samples[start_index].position_deg[servo_index],
            smooth_samples[start_index].velocity_deg_per_s[servo_index],
            smooth_samples[start_index].acceleration_deg_per_s2[servo_index],
            smooth_samples[end_index].position_deg[servo_index],
            smooth_samples[end_index].velocity_deg_per_s[servo_index],
            smooth_samples[end_index].acceleration_deg_per_s2[servo_index],
            elapsed_ms
        );

        app->servos[servo_index].settings.hold_target_deg =
            control_testing_clamp_servo_hold_target_deg(&app->servos[servo_index], interpolated_deg);
    }
}

// Applies the current segment target for the active playback profile.
static void control_testing_apply_playback_segment_target(
    ControlTestingApp *app,
    absolute_time_t now
) {
    uint16_t end_index = 0u;
    int64_t elapsed_us = 0;
    uint32_t elapsed_ms = 0u;

    hard_assert(app != NULL);

    if (!control_testing_playback_has_interpolated_segment(app)) {
        return;
    }

    end_index = control_testing_playback_segment_end_index(app);
    elapsed_us = absolute_time_diff_us(app->teach.playback_segment_started_at, now);
    if (elapsed_us > 0) {
        elapsed_ms = (uint32_t)(elapsed_us / 1000);
    }

    if (app->teach.playback_active_profile == CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_LINEAR) {
        control_testing_apply_interpolated_teach_sample(
            app,
            &app->teach.samples[app->teach.playback_index],
            &app->teach.samples[end_index],
            elapsed_ms
        );
        return;
    }

    control_testing_apply_smooth_playback_segment(
        app,
        app->teach.smooth_samples,
        app->teach.sample_count,
        app->teach.playback_index,
        end_index,
        elapsed_ms
    );
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
    bool repeat,
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

    control_testing_capture_current_pose_as_hold_targets(app);
    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        servo_set_control_mode(&app->servos[servo_index], CONTROL_MODE_HOLD);
    }

    app->teach.mode = CONTROL_TESTING_TEACH_MODE_PLAYING;
    app->teach.waiting_for_alignment = false;
    app->teach.playback_index = 0u;
    app->teach.playback_repeat = repeat;
    control_testing_prepare_playback_profile(app);
    app->teach.playback_segment_started_at = get_absolute_time();
    control_testing_apply_playback_sample(app, 0u);
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

    control_testing_apply_playback_segment_target(app, now);

    if (!time_reached(app->teach.next_sample_at)) {
        return;
    }

    app->teach.playback_index++;

    if (app->teach.playback_index >= app->teach.sample_count) {
        if (!app->teach.playback_repeat) {
            control_testing_stop_playback(app);
            return;
        }
        app->teach.playback_index = 0u;
    }

    app->teach.playback_segment_started_at = now;
    control_testing_apply_playback_sample(app, app->teach.playback_index);

    if (!app->teach.playback_repeat && app->teach.playback_index + 1u >= app->teach.sample_count) {
        control_testing_stop_playback(app);
        return;
    }

    app->teach.next_sample_at = make_timeout_time_ms(CONTROL_TESTING_TEACH_SAMPLE_PERIOD_MS);
}

// Begins one blended gait transition from the current commanded pose.
static void control_testing_gait_begin_transition(
    ControlTestingApp *app,
    ControlTestingGaitMode mode,
    const float target_pose_deg[CONTROL_TESTING_SERVO_COUNT]
) {
    hard_assert(app != NULL);
    hard_assert(target_pose_deg != NULL);

    control_testing_copy_pose(app->gait.segment_start_pose_deg, app->gait.current_pose_deg);
    control_testing_copy_pose(app->gait.segment_target_pose_deg, target_pose_deg);
    app->gait.transition_total_samples = CONTROL_TESTING_GAIT_TRANSITION_SAMPLE_COUNT;
    app->gait.transition_sample_index = 0u;
    app->gait.mode = mode;
}

// Stops gait cleanly before another subsystem takes over.
static void control_testing_cancel_gait_for_override(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->gait.mode == CONTROL_TESTING_GAIT_MODE_IDLE) {
        return;
    }

    app->gait.mode = CONTROL_TESTING_GAIT_MODE_IDLE;
    app->gait.phase_u = 0.0f;
    app->gait.transition_total_samples = 0u;
    app->gait.transition_sample_index = 0u;
    control_testing_capture_measured_pose(app, app->gait.current_pose_deg);
    control_testing_copy_pose(app->gait.segment_start_pose_deg, app->gait.current_pose_deg);
    control_testing_copy_pose(app->gait.segment_target_pose_deg, app->gait.current_pose_deg);
    control_testing_copy_pose(app->gait.reference_pose_deg, app->gait.current_pose_deg);
}

// Stops active teach playback or recording before gait takes ownership.
static void control_testing_cancel_teach_for_gait(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->teach.mode == CONTROL_TESTING_TEACH_MODE_PLAYING) {
        control_testing_stop_playback(app);
    } else if (app->teach.mode == CONTROL_TESTING_TEACH_MODE_RECORDING) {
        control_testing_stop_recording(app);
    }
}

// Starts the canonical gait from phase zero.
static bool control_testing_start_gait(
    ControlTestingApp *app,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingGaitPathTarget start_target = {0};
    float solved_pose_deg[CONTROL_TESTING_SERVO_COUNT] = {0.0f, 0.0f, 0.0f};
    float measured_pose_deg[CONTROL_TESTING_SERVO_COUNT] = {0.0f, 0.0f, 0.0f};
    float start_pose_deg[CONTROL_TESTING_SERVO_COUNT] = {0.0f, 0.0f, 0.0f};

    hard_assert(app != NULL);
    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    *out_error_code = NULL;
    *out_error_message = NULL;

    control_testing_capture_measured_pose(app, measured_pose_deg);
    for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
        const Servo *servo = control_testing_get_servo_const(app, (uint8_t)servo_index);

        hard_assert(servo != NULL);
        start_pose_deg[servo_index] = servo_clamp_target_deg(
            servo,
            control_testing_clamp_hold_target_deg(measured_pose_deg[servo_index])
        );
    }

    control_testing_gait_compute_path_target(0.0f, &start_target);
    if (!control_testing_gait_solve_ik(
            app,
            start_target.x_mm,
            start_target.y_mm,
            start_target.z_mm,
            start_pose_deg,
            solved_pose_deg
        )) {
        *out_error_code = "ik_unreachable";
        *out_error_message = "path start is outside the reachable workspace";
        return false;
    }

    control_testing_cancel_teach_for_gait(app);
    control_testing_gait_apply_hold_pose(app, start_pose_deg);
    control_testing_copy_pose(app->gait.reference_pose_deg, app->gait.current_pose_deg);
    app->gait.phase_u = 0.0f;
    app->command_state = CONTROL_TESTING_COMMAND_STATE_CUSTOM;
    control_testing_gait_begin_transition(
        app,
        CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_PATH,
        solved_pose_deg
    );
    app->next_gait_at = get_absolute_time();
    return true;
}

// Returns the leg to the assembly pose and then idles.
static void control_testing_pause_gait(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->gait.mode != CONTROL_TESTING_GAIT_MODE_RUNNING
        && app->gait.mode != CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_PATH) {
        return;
    }

    app->command_state = CONTROL_TESTING_COMMAND_STATE_CUSTOM;
    control_testing_gait_begin_transition(
        app,
        CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_ASSEMBLY,
        g_control_testing_gait_assembly_pose_deg
    );
    app->next_gait_at = get_absolute_time();
}

// Advances the gait transition or playback state machine.
static void control_testing_update_gait(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (app->gait.mode == CONTROL_TESTING_GAIT_MODE_IDLE) {
        return;
    }
    if (!time_reached(app->next_gait_at)) {
        return;
    }

    app->next_gait_at = make_timeout_time_ms(CONTROL_TESTING_GAIT_UPDATE_PERIOD_MS);

    if (app->gait.mode == CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_PATH
        || app->gait.mode == CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_ASSEMBLY) {
        float interpolated_pose_deg[CONTROL_TESTING_SERVO_COUNT] = {0.0f, 0.0f, 0.0f};

        if (app->gait.transition_total_samples == 0u) {
            return;
        }

        app->gait.transition_sample_index++;
        for (size_t servo_index = 0u; servo_index < CONTROL_TESTING_SERVO_COUNT; servo_index++) {
            float start_deg = app->gait.segment_start_pose_deg[servo_index];
            float target_deg = app->gait.segment_target_pose_deg[servo_index];
            float blend = (float)app->gait.transition_sample_index / (float)app->gait.transition_total_samples;

            interpolated_pose_deg[servo_index] = start_deg + ((target_deg - start_deg) * blend);
        }
        control_testing_gait_apply_hold_pose(app, interpolated_pose_deg);
        control_testing_copy_pose(app->gait.reference_pose_deg, app->gait.current_pose_deg);

        if (app->gait.transition_sample_index < app->gait.transition_total_samples) {
            return;
        }

        app->gait.transition_total_samples = 0u;
        app->gait.transition_sample_index = 0u;
        if (app->gait.mode == CONTROL_TESTING_GAIT_MODE_TRANSITION_TO_PATH) {
            app->gait.mode = CONTROL_TESTING_GAIT_MODE_RUNNING;
            app->gait.phase_u = 0.0f;
            return;
        }

        app->gait.mode = CONTROL_TESTING_GAIT_MODE_IDLE;
        app->gait.phase_u = 0.0f;
        control_testing_copy_pose(app->gait.segment_start_pose_deg, app->gait.current_pose_deg);
        control_testing_copy_pose(app->gait.segment_target_pose_deg, app->gait.current_pose_deg);
        return;
    }

    if (app->gait.mode == CONTROL_TESTING_GAIT_MODE_RUNNING) {
        ControlTestingGaitPathTarget target = {0};
        float solved_pose_deg[CONTROL_TESTING_SERVO_COUNT] = {0.0f, 0.0f, 0.0f};
        float phase_step = ((float)CONTROL_TESTING_GAIT_UPDATE_PERIOD_MS / 1000.0f)
            / control_testing_gait_cycle_time_s(app->gait.speed_mode);

        control_testing_gait_compute_path_target(app->gait.phase_u, &target);
        if (control_testing_gait_solve_ik(
                app,
                target.x_mm,
                target.y_mm,
                target.z_mm,
                app->gait.reference_pose_deg,
                solved_pose_deg
            )) {
            control_testing_gait_apply_hold_pose(app, solved_pose_deg);
            control_testing_copy_pose(app->gait.reference_pose_deg, app->gait.current_pose_deg);
        }

        app->gait.phase_u = control_testing_wrap_phase_u(app->gait.phase_u + phase_step);
    }
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
    if (param->user_data == CONTROL_TESTING_APP_PARAM_GAIT_SPEED_MODE) {
        *out_value = DEVLINK_SERIAL_VALUE_U8(app->gait.speed_mode);
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
    if (param->user_data == CONTROL_TESTING_APP_PARAM_GAIT_SPEED_MODE) {
        app->gait.speed_mode = (uint8_t)value.u32_value;
        return true;
    }
    if (!control_testing_decode_servo_user_data(param->user_data, &servo_index, &local_param_id)) {
        *out_error_code = "unknown_param";
        *out_error_message = "unknown parameter";
        return false;
    }

    if (app->gait.mode != CONTROL_TESTING_GAIT_MODE_IDLE
        && (local_param_id == CONTROL_TESTING_SERVO_PARAM_MOTOR_STATE
            || local_param_id == CONTROL_TESTING_SERVO_PARAM_MOTOR_DRIVE_PCT
            || local_param_id == CONTROL_TESTING_SERVO_PARAM_CONTROL_MODE
            || local_param_id == CONTROL_TESTING_SERVO_PARAM_HOLD_TARGET_DEG)) {
        control_testing_cancel_gait_for_override(app);
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
            servo->settings.hold_target_deg = control_testing_clamp_servo_hold_target_deg(
                servo,
                value.f32_value
            );
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

    control_testing_cancel_gait_for_override(app);
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

    control_testing_cancel_gait_for_override(app);
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

    control_testing_cancel_gait_for_override(app);
    if (!control_testing_start_playback(app, false, out_error_code, out_error_message)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Starts teach playback from recorded samples in a loop.
static DevlinkSerialCommandStatus handle_cmd_teach_play_repeat(
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

    control_testing_cancel_gait_for_override(app);
    if (!control_testing_start_playback(app, true, out_error_code, out_error_message)) {
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

    control_testing_cancel_gait_for_override(app);
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

    control_testing_cancel_gait_for_override(app);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Selects the legacy linear playback profile.
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

    control_testing_cancel_gait_for_override(app);
    control_testing_set_playback_profile(app, CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_LINEAR);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Selects the legacy step playback profile.
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

    control_testing_cancel_gait_for_override(app);
    control_testing_set_playback_profile(app, CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_STEP);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Selects step playback explicitly.
static DevlinkSerialCommandStatus handle_cmd_teach_play_profile_step(
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

    control_testing_cancel_gait_for_override(app);
    control_testing_set_playback_profile(app, CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_STEP);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Selects linear playback explicitly.
static DevlinkSerialCommandStatus handle_cmd_teach_play_profile_linear(
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

    control_testing_cancel_gait_for_override(app);
    control_testing_set_playback_profile(app, CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_LINEAR);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Selects smooth playback explicitly.
static DevlinkSerialCommandStatus handle_cmd_teach_play_profile_smooth(
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

    control_testing_cancel_gait_for_override(app);
    control_testing_set_playback_profile(app, CONTROL_TESTING_TEACH_PLAYBACK_PROFILE_SMOOTH);
    if (!control_testing_write_teach_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Starts the gait transition from the current pose to the path start.
static DevlinkSerialCommandStatus handle_cmd_gait_play(
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

    if (app->gait.mode == CONTROL_TESTING_GAIT_MODE_IDLE
        && !control_testing_start_gait(app, out_error_code, out_error_message)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    if (!control_testing_write_gait_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Returns the gait to the assembly pose.
static DevlinkSerialCommandStatus handle_cmd_gait_pause(
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

    control_testing_pause_gait(app);
    if (!control_testing_write_gait_status_result(out_result_json, out_result_json_size, app)) {
        return DEVLINK_SERIAL_COMMAND_ERROR;
    }
    return DEVLINK_SERIAL_COMMAND_OK_WITH_RESULT;
}

// Reports current gait status.
static DevlinkSerialCommandStatus handle_cmd_gait_status(
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

    if (!control_testing_write_gait_status_result(out_result_json, out_result_json_size, app)) {
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

    control_testing_update_gait(app);
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
