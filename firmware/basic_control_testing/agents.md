# Basic Leg Comparison Notes

These notes capture the current agreed plan for the basic leg only.

## Scope

- Focus on the basic leg first.
- Use the report DH model as the shared geometric reference.
- Use the same Cartesian path later for the designed-leg comparison.
- Do not commit to the final report graphics beyond a head-on comparison plot plus the retained 3D path data.

## Shared Geometry

Use the DH model values listed below as the shared geometric reference for the
basic-leg comparison work.

Shared DH model values:

- Link lengths: `36.0 mm`, `62.0 mm`, `87.0 mm`
- Raw-servo to DH conversion:
  - `theta1 = A`
  - `theta2 = B - 90`
  - `theta3 = 20 - C`

The basic leg is treated as the same linkage as the designed leg, but with a restricted commanded range and no closed-loop control.

## Basic Leg Command Space

Basic-leg commanded joints:

- `qA in [0, 50] deg`
- `qB in [0, 50] deg`
- `qC in [0, 50] deg`

Basic-leg absolute DH servo angles:

- `A_abs = 65 + qA`
- `B_abs = 62 + qB`
- `C_abs = 51 + qC`

The current physical assembly is the reference hardware state. Do not reopen horn indexing unless there is an explicit later decision to do so.

## Basic Leg Measurement Mapping

Measured servo and ADC mapping:

- Servo `A` on `GP16` maps to `ADCA` on `GP26`
- Servo `B` on `GP17` maps to `ADCB` on `GP27`
- Servo `C` on `GP18` maps to `ADCC` on `GP28`

Use the calibration already recorded in `BOARD_SPECIFIC_PINOUT.md`:

- Piecewise-linear interpolation from ADC to measured basic-leg angle `q`
- Then add offsets to recover measured absolute DH angles

Measured fields to derive:

- `meas_q_a_deg`, `meas_q_b_deg`, `meas_q_c_deg`
- `meas_a_abs_deg`, `meas_b_abs_deg`, `meas_c_abs_deg`

## Path Definition

The old fixed-`A` section-plane waypoint plan is retired. The canonical basic-leg path is a 3D IK-driven walking loop whose head-on projection matches the intended gait sketch.

Canonical Cartesian path in the report model frame:

- Let `u in [0, 1)` be the cycle phase.
- Stance for `u in [0, 0.6]`, with `s = u / 0.6`:
  - `x = 25 - 50*s`
  - `y = 130`
  - `z = -98`
- Swing for `u in (0.6, 1.0)`, with `s = (u - 0.6) / 0.4`:
  - `x = -25 + 50*s`
  - `y = 130 + 15*sin(pi*s)`
  - `z = -98 + 50*sin(pi*s)`

Key path points:

- Stance start: `(25, 130, -98) mm`
- Mid stance: `(0, 130, -98) mm`
- Stance end: `(-25, 130, -98) mm`
- Swing apex: `(0, 145, -48) mm`
- Close back to stance start

Validated basic-leg command envelope for this path:

- `qA ~= 14.1 .. 35.7 deg`
- `qB ~= 6.9 .. 46.3 deg`
- `qC ~= 15.1 .. 44.1 deg`

This path is intentionally chosen because it uses all three servos while remaining comfortably inside the current `0..50 deg` basic-leg limits.

## Playback Controls

Buttons:

- `GP9`: play/pause
- `GP10`: speed mode

Play/pause semantics:

- If the leg is idle in the assembly pose, pressing `GP9` starts the gait from phase `u = 0`.
- If the gait is running, or still transitioning into the gait, pressing `GP9` pauses by returning the leg to the assembly pose.
- Pause does not freeze in place; it always returns to assembly.
- Pressing play again after pause restarts the gait from the beginning of the loop.

Speed modes:

- Base: `2.0 s` cycle time
- Fast 1: `1.5 s` cycle time
- Fast 2: `1.0 s` cycle time
- Fast 3: `0.75 s` cycle time

Speed-button behavior:

- `GP10` cycles immediately through `Base -> Fast 1 -> Fast 2 -> Fast 3 -> Base`
- While running, the new speed takes effect on the next motion tick without resetting phase
- While paused, the selected speed is retained and used on the next play

LED meanings:

- `GP2`: run-state LED
  - on while the gait is actively running
  - off while paused in the assembly pose
  - blinking while transitioning to or from assembly
- `GP3`, `GP5`, `GP6`: speed LEDs
  - Base: all off
  - Fast 1: first LED on
  - Fast 2: first two LEDs on
  - Fast 3: all three LEDs on

## Playback and Data Retrieval

Playback implementation assumptions:

- Motion update tick remains `20 ms` (`50 Hz`)
- The gait path is evaluated from a continuous phase accumulator, not from a fixed integer waypoint index
- The current speed mode only changes how fast phase advances; it does not change the path geometry
- The existing transition-to-path and transition-to-assembly blends remain in place

Desired telemetry fields during active playback:

- `state`
- `speed_mode`
- `cycle_time_ms`
- `time_us`
- `sample_index`
- `phase_u`
- `cmd_x_mm`, `cmd_y_mm`, `cmd_z_mm`
- `cmd_q_a_deg`, `cmd_q_b_deg`, `cmd_q_c_deg`
- `cmd_a_abs_deg`, `cmd_b_abs_deg`, `cmd_c_abs_deg`
- `adc_a_raw`, `adc_b_raw`, `adc_c_raw`
- `meas_q_a_deg`, `meas_q_b_deg`, `meas_q_c_deg`
- `meas_a_abs_deg`, `meas_b_abs_deg`, `meas_c_abs_deg`
- `meas_x_mm`, `meas_y_mm`, `meas_z_mm`

Telemetry notes:

- `sample_index` is the current `0..99` phase bin derived from `phase_u`, not a monotonic packet counter
- Continuous telemetry is emitted only while the gait is actively running
- While paused in assembly, firmware should only emit short status lines for state and speed changes

Intended use of the captured data:

- Compare the intended Cartesian path against the measured basic-leg path
- Reconstruct commanded and measured end-effector motion in the same DH frame
- Later command the designed leg to follow the same Cartesian path for a like-for-like comparison

## Plotting Expectations

The comparison tooling should eventually produce:

- A head-on plot of commanded vs measured `(x, z)` for the basic leg
- The same head-on `(x, z)` plot for the designed leg on the same axes
- A retained full 3D plot or data export so the hidden `y` variation is not lost
