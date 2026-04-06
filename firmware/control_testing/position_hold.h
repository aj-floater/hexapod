#ifndef POSITION_HOLD_H
#define POSITION_HOLD_H

#include <stdint.h>

// Constants
#define CONTROL_MODE_MANUAL 0u      // motor controlled by motor.state / motor.drive_pct
#define CONTROL_MODE_HOLD 1u        // closed-loop position hold
#define HOLD_TARGET_DEFAULT 900u    // default target: 90.0 degrees
#define HOLD_TARGET_MIN 0u          // 0.0 degrees
#define HOLD_TARGET_MAX 1800u       // 180.0 degrees
#define HOLD_DEADBAND_DEFAULT 20u   // default deadband: 2.0 degrees
#define HOLD_DEADBAND_MIN 0u        // no deadband
#define HOLD_DEADBAND_MAX 200u      // 20.0 degrees max deadband
#define HOLD_P_GAIN_DEFAULT 10u     // duty_pct = error_tenths * (p_gain / 10)
#define HOLD_P_GAIN_MIN 0u          // gain 0.0 (no response)
#define HOLD_P_GAIN_MAX 100u         // gain 5.0 (most aggressive)
#define HOLD_MAX_DUTY_DEFAULT 60u   // max motor duty percent in hold mode

// Types
typedef struct {
    uint8_t motor_state;
    uint8_t motor_drive_pct;
    int16_t output_pct;
} PositionHoldResult;

// Functions
PositionHoldResult position_hold_update(
    uint16_t target_deg_tenths,
    uint16_t measured_deg_tenths,
    uint16_t deadband_deg_tenths,
    uint8_t p_gain,
    uint8_t max_duty
);

#endif
