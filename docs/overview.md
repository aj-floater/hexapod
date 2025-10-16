# Hexapod Robot — Overview

Concise summary of the project scope and near-term plan for the hexapod robot.

## Current Focus

- Variable terrain generator to test the simulated hexapod over difficult terrain.
  - Procedural heightmap generation (likely noise-based).
  - Parameterizable difficulty: slope, roughness, obstacles, step height, and friction.
  - `more research required`
- Path planning that operates over the generated terrain.
  - `more research required` `google scholar`
- Closed-loop smart servo:
  - Modify an inexpensive SG90-class servo.
  - Use PID control with low-pass filtering.
  - Support I2C to read servo angle.
  - Consider sliding mode control for robustness.
- Integrated battery management system:
  - Two 18650 cells.
  - Research/select a dedicated charge/discharge solution.
  - Battery protection and balancing (because they'll be in series)
  - USB-C charging.

## Stretch Goals

- Add FPV for improved remote control.
  - Include a Low-latency video link for teleoperation
  - Include a Low-latency control link
- Explore offboard computer vision that leverages the simulation terrain system.
  - Perhaps making use of the video link connected to a more powerful remote computer?

---

See `literature_report.md` for background and references.
