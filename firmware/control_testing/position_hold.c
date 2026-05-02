#include "position_hold.h"

// Constants
#define MOTOR_STATE_COAST 0u
#define MOTOR_STATE_BRAKE 1u
#define MOTOR_STATE_FORWARD 2u
#define MOTOR_STATE_REVERSE 3u
// Temporary behavior: disable active braking for all position-hold users and coast instead.
#define POSITION_HOLD_SETTLED_MOTOR_STATE MOTOR_STATE_COAST

// Computes one PID motor command.
PositionHoldResult position_hold_update(
    float target_deg,
    float measured_deg,
    float deadband_deg,
    float p_gain,
    float i_gain,
    float d_gain,
    uint8_t max_duty,
    PositionHoldState *state
) {
    PositionHoldResult result = {0};
    float error = target_deg - measured_deg;
    float error_magnitude = error >= 0.0f ? error : -error;

    if (error_magnitude <= deadband_deg) {
        state->prev_error_deg = error;
        result.motor_state = POSITION_HOLD_SETTLED_MOTOR_STATE;
        return result;
    }

    // P term
    float output = error * p_gain;

    // I term — accumulate error, clamp to prevent windup
    if (i_gain > 0.0f) {
        state->i_accum += error;
        float i_max = (float)max_duty / i_gain;
        if (state->i_accum >  i_max) state->i_accum =  i_max;
        if (state->i_accum < -i_max) state->i_accum = -i_max;
        output += state->i_accum * i_gain;
    }

    // D term — skip on first tick
    if (d_gain > 0.0f && state->initialized) {
        output += (error - state->prev_error_deg) * d_gain;
    }
    state->initialized = true;
    state->prev_error_deg = error;

    // Clamp output to [-max_duty, +max_duty]
    float max = (float)max_duty;
    if (output >  max) output =  max;
    if (output < -max) output = -max;

    result.output_pct = (int16_t)output;
    if (output > 0.0f) {
        result.motor_state = MOTOR_STATE_FORWARD;
        result.motor_drive_pct = (uint8_t)output;
    } else if (output < 0.0f) {
        result.motor_state = MOTOR_STATE_REVERSE;
        result.motor_drive_pct = (uint8_t)(-output);
    } else {
        result.motor_state = POSITION_HOLD_SETTLED_MOTOR_STATE;
    }

    return result;
}
