#ifndef POSITION_HOLD_H
#define POSITION_HOLD_H

#include <stdint.h>
#include <stdbool.h>

// Constants
#define CONTROL_MODE_MANUAL 0u      // motor controlled by motor.state / motor.drive_pct
#define CONTROL_MODE_HOLD 1u        // closed-loop position hold
#define HOLD_TARGET_DEFAULT 90.0f   // default target: 30.0 degrees
#define HOLD_TARGET_MIN 0.0f        // 0.0 degrees
#define HOLD_TARGET_MAX 180.0f      // 180.0 degrees
#define HOLD_DEADBAND_DEFAULT 0.0f  // default deadband: 0.0 degrees
#define HOLD_DEADBAND_MIN 0.0f      // no deadband
#define HOLD_DEADBAND_MAX 20.0f     // 20.0 degrees max deadband
#define HOLD_P_GAIN_DEFAULT 80.0f   // output += error_deg * p_gain
#define HOLD_P_GAIN_MIN 0.0f
#define HOLD_P_GAIN_MAX 1000.0f
#define HOLD_I_GAIN_DEFAULT 0.5f    // output += i_accum * i_gain
#define HOLD_I_GAIN_MIN 0.0f
#define HOLD_I_GAIN_MAX 1000.0f
#define HOLD_D_GAIN_DEFAULT 600.0f  // output += d_error_deg * d_gain
#define HOLD_D_GAIN_MIN 0.0f
#define HOLD_D_GAIN_MAX 1000.0f
#define HOLD_MAX_DUTY_DEFAULT 100u  // max motor duty percent in hold mode

// Types
typedef struct {
    float i_accum;
    float prev_error_deg;
    bool initialized;
} PositionHoldState;

typedef struct {
    uint8_t motor_state;
    uint8_t motor_drive_pct;
    int16_t output_pct;
} PositionHoldResult;

// Functions
PositionHoldResult position_hold_update(
    float target_deg,
    float measured_deg,
    float deadband_deg,
    float p_gain,
    float i_gain,
    float d_gain,
    uint8_t max_duty,
    PositionHoldState *state
);

#endif
