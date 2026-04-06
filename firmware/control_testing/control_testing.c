#include <stdbool.h>
#include <stdint.h>

#include "pico/stdlib.h"
#include "pico/time.h"

#include "adc_input.h"
#include "devlink_serial.h"
#include "motor_pwm.h"
#include "pio_uart_rx.h"
#include "position_hold.h"

#ifndef PICO_DEFAULT_LED_PIN
#error "control_testing requires PICO_DEFAULT_LED_PIN"
#endif

// Constants
#define COMMAND_RX_GPIO 3u          // board RX pin for incoming commands
#define COMMAND_BAUD 115200u        // UART speed
#define COMMAND_BUFFER_LEN 256u     // max line length for a single JSON command
#define COMMAND_IDLE_FLUSH_MS 80u   // how long to wait before flushing a partial line?
#define ADC_C_GPIO 28u              // adc_c potentiometer input
#define ADC_SAMPLE_PERIOD_MS 100u   // slower telemetry keeps devlink responsive at 115200 baud
#define ADC_AVERAGE_SAMPLE_COUNT 16u // how many adc samples to average
#define ADC_LP_ALPHA_DEFAULT_PCT 85u // default low pass alpha
#define ADC_LP_ALPHA_MIN_PCT 1u     // minimum low pass alpha
#define ADC_LP_ALPHA_MAX_PCT 100u   // maximum low pass alpha
#define ADC_C_RAW_MIN 0u            // minimum useful pot reading
#define ADC_C_RAW_MAX 4080u         // maximum useful pot reading
#define ADC_C_MIN_DEG 0u            // minimum reported angle
#define ADC_C_MAX_DEG 180u          // maximum reported angle
#define ADC_C_TENTHS_PER_DEG 10u    // one decimal place for reported angle
#define MOTOR_C_IN1_GPIO 22u        // motor_c driver input 1
#define MOTOR_C_IN2_GPIO 23u        // motor_c driver input 2
#define MOTOR_PWM_HZ 20000u         // motor pwm frequency
#define ANGLE_SOURCE_AVG 0u         // angle uses averaged adc
#define ANGLE_SOURCE_LP 1u          // angle uses low pass adc
#define ANGLE_SOURCE_BOTH 2u        // angle uses both averaged and low pass adc
#define MOTOR_STATE_COAST 0u        // motor output is released
#define MOTOR_STATE_BRAKE 1u        // motor output actively brakes
#define MOTOR_STATE_FORWARD 2u      // motor drives forward
#define MOTOR_STATE_REVERSE 3u      // motor drives reverse


// Parameter Ids
enum {
    PARAM_STATUS_LED_ON = 0,
    PARAM_FILTER_ALPHA_PCT,
    PARAM_ANGLE_SOURCE_MODE,
    PARAM_MOTOR_STATE,
    PARAM_MOTOR_DRIVE_PCT,
    PARAM_CONTROL_MODE,
    PARAM_HOLD_TARGET_DEG_TENTHS,
    PARAM_HOLD_DEADBAND_DEG_TENTHS,
    PARAM_HOLD_P_GAIN,
    PARAM_HOLD_MAX_DUTY,
};

// App State
typedef struct {
    bool status_led_on;
    AdcInput adc_c;
    MotorPwm motor_c;
    bool adc_lp_ready;
    uint8_t adc_lp_alpha_pct;
    uint8_t angle_source_mode;
    uint8_t motor_state;
    uint8_t motor_drive_pct;
    uint8_t control_mode;
    uint16_t hold_target_deg_tenths;
    uint16_t hold_deadband_deg_tenths;
    uint8_t hold_p_gain;
    uint8_t hold_max_duty;
    int16_t hold_output_pct;
    uint16_t adc_lp_raw;
    uint32_t adc_raw_sample_seq;
    uint32_t adc_avg_sample_seq;
    uint32_t adc_lp_sample_seq;
    uint32_t adc_angle_avg_sample_seq;
    uint32_t adc_angle_lp_sample_seq;
    uint32_t motor_sample_seq;
    uint32_t hold_sample_seq;
    absolute_time_t next_adc_sample_at;
} ControlTestingApp;

typedef struct {
    uint16_t deg;
    uint16_t raw;
} ControlTestingCalibrationPoint;

// Devlink Forward Declarations
// devlink calls these two functions when the host reads or writes a parameter.
// they are defined further down but declared here so the device descriptor can reference them.
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

// Devlink Stream Definitions
// each stream is a named channel of time-series data sent to the host for plotting.
// a stream has one or more fields, each with a name, type, and unit.
// for example the "adc" stream sends one U16 value called "adc_c_raw" with unit "adc".
// the host uses these definitions to label axes and group plots automatically.
static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_fields[] = {
    {"adc_c_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_avg_fields[] = {
    {"adc_c_avg_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_lp_fields[] = {
    {"adc_c_lp_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_angle_avg_fields[] = {
    {"adc_c_avg_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_angle_lp_fields[] = {
    {"adc_c_lp_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
};

// Motor Stream
static const DevlinkSerialStreamFieldDescriptor g_control_testing_motor_fields[] = {
    {"motor_state", DEVLINK_SERIAL_TYPE_U8, "state"},
    {"motor_drive_pct", DEVLINK_SERIAL_TYPE_U8, "pct"},
};

// Position Hold Stream
static const DevlinkSerialStreamFieldDescriptor g_control_testing_hold_fields[] = {
    {"hold_target_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_actual_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_error_deg", DEVLINK_SERIAL_TYPE_F32, "deg"},
    {"hold_output_pct", DEVLINK_SERIAL_TYPE_I16, "pct"},
};

// Devlink Stream Registry
// this array registers all streams with the device. the host discovers these at startup
// and creates a plot for each one. order matters — streams are referenced by index elsewhere.
static const DevlinkSerialStreamDescriptor g_control_testing_streams[] = {
    {"control_testing.adc", g_control_testing_adc_fields, count_of(g_control_testing_adc_fields)},
    {"control_testing.adc_avg", g_control_testing_adc_avg_fields, count_of(g_control_testing_adc_avg_fields)},
    {"control_testing.adc_lp", g_control_testing_adc_lp_fields, count_of(g_control_testing_adc_lp_fields)},
    {"control_testing.angle_avg", g_control_testing_angle_avg_fields, count_of(g_control_testing_angle_avg_fields)},
    {"control_testing.angle_lp", g_control_testing_angle_lp_fields, count_of(g_control_testing_angle_lp_fields)},
    {"control_testing.motor", g_control_testing_motor_fields, count_of(g_control_testing_motor_fields)},
    {"control_testing.hold", g_control_testing_hold_fields, count_of(g_control_testing_hold_fields)},
};

// Devlink Parameter Definitions
// each param is a named value the host can read and write, shown as a slider or toggle in the UI.
// fields: name, type, access (RO or RW), default, has_bounds, min, max, user_data (our enum ID).
// devlink enforces min/max bounds before calling our setter, so we don't need to range-check.
static const DevlinkSerialParamDescriptor g_control_testing_params[] = {
    {
        "status_led.on",
        DEVLINK_SERIAL_TYPE_BOOL,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_BOOL(false),
        false,
        DEVLINK_SERIAL_VALUE_BOOL(false),
        DEVLINK_SERIAL_VALUE_BOOL(true),
        PARAM_STATUS_LED_ON,
    },
    {
        "filter.alpha_pct",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(ADC_LP_ALPHA_DEFAULT_PCT),
        true,
        DEVLINK_SERIAL_VALUE_U8(ADC_LP_ALPHA_MIN_PCT),
        DEVLINK_SERIAL_VALUE_U8(ADC_LP_ALPHA_MAX_PCT),
        PARAM_FILTER_ALPHA_PCT,
    },
    {
        "angle.source_mode",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(ANGLE_SOURCE_BOTH),
        true,
        DEVLINK_SERIAL_VALUE_U8(ANGLE_SOURCE_AVG),
        DEVLINK_SERIAL_VALUE_U8(ANGLE_SOURCE_BOTH),
        PARAM_ANGLE_SOURCE_MODE,
    },
    {
        "motor.state",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(MOTOR_STATE_COAST),
        true,
        DEVLINK_SERIAL_VALUE_U8(MOTOR_STATE_COAST),
        DEVLINK_SERIAL_VALUE_U8(MOTOR_STATE_REVERSE),
        PARAM_MOTOR_STATE,
    },
    {
        "motor.drive_pct",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(0u),
        true,
        DEVLINK_SERIAL_VALUE_U8(0u),
        DEVLINK_SERIAL_VALUE_U8(100u),
        PARAM_MOTOR_DRIVE_PCT,
    },
    {
        "control.mode",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(CONTROL_MODE_MANUAL),
        true,
        DEVLINK_SERIAL_VALUE_U8(CONTROL_MODE_MANUAL),
        DEVLINK_SERIAL_VALUE_U8(CONTROL_MODE_HOLD),
        PARAM_CONTROL_MODE,
    },
    {
        "hold.target_deg_tenths",
        DEVLINK_SERIAL_TYPE_U16,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U16(HOLD_TARGET_DEFAULT),
        true,
        DEVLINK_SERIAL_VALUE_U16(HOLD_TARGET_MIN),
        DEVLINK_SERIAL_VALUE_U16(HOLD_TARGET_MAX),
        PARAM_HOLD_TARGET_DEG_TENTHS,
    },
    {
        "hold.deadband_deg_tenths",
        DEVLINK_SERIAL_TYPE_U16,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U16(HOLD_DEADBAND_DEFAULT),
        true,
        DEVLINK_SERIAL_VALUE_U16(HOLD_DEADBAND_MIN),
        DEVLINK_SERIAL_VALUE_U16(HOLD_DEADBAND_MAX),
        PARAM_HOLD_DEADBAND_DEG_TENTHS,
    },
    {
        "hold.p_gain",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(HOLD_P_GAIN_DEFAULT),
        true,
        DEVLINK_SERIAL_VALUE_U8(HOLD_P_GAIN_MIN),
        DEVLINK_SERIAL_VALUE_U8(HOLD_P_GAIN_MAX),
        PARAM_HOLD_P_GAIN,
    },
    {
        "hold.max_duty",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(HOLD_MAX_DUTY_DEFAULT),
        true,
        DEVLINK_SERIAL_VALUE_U8(0u),
        DEVLINK_SERIAL_VALUE_U8(100u),
        PARAM_HOLD_MAX_DUTY,
    },
};

static const ControlTestingCalibrationPoint g_control_testing_calibration_points[] = {
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

// Devlink Device Descriptor
// this is the top-level object that ties everything together: device name, firmware version,
// the list of streams and params, and the getter/setter callbacks. devlink sends this to
// the host at startup so it knows the full capabilities of this device.
static const DevlinkSerialDeviceDescriptor g_control_testing_device = {
    .device = "control_testing",
    .firmware = "0.6.0",
    .commands = NULL,
    .command_count = 0u,
    .streams = g_control_testing_streams,
    .stream_count = count_of(g_control_testing_streams),
    .params = g_control_testing_params,
    .param_count = count_of(g_control_testing_params),
    .param_getter = control_testing_param_get,
    .param_setter = control_testing_param_set,
};

// LED Helpers
// writes current app state to LED
static void control_testing_apply_status_led(const ControlTestingApp *app) {
    hard_assert(app != NULL);
    gpio_put(PICO_DEFAULT_LED_PIN, app->status_led_on);
}

// Motor Helpers
// writes current app state to the motor driver
static void control_testing_apply_motor_output(ControlTestingApp *app) {
    hard_assert(app != NULL);

    switch (app->motor_state) {
        case MOTOR_STATE_BRAKE:
            motor_pwm_brake(&app->motor_c);
            break;
        case MOTOR_STATE_FORWARD:
            motor_pwm_set_forward_duty(&app->motor_c, app->motor_drive_pct);
            break;
        case MOTOR_STATE_REVERSE:
            motor_pwm_set_reverse_duty(&app->motor_c, app->motor_drive_pct);
            break;
        case MOTOR_STATE_COAST:
        default:
            motor_pwm_coast(&app->motor_c);
            break;
    }
}

// ADC Helpers
// sets up the LED GPIO as output
// also sets up adc_c, motor_c, and sample timing
static void control_testing_init(ControlTestingApp *app) {
    absolute_time_t now = get_absolute_time();

    hard_assert(app != NULL);

    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);

    adc_input_system_init();
    adc_input_init(&app->adc_c, ADC_C_GPIO);
    motor_pwm_init(&app->motor_c, "motor_c", MOTOR_C_IN1_GPIO, MOTOR_C_IN2_GPIO, MOTOR_PWM_HZ);

    app->status_led_on = false;
    app->adc_lp_ready = false;
    app->adc_lp_alpha_pct = ADC_LP_ALPHA_DEFAULT_PCT;
    app->angle_source_mode = ANGLE_SOURCE_BOTH;
    app->motor_state = MOTOR_STATE_COAST;
    app->motor_drive_pct = 0u;
    app->control_mode = CONTROL_MODE_MANUAL;
    app->hold_target_deg_tenths = HOLD_TARGET_DEFAULT;
    app->hold_deadband_deg_tenths = HOLD_DEADBAND_DEFAULT;
    app->hold_p_gain = HOLD_P_GAIN_DEFAULT;
    app->hold_max_duty = HOLD_MAX_DUTY_DEFAULT;
    app->hold_output_pct = 0;
    app->adc_lp_raw = 0u;
    app->adc_raw_sample_seq = 0u;
    app->adc_avg_sample_seq = 0u;
    app->adc_lp_sample_seq = 0u;
    app->adc_angle_avg_sample_seq = 0u;
    app->adc_angle_lp_sample_seq = 0u;
    app->motor_sample_seq = 0u;
    app->hold_sample_seq = 0u;
    app->next_adc_sample_at = now;

    control_testing_apply_status_led(app);
    control_testing_apply_motor_output(app);
}

// Calibration Helpers
// clamps the raw adc value to the range we can actually use
static uint16_t control_testing_bound_adc_raw(uint16_t raw_value) {
    if (raw_value < ADC_C_RAW_MIN) {
        return ADC_C_RAW_MIN;
    }
    if (raw_value > ADC_C_RAW_MAX) {
        return ADC_C_RAW_MAX;
    }
    return raw_value;
}

// converts the bounded raw value into degrees using the measured calibration points
static uint16_t control_testing_adc_raw_to_deg_tenths(uint16_t raw_value) {
    const ControlTestingCalibrationPoint *upper_point = NULL;
    const ControlTestingCalibrationPoint *lower_point = NULL;
    uint32_t raw_span = 0u;
    uint32_t raw_offset = 0u;
    uint32_t deg_span = 0u;
    uint32_t interpolated_deg_tenths = 0u;

    raw_value = control_testing_bound_adc_raw(raw_value);

    if (raw_value >= g_control_testing_calibration_points[0].raw) {
        return (uint16_t)(g_control_testing_calibration_points[0].deg * ADC_C_TENTHS_PER_DEG);
    }
    if (raw_value <= g_control_testing_calibration_points[count_of(g_control_testing_calibration_points) - 1u].raw) {
        return (uint16_t)(
            g_control_testing_calibration_points[count_of(g_control_testing_calibration_points) - 1u].deg
            * ADC_C_TENTHS_PER_DEG
        );
    }

    for (size_t point_index = 0u; point_index + 1u < count_of(g_control_testing_calibration_points); point_index++) {
        upper_point = &g_control_testing_calibration_points[point_index];
        lower_point = &g_control_testing_calibration_points[point_index + 1u];

        if (raw_value <= upper_point->raw && raw_value >= lower_point->raw) {
            raw_span = (uint32_t)(upper_point->raw - lower_point->raw);
            raw_offset = (uint32_t)(upper_point->raw - raw_value);
            deg_span = (uint32_t)(lower_point->deg - upper_point->deg);
            interpolated_deg_tenths = (uint32_t)(upper_point->deg * ADC_C_TENTHS_PER_DEG)
                + ((raw_offset * deg_span * ADC_C_TENTHS_PER_DEG) + (raw_span / 2u)) / raw_span;
            return (uint16_t)interpolated_deg_tenths;
        }
    }

    return (uint16_t)(ADC_C_MAX_DEG * ADC_C_TENTHS_PER_DEG);
}

// converts internal tenths-of-a-degree values into float degrees for devlink
static float control_testing_deg_tenths_to_f32(uint16_t deg_tenths) {
    return (float)deg_tenths / (float)ADC_C_TENTHS_PER_DEG;
}

// Filter Helpers
// updates the low pass value using the averaged adc reading
static uint16_t control_testing_update_adc_lp(ControlTestingApp *app, uint16_t avg_raw_value) {
    uint32_t filtered_raw = 0u;
    uint32_t previous_weight = 0u;

    hard_assert(app != NULL);

    if (!app->adc_lp_ready) {
        app->adc_lp_raw = avg_raw_value;
        app->adc_lp_ready = true;
        return app->adc_lp_raw;
    }

    previous_weight = (uint32_t)(ADC_LP_ALPHA_MAX_PCT - app->adc_lp_alpha_pct);
    filtered_raw = ((uint32_t)app->adc_lp_alpha_pct * avg_raw_value)
        + (previous_weight * app->adc_lp_raw);
    app->adc_lp_raw = (uint16_t)((filtered_raw + 50u) / 100u);
    app->adc_lp_raw = control_testing_bound_adc_raw(app->adc_lp_raw);
    return app->adc_lp_raw;
}

// tells the firmware which angle stream or streams should be sent
static bool control_testing_should_emit_angle_avg(const ControlTestingApp *app) {
    hard_assert(app != NULL);
    return app->angle_source_mode == ANGLE_SOURCE_AVG || app->angle_source_mode == ANGLE_SOURCE_BOTH;
}

static bool control_testing_should_emit_angle_lp(const ControlTestingApp *app) {
    hard_assert(app != NULL);
    return app->angle_source_mode == ANGLE_SOURCE_LP || app->angle_source_mode == ANGLE_SOURCE_BOTH;
}

// Devlink Parameter Getter
// called by devlink when the host reads a parameter.
// we look up which param it is using the user_data enum ID, then return the current app value.
static bool control_testing_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
) {
    ControlTestingApp *app = (ControlTestingApp *)context;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_value != NULL);

    switch ((int)param->user_data) {
        case PARAM_STATUS_LED_ON:
            *out_value = DEVLINK_SERIAL_VALUE_BOOL(app->status_led_on);
            return true;
        case PARAM_FILTER_ALPHA_PCT:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->adc_lp_alpha_pct);
            return true;
        case PARAM_ANGLE_SOURCE_MODE:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->angle_source_mode);
            return true;
        case PARAM_MOTOR_STATE:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->motor_state);
            return true;
        case PARAM_MOTOR_DRIVE_PCT:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->motor_drive_pct);
            return true;
        case PARAM_CONTROL_MODE:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->control_mode);
            return true;
        case PARAM_HOLD_TARGET_DEG_TENTHS:
            *out_value = DEVLINK_SERIAL_VALUE_U16(app->hold_target_deg_tenths);
            return true;
        case PARAM_HOLD_DEADBAND_DEG_TENTHS:
            *out_value = DEVLINK_SERIAL_VALUE_U16(app->hold_deadband_deg_tenths);
            return true;
        case PARAM_HOLD_P_GAIN:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->hold_p_gain);
            return true;
        case PARAM_HOLD_MAX_DUTY:
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->hold_max_duty);
            return true;
        default:
            return false;
    }
}

// Devlink Parameter Setter
// called by devlink when the host writes a parameter.
// we store the new value in app state, then apply any side effects (e.g. updating motor output).
static bool control_testing_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    *out_error_code = NULL;
    *out_error_message = NULL;

    switch ((int)param->user_data) {
        case PARAM_STATUS_LED_ON:
            app->status_led_on = value.bool_value;
            control_testing_apply_status_led(app);
            return true;
        case PARAM_FILTER_ALPHA_PCT:
            app->adc_lp_alpha_pct = (uint8_t)value.u32_value;
            return true;
        case PARAM_ANGLE_SOURCE_MODE:
            app->angle_source_mode = (uint8_t)value.u32_value;
            return true;
        case PARAM_MOTOR_STATE:
            app->motor_state = (uint8_t)value.u32_value;
            control_testing_apply_motor_output(app);
            return true;
        case PARAM_MOTOR_DRIVE_PCT:
            app->motor_drive_pct = (uint8_t)value.u32_value;
            control_testing_apply_motor_output(app);
            return true;
        case PARAM_CONTROL_MODE:
            app->control_mode = (uint8_t)value.u32_value;
            if (app->control_mode == CONTROL_MODE_MANUAL) {
                app->motor_state = MOTOR_STATE_COAST;
                app->motor_drive_pct = 0u;
                app->hold_output_pct = 0;
                control_testing_apply_motor_output(app);
            }
            return true;
        case PARAM_HOLD_TARGET_DEG_TENTHS:
            app->hold_target_deg_tenths = (uint16_t)value.u32_value;
            return true;
        case PARAM_HOLD_DEADBAND_DEG_TENTHS:
            app->hold_deadband_deg_tenths = (uint16_t)value.u32_value;
            return true;
        case PARAM_HOLD_P_GAIN:
            app->hold_p_gain = (uint8_t)value.u32_value;
            return true;
        case PARAM_HOLD_MAX_DUTY:
            app->hold_max_duty = (uint8_t)value.u32_value;
            return true;
        default:
            *out_error_code = "unknown_param";
            *out_error_message = "unknown parameter";
            return false;
    }
}

// Devlink Sample Emission
// called every 100ms by the tick function. reads sensors, runs the controller,
// then sends each stream's current values to the host as a timestamped sample.
// devlink_serial_print_sample serializes the values as JSON over UART.
static void control_testing_emit_adc_sample(ControlTestingApp *app) {
    uint16_t raw_value = 0u;
    uint16_t avg_raw_value = 0u;
    uint16_t lp_raw_value = 0u;
    uint16_t angle_avg_deg_tenths = 0u;
    uint16_t angle_lp_deg_tenths = 0u;
    uint64_t sample_time_us = 0u;
    DevlinkSerialValue values[count_of(g_control_testing_adc_fields)];
    DevlinkSerialValue avg_values[count_of(g_control_testing_adc_avg_fields)];
    DevlinkSerialValue lp_values[count_of(g_control_testing_adc_lp_fields)];
    DevlinkSerialValue angle_avg_values[count_of(g_control_testing_angle_avg_fields)];
    DevlinkSerialValue angle_lp_values[count_of(g_control_testing_angle_lp_fields)];
    DevlinkSerialValue motor_values[count_of(g_control_testing_motor_fields)];

    hard_assert(app != NULL);

    raw_value = control_testing_bound_adc_raw(adc_input_read_raw(&app->adc_c));
    avg_raw_value = control_testing_bound_adc_raw(
        adc_input_read_average_raw(&app->adc_c, ADC_AVERAGE_SAMPLE_COUNT)
    );
    lp_raw_value = control_testing_update_adc_lp(app, avg_raw_value);
    angle_avg_deg_tenths = control_testing_adc_raw_to_deg_tenths(avg_raw_value);
    angle_lp_deg_tenths = control_testing_adc_raw_to_deg_tenths(lp_raw_value);

    if (app->control_mode == CONTROL_MODE_HOLD) {
        PositionHoldResult hold_result = position_hold_update(
            app->hold_target_deg_tenths,
            angle_lp_deg_tenths,
            app->hold_deadband_deg_tenths,
            app->hold_p_gain,
            app->hold_max_duty
        );
        app->motor_state = hold_result.motor_state;
        app->motor_drive_pct = hold_result.motor_drive_pct;
        app->hold_output_pct = hold_result.output_pct;
        control_testing_apply_motor_output(app);
    }

    sample_time_us = time_us_64();

    values[0] = DEVLINK_SERIAL_VALUE_U16(raw_value);
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[0],
        app->adc_raw_sample_seq++,
        sample_time_us,
        values
    );

    avg_values[0] = DEVLINK_SERIAL_VALUE_U16(avg_raw_value);
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[1],
        app->adc_avg_sample_seq++,
        sample_time_us,
        avg_values
    );

    lp_values[0] = DEVLINK_SERIAL_VALUE_U16(lp_raw_value);
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[2],
        app->adc_lp_sample_seq++,
        sample_time_us,
        lp_values
    );

    if (control_testing_should_emit_angle_avg(app)) {
        angle_avg_values[0] = DEVLINK_SERIAL_VALUE_F32(
            control_testing_deg_tenths_to_f32(angle_avg_deg_tenths)
        );
        devlink_serial_print_sample(
            &g_control_testing_device,
            &g_control_testing_streams[3],
            app->adc_angle_avg_sample_seq++,
            sample_time_us,
            angle_avg_values
        );
    }

    if (control_testing_should_emit_angle_lp(app)) {
        angle_lp_values[0] = DEVLINK_SERIAL_VALUE_F32(
            control_testing_deg_tenths_to_f32(angle_lp_deg_tenths)
        );
        devlink_serial_print_sample(
            &g_control_testing_device,
            &g_control_testing_streams[4],
            app->adc_angle_lp_sample_seq++,
            sample_time_us,
            angle_lp_values
        );
    }

    motor_values[0] = DEVLINK_SERIAL_VALUE_U8(app->motor_state);
    motor_values[1] = DEVLINK_SERIAL_VALUE_U8(app->motor_drive_pct);
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[5],
        app->motor_sample_seq++,
        sample_time_us,
        motor_values
    );

    if (app->control_mode == CONTROL_MODE_HOLD) {
        DevlinkSerialValue hold_values[count_of(g_control_testing_hold_fields)];
        int32_t error_deg_tenths = (int32_t)app->hold_target_deg_tenths - (int32_t)angle_lp_deg_tenths;

        hold_values[0] = DEVLINK_SERIAL_VALUE_F32(
            control_testing_deg_tenths_to_f32(app->hold_target_deg_tenths)
        );
        hold_values[1] = DEVLINK_SERIAL_VALUE_F32(
            control_testing_deg_tenths_to_f32(angle_lp_deg_tenths)
        );
        hold_values[2] = DEVLINK_SERIAL_VALUE_F32(
            (float)error_deg_tenths / (float)ADC_C_TENTHS_PER_DEG
        );
        hold_values[3] = DEVLINK_SERIAL_VALUE_I16(app->hold_output_pct);
        devlink_serial_print_sample(
            &g_control_testing_device,
            &g_control_testing_streams[6],
            app->hold_sample_seq++,
            sample_time_us,
            hold_values
        );
    }
}

static void control_testing_tick(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (!time_reached(app->next_adc_sample_at)) {
        return;
    }

    control_testing_emit_adc_sample(app);
    app->next_adc_sample_at = make_timeout_time_ms(ADC_SAMPLE_PERIOD_MS);
}

// Devlink Command Input
// reads bytes from the PIO UART, assembles them into lines, and hands complete lines
// to devlink for parsing. devlink matches the JSON command to a param get/set or custom
// command and calls our callbacks. also handles idle-flush for partial lines.
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
        DevlinkSerialLineReadStatus read_status = devlink_serial_line_buffer_push(
            line_buffer,
            (int)received_byte,
            command_line,
            command_line_size
        );

        if (read_status == DEVLINK_SERIAL_LINE_READY) {
            devlink_serial_handle_command_line(&g_control_testing_device, app, command_line);
        } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
            devlink_serial_print_event(&g_control_testing_device, "protocol.line_too_long", "error");
        }
    }

    {
        DevlinkSerialLineReadStatus read_status = devlink_serial_line_buffer_flush_if_idle(
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
}

// Main
int main(void) {
    // create runtime objects and buffers
    PioUartRx command_rx = {0};
    ControlTestingApp app = {0};
    DevlinkSerialLineBuffer command_buffer = {0};
    char command_storage[COMMAND_BUFFER_LEN] = {0};
    char command_line[COMMAND_BUFFER_LEN] = {0};

    // start stdio over UART
    stdio_init_all();
    sleep_ms(200u);

    // init the LED
    // also init adc_c, motor_c, and sample timing
    control_testing_init(&app);

    // start the PIO UART receiver
    if (!pio_uart_rx_init(&command_rx, pio0, COMMAND_RX_GPIO, COMMAND_BAUD)) {
        devlink_serial_print_log(&g_control_testing_device, "error", "pio rx init failed");
        while (true) {
            tight_loop_contents();
        }
    }

    // initialize the line buffer
    devlink_serial_line_buffer_init(
        &command_buffer,
        command_storage,
        sizeof(command_storage),
        COMMAND_IDLE_FLUSH_MS
    );

    // sends devlink discovery messages
    devlink_serial_print_discovery(&g_control_testing_device);
    devlink_serial_print_log(&g_control_testing_device, "info", "control_testing ready");
    devlink_serial_print_event(&g_control_testing_device, "device.ready", "info");

    // main loop
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
