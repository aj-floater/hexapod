#include "servo.h"

#include "pico/stdlib.h"

#define SERVO_ADC_AVERAGE_SAMPLE_COUNT 16u
#define SERVO_ADC_RAW_MIN 0u
#define SERVO_ADC_RAW_MAX 4080u
#define SERVO_ADC_MAX_DEG 180u
#define SERVO_MOTOR_PWM_HZ 20000u

static uint16_t servo_bound_adc_raw(uint16_t raw_value) {
    if (raw_value < SERVO_ADC_RAW_MIN) {
        return SERVO_ADC_RAW_MIN;
    }
    if (raw_value > SERVO_ADC_RAW_MAX) {
        return SERVO_ADC_RAW_MAX;
    }
    return raw_value;
}

static float servo_deg_tenths_to_f32(uint16_t deg_tenths) {
    return (float)deg_tenths / (float)SERVO_TENTHS_PER_DEG;
}

static uint16_t servo_adc_raw_to_deg_tenths(
    const Servo *servo,
    uint16_t raw_value
) {
    const ServoCalibrationPoint *upper_point = NULL;
    const ServoCalibrationPoint *lower_point = NULL;
    uint32_t raw_span = 0u;
    uint32_t raw_offset = 0u;
    uint32_t deg_span = 0u;
    uint32_t interpolated_deg_tenths = 0u;

    hard_assert(servo != NULL);
    hard_assert(servo->calibration_points != NULL);
    hard_assert(servo->calibration_point_count > 1u);

    raw_value = servo_bound_adc_raw(raw_value);

    if (raw_value >= servo->calibration_points[0].raw) {
        return (uint16_t)(servo->calibration_points[0].deg * SERVO_TENTHS_PER_DEG);
    }
    if (raw_value <= servo->calibration_points[servo->calibration_point_count - 1u].raw) {
        return (uint16_t)(
            servo->calibration_points[servo->calibration_point_count - 1u].deg
            * SERVO_TENTHS_PER_DEG
        );
    }

    for (size_t point_index = 0u; point_index + 1u < servo->calibration_point_count; point_index++) {
        upper_point = &servo->calibration_points[point_index];
        lower_point = &servo->calibration_points[point_index + 1u];

        if (raw_value <= upper_point->raw && raw_value >= lower_point->raw) {
            raw_span = (uint32_t)(upper_point->raw - lower_point->raw);
            raw_offset = (uint32_t)(upper_point->raw - raw_value);
            deg_span = (uint32_t)(lower_point->deg - upper_point->deg);
            interpolated_deg_tenths = (uint32_t)(upper_point->deg * SERVO_TENTHS_PER_DEG)
                + ((raw_offset * deg_span * SERVO_TENTHS_PER_DEG) + (raw_span / 2u)) / raw_span;
            return (uint16_t)interpolated_deg_tenths;
        }
    }

    return (uint16_t)(SERVO_ADC_MAX_DEG * SERVO_TENTHS_PER_DEG);
}

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

void servo_init(
    Servo *servo,
    const ServoConfig *config
) {
    hard_assert(servo != NULL);
    hard_assert(config != NULL);

    servo->id = config->id;
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
    servo->control_mode = config->default_control_mode;
    servo->settings.filter_alpha_pct = SERVO_FILTER_ALPHA_DEFAULT_PCT;
    servo->settings.hold_target_deg = HOLD_TARGET_DEFAULT;
    servo->settings.hold_deadband_deg = HOLD_DEADBAND_DEFAULT;
    servo->settings.hold_p_gain = HOLD_P_GAIN_DEFAULT;
    servo->settings.hold_i_gain = HOLD_I_GAIN_DEFAULT;
    servo->settings.hold_d_gain = HOLD_D_GAIN_DEFAULT;
    servo->settings.hold_max_duty = HOLD_MAX_DUTY_DEFAULT;
    servo->telemetry = (ServoTelemetry){
        .motor_state = SERVO_MOTOR_STATE_COAST,
        .motor_drive_pct = 0u,
        .hold_output_pct = 0,
    };
    servo->hold_state = (PositionHoldState){0};

    servo_apply_output(servo);
}

void servo_set_control_mode(Servo *servo, uint8_t mode) {
    hard_assert(servo != NULL);

    servo->control_mode = mode;
    if (servo->control_mode == CONTROL_MODE_MANUAL) {
        servo->telemetry.motor_state = SERVO_MOTOR_STATE_COAST;
        servo->telemetry.motor_drive_pct = 0u;
        servo->telemetry.hold_output_pct = 0;
        servo_apply_output(servo);
    } else if (servo->control_mode == CONTROL_MODE_HOLD) {
        servo->hold_state = (PositionHoldState){0};
    }
}

void servo_set_motor_state(Servo *servo, uint8_t state) {
    hard_assert(servo != NULL);

    servo->telemetry.motor_state = state;
    servo_apply_output(servo);
}

void servo_set_motor_drive_pct(Servo *servo, uint8_t pct) {
    hard_assert(servo != NULL);

    servo->telemetry.motor_drive_pct = pct;
    servo_apply_output(servo);
}

void servo_tick(Servo *servo) {
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

    if (servo->control_mode == CONTROL_MODE_HOLD) {
        PositionHoldResult hold_result = position_hold_update(
            servo->settings.hold_target_deg,
            servo_deg_tenths_to_f32(servo->telemetry.angle_lp_deg_tenths),
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
        servo_apply_output(servo);
    } else {
        servo->telemetry.hold_output_pct = 0;
    }
}
