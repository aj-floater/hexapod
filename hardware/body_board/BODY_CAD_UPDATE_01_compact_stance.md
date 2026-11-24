# Body CAD — Update 01: compact body, narrow and low stance

> Written 2026-11-23 for the FreeCAD body-CAD agent. It **adds to and overrides** `BODY_CAD_HANDOFF.md` Part 2 where they conflict.
> Source: the leg current/torque model in `hardware/body_board/research/leg_current_estimate.md` (modelled, not yet measured).

---

## 1. Why this changes

The femur servo (joint B, MG90D, stall ≈0.22 N·m at 5 V) **cannot hold the robot up in the current gait stance**. In tripod gait the middle leg carries about half the robot's weight. With the foot 94 mm out from joint B, that leg stalls at a robot mass of **0.54 kg**. The robot is estimated at about **0.9 kg**, so the middle legs would stall and overheat while walking.

**Archie's decision (2026-11-23):**
- **Narrow the stance** (feet closer to the body).
- **Lower the body.**
- **Make the body as small and light as physically possible.**

## 2. Targets

Leg frame (from `firmware/control_testing/control_testing.c`): **y** is the radial distance from the coxa yaw axis (joint A) to the foot, and **z** is the foot height relative to the leg's joint plane (negative is down).

| | Current firmware | **Target** |
|---|---|---|
| Stance y | 130 mm | **90–100 mm** (as close to 90 as the geometry allows) |
| Stance z | −98 mm | **≈ −80 mm** (lower body) |
| Body mass (everything except the 6 legs) | ≈280 g (estimate) | **as low as possible; aim ≤ 200 g** |
| Robot total | ≈0.9 kg | **≤ ~0.85 kg** (legs alone are 6 × 106 g = 0.64 kg) |

Mass at which joint B stalls in the tripod middle leg, for context (from the model):

| Stance | Stall mass | At 60 % torque margin |
|---|---|---|
| y = 130 mm (now) | 0.54 kg | 0.35 kg |
| y = 110 mm | 0.68 kg | 0.44 kg |
| y = 100 mm, z = −80 mm | 0.78 kg | 0.51 kg |
| y = 90 mm | 0.93 kg | 0.60 kg |

**Even at y = 90 mm and about 0.85 kg the margin is thin.** The legs alone weigh 0.64 kg, so the body cannot fix this on its own. Every gram and every millimetre of stance width matters. Report the achieved numbers (§5) so Archie can decide whether the legs also need lightening or a stronger femur servo.

## 3. What "as small as possible" means: the real limits

Find the binding constraint for each item and design right up to it, with sensible clearance:
1. **Battery:** 2× 18650 at Ø18.4 × 65 mm (bare; protected cells 67–70 mm), 93 g total. That is a ~37 × 65 mm footprint side by side, or ~18 × 132 mm end to end. Battery orientation is free: choose whichever gives the smallest body.
2. **Body PCB:** it must fit the 6 leg connectors (JST-XH 4-pin, 9.8 × 5.75 mm each, vertical), USB-C, 2 buttons and the OLED header. Propose the smallest outline that still leaves room for the BMS, the six eFuses and the RP2350B: roughly **≥ 60 × 70 mm** of usable area. Report what you end up with. Stacking the PCB directly over the battery is fine and is probably the smallest arrangement.
3. **Coxa mounts:** 6 leg base mounts (`BaseServoHolder` with servo A, from `LegAssembly.FCStd`). Their spacing is set by:
   - **Coxa sweep:** adjacent legs must not collide anywhere in their yaw range.
   - **Foot-to-foot clearance in gait:** with the narrower stance, adjacent feet are closer together. Check that adjacent legs don't collide during a tripod gait with the firmware stride (±25 mm in x, `CONTROL_TESTING_GAIT_PATH_HALF_WIDTH_MM` in `control_testing.c`), plus the 15 mm y-arc and 50 mm lift in swing. Use about 10 mm minimum clearance between any parts of adjacent legs.
   - **Harness:** the harness runs through each coxa yaw joint and needs a slack loop.
4. **Ground clearance at z ≈ −80 mm:** the body's underside must stay clear of the ground. Aim for **≥ 15–20 mm** clearance at the stance height, and less while stepping on obstacles is out of scope for now. If the battery under the PCB makes this impossible, report how far apart the two are.
5. **Mass:**
   - Thin printed walls and plates.
   - The PCB as a structural plate where it helps (it was an open question; now preferred if it saves mass).
   - No decorative shell.
   - Estimate the mass of every printed part (PLA 1.24 g/cm³ × volume × an infill factor) and list it.

## 3a. Leg layout: corner legs pulled in and angled out (Archie, 2026-11-23)

To shrink the footprint, **bring the front and rear leg pairs closer in to the middle pair along the body length, and angle them outwards** instead of having all six legs point straight sideways.
- **Middle legs:** neutral yaw perpendicular to the body axis (0°).
- **Corner legs:** neutral yaw splayed out towards the front/rear. Start at **±45°** and sweep **30–60°** to find the most compact layout that passes the checks below. Report the angle chosen.
- **Spacing:** make the fore-aft spacing between the corner mounts and the middle mounts as small as possible. The coxa mounts and servo A bodies may nest closely; the angled splay is what keeps the feet and lower legs apart.
- **Parametric:** put the corner splay angle and the fore-aft mount offset in the Spreadsheet as parameters.

Checks this layout needs (it trades footprint against them):
1. **Clearance between adjacent legs**, both at the mounts and through the full gait. With the mounts closer together, the risk moves to the coxa/femur region near the body and to the corner leg's swing sweeping towards the middle leg. Apply the gait stride *in each leg's own frame* (rotated by its splay angle) and keep ≥10 mm everywhere.
2. **Static stability:** in each tripod phase, the body's centre of mass must stay inside the support triangle (front-left, middle-right, rear-left and its mirror) throughout stance. Pulling the corner feet in fore-aft shrinks those triangles. Report the minimum stability margin (distance from the CoM to the nearest triangle edge) over the gait; aim for ≥15–20 mm.
3. **Coxa yaw range:** with a 45° neutral, a corner leg uses its yaw range asymmetrically during the stride. Confirm that servo A stays within its range with margin.
4. **Joint B load: this layout can help.** In a tripod (two corner feet on one side, the middle foot on the other) with the CoM on the centreline, roll balance gives:
   - middle-leg load **F_m = W · d_c / (d_m + d_c)**
   - each corner leg's load **F_c = W · d_m / (2 (d_m + d_c))**

   Here d_m and d_c are the lateral distances (from the body centreline) of the middle and corner feet. With all feet equally far out, F_m = W/2, which is today's worst case. **Splaying the corner legs brings their feet nearer the centreline (smaller d_c), which moves load off the middle leg.** At **d_c = d_m / 2** every supporting leg carries **W/3**, which raises the stall mass from 0.54 kg to about 0.8 kg at the same lever arm. The cost is roll stability: the margin to the corner-foot line is d_c, so a smaller d_c means the robot tips more easily. Report d_m, d_c and the resulting F_m and F_c (as fractions of W) for the chosen layout. Aim for d_c ≈ 0.5–0.7 × d_m, keeping the stability margin from check 2.

Firmware note (Archie's side, no action for the CAD agent): the body IK will need each leg's mount position and splay angle. Record them in the connector/mount table in `body_geometry.md`.

## 4. Check leg geometry against CAD

The CAD femur (joint B → joint C horn-axis distance) measures **50.8 mm**. The firmware IK uses **L2 = 62 mm** (coxa ≈40 vs 36 mm, tibia ≈87 mm). **Use the real CAD geometry** for reach and clearance checks, and confirm the target stance (y ≈ 90–100, z ≈ −80) is reachable with joint angles inside the servo range. Report the measured link lengths (A→B, B→C, C→foot tip) so Archie can fix the firmware constants.

## 5. Report back

Add these to `hardware/body_board/research/body_geometry.md`, along with the original deliverables:
- the **achieved stance** (y, z) and the **body mass** breakdown (part by part), with the estimated robot total
- the **leg layout**: mount (x, y) and neutral yaw angle for all 6 legs, and the minimum tripod stability margin
- which constraint is binding: battery, PCB, leg collision, harness or ground clearance
- the measured link lengths (§4)
- minimum leg-to-leg clearance found during the gait sweep, and where it occurs
- the PCB outline, holes and connector table, as in the original handoff

The current estimate and the gait constants get re-run from these numbers afterwards. **Don't edit firmware or `research/leg_current_estimate.md` yourself.**
