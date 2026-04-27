# Leg Workspace Tooling

This directory contains report-specific tooling for visualising the three-joint hexapod leg.

## Kinematic Assumptions

- The model uses the standard DH convention from the frame sketch.
- All joints are revolute.
- Link lengths are fixed to the measured leg values:
  - `l1 = 36 mm`
  - `l2 = 62 mm`
  - `l3 = 87 mm`
- DH parameters:
  - `d = 0` for all joints
  - `theta = [theta1, theta2 - 90 deg, 20 deg - theta3]`
  - `a/r = l_i`
  - `alpha = [-90, 180, -90] deg`
- Servo mapping:
  - raw servo A angle is passed in as `theta1`
  - raw servo B angle is passed in as `theta2`
  - raw servo C angle is passed in as `theta3`
  - the DH row theta offsets/sign are applied internally by `leg_kinematics.py`

## Workspace Plot Plan

The workspace figure is a sampled DH end-effector workspace generated from servo soft bounds, not a measured workspace.

- Servo soft bounds:
  - A / `theta1`: `40 deg` to `140 deg`
  - B / `theta2`: `30 deg` to `130 deg`
  - C / `theta3`: `20 deg` to `170 deg`
- Outer rings:
  - hold `C = 20 deg`, the most extended configuration
  - for each B layer from min to max, sweep A from min to max
- Inner rings:
  - hold `C = 170 deg`, the least extended configuration
  - for each B layer from min to max, sweep A from min to max
- B-max C sweep:
  - hold `B = 130 deg`
  - for each C layer from min to max, sweep A from min to max
- B-min C sweep:
  - hold `B = 30 deg`
  - for each C layer from min to max, sweep A from min to max

The default sampling step is `5 deg` for A, B, and C where each axis is sampled. This gives:
- original C-boundary sweeps: `21 * 21 * 2 = 882` end-effector points
- added B-boundary sweeps: `21 * 31 * 2 = 1302` end-effector points
- combined total: `2184` end-effector points

## Figure Requirements

- Keep graph scaling fixed from the full maximum reach of the leg.
- Save the report-ready figure to `../figures/leg_workspace_point_cloud.png` by default.
- Label axes in millimetres.
- Distinguish all four sampled sweep families in the legend.
- Describe the result as a sampled workspace from the DH model and servo soft bounds.
