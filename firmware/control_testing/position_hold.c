#include "position_hold.h"

// Constants
#define MOTOR_STATE_COAST 0u
#define MOTOR_STATE_BRAKE 1u
#define MOTOR_STATE_FORWARD 2u
#define MOTOR_STATE_REVERSE 3u

// Functions
// runs the P controller and returns the motor command
PositionHoldResult position_hold_update(
    uint16_t target_deg_tenths,
    uint16_t measured_deg_tenths,
    uint16_t deadband_deg_tenths,
    uint8_t p_gain,
    uint8_t max_duty
) {
    PositionHoldResult result = {0};
    int32_t error = 0;
    uint32_t error_magnitude = 0u;
    uint16_t duty_pct = 0u;

    error = (int32_t)target_deg_tenths - (int32_t)measured_deg_tenths;
    error_magnitude = (error >= 0) ? (uint32_t)error : (uint32_t)(-error);

    if (error_magnitude <= deadband_deg_tenths) {
        result.motor_state = MOTOR_STATE_BRAKE;
        result.motor_drive_pct = 0u;
        result.output_pct = 0;
    } else {
        duty_pct = (uint16_t)((error_magnitude * p_gain) / 10u);
        if (duty_pct > max_duty) {
            duty_pct = max_duty;
        }

        result.motor_drive_pct = (uint8_t)duty_pct;
        if (error > 0) {
            result.motor_state = MOTOR_STATE_FORWARD;
            result.output_pct = (int16_t)duty_pct;
        } else {
            result.motor_state = MOTOR_STATE_REVERSE;
            result.output_pct = (int16_t)(-(int16_t)duty_pct);
        }
    }

    return result;
}
