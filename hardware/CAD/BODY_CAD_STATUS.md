# Body CAD: status and handoff (for the next agent)

> Written 2026-11-24 when work moved from Archie's laptop to the Steam Deck. Branch: `body-cad-option-a`.
> **Read this first**, then the two briefs in `reference/` (see §1).
> Rules that still apply:
> - Never save over `LegAssembly.FCStd` or `Parts.FCStd`; they are inputs.
> - Don't commit unrelated work.
> - Archie prefers to do simple GUI steps himself, and wants the proper FreeCAD workflow (constrained sketches, PartDesign features, Assembly), not scripted Part primitives.
> - Archie does not need saved view images.

---

## 1. What this is

A compact, light hexapod body in FreeCAD (`hardware/CAD/Body.FCStd`). Its job is to fix the leg geometry and provide the numbers the body PCB and body IK need.

Briefs (copies are committed in `hardware/body_board/`):
- `BODY_CAD_HANDOFF.md`: the original brief (Part 2).
- `BODY_CAD_UPDATE_01_compact_stance.md`: **overrides** the original where they conflict. Narrow, low stance (y ≈ 95, z ≈ −80), body ≤ 200 g, corner legs pulled in and splayed out. Report the mass, the binding constraints and the link lengths.

Archie's design inputs (in `hardware/CAD/reference/`):

| File | Meaning |
|---|---|
| `sketch_top_view_body_and_legs.png` | Angular body outline (light grey), compact PCB (green), corner legs pulled in and splayed out |
| `sketch_front_section_diamond.png` | Front section: flattened diamond (flat top, angled shoulders, legs plug in at the waist). Looks only. |
| `sketch_leg_femur_board_under.png` | Leg idea for later: shorter femur housing, with the smart-servo board moved under the servo pair |
| `sketch_slot_outline_iso.png`, `sketch_slot_outline_top_view.png` | **Current direction:** the body wall comes out beside each holder (holders sit in slots). Two screws either side of each holder (green circles). |
| `draft_leg_v3_and_socket.step` | Shapr3D draft. "leg v3" has an in-line femur, B→C ≈ 43 mm, with the board under the servos (the intent for a future leg task; do not replace the current leg with it). It also has a body socket/sandwich connection draft. |

## 2. Decision log (all from Archie unless noted)

| Date | Decision |
|---|---|
| 2026-11-23 | Femur servo (joint B) → **TowerPro MG92B** (about 0.30 N·m at 5 V). Suggested: raise the leg board's motor buck to about 6 V (R1 40.2k → 48.7k) for about 0.34 N·m. |
| 2026-11-24 | Layout family "Option A": middle legs perpendicular, corner legs splayed **60° from lateral** (holder 30° off the body X axis). **Coxa yaw soft limit ±30°** (servo A 60–120°), because coxa cages collide at ±50°. |
| 2026-11-24 | Stance **y = 95, z = −80** (leg frame: y radial from the yaw axis, z relative to the femur-axis plane). |
| 2026-11-24 | Battery: **fixed 2S 18650 pack** (65 × 36.8 × 18.4 obround), charged in place, under the PCB, cells along X. |
| 2026-11-24 | Two printed parts (bottom tray + top shell), M3 heat-set inserts, no standoffs, **all screws from underneath**. Keep a thin top shell (looks: flat top, chamfered shoulders). |
| 2026-11-24 | **Slot body (current):** the body wall comes out to about 8 mm inboard of each coxa yaw axis. Holders sit in slots in the body side and are fixed by **two side ears** (see §3). Legs pulled in and re-optimised. |
| 2026-11-24 | PCB placed **high (above the ear ledges)** for board area (~4600 mm²); body top Z 42. |
| 2026-11-24 | Leg interference checks in FreeCAD **should not be run any more**: full-STEP leg booleans freeze FreeCAD for 10+ minutes. Use `layout_sim` (point clouds) and small targeted checks instead. |

History:
- v0.1 (plates), "sandwich v2" (archived as `Body_v2_sandwich.FCStd`), then v0.2 (Option A with tray sockets, commit `44b1932`; documented in `hardware/body_board/research/body_geometry.md`).
- **The current file is v0.3 (slot body), in progress.** `body_geometry.md` still describes v0.2.

## 3. Current model (Body.FCStd v0.3)

Everything is driven by the **`Params`** spreadsheet. Frame: X forward, Y left, Z up; Z = 0 is the coxa holder datum (holder base Z −4, top Z 19.8). "s" = distance inboard of a leg's yaw axis; "t" = sideways from the leg axis.

**Key Params:**

| Group | Values |
|---|---|
| Middle legs | yaw axes at (0, ±`legM_y` = 45), holders at ±90° |
| Corner legs | yaw axes at (±`legC_x` = 55, ±`legC_y` = 28), front holders at ±`legC_ang` = 30° from +X, rear at ±150° |
| Wall corners | `s_out` = 8 (corners); `s_out_m` = 5.54 (middle; computed so the long sides are straight, which keeps the outline convex) |
| Slots | `slot_in` 15.5 (half-width incl. clearance), `slot_half` 17.5 (+ wall) |
| Ears (HolderV2) | from the holder inner face (s 21.55) out to `ear_out` 9.5; width `ear_w` 7 beside the holder (t 8.2 → 15.2); full holder height. Bottom insert at s `ear_ins_s` 18.5; through-hole at s `ear_thru_s` 12.5. |
| Heights | tray underside `z_bot` −6, `split_z` 19.8 (= holder top), ledge `ledge_t` 5.5 (top-shell ledge over the ears, Z 19.8–25.3), `pcb_z` 25.8 (PCB 25.8–27.4), `top_z` 42, `top_ch` 8 (shoulder chamfer), `bot_ch` 2.5, walls `tray_t` 2 / `top_t` 1.6 |
| Sweep relief | `sweep_s` 12.6 (the coxa top bracket swings in to 10.6 mm inboard above Z 26) |
| Stance | `pose` 1 = new stance (femur −33.43°, tibia −4.855° deltas from the LegAssembly saved pose), 0 = old firmware stance; `coxa_zero` −3.9; `stance_coxa` = test yaw offset |

**Model tree:**
- **`Skeleton/LayoutSketch`**: master outline. Per leg there is a construction point at the yaw axis, an inward direction line (angle and length constraints) and a face segment (perpendicular, symmetric, width `2*slot_half`, at distance `s_out` or `s_out_m`). Connector edges close the outline. Fully constrained; every part derives from it through SubShapeBinders.
- **`HolderV2`** (PartDesign): BaseFeature = SubShapeBinder of `Parts#Body006` (the original BaseServoHolder; `Parts.FCStd` untouched). Adds `EarPad` and `EarInserts` (bottom, Ø`ins_d` × `ins_l`). Has through-holes (`EarThroughHoles`, Ø3.4). The leg template's `L_BaseServoHolder` link points to HolderV2.
- **`BottomTray`** (PartDesign), in this order:
  1. Pad (two-sided) → Thickness (open top) → Chamfer (outer bottom edges). The order matters, see §6.
  2. PCB bosses with inserts at (±23, ±24), up to `pcb_z`.
  3. Pack cradle and pack-bay keep-out.
  4. `SlotBoss` (U-walls, starting at `z_bot+bot_ch`) → `SlotPocket` (open slot).
  5. `EarScrewHoles`: Ø3.4 through the floor at both ear screw positions, for screws from below.
- **`TopShell`** (PartDesign), in this order:
  1. Pad → `ShoulderChamfer` → `Cavity` + `CavityTaper` (hollowing by pockets from offset binders, because Thickness fails here; see §6).
  2. OLED window, MOTORS OFF sleeve and hole, antenna hole.
  3. `LedgeBoss` (ear clamp ledges, Z 19.8–25.3).
  4. `ColumnWall` + `SweepWall` (walls around the openings above the ledge).
  5. `SweepRelief` (opening above the ledge for the coxa bracket sweep, |t| ≤ `slot_in`, s ≤ `sweep_s`).
  6. `HolderCut` (coxa servo column, full height).
  7. `LedgeInserts` (short M3 inserts, `ins_short_l` 4.3, from below).
  8. USB-C and POWER openings (right wall).
  9. `MidMouthRelief` (middle slots: cut back to `s_out` above the ledge).
- **`PCB`** (PartDesign): offset binder of the outline at `pcb_z` → Pad 1.6 → notches around each servo column and sweep zone → 4 M3 holes. About 4584 mm², bounding box 108 × 73.
- **`Pack`**: obround PartDesign body.
- **`PCB_Parts`**: keep-out placeholders (Part boxes placed by expressions). Leg JSTs sit on each leg axis at `jst_s` = 30 inboard. Also USB-C, POWER, MOTORS OFF tactile and plunger, OLED (ceiling-mounted), ELRS receiver and antenna, IMU, battery pads, balance JST.
- **`BodyAssembly`** (Assembly workbench):
  - TrayLink is grounded.
  - Fixed joints for the top shell, PCB, pack and parts.
  - **Six leg links** (`Leg_FL` … `Leg_RR`) on Fixed joints whose `Offset1` is bound to Params (position and yaw).
  - Joint references use the **component-rooted form** `[component, ["", ""]]`.
- **`LegTemplate`**: the current leg (links into `Parts.FCStd`) with expression-driven joints (CoxaJoint / FemurJoint / TibiaJoint angles from Params). `FootTip` and `J4Top` marker spheres.

**Fastening per leg (all from below):**
- 2× M3 up through the tray floor into the **ear bottom inserts**. These hold the leg to the tray.
- 2× M3 up through the tray floor and the **ear through-holes** into the **top-shell ledge inserts**. These clamp the top shell.
- So the top shell comes off without loosening the legs.
- The PCB uses 4× M3 into the tray boss inserts.

## 4. Verified so far (v0.3)

- 27 sketches, all fully constrained with no redundancy. HolderV2, BottomTray, TopShell, PCB and Pack are each one valid solid.
- Screw holes line up exactly (XY offset 0.000 mm) across all three parts: tray ↔ HolderV2 ear holes ↔ top-shell ledge inserts.
- No overlaps between body parts and component placeholders. The pack is 0.3 mm from the tray. The JSTs have about 3.7 mm below the ceiling.
- `layout_sim` (`layout_slots.py check 45 60 55 28`):
  - leg-to-leg gait clearance 20.2 mm (front and rear pairs);
  - stability margin 61 mm;
  - coxa cages within ±30°: 15.1 mm;
  - d_c/d_m 0.59, F_m 0.37 W, F_c 0.31 W.
- Ears against their own leg's moving coxa parts (point clouds, ±30°): 6.9 mm.
- Volumes: tray 43.0 cm³, top shell 27.5 cm³, ears +3.5 cm³ per leg.
- Mass estimate **about 225 g** (target ≤ 200 g, so mass work is still to do):
  - printed about 76 g;
  - pack 93 g;
  - PCB about 29 g;
  - harness about 12 g;
  - fasteners about 18 g.

## 5. OPEN ISSUE and next steps (in order)

1. **Coxa top bracket graze (open, must fix).**
   - At coxa yaw ±30°, each leg's `ServoArm` (top coxa bracket, Z 31.8–36) touches the top shell's **SweepWall** inner faces.
   - Contact is at s 8.0–8.6 mm inboard, |t| 15.5–15.7, overlap 0.06–0.16 mm³ per leg.
   - Fix options:
     - (a) Add a Params cell `sweep_t` (≈ 17) and use it for the `SweepRelief` width and the PCB sweep notch instead of `slot_in`. Check that `SweepWall` (width `2*(sweep_t+top_t)`) does not poke outside the outer wall near the slot mouth; if it does, start it at a larger s or drop it there.
     - (b) Cut the sweep relief back to `s_out` + a margin for all legs, like `MidMouthRelief`.
   - Re-check with the quick targeted check: only the `CoxaJoint` children placed by each `Leg_*` placement at yaw −30/0/+30, against the TopLink/TrayLink shapes. That takes seconds; **do not** run whole-leg booleans.
   - Aim for ≥ 1 mm clearance.
2. **Mass down to ≤ 200 g:**
   - tray walls 1.6 or lighter infill (tray is 43 cm³);
   - review the top-shell skin and the U-wall heights;
   - nylon M3 for the leg screws;
   - possibly lower `top_z` now that the PCB layout is known.
3. **Hand-back refresh (v0.3):**
   - run `hardware/CAD/body_measure.py` (mount table, J positions, harness cut lengths);
   - re-export `hardware/body_board/research/body_pcb_outline.dxf` from the PCB pad outline + the 4 holes (see §7);
   - rewrite `hardware/body_board/research/body_geometry.md` for v0.3: mounts, stance, mass, binding constraints, keep-outs (PCB at Z 25.8; pack below with 11 mm of headroom for bottom-side parts), connector table.
4. **Commit and push** on `body-cad-option-a` once the graze is fixed and verified.
5. **Later, a separate task: leg v3.** Use the in-line femur from `reference/draft_leg_v3_and_socket.step` (B→C ≈ 43 mm, board under the servos), plus the MG92B pocket (about 2.5 mm taller than the MG90D) and HolderV2 ears. Then re-export the leg clouds (`layout_sim/export_leg_clouds.py`) and re-run `layout_slots.py`.
6. **For Archie / firmware (not CAD):**
   - servo A soft limits ±30°;
   - IK constants from CAD: A→B 36.9 radial, B axis 15.75 above the holder datum, leg-plane offset 8.3, B→C 62.1, C→foot tip 89.3;
   - the "50.8 mm femur" in the leg current estimate does not match the CAD horn axes.

## 6. FreeCAD 1.1.1 scripting gotchas (learned the hard way)

- **Recompute after every PartDesign feature** before adding the next one ("Base feature's TopoShape is invalid" otherwise). `body_sketch_helpers.feature()` does this and raises if the result is not one valid solid.
- **Two-sided Pad:** `SideType = "Two sides"`. The `Type` enum no longer has `TwoLengths`.
- **Thickness fails on chamfered solids when the outline has concave corners or short chamfered edges.** Use Pad → Thickness → Chamfer (tray, small chamfer), or hollow with Pockets from offset SubShapeBinders (top shell). Keep the outline convex (`s_out_m`).
- **Coplanar faces:** a pad whose face lies exactly in the outer-wall plane can fuse to nothing. Start bosses 0.3 mm inboard, and start slot walls above the bottom chamfer.
- **Assembly joint refs:** `[component, ["", ""]]` (rooted at the component). `[assembly, ["Name.", "Name."]]` makes the solver move the *assembly container* (that happened once; `BodyAssembly.Placement` must stay identity).
- **Don't delete App::Origin objects** (App::Part breaks: "Can't find Origin"). New documents must be **saved once** before they can hold links to other files.
- **SubShapeBinder of an object inside an App::Part** bakes in the container placement. Bind the inner Body directly for local coordinates.
- **Never** run `distToShape`/booleans of whole legs (244 STEP solids) in the GUI thread: it froze FreeCAD twice. Use `layout_sim` point clouds, or only the small coxa parts.
- Sketch helpers: when a sketch gets several circle pairs per leg, give a constraint-tag suffix (`sfx=`), or the constraint names clash.

## 7. Setup on a new machine (Steam Deck)

1. Install the FreeCAD **1.1.x** flatpak and the MCP addon. Archie's laptop used neka-nat/freecad-mcp v0.1.32: the server is in `~/Coding/freecad-mcp`; the addon `FreeCADMCP` goes in the flatpak `Mod` folder. Start the RPC server (MCP Addon workbench → Start RPC Server, or tick Auto-Start).
2. Open `hardware/CAD/Body.FCStd`. It loads `Parts.FCStd` from the same folder through its links.
3. Paths in scripts are written for `/home/arjames/Coding/hexapod`. Adjust them, e.g. `exec(open("<repo>/hardware/CAD/body_sketch_helpers.py").read())`.
4. `layout_sim` needs numpy, and leg clouds in `~/.cache/hexapod_body/leg_clouds.npz`. They are not in git; regenerate them by running `layout_sim/export_leg_clouds.py` inside FreeCAD with Body.FCStd open (pose 1).
5. DXF export of the PCB (Edge.Cuts + holes, z = 0, board-centre origin):

   ```python
   import FreeCAD as App, Part, importDXF
   bd = App.getDocument("Body"); pcb = bd.getObject("PCB").Shape
   bottom = [f for f in pcb.Faces if f.BoundBox.ZLength < 1e-6 and abs(f.BoundBox.ZMin - bd.getObject("Params").pcb_z) < 1e-6][0]
   edges = Part.makeCompound(bottom.Edges); edges.translate(App.Vector(0, 0, -bottom.BoundBox.ZMin))
   tmp = bd.addObject("Part::Feature", "tmp_dxf"); tmp.Shape = edges
   importDXF.export([tmp], "<repo>/hardware/body_board/research/body_pcb_outline.dxf"); bd.removeObject(tmp.Name)
   ```

## 8. Files

| Path | What |
|---|---|
| `hardware/CAD/Body.FCStd` | The model (v0.3 in progress) |
| `hardware/CAD/Body_v2_sandwich.FCStd` | Archived earlier design |
| `hardware/CAD/Parts.FCStd`, `LegAssembly.FCStd` | Leg inputs (read-only for body work) |
| `hardware/CAD/body_sketch_helpers.py` | Constrained-sketch + feature helpers used to build the model |
| `hardware/CAD/body_measure.py` | Mount, connector and harness table (v0.3 route through the slot opening) |
| `hardware/CAD/reference/` | Archie's sketches and `draft_leg_v3_and_socket.step` |
| `hardware/body_board/BODY_CAD_HANDOFF.md`, `BODY_CAD_UPDATE_01_compact_stance.md` | Briefs |
| `hardware/body_board/research/layout_sim/` | Kinematics, gait clearance, stability and load sweeps. `layout_slots.py` is for the slot body; `slots_ym*.json` are the sweep results. |
| `hardware/body_board/research/body_geometry.md`, `body_pcb_outline.dxf` | **v0.2** hand-back (to be refreshed for v0.3) |

The body PCB specification (`SPEC.md`, `HANDOFF.md`, `leg_current_estimate.md`) lives on Archie's laptop with a separate agent and is not in this branch. The key leg-torque numbers are already in §2 and §5.
