#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "hardware/adc.h"
#include "hardware/pwm.h"
#include "pico/stdlib.h"

#define SERVO_COUNT 3u
#define ADC_CAL_POINT_COUNT 6u
#define ADC_AVERAGE_SAMPLE_COUNT 8u
#define PATH_SAMPLE_COUNT 100u
#define SPEED_MODE_COUNT 4u
#define SPEED_LED_COUNT 3u

static const uint RUN_LED_PIN = 2u;
static const uint SPEED_LED_PINS[SPEED_LED_COUNT] = {3u, 5u, 6u};
static const uint PLAY_PAUSE_BUTTON_PIN = 9u;
static const uint SPEED_BUTTON_PIN = 10u;
static const uint SERVO_PINS[SERVO_COUNT] = {16u, 17u, 18u};
static const uint ADC_PINS[SERVO_COUNT] = {26u, 27u, 28u};
static const uint ADC_INPUTS[SERVO_COUNT] = {0u, 1u, 2u};

static const uint32_t LED_STATUS_UPDATE_MS = 100u;
static const uint32_t BUTTON_DEBOUNCE_MS = 25u;
static const uint32_t MOTION_UPDATE_PERIOD_MS = 20u;
static const uint32_t USB_ENUMERATION_DELAY_MS = 1500u;
static const uint16_t SERVO_PWM_PERIOD_US = 20000u;
static const float SERVO_PWM_CLKDIV = 125.0f;
static const uint16_t SERVO_MIN_PULSE_US = 1250u;
static const uint16_t SERVO_MAX_PULSE_US = 1750u;
static const uint8_t SERVO_MIN_ANGLE_DEG = 0u;
static const uint8_t SERVO_MAX_ANGLE_DEG = 50u;
static const uint16_t TRANSITION_SAMPLE_COUNT = 40u;

static const float LINK_1_MM = 36.0f;
static const float LINK_2_MM = 62.0f;
static const float LINK_3_MM = 87.0f;
static const float PI_F = 3.14159265358979323846f;
static const float IK_COS_TOLERANCE = 1e-5f;
static const float IK_POSITION_TOLERANCE_MM = 0.5f;
static const float SPEED_CYCLE_TIME_S[SPEED_MODE_COUNT] = {2.0f, 1.5f, 1.0f, 0.75f};
static const char *const SPEED_MODE_NAMES[SPEED_MODE_COUNT] = {"Base", "Fast 1", "Fast 2", "Fast 3"};

static const float PATH_STANCE_RATIO = 0.60f;
static const float PATH_HALF_WIDTH_MM = 25.0f;
static const float PATH_STANCE_Y_MM = 130.0f;
static const float PATH_STANCE_Z_MM = -98.0f;
static const float PATH_SWING_Y_ARC_MM = 15.0f;
static const float PATH_SWING_Z_LIFT_MM = 50.0f;

static const uint8_t SERVO_ASSEMBLY_Q_DEG[SERVO_COUNT] = {25u, 20u, 40u};
static const float SERVO_OFFSETS_DEG[SERVO_COUNT] = {65.0f, 62.0f, 51.0f};
static const uint8_t ADC_CAL_ANGLES_DEG[ADC_CAL_POINT_COUNT] = {0u, 10u, 20u, 30u, 40u, 50u};
static const uint16_t ADC_CAL_VALUES[SERVO_COUNT][ADC_CAL_POINT_COUNT] = {
    {2575u, 2413u, 2207u, 1999u, 1803u, 1592u},
    {2569u, 2397u, 2196u, 1988u, 1785u, 1581u},
    {2584u, 2420u, 2216u, 2012u, 1813u, 1609u},
};

typedef enum {
    MOTION_STATE_IDLE_ASSEMBLY = 0,
    MOTION_STATE_TRANSITION_TO_PATH,
    MOTION_STATE_PATH_LOOPING,
    MOTION_STATE_TRANSITION_TO_ASSEMBLY,
} motion_state_t;

typedef struct {
    uint gpio;
    bool stable_pressed;
    bool last_raw_pressed;
    absolute_time_t last_change_time;
} button_state_t;

typedef struct {
    float x_mm;
    float y_mm;
    float z_mm;
    float phase_u;
    uint8_t sample_index;
} path_target_t;

typedef struct {
    motion_state_t state;
    uint8_t speed_mode;
    float phase_u;
    float current_q_deg[SERVO_COUNT];
    float segment_start_q_deg[SERVO_COUNT];
    float segment_target_q_deg[SERVO_COUNT];
    float reference_raw_deg[SERVO_COUNT];
    uint16_t segment_total_samples;
    uint16_t segment_sample_index;
} motion_controller_t;

static float clamp_basic_q_deg(float angle_deg) {
    if (angle_deg < (float)SERVO_MIN_ANGLE_DEG) {
        return (float)SERVO_MIN_ANGLE_DEG;
    }
    if (angle_deg > (float)SERVO_MAX_ANGLE_DEG) {
        return (float)SERVO_MAX_ANGLE_DEG;
    }
    return angle_deg;
}

static uint8_t quantize_basic_q_deg(float angle_deg) {
    return (uint8_t)(clamp_basic_q_deg(angle_deg) + 0.5f);
}

static float wrap_angle_deg(float angle_deg) {
    while (angle_deg >= 180.0f) {
        angle_deg -= 360.0f;
    }
    while (angle_deg < -180.0f) {
        angle_deg += 360.0f;
    }
    return angle_deg;
}

static float wrap_phase_u(float phase_u) {
    while (phase_u >= 1.0f) {
        phase_u -= 1.0f;
    }
    while (phase_u < 0.0f) {
        phase_u += 1.0f;
    }
    return phase_u;
}

static void copy_pose_from_u8(float dest[SERVO_COUNT], const uint8_t source[SERVO_COUNT]) {
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        dest[i] = (float)source[i];
    }
}

static void copy_pose_f32(float dest[SERVO_COUNT], const float source[SERVO_COUNT]) {
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        dest[i] = source[i];
    }
}

static void current_q_to_reference_raw(const float q_deg[SERVO_COUNT], float raw_deg[SERVO_COUNT]) {
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        raw_deg[i] = SERVO_OFFSETS_DEG[i] + (float)quantize_basic_q_deg(q_deg[i]);
    }
}

static float pose_distance_sq(const float left[SERVO_COUNT], const float right[SERVO_COUNT]) {
    float distance_sq = 0.0f;

    for (uint i = 0; i < SERVO_COUNT; ++i) {
        const float delta = left[i] - right[i];
        distance_sq += delta * delta;
    }

    return distance_sq;
}

static uint16_t angle_deg_to_pulse_us(uint8_t angle_deg) {
    const uint32_t pulse_span_us = (uint32_t)(SERVO_MAX_PULSE_US - SERVO_MIN_PULSE_US);
    const uint32_t angle_span_deg = (uint32_t)(SERVO_MAX_ANGLE_DEG - SERVO_MIN_ANGLE_DEG);

    hard_assert(angle_deg >= SERVO_MIN_ANGLE_DEG && angle_deg <= SERVO_MAX_ANGLE_DEG);
    hard_assert(angle_span_deg > 0u);

    return (uint16_t)(
        SERVO_MIN_PULSE_US
        + (((uint32_t)(angle_deg - SERVO_MIN_ANGLE_DEG) * pulse_span_us) + (angle_span_deg / 2u)) / angle_span_deg
    );
}

static const char *motion_state_name(motion_state_t state) {
    switch (state) {
        case MOTION_STATE_IDLE_ASSEMBLY:
            return "idle";
        case MOTION_STATE_TRANSITION_TO_PATH:
            return "transition_to_path";
        case MOTION_STATE_PATH_LOOPING:
            return "running";
        case MOTION_STATE_TRANSITION_TO_ASSEMBLY:
            return "transition_to_assembly";
        default:
            return "unknown";
    }
}

static uint32_t cycle_time_ms_for_speed_mode(uint8_t speed_mode) {
    return (uint32_t)(SPEED_CYCLE_TIME_S[speed_mode] * 1000.0f + 0.5f);
}

static float cycle_time_s_for_speed_mode(uint8_t speed_mode) {
    return SPEED_CYCLE_TIME_S[speed_mode];
}

static void write_status_leds(motion_state_t state, uint8_t speed_mode, bool transition_blink_on) {
    bool run_led_on = false;

    if (state == MOTION_STATE_PATH_LOOPING) {
        run_led_on = true;
    } else if (state == MOTION_STATE_TRANSITION_TO_PATH || state == MOTION_STATE_TRANSITION_TO_ASSEMBLY) {
        run_led_on = transition_blink_on;
    }

    gpio_put(RUN_LED_PIN, run_led_on ? 1u : 0u);
    for (uint i = 0; i < SPEED_LED_COUNT; ++i) {
        gpio_put(SPEED_LED_PINS[i], speed_mode > i ? 1u : 0u);
    }
}

static void init_leds(void) {
    gpio_init(RUN_LED_PIN);
    gpio_set_dir(RUN_LED_PIN, GPIO_OUT);
    gpio_put(RUN_LED_PIN, 0);

    for (uint i = 0; i < SPEED_LED_COUNT; ++i) {
        gpio_init(SPEED_LED_PINS[i]);
        gpio_set_dir(SPEED_LED_PINS[i], GPIO_OUT);
        gpio_put(SPEED_LED_PINS[i], 0);
    }
}

static void init_button(button_state_t *button, uint gpio) {
    button->gpio = gpio;
    button->stable_pressed = false;
    button->last_raw_pressed = false;
    button->last_change_time = get_absolute_time();

    gpio_init(gpio);
    gpio_set_dir(gpio, GPIO_IN);
    gpio_pull_up(gpio);
}

static bool consume_button_press(button_state_t *button) {
    const bool raw_pressed = gpio_get(button->gpio) == 0u;
    const absolute_time_t now = get_absolute_time();

    if (raw_pressed != button->last_raw_pressed) {
        button->last_raw_pressed = raw_pressed;
        button->last_change_time = now;
    }

    if (raw_pressed != button->stable_pressed
        && absolute_time_diff_us(button->last_change_time, now) >= (int64_t)BUTTON_DEBOUNCE_MS * 1000) {
        button->stable_pressed = raw_pressed;
        return button->stable_pressed;
    }

    return false;
}

static void init_servos(void) {
    bool slice_configured[NUM_PWM_SLICES] = {false};

    for (uint i = 0; i < SERVO_COUNT; ++i) {
        const uint gpio = SERVO_PINS[i];
        const uint slice_num = pwm_gpio_to_slice_num(gpio);

        gpio_set_function(gpio, GPIO_FUNC_PWM);

        if (!slice_configured[slice_num]) {
            pwm_config config = pwm_get_default_config();

            // Run the PWM counter at 1 MHz so duty levels map directly to microseconds.
            pwm_config_set_clkdiv(&config, SERVO_PWM_CLKDIV);
            pwm_config_set_wrap(&config, SERVO_PWM_PERIOD_US - 1u);
            pwm_init(slice_num, &config, true);
            slice_configured[slice_num] = true;
        }
    }
}

static void set_servo_angle_deg(uint gpio, uint8_t angle_deg) {
    pwm_set_gpio_level(gpio, angle_deg_to_pulse_us(angle_deg));
}

static void apply_pose_q_deg(const float q_deg[SERVO_COUNT]) {
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        set_servo_angle_deg(SERVO_PINS[i], quantize_basic_q_deg(q_deg[i]));
    }
}

static void apply_pose_q_u8(const uint8_t q_deg[SERVO_COUNT]) {
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        set_servo_angle_deg(SERVO_PINS[i], q_deg[i]);
    }
}

static void init_adc_inputs(void) {
    adc_init();
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        adc_gpio_init(ADC_PINS[i]);
    }
}

static uint16_t read_adc_average(uint input) {
    uint32_t sum = 0u;

    adc_select_input(input);
    (void)adc_read();
    for (uint i = 0; i < ADC_AVERAGE_SAMPLE_COUNT; ++i) {
        sum += adc_read();
    }

    return (uint16_t)((sum + (ADC_AVERAGE_SAMPLE_COUNT / 2u)) / ADC_AVERAGE_SAMPLE_COUNT);
}

static void read_all_adc(uint16_t adc_raw[SERVO_COUNT]) {
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        adc_raw[i] = read_adc_average(ADC_INPUTS[i]);
    }
}

static bool basic_q_within_limits(const float q_deg[SERVO_COUNT]) {
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        if (q_deg[i] < (float)SERVO_MIN_ANGLE_DEG - 1e-3f || q_deg[i] > (float)SERVO_MAX_ANGLE_DEG + 1e-3f) {
            return false;
        }
    }
    return true;
}

static void end_effector_from_raw_pose(const float raw_deg[SERVO_COUNT], float xyz_mm[SERVO_COUNT]) {
    const float theta1_rad = raw_deg[0] * (PI_F / 180.0f);
    const float beta_rad = (raw_deg[1] - 90.0f) * (PI_F / 180.0f);
    const float kappa_rad = (raw_deg[2] - 20.0f) * (PI_F / 180.0f);
    const float signed_radius_mm = LINK_1_MM
        + (LINK_2_MM * cosf(beta_rad))
        + (LINK_3_MM * cosf(beta_rad + kappa_rad));

    xyz_mm[0] = signed_radius_mm * cosf(theta1_rad);
    xyz_mm[1] = signed_radius_mm * sinf(theta1_rad);
    xyz_mm[2] = -((LINK_2_MM * sinf(beta_rad)) + (LINK_3_MM * sinf(beta_rad + kappa_rad)));
}

static bool solve_inverse_kinematics(
    float x_mm,
    float y_mm,
    float z_mm,
    const float reference_raw_deg[SERVO_COUNT],
    float solved_raw_deg[SERVO_COUNT],
    uint8_t solved_q_deg[SERVO_COUNT]
) {
    const float radial_distance_mm = hypotf(x_mm, y_mm);
    const float base_heading_deg = atan2f(y_mm, x_mm) * (180.0f / PI_F);
    const float vertical_target_mm = -z_mm;
    float best_raw_deg[SERVO_COUNT] = {0.0f, 0.0f, 0.0f};
    uint8_t best_q_deg[SERVO_COUNT] = {0u, 0u, 0u};
    float best_distance_sq = 0.0f;
    bool found_solution = false;

    for (uint branch = 0; branch < 2u; ++branch) {
        const float signed_radius_mm = branch == 0u ? radial_distance_mm : -radial_distance_mm;
        const float theta1_deg = wrap_angle_deg(branch == 0u ? base_heading_deg : base_heading_deg + 180.0f);
        const float planar_x_mm = signed_radius_mm - LINK_1_MM;
        float cos_kappa = ((planar_x_mm * planar_x_mm) + (vertical_target_mm * vertical_target_mm)
            - (LINK_2_MM * LINK_2_MM) - (LINK_3_MM * LINK_3_MM))
            / (2.0f * LINK_2_MM * LINK_3_MM);

        if (cos_kappa < -1.0f - IK_COS_TOLERANCE || cos_kappa > 1.0f + IK_COS_TOLERANCE) {
            continue;
        }

        if (cos_kappa < -1.0f) {
            cos_kappa = -1.0f;
        } else if (cos_kappa > 1.0f) {
            cos_kappa = 1.0f;
        }

        const float kappa_abs_deg = acosf(cos_kappa) * (180.0f / PI_F);
        for (uint kappa_index = 0u; kappa_index < 2u; ++kappa_index) {
            const float kappa_deg = kappa_index == 0u ? kappa_abs_deg : -kappa_abs_deg;
            const float kappa_rad = kappa_deg * (PI_F / 180.0f);
            const float beta_rad = atan2f(vertical_target_mm, planar_x_mm)
                - atan2f(LINK_3_MM * sinf(kappa_rad), LINK_2_MM + (LINK_3_MM * cosf(kappa_rad)));
            const float candidate_raw_deg[SERVO_COUNT] = {
                wrap_angle_deg(theta1_deg),
                (beta_rad * (180.0f / PI_F)) + 90.0f,
                kappa_deg + 20.0f,
            };
            float candidate_q_deg[SERVO_COUNT];
            float candidate_xyz_mm[SERVO_COUNT];
            uint8_t candidate_q_u8[SERVO_COUNT];

            for (uint i = 0; i < SERVO_COUNT; ++i) {
                candidate_q_deg[i] = candidate_raw_deg[i] - SERVO_OFFSETS_DEG[i];
            }
            if (!basic_q_within_limits(candidate_q_deg)) {
                continue;
            }

            end_effector_from_raw_pose(candidate_raw_deg, candidate_xyz_mm);
            if (fabsf(candidate_xyz_mm[0] - x_mm) > IK_POSITION_TOLERANCE_MM
                || fabsf(candidate_xyz_mm[1] - y_mm) > IK_POSITION_TOLERANCE_MM
                || fabsf(candidate_xyz_mm[2] - z_mm) > IK_POSITION_TOLERANCE_MM) {
                continue;
            }

            for (uint i = 0; i < SERVO_COUNT; ++i) {
                candidate_q_u8[i] = quantize_basic_q_deg(candidate_q_deg[i]);
            }

            if (!found_solution || pose_distance_sq(candidate_raw_deg, reference_raw_deg) < best_distance_sq) {
                for (uint i = 0; i < SERVO_COUNT; ++i) {
                    best_raw_deg[i] = SERVO_OFFSETS_DEG[i] + (float)candidate_q_u8[i];
                    best_q_deg[i] = candidate_q_u8[i];
                }
                best_distance_sq = pose_distance_sq(best_raw_deg, reference_raw_deg);
                found_solution = true;
            }
        }
    }

    if (!found_solution) {
        return false;
    }

    for (uint i = 0; i < SERVO_COUNT; ++i) {
        solved_raw_deg[i] = best_raw_deg[i];
        solved_q_deg[i] = best_q_deg[i];
    }

    return true;
}

static void compute_path_target(float phase_u, path_target_t *target) {
    const float wrapped_phase_u = wrap_phase_u(phase_u);

    target->phase_u = wrapped_phase_u;
    target->sample_index = (uint8_t)((uint32_t)(wrapped_phase_u * (float)PATH_SAMPLE_COUNT) % PATH_SAMPLE_COUNT);

    if (wrapped_phase_u <= PATH_STANCE_RATIO) {
        const float stance_phase = wrapped_phase_u / PATH_STANCE_RATIO;
        target->x_mm = PATH_HALF_WIDTH_MM - (2.0f * PATH_HALF_WIDTH_MM * stance_phase);
        target->y_mm = PATH_STANCE_Y_MM;
        target->z_mm = PATH_STANCE_Z_MM;
        return;
    }

    {
        const float swing_phase = (wrapped_phase_u - PATH_STANCE_RATIO) / (1.0f - PATH_STANCE_RATIO);
        const float swing_arc = sinf(PI_F * swing_phase);

        target->x_mm = -PATH_HALF_WIDTH_MM + (2.0f * PATH_HALF_WIDTH_MM * swing_phase);
        target->y_mm = PATH_STANCE_Y_MM + (PATH_SWING_Y_ARC_MM * swing_arc);
        target->z_mm = PATH_STANCE_Z_MM + (PATH_SWING_Z_LIFT_MM * swing_arc);
    }
}

static void measured_q_from_adc(const uint16_t adc_raw[SERVO_COUNT], float measured_q_deg[SERVO_COUNT]) {
    for (uint axis = 0; axis < SERVO_COUNT; ++axis) {
        const uint16_t *cal = ADC_CAL_VALUES[axis];

        if (adc_raw[axis] >= cal[0]) {
            measured_q_deg[axis] = (float)ADC_CAL_ANGLES_DEG[0];
            continue;
        }
        if (adc_raw[axis] <= cal[ADC_CAL_POINT_COUNT - 1u]) {
            measured_q_deg[axis] = (float)ADC_CAL_ANGLES_DEG[ADC_CAL_POINT_COUNT - 1u];
            continue;
        }

        for (uint point = 0; point < ADC_CAL_POINT_COUNT - 1u; ++point) {
            const uint16_t adc_high = cal[point];
            const uint16_t adc_low = cal[point + 1u];

            if (adc_raw[axis] <= adc_high && adc_raw[axis] >= adc_low) {
                const float angle_high = (float)ADC_CAL_ANGLES_DEG[point];
                const float angle_low = (float)ADC_CAL_ANGLES_DEG[point + 1u];
                const float blend = (float)(adc_high - adc_raw[axis]) / (float)(adc_high - adc_low);
                measured_q_deg[axis] = angle_high + ((angle_low - angle_high) * blend);
                break;
            }
        }
    }
}

static void measured_raw_from_q(const float measured_q_deg[SERVO_COUNT], float measured_raw_deg[SERVO_COUNT]) {
    for (uint i = 0; i < SERVO_COUNT; ++i) {
        measured_raw_deg[i] = SERVO_OFFSETS_DEG[i] + measured_q_deg[i];
    }
}

static void print_startup_pose(void) {
    printf("Basic leg assembly pose active\r\n");
    printf(
        "qA=%u qB=%u qC=%u\r\n",
        (unsigned int)SERVO_ASSEMBLY_Q_DEG[0],
        (unsigned int)SERVO_ASSEMBLY_Q_DEG[1],
        (unsigned int)SERVO_ASSEMBLY_Q_DEG[2]
    );
    printf(
        "A=%.0f B=%.0f C=%.0f\r\n",
        (double)(SERVO_OFFSETS_DEG[0] + (float)SERVO_ASSEMBLY_Q_DEG[0]),
        (double)(SERVO_OFFSETS_DEG[1] + (float)SERVO_ASSEMBLY_Q_DEG[1]),
        (double)(SERVO_OFFSETS_DEG[2] + (float)SERVO_ASSEMBLY_Q_DEG[2])
    );
    printf(
        "Using offsets A=%.0f B=%.0f C=%.0f\r\n",
        (double)SERVO_OFFSETS_DEG[0],
        (double)SERVO_OFFSETS_DEG[1],
        (double)SERVO_OFFSETS_DEG[2]
    );
    fflush(stdout);
}

static void print_speed_status(const motion_controller_t *controller) {
    printf(
        "Speed mode: %s (%lu ms cycle)\r\n",
        SPEED_MODE_NAMES[controller->speed_mode],
        (unsigned long)cycle_time_ms_for_speed_mode(controller->speed_mode)
    );
    fflush(stdout);
}

static void print_telemetry_header(void) {
    printf("state,speed_mode,cycle_time_ms,time_us,sample_index,phase_u,");
    printf("cmd_x_mm,cmd_y_mm,cmd_z_mm,");
    printf("cmd_q_a_deg,cmd_q_b_deg,cmd_q_c_deg,");
    printf("cmd_a_abs_deg,cmd_b_abs_deg,cmd_c_abs_deg,");
    printf("adc_a_raw,adc_b_raw,adc_c_raw,");
    printf("meas_q_a_deg,meas_q_b_deg,meas_q_c_deg,");
    printf("meas_a_abs_deg,meas_b_abs_deg,meas_c_abs_deg,");
    printf("meas_x_mm,meas_y_mm,meas_z_mm\r\n");
    fflush(stdout);
}

static void print_telemetry_row(
    const motion_controller_t *controller,
    uint64_t time_us,
    const path_target_t *target,
    const uint8_t cmd_q_deg[SERVO_COUNT],
    const float cmd_raw_deg[SERVO_COUNT],
    const uint16_t adc_raw[SERVO_COUNT],
    const float measured_q_deg[SERVO_COUNT],
    const float measured_raw_deg[SERVO_COUNT],
    const float measured_xyz_mm[SERVO_COUNT]
) {
    printf(
        "%s,%u,%lu,%llu,%u,%.3f,%.2f,%.2f,%.2f,%u,%u,%u,%.2f,%.2f,%.2f,%u,%u,%u,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\r\n",
        motion_state_name(controller->state),
        (unsigned int)controller->speed_mode,
        (unsigned long)cycle_time_ms_for_speed_mode(controller->speed_mode),
        (unsigned long long)time_us,
        (unsigned int)target->sample_index,
        (double)target->phase_u,
        (double)target->x_mm,
        (double)target->y_mm,
        (double)target->z_mm,
        (unsigned int)cmd_q_deg[0],
        (unsigned int)cmd_q_deg[1],
        (unsigned int)cmd_q_deg[2],
        (double)cmd_raw_deg[0],
        (double)cmd_raw_deg[1],
        (double)cmd_raw_deg[2],
        (unsigned int)adc_raw[0],
        (unsigned int)adc_raw[1],
        (unsigned int)adc_raw[2],
        (double)measured_q_deg[0],
        (double)measured_q_deg[1],
        (double)measured_q_deg[2],
        (double)measured_raw_deg[0],
        (double)measured_raw_deg[1],
        (double)measured_raw_deg[2],
        (double)measured_xyz_mm[0],
        (double)measured_xyz_mm[1],
        (double)measured_xyz_mm[2]
    );
}

static void motion_controller_init(motion_controller_t *controller) {
    controller->state = MOTION_STATE_IDLE_ASSEMBLY;
    controller->speed_mode = 0u;
    controller->phase_u = 0.0f;
    copy_pose_from_u8(controller->current_q_deg, SERVO_ASSEMBLY_Q_DEG);
    copy_pose_from_u8(controller->segment_start_q_deg, SERVO_ASSEMBLY_Q_DEG);
    copy_pose_from_u8(controller->segment_target_q_deg, SERVO_ASSEMBLY_Q_DEG);
    controller->segment_total_samples = 0u;
    controller->segment_sample_index = 0u;
    current_q_to_reference_raw(controller->current_q_deg, controller->reference_raw_deg);
}

static void motion_begin_transition(
    motion_controller_t *controller,
    motion_state_t state,
    const float target_q_deg[SERVO_COUNT]
) {
    copy_pose_f32(controller->segment_start_q_deg, controller->current_q_deg);
    copy_pose_f32(controller->segment_target_q_deg, target_q_deg);
    controller->segment_total_samples = TRANSITION_SAMPLE_COUNT;
    controller->segment_sample_index = 0u;
    controller->state = state;
}

static bool motion_start_path(motion_controller_t *controller) {
    path_target_t start_target;
    float solved_raw_deg[SERVO_COUNT];
    uint8_t solved_q_deg[SERVO_COUNT];
    float target_q_deg[SERVO_COUNT];

    controller->phase_u = 0.0f;
    compute_path_target(controller->phase_u, &start_target);
    if (!solve_inverse_kinematics(
            start_target.x_mm,
            start_target.y_mm,
            start_target.z_mm,
            controller->reference_raw_deg,
            solved_raw_deg,
            solved_q_deg)) {
        printf("Unable to solve IK for path start\r\n");
        fflush(stdout);
        return false;
    }

    for (uint i = 0; i < SERVO_COUNT; ++i) {
        target_q_deg[i] = (float)solved_q_deg[i];
    }

    printf(
        "Starting path loop at %s (%lu ms cycle)\r\n",
        SPEED_MODE_NAMES[controller->speed_mode],
        (unsigned long)cycle_time_ms_for_speed_mode(controller->speed_mode)
    );
    fflush(stdout);
    motion_begin_transition(controller, MOTION_STATE_TRANSITION_TO_PATH, target_q_deg);
    return true;
}

static void motion_start_return_to_assembly(motion_controller_t *controller) {
    float assembly_q_deg[SERVO_COUNT];

    copy_pose_from_u8(assembly_q_deg, SERVO_ASSEMBLY_Q_DEG);
    printf("Returning to assembly pose\r\n");
    fflush(stdout);
    motion_begin_transition(controller, MOTION_STATE_TRANSITION_TO_ASSEMBLY, assembly_q_deg);
}

static void motion_cycle_speed(motion_controller_t *controller) {
    controller->speed_mode = (uint8_t)((controller->speed_mode + 1u) % SPEED_MODE_COUNT);
    print_speed_status(controller);
}

static void motion_tick(motion_controller_t *controller) {
    if (controller->state == MOTION_STATE_IDLE_ASSEMBLY) {
        return;
    }

    if (controller->state == MOTION_STATE_TRANSITION_TO_PATH || controller->state == MOTION_STATE_TRANSITION_TO_ASSEMBLY) {
        if (controller->segment_total_samples == 0u) {
            return;
        }

        controller->segment_sample_index++;
        for (uint i = 0; i < SERVO_COUNT; ++i) {
            const float start_q = controller->segment_start_q_deg[i];
            const float target_q = controller->segment_target_q_deg[i];
            const float blend = (float)controller->segment_sample_index / (float)controller->segment_total_samples;

            controller->current_q_deg[i] = start_q + ((target_q - start_q) * blend);
        }
        apply_pose_q_deg(controller->current_q_deg);

        if (controller->segment_sample_index < controller->segment_total_samples) {
            return;
        }

        copy_pose_f32(controller->current_q_deg, controller->segment_target_q_deg);
        apply_pose_q_deg(controller->current_q_deg);
        current_q_to_reference_raw(controller->current_q_deg, controller->reference_raw_deg);
        controller->segment_total_samples = 0u;
        controller->segment_sample_index = 0u;

        if (controller->state == MOTION_STATE_TRANSITION_TO_PATH) {
            controller->state = MOTION_STATE_PATH_LOOPING;
            controller->phase_u = 0.0f;
            print_telemetry_header();
            return;
        }

        controller->state = MOTION_STATE_IDLE_ASSEMBLY;
        printf("Assembly pose active\r\n");
        fflush(stdout);
        return;
    }

    if (controller->state == MOTION_STATE_PATH_LOOPING) {
        path_target_t target;
        float solved_raw_deg[SERVO_COUNT];
        uint8_t solved_q_deg[SERVO_COUNT];
        const float phase_step = ((float)MOTION_UPDATE_PERIOD_MS / 1000.0f) / cycle_time_s_for_speed_mode(controller->speed_mode);

        compute_path_target(controller->phase_u, &target);
        if (!solve_inverse_kinematics(
                target.x_mm,
                target.y_mm,
                target.z_mm,
                controller->reference_raw_deg,
                solved_raw_deg,
                solved_q_deg)) {
            printf(
                "IK fault,sample=%u,x=%.2f,y=%.2f,z=%.2f\r\n",
                (unsigned int)target.sample_index,
                (double)target.x_mm,
                (double)target.y_mm,
                (double)target.z_mm
            );
            fflush(stdout);
            controller->phase_u = wrap_phase_u(controller->phase_u + phase_step);
            return;
        }

        apply_pose_q_u8(solved_q_deg);
        for (uint i = 0; i < SERVO_COUNT; ++i) {
            controller->current_q_deg[i] = (float)solved_q_deg[i];
            controller->reference_raw_deg[i] = solved_raw_deg[i];
        }

        {
            uint16_t adc_raw[SERVO_COUNT];
            float measured_q_deg[SERVO_COUNT];
            float measured_raw_deg[SERVO_COUNT];
            float measured_xyz_mm[SERVO_COUNT];
            const uint64_t time_us = to_us_since_boot(get_absolute_time());

            read_all_adc(adc_raw);
            measured_q_from_adc(adc_raw, measured_q_deg);
            measured_raw_from_q(measured_q_deg, measured_raw_deg);
            end_effector_from_raw_pose(measured_raw_deg, measured_xyz_mm);
            print_telemetry_row(
                controller,
                time_us,
                &target,
                solved_q_deg,
                solved_raw_deg,
                adc_raw,
                measured_q_deg,
                measured_raw_deg,
                measured_xyz_mm
            );
        }

        controller->phase_u = wrap_phase_u(controller->phase_u + phase_step);
    }
}

int main(void) {
    button_state_t play_pause_button;
    button_state_t speed_button;
    motion_controller_t motion;
    absolute_time_t next_led_update = nil_time;
    absolute_time_t next_motion_update = nil_time;
    bool transition_led_on = false;

    stdio_init_all();
    init_leds();
    init_button(&play_pause_button, PLAY_PAUSE_BUTTON_PIN);
    init_button(&speed_button, SPEED_BUTTON_PIN);
    init_servos();
    init_adc_inputs();
    motion_controller_init(&motion);
    apply_pose_q_deg(motion.current_q_deg);
    write_status_leds(motion.state, motion.speed_mode, transition_led_on);

    sleep_ms(USB_ENUMERATION_DELAY_MS);
    print_startup_pose();
    print_speed_status(&motion);

    next_led_update = make_timeout_time_ms(LED_STATUS_UPDATE_MS);
    next_motion_update = make_timeout_time_ms(MOTION_UPDATE_PERIOD_MS);

    while (true) {
        if (consume_button_press(&play_pause_button)) {
            motion_cycle_speed(&motion);
            write_status_leds(motion.state, motion.speed_mode, transition_led_on);
        }

        if (consume_button_press(&speed_button)) {
            if (motion.state == MOTION_STATE_IDLE_ASSEMBLY) {
                (void)motion_start_path(&motion);
            } else if (motion.state == MOTION_STATE_PATH_LOOPING || motion.state == MOTION_STATE_TRANSITION_TO_PATH) {
                motion_start_return_to_assembly(&motion);
            }
            write_status_leds(motion.state, motion.speed_mode, transition_led_on);
        }

        if (time_reached(next_motion_update)) {
            motion_tick(&motion);
            if (motion.state != MOTION_STATE_TRANSITION_TO_PATH && motion.state != MOTION_STATE_TRANSITION_TO_ASSEMBLY) {
                transition_led_on = motion.state == MOTION_STATE_PATH_LOOPING;
            }
            write_status_leds(motion.state, motion.speed_mode, transition_led_on);
            next_motion_update = delayed_by_ms(next_motion_update, MOTION_UPDATE_PERIOD_MS);
        }

        if (time_reached(next_led_update)) {
            if (motion.state == MOTION_STATE_TRANSITION_TO_PATH || motion.state == MOTION_STATE_TRANSITION_TO_ASSEMBLY) {
                transition_led_on = !transition_led_on;
            } else {
                transition_led_on = motion.state == MOTION_STATE_PATH_LOOPING;
            }
            write_status_leds(motion.state, motion.speed_mode, transition_led_on);
            next_led_update = delayed_by_ms(next_led_update, LED_STATUS_UPDATE_MS);
        }

        tight_loop_contents();
        sleep_ms(1);
    }

    return 0;
}
