# Body geometry: hand-back to the body PCB layout and body IK

> ⚠️ **Superseded (2026-11-24).** This describes v0.2 (Option A with tray sockets). `Body.FCStd` is now v0.3, the "slot body" (legs at (0, ±45) / (±55, ±28), holders in side slots with ears, PCB at Z 25.8). That work is in progress; see `hardware/CAD/BODY_CAD_STATUS.md`. This file and `body_pcb_outline.dxf` still need refreshing for v0.3.

> **Status:** DRAFT v0.2, 2026-11-24. Compact body (Option A), from `hardware/CAD/Body.FCStd` (FreeCAD 1.1.1). For discussion; not signed off.
> Inputs: `BODY_CAD_HANDOFF.md`, *Update 01* (narrow and low stance, light body), Archie's sketches (angular top view, flattened-diamond section) and `draft.step` (the leg socket connection).
> Replaces v0.1 (plate body) and the "sandwich v2" design (archived as `hardware/CAD/Body_v2_sandwich.FCStd`).
> Re-measure after changing `Params`: run `hardware/CAD/body_measure.py` in the FreeCAD console. Re-run the layout checks with `layout_sim/` (see its README).

---

## 1. Conventions

- **Body frame:** X forward, Y left, Z up. Origin = body centre = **PCB centre** in X/Y.
- **Z = 0** is the coxa holder datum. Holder base is at Z = −4, holder top at Z = 19.8, femur (B) axis at Z = 15.75.
- **Leg frame (firmware):** y = radial distance from the coxa yaw axis (joint A) to the foot; z = foot height relative to the femur-axis plane; x = tangential.
- **KiCad:** import `body_pcb_outline.dxf` to Edge.Cuts with its origin at the board centre. KiCad's Y points down, so a body point (x, y) becomes KiCad (x, −y).
- Every dimension lives in the `Params` spreadsheet. All sketches are fully constrained and driven by it.

## 2. What was built (FreeCAD model tree)

| Object | What |
|---|---|
| `Params` | Spreadsheet: layout, stance, holder block, fasteners, shells, pack, PCB, UI positions |
| `Skeleton/LayoutSketch` | Master top-view sketch. Six yaw-axis points (from Params), inward direction lines with angle and length constraints, holder-face segments (perpendicular and symmetric), and the closed 12-edge body outline. Fully constrained. |
| `HolderV2` | PartDesign Body. The base is a **SubShapeBinder of `Parts#Body006`** (the existing BaseServoHolder; `Parts.FCStd` untouched). Adds a constrained rear-block Pad and Hole features for 2 top + 2 bottom heat-set inserts. The leg template links to it. |
| `BottomTray` | PartDesign Body. Outline binder → two-sided Pad → lower Chamfer → Thickness. Six leg sockets (boss + pocket, open to the outside, with a roof). Leg screw through-holes plus roof countersinks. 4 PCB bosses with insert holes. 2 counterbored cover-screw pillars. Pack cradle and pack-bay keep-out. |
| `TopShell` | PartDesign Body. Outline binder → Pad → shoulder Chamfer → Thickness. Cover bosses with inserts. Harness notches over each socket. OLED window. MOTORS OFF sleeve and hole. Antenna hole. USB-C and POWER openings. |
| `PCB` | PartDesign Body. Outline = skeleton binder with a 2D offset (inner wall + gap), padded 1.6 mm, Hole features. |
| `Pack` | PartDesign Body. 2S 18650 obround, 65 × 36.8 × 18.4 mm. |
| `PCB_Parts` | Keep-out placeholders for the PCB-mounted and ceiling-mounted parts (§6). |
| `BodyAssembly` | Assembly workbench. Tray grounded. Top shell, PCB, pack and parts on Fixed joints. **Six legs on Fixed joints whose `Offset1` is bound to Params** (mount position and yaw). |
| `LegTemplate` | The current leg (links into `Parts.FCStd`) with expression-driven joints. `pose` = 1 for the new stance (y 95, z −80), 0 for the old firmware stance. |

Verified: all 24 sketches are fully constrained, with no redundant or conflicting constraints. Every Body is a valid single solid. A parametric test (`legM_y` +4, `pack_L` +2) recomputes cleanly and moves the legs, tray, PCB and pack.

## 3. Leg layout (Option A): mount table for the body IK

| Leg | Coxa yaw axis (x, y) mm | Holder (neutral) yaw from +X | Neutral foot at stance (x, y) mm |
|---|---|---|---|
| FL | (66.0, 26.0) | +30° | (144.1, 80.7) |
| ML | (0.0, 52.05) | +90° | (−8.3, 147.0) |
| RL | (−66.0, 26.0) | +150° | (−152.4, 66.3) |
| FR | (66.0, −26.0) | −30° | (152.4, −66.3) |
| MR | (0.0, −52.05) | −90° | (8.3, −147.0) |
| RR | (−66.0, −26.0) | −150° | (−144.1, −80.7) |

- **Corner splay:** 60° from lateral (corner legs 30° off the body axis). This is `legC_ang` = 30.
- **Fore-aft corner offset:** 66 mm. Both are Params cells.
- **Leg plane offset:** the six legs are identical, not mirrored. Each foot sits 8.3 mm to the leg's left of its yaw-axis line (CAD), which is why FL and RL feet differ.
- **Coxa yaw (servo A):**
  - The neutral pose (all deltas zero in the IK) is the holder's +X direction, which is `coxa_zero` = −3.9° from the LegAssembly saved pose.
  - **Soft limit ±30°** (servo A 60–120°). That is required: neighbouring coxa cages collide at the full ±50°.
  - Walking uses corners −10° to +10°, middle legs ±15°.

## 4. Stance, link lengths, loads

- **Achieved stance:** y = 95 mm, z = −80 mm (target met).
  - Foot tip at body Z = −64.2.
  - Joint deltas from the LegAssembly pose: femur −33.43°, tibia −4.86°.
  - Firmware IK gives servo B ≈ 83.6°, C ≈ 118° (limits 30–130°, 20–170°).
- **Ground clearance:** tray underside Z = −6.0, so **58 mm**. Not binding.

**Measured link lengths (CAD, between horn-hub axes):**

| Link | CAD | Firmware |
|---|---|---|
| A→B (radial) | 36.9 | 36 |
| B→C | 62.1 | 62 |
| C→foot tip | 89.3 | 87 |

- B axis height: 15.75 above the holder datum.
- Leg plane offset: 8.3 mm.
- The "50.8 mm femur" in `leg_current_estimate.md` does not match the CAD horn axes. Leg v3 (`draft.step`) has B→C ≈ 43 mm.

**Tripod load split (roll balance, CoM on the centreline):**

| Quantity | Value |
|---|---|
| d_m | 147.1 mm |
| d_c | 80.7 mm |
| d_c / d_m | 0.55 |
| F_m (middle leg) | **0.35 W** (was 0.50 W) |
| F_c (each corner leg) | 0.32 W |

**Joint B at ≈0.88 kg** (W = 8.6 N, middle-leg lever 58 mm): **0.175 N·m**, which is this share of stall:

| Servo | Share of stall |
|---|---|
| MG90D at 5 V | 80% |
| **MG92B at 5 V** | **58%** |
| MG92B at 6 V | 51% |

## 5. Gait and stability checks (real leg CAD, point clouds, `layout_sim/`)

- **Gait:** tripod, 60% stance, ±25 mm stride, 15 mm arc and 50 mm lift. The stride was applied in each leg's own frame and also along body X.
- **Minimum leg-to-leg clearance: 16.2 mm.** It occurs at the front pair (FL/FR holders, across the nose) and likewise at the rear pair. Target ≥ 10 mm ✓.
  - Inside the body, the FL and FR holder blocks are about 8 mm apart, separated by their socket walls.
- **Coxa cages within ±30° yaw:** 11.3 mm.
- **Minimum tripod stability margin:** **68.1 mm** walking along X, 73.5 mm with the stride in each leg's own frame. Target ≥ 15–20 mm ✓.
- **Body interference (CAD booleans):** no leg touches the tray, top shell, PCB, pack or any component placeholder, in either pose, at coxa yaw −30°, 0° and +30°. No part overlaps another.
- **Binding constraints:**
  1. **Battery vs corner sockets** set the corner legs' fore-aft position (x = 66). The 65 mm pack corner sits 0.3 mm from the pack-bay pocket.
  2. **Front and rear pair clearance** (16 mm).
  3. **Coxa cage sweep**, which forces the ±30° yaw limit.
  4. The PCB area (4668 mm²) and ground clearance (58 mm) are not binding.

## 6. Body structure and assembly

- **Overall:** 106.7 × 61.0 mm footprint, Z −6 to 38 (44 mm tall).
- **Shape:** pointed nose and tail formed by the corner holder faces, angled shoulders, flat top. Flattened-diamond section: 4 mm lower chamfer, 8 mm shoulder chamfer.
- **Leg sockets (in the tray, based on `draft.step`):**
  - each HolderV2 rear block (10 × 18 × 23.8 mm) slides in from outside into an open socket with floor, side walls and roof;
  - **2× M3×8 button head from below** into the block's bottom inserts;
  - **2× M3×6 countersunk down through the roof** into the block's top inserts, fitted before the PCB.
  - The holes line up with the inserts to 0.000 mm.
  - The top shell comes off without touching the legs.
- **PCB:** rests on the socket roofs and 4 tray bosses (Z 22.1). **4× M3** into boss inserts at (±20, ±24).
- **Top shell:** **2× M3 (~30 mm) from below** through the tray pillars and PCB into inserts in top-shell bosses at (±38, 0). These also clamp the PCB. The top surface has no screws.
- **Battery:** fixed 2S pack (lies in the tray cradle under the PCB, charged in place). Main leads soldered to PCB pads; balance lead on a JST-XH 3-pin.
- **Inserts:** M3 heat-set, hole Ø4.0 × 5.7 deep. **Check against the insert datasheet before printing.**

## 7. PCB outline, holes, keep-outs

- **Outline:** 12-sided, 101.1 × 55.4 mm, **4668 mm²**. It is the body outline offset inwards by 2.8 mm (wall + gap), so it follows the body.
  - Vertices: (±50.54, ±4.08), (±39.57, ±23.07), (±11.77, ±27.7).
  - DXF: `body_pcb_outline.dxf` (12 lines + 6 circles, mm, PCB-centre origin).
- **PCB:** Z 22.1 to 23.7.
- **Holes (Ø3.4):** mounting (±20, ±24); cover screws (±38, 0), passing through the PCB.
- **Below the PCB:**
  - pack at Z −3.7 to 14.7, so 7.4 mm free for bottom-side parts over the pack;
  - **0 mm** over the six socket roofs (each runs about 13 mm in from the edge, at each leg face);
  - 0 mm over the bosses and pillars.
- **Above the PCB:**
  - up to 12.7 mm under the flat ceiling (Z 36.4);
  - 9.7 mm under the OLED module;
  - 6.7 mm under the receiver;
  - less within about 8 mm of the edge (shoulder slope).

**Placed parts (placeholders, centres, PCB top unless stated):**

| Part | (x, y) | Notes |
|---|---|---|
| J_FL / J_FR (JST-XH 4-pin, vertical) | (30, ±16) | Pin row along X. Harness exits through the top-shell notch at that leg's face. |
| J_ML / J_MR | (−10, ±17.3) | |
| J_RL / J_RR | (−31, ±15) | |
| USB-C | (−23, −22.2), opening −Y | Right wall, between the middle and rear legs. Top-shell opening 13 × 7.5. |
| POWER (side tactile) | (−10, −24.1), pushes −Y | Pin through the right wall. |
| MOTORS OFF (12×12 tactile) | (−22, 0) | Printed plunger through a Ø10 hole in the flat top, with a guide sleeve. |
| OLED (0.96" module) | module under the window, centre (−0.5, 0) | Screwed under the top; 4-pin cable to the header at (4, 16). |
| ELRS receiver | under the top at (24, 0) | Antenna up through a Ø4 hole at (30, 0). Header at (20, −10). |
| IMU | (0, 0) | Body centre. |
| Battery pads / balance JST-XH 3 | (−31, 7) / (−31, −7) | Fixed pack. |

**Headroom:** the JST headers have 3.2 mm clearance to the shell. A mated XH plug adds about 2.8 mm, so it is tight. Consider low-profile or side-entry connectors, or move them inboard.

## 8. Harness

- **Route:** JST → out through the top-shell notch over the socket → up the outside of the wall → strain-relief clip on the yaw axis above the coxa horn (slack loop for ±30°) → across the femur joint at its axis → J4.
- **Lengths:** routed about 177 mm per leg; **cut length 230 mm** (all six), including loops and terminations.

## 9. Mass

| Item | Mass (g) | Basis |
|---|---|---|
| Bottom tray (PLA) | 36.7 | 34.8 cm³ × 1.24 × 0.85 |
| Top shell (PLA) | 14.9 | 12.7 cm³ × 1.24 × 0.95 |
| Plunger | 0.4 | |
| 2S 18650 pack | 93 | |
| PCB (bare 13.8 + parts ≈15) | ≈29 | |
| Harnesses (6 × 230 mm × 4 wires, 26 AWG, housings) | ≈12 | estimate |
| Fasteners (24 leg screws, 4 PCB, 2 cover; 6 body inserts) | ≈19 | steel screws |
| OLED, receiver + antenna, tape/foam, leads | ≈7 | |
| **Body total** | **≈ 212 g** | target ≤ 200 g |
| Legs: 6 × (106 + MG92B 0.4 + holder block 3.0 + 4 inserts 1.1) | ≈ 663 | |
| **Robot** | **≈ 0.88 kg** | target ≤ 0.85 kg |

Ways to save weight:
- Tray at 1.6 mm walls / 15% infill: about −8 g.
- Nylon M3 for the 24 leg screws: about −8 g.
- Lighter top-shell infill: about −2 g.

These together reach about 195 g for the body.

## 10. Open questions for Archie

1. **Coxa yaw ±30° soft limit:** OK for the firmware (servo A 60–120°)?
2. **HolderV2 block** (`HolderV2` body): the block is fused to the existing holder for modelling only. Print it as part of a new holder, or as a separate glued/screwed block?
3. **Insert spec:** confirm the M3 heat-set insert dimensions (hole Ø4.0 × 5.7) and the screw lengths (M3×8 button below, M3×6 countersunk in the roof, M3×30 cover).
4. **Mass:** accept ≈212 g, or apply the savings above (nylon screws, thinner tray walls)?
5. **JST headroom:** vertical XH headers are tight under the shell. Switch to side-entry or low-profile, or keep them inboard as placed?
6. **Leg v3** (`draft.step`: in-line femur, B→C ≈ 43 mm, board under the servos, MG92B pocket) is the next task. Then re-run `layout_sim` with the new leg clouds.
7. **Firmware IK constants:** update from §4 (36.9 / 62.1 / 89.3, plus the 8.3 mm plane offset and the 15.75 B height).

## 11. Files

| File | What |
|---|---|
| `hardware/CAD/Body.FCStd` | The parametric model (§2). Links `Parts.FCStd`, so keep it in the same folder. |
| `hardware/CAD/Body_v2_sandwich.FCStd` | Archived previous design. |
| `hardware/CAD/body_measure.py` | Prints the mount, connector and harness table and the heights. |
| `hardware/body_board/research/body_pcb_outline.dxf` | Edge.Cuts plus holes. |
| `hardware/body_board/research/layout_sim/` | Layout, gait, clearance and load analysis (README inside). |

`LegAssembly.FCStd` and `Parts.FCStd` were only read (a binder and links point to them). Nothing has been committed.
