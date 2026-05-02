#include "servo.h"

#include "pico/stdlib.h"

#define SERVO_ADC_AVERAGE_SAMPLE_COUNT 16u
#define SERVO_ADC_RAW_MIN 0u
#define SERVO_ADC_RAW_MAX 4080u
#define SERVO_MOTOR_PWM_HZ 20000u
#define SERVO_BOUNDARY_RELEASE_MARGIN_DEG 1.0f

// Clamps raw ADC values to the usable range.
static uint16_t servo_bound_adc_raw(uint16_t raw_value) {
    if (raw_value < SERVO_ADC_RAW_MIN) {
        return SERVO_ADC_RAW_MIN;
    }
    if (raw_value > SERVO_ADC_RAW_MAX) {
        return SERVO_ADC_RAW_MAX;
    }
    return raw_value;
}

// Converts tenths of degrees to float degrees.
static float servo_deg_tenths_to_f32(int16_t deg_tenths) {
    return (float)deg_tenths / (float)SERVO_TENTHS_PER_DEG;
}

// Clamps one target angle to the configured servo-safe range.
float servo_clamp_target_deg(const Servo *servo, float target_deg) {
    hard_assert(servo != NULL);

    if (target_deg < servo->min_angle_deg) {
        return servo->min_angle_deg;
    }
    if (target_deg > servo->max_angle_deg) {
        return servo->max_angle_deg;
    }
    return target_deg;
}

// Divides with nearest-integer rounding for positive and negative numerators.
static int32_t servo_divide_round_nearest(int32_t numerator, uint32_t denominator) {
    hard_assert(denominator != 0u);

    if (numerator >= 0) {
        return (numerator + (int32_t)(denominator / 2u)) / (int32_t)denominator;
    }
    return (numerator - (int32_t)(denominator / 2u)) / (int32_t)denominator;
}

// Interpolates or extrapolates one angle from a calibration segment.
static int16_t servo_segment_raw_to_deg_tenths(
    const ServoCalibrationPoint *upper_point,
    const ServoCalibrationPoint *lower_point,
    uint16_t raw_value
) {
    int32_t raw_offset = 0;
    uint32_t raw_span = 0u;
    uint32_t deg_span_tenths = 0u;
    int32_t interpolated_deg_tenths = 0;

    hard_assert(upper_point != NULL);
    hard_assert(lower_point != NULL);
    hard_assert(upper_point->raw > lower_point->raw);

    raw_offset = (int32_t)upper_point->raw - (int32_t)raw_value;
    raw_span = (uint32_t)upper_point->raw - (uint32_t)lower_point->raw;
    deg_span_tenths = ((uint32_t)lower_point->deg - (uint32_t)upper_point->deg) * SERVO_TENTHS_PER_DEG;
    interpolated_deg_tenths = (int32_t)upper_point->deg * (int32_t)SERVO_TENTHS_PER_DEG
        + servo_divide_round_nearest(raw_offset * (int32_t)deg_span_tenths, raw_span);
    hard_assert(interpolated_deg_tenths >= INT16_MIN && interpolated_deg_tenths <= INT16_MAX);
    return (int16_t)interpolated_deg_tenths;
}

// Converts one ADC sample into angle tenths.
static int16_t servo_adc_raw_to_deg_tenths(
    const Servo *servo,
    uint16_t raw_value
) {
    const ServoCalibrationPoint *upper_point = NULL;
    const ServoCalibrationPoint *lower_point = NULL;

    hard_assert(servo != NULL);
    hard_assert(servo->calibration_points != NULL);
    hard_assert(servo->calibration_point_count > 1u);

    raw_value = servo_bound_adc_raw(raw_value);

    if (raw_value >= servo->calibration_points[0].raw) {
        return servo_segment_raw_to_deg_tenths(
            &servo->calibration_points[0],
            &servo->calibration_points[1],
            raw_value
        );
    }
    if (raw_value <= servo->calibration_points[servo->calibration_point_count - 1u].raw) {
        return servo_segment_raw_to_deg_tenths(
            &servo->calibration_points[servo->calibration_point_count - 2u],
            &servo->calibration_points[servo->calibration_point_count - 1u],
            raw_value
        );
    }

    for (size_t point_index = 0u; point_index + 1u < servo->calibration_point_count; point_index++) {
        upper_point = &servo->calibration_points[point_index];
        lower_point = &servo->calibration_points[point_index + 1u];

        if (raw_value <= upper_point->raw && raw_value >= lower_point->raw) {
            return servo_segment_raw_to_deg_tenths(upper_point, lower_point, raw_value);
        }
    }

    return servo_segment_raw_to_deg_tenths(
        &servo->calibration_points[servo->calibration_point_count - 2u],
        &servo->calibration_points[servo->calibration_point_count - 1u],
        raw_value
    );
}

// Updates the low-pass ADC sample.
static uint16_t servo_update_adc_lp(Servo *servo, uint16_t avg_raw_value) {
    uint32_t filtered_raw = 0u;
    uint32_t previous_weight = 0u;

    hard_assert(servo != NULL);

    if (!servo->adc_lp_ready) {
        servo->telemetry.adc_lp_raw = avg_raw_value;
        servo->adc_lp_ready = true;
        return servo->telemetry.adc_lp_raw;
    }

    previous_weight = (uint32_t)(
        SERVO_FILTER_ALPHA_MAX_PCT - servo->settings.filter_alpha_pct
    );
    filtered_raw = ((uint32_t)servo->settings.filter_alpha_pct * avg_raw_value)
        + (previous_weight * servo->telemetry.adc_lp_raw);
    servo->telemetry.adc_lp_raw = (uint16_t)((filtered_raw + 50u) / 100u);
    servo->telemetry.adc_lp_raw = servo_bound_adc_raw(servo->telemetry.adc_lp_raw);
    return servo->telemetry.adc_lp_raw;
}

// Returns the low-side recovery target just inside the legal range.
static float servo_boundary_low_target_deg(const Servo *servo) {
    float target_deg = 0.0f;

    hard_assert(servo != NULL);

    target_deg = servo->min_angle_deg + SERVO_BOUNDARY_RELEASE_MARGIN_DEG;
    if (target_deg > servo->max_angle_deg) {
        target_deg = servo->max_angle_deg;
    }
    return target_deg;
}

// Returns the high-side recovery target just inside the legal range.
static float servo_boundary_high_target_deg(const Servo *servo) {
    float target_deg = 0.0f;

    hard_assert(servo != NULL);

    target_deg = servo->max_angle_deg - SERVO_BOUNDARY_RELEASE_MARGIN_DEG;
    if (target_deg < servo->min_angle_deg) {
        target_deg = servo->min_angle_deg;
    }
    return target_deg;
}

// Checks whether the servo should start or continue a boundary override.
static bool servo_boundary_override_needed(
    Servo *servo,
    float measured_deg,
    float *out_target_deg
) {
    hard_assert(servo != NULL);
    hard_assert(out_target_deg != NULL);

    if (servo->boundary_override_active) {
        if (servo->boundary_override_low_side) {
            *out_target_deg = servo_boundary_low_target_deg(servo);
            if (measured_deg >= *out_target_deg) {
                servo->boundary_override_active = false;
                servo->hold_state = (PositionHoldState){0};
                servo->boundary_hold_state = (PositionHoldState){0};
                return false;
            }
            return true;
        }

        *out_target_deg = servo_boundary_high_target_deg(servo);
        if (measured_deg <= *out_target_deg) {
            servo->boundary_override_active = false;
            servo->hold_state = (PositionHoldState){0};
            servo->boundary_hold_state = (PositionHoldState){0};
            return false;
        }
        return true;
    }

    if (measured_deg < servo->min_angle_deg) {
        servo->boundary_override_active = true;
        servo->boundary_override_low_side = true;
        servo->hold_state = (PositionHoldState){0};
        servo->boundary_hold_state = (PositionHoldState){0};
        *out_target_deg = servo_boundary_low_target_deg(servo);
        return true;
    }
    if (measured_deg > servo->max_angle_deg) {
        servo->boundary_override_active = true;
        servo->boundary_override_low_side = false;
        servo->hold_state = (PositionHoldState){0};
        servo->boundary_hold_state = (PositionHoldState){0};
        *out_target_deg = servo_boundary_high_target_deg(servo);
        return true;
    }

    return false;
}

// Applies the cached motor command.
static void servo_apply_output(Servo *servo) {
    hard_assert(servo != NULL);

    switch (servo->telemetry.motor_state) {
        case SERVO_MOTOR_STATE_BRAKE:
            motor_pwm_brake(&servo->motor);
            break;
        case SERVO_MOTOR_STATE_FORWARD:
            motor_pwm_set_forward_duty(&servo->motor, servo->telemetry.motor_drive_pct);
            break;
        case SERVO_MOTOR_STATE_REVERSE:
            motor_pwm_set_reverse_duty(&servo->motor, servo->telemetry.motor_drive_pct);
            break;
        case SERVO_MOTOR_STATE_COAST:
        default:
            motor_pwm_coast(&servo->motor);
            break;
    }
}

// Initializes one servo runtime object.
void servo_init(
    Servo *servo,
    const ServoConfig *config
) {
    hard_assert(servo != NULL);
    hard_assert(config != NULL);

    servo->id = config->id;
    servo->min_angle_deg = config->min_angle_deg;
    servo->max_angle_deg = config->max_angle_deg;
    servo->calibration_points = config->calibration_points;
    servo->calibration_point_count = config->calibration_point_count;

    adc_input_init(&servo->adc, config->adc_gpio);
    motor_pwm_init(
        &servo->motor,
        config->motor_name,
        config->motor_in1_gpio,
        config->motor_in2_gpio,
        SERVO_MOTOR_PWM_HZ
    );

    servo->adc_lp_ready = false;
    servo->boundary_override_active = false;
    servo->boundary_override_low_side = false;
    servo->control_mode = config->default_control_mode;
    servo->manual_motor_state = SERVO_MOTOR_STATE_COAST;
    servo->manual_motor_drive_pct = 0u;
    servo->settings.filter_alpha_pct = SERVO_FILTER_ALPHA_DEFAULT_PCT;
    servo->settings.hold_target_deg = servo_clamp_target_deg(servo, HOLD_TARGET_DEFAULT);
    servo->settings.hold_deadband_deg = HOLD_DEADBAND_DEFAULT;
    servo->settings.hold_p_gain = config->default_hold_p_gain;
    servo->settings.hold_i_gain = config->default_hold_i_gain;
    servo->settings.hold_d_gain = config->default_hold_d_gain;
    servo->settings.hold_max_duty = HOLD_MAX_DUTY_DEFAULT;
    servo->telemetry = (ServoTelemetry){
        .motor_state = SERVO_MOTOR_STATE_COAST,
        .motor_drive_pct = 0u,
        .hold_output_pct = 0,
    };
    servo->hold_state = (PositionHoldState){0};
    servo->boundary_hold_state = (PositionHoldState){0};

    servo_apply_output(servo);
}

// Changes the servo control mode.
void servo_set_control_mode(Servo *servo, uint8_t mode) {
    hard_assert(servo != NULL);

    servo->control_mode = mode;
    servo->boundary_override_active = false;
    servo->boundary_hold_state = (PositionHoldState){0};
    if (servo->control_mode == CONTROL_MODE_MANUAL) {
        servo->manual_motor_state = SERVO_MOTOR_STATE_COAST;
        servo->manual_motor_drive_pct = 0u;
        servo->telemetry.motor_state = servo->manual_motor_state;
        servo->telemetry.motor_drive_pct = servo->manual_motor_drive_pct;
        servo->telemetry.hold_output_pct = 0;
    } else if (servo->control_mode == CONTROL_MODE_HOLD) {
        servo->hold_state = (PositionHoldState){0};
    }
}

// Updates the manual motor state.
void servo_set_motor_state(Servo *servo, uint8_t state) {
    hard_assert(servo != NULL);

    servo->manual_motor_state = state;
}

// Updates the manual motor duty.
void servo_set_motor_drive_pct(Servo *servo, uint8_t pct) {
    hard_assert(servo != NULL);

    servo->manual_motor_drive_pct = pct;
}

// Runs one servo control cycle.
void servo_tick(Servo *servo) {
    float measured_deg = 0.0f;
    float boundary_target_deg = 0.0f;

    hard_assert(servo != NULL);

    servo->telemetry.adc_raw = servo_bound_adc_raw(adc_input_read_raw(&servo->adc));
    servo->telemetry.adc_avg_raw = servo_bound_adc_raw(
        adc_input_read_average_raw(&servo->adc, SERVO_ADC_AVERAGE_SAMPLE_COUNT)
    );
    servo->telemetry.adc_lp_raw = servo_update_adc_lp(servo, servo->telemetry.adc_avg_raw);
    servo->telemetry.angle_avg_deg_tenths = servo_adc_raw_to_deg_tenths(
        servo,
        servo->telemetry.adc_avg_raw
    );
    servo->telemetry.angle_lp_deg_tenths = servo_adc_raw_to_deg_tenths(
        servo,
        servo->telemetry.adc_lp_raw
    );
    measured_deg = servo_deg_tenths_to_f32(servo->telemetry.angle_lp_deg_tenths);

    if (servo_boundary_override_needed(servo, measured_deg, &boundary_target_deg)) {
        PositionHoldResult boundary_result = position_hold_update(
            boundary_target_deg,
            measured_deg,
            0.0f,
            servo->settings.hold_p_gain,
            servo->settings.hold_i_gain,
            servo->settings.hold_d_gain,
            servo->settings.hold_max_duty,
            &servo->boundary_hold_state
        );
        servo->telemetry.motor_state = boundary_result.motor_state;
        servo->telemetry.motor_drive_pct = boundary_result.motor_drive_pct;
        servo->telemetry.hold_output_pct = boundary_result.output_pct;
    } else if (servo->control_mode == CONTROL_MODE_HOLD) {
        PositionHoldResult hold_result = position_hold_update(
            servo_clamp_target_deg(servo, servo->settings.hold_target_deg),
            measured_deg,
            servo->settings.hold_deadband_deg,
            servo->settings.hold_p_gain,
            servo->settings.hold_i_gain,
            servo->settings.hold_d_gain,
            servo->settings.hold_max_duty,
            &servo->hold_state
        );
        servo->telemetry.motor_state = hold_result.motor_state;
        servo->telemetry.motor_drive_pct = hold_result.motor_drive_pct;
        servo->telemetry.hold_output_pct = hold_result.output_pct;
    } else {
        servo->telemetry.motor_state = servo->manual_motor_state;
        servo->telemetry.motor_drive_pct = servo->manual_motor_drive_pct;
        servo->telemetry.hold_output_pct = 0;
    }

    servo_apply_output(servo);
}
