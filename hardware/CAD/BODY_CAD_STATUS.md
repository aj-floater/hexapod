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
| 2026-11-24 | Coxa top-bracket graze fixed by option (b): the top shell is cut back above the ledge to `mouth_s` 10.6 at all six mouths (option (a), widening the relief to |t| 17.3, would leave a 0.2 mm knife-edge at the corner-mouth lip). New tray `HubRelief` gives the middle legs' lower coxa hub 1 mm. |
| 2026-11-24 | **Top shell rebuilt as `TopShellV2`** (old `TopShell`, its patches and `mouth_s`/`mouth_wc` deleted): clean hollow by Boolean with a `TopCavityTool` body, closed roof, one flared `ShoulderNotch` per leg, full ledge blocks, 2 mm walls + roof round each servo column (kept despite +7.8 cm³). PCB notches now derive from the housing sketches. |
| 2026-11-24 | **Ear ledges shortened to `ledge_s` 16.5** (ledge insert edge + wall). The full ledges ran to s 23.85 under the PCB, so the top shell could not be lowered onto a PCB already screwed to the tray (pre-existing in v0.3). The PCB keep-out now includes the ledges: one straight edge per leg. The ears stay held by the tray screws at s 18.5. |
| 2026-11-24 | **HolderV2 shaved by Archie** (Sketch → Pocket → Draft ×2): each ear's inboard-outer corner cut at 45° in plan (s + \|t\| ≥ 29.68) above Z 6.3, with a 45° sloped underside up to Z 11.3; also `Pad`/`Pad001` fill the holder sides \|t\| 6.2–8.2 from s 5.0 to 17.15, Z −4 to 9.8. These sketches are not Params-driven yet. |
| 2026-11-24 | **Tray slot corners folded to follow the ear shave** (Archie modelled RL +t by hand; replaces the scripted `SlotCornerRelief`, which cut holes from the slots into the tray). A 2 mm wall on the 45° line 0.3 mm outside the ear shave, with 45° sloped undersides (printable), patterned to all 12 corners by two MultiTransforms. |
| 2026-11-24 | **Top shell split plane matched to the tray** (tray takes priority): `LedgeBlock` now follows the tray U-wall outline (\|t\| ≤ `slot_half`, 45° fold, back wall at s 23.85), so it runs inboard past `ledge_s` again; `ColumnHousing` corners cut on the same fold line; `NotchHousing` starts at the ledge top. **PCB keep-out ignored for now** (`PcbHousingNotch` is broken: "Wires are not coplanar"; redo the PCB outline later). |
| 2026-11-24 | **Shoulder-opening cap (Archie, `Pad003`/`Pocket002`) on all six openings**: a 2 mm cross wall at s `sweep_s`…+`house_t` and a 2 mm floor (Z 25.3–27.3) over the column cavity, with the column housing opened into the main cavity inboard of it. −256 mm³ per opening. |
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
| Shoulder notch / housings | `fold_len` 10 (tray slot-corner fold, see below), `sweep_t` 16 (notch half-width), `flare_s` 10 (45° flare outboard of it), `house_t` 2 (notch and column walls), `col_top` 34.7 (column roof underside; servo top Z 33.7), `ledge_s` 16.5 (ear ledge inboard end), `hub_r` 6.75 (tray relief round the middle yaw axes; coxa lower-arm hub r 5.75 reaches Z −4.45) |
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
  6. `HubRelief`: Ø`2*hub_r` through-all at the two middle yaw axes (a 1.6 mm³ crescent off the floor edge).
  7. Slot corners (RL +t corner, built by Archie): `Sketch003` (on the tray top, Z 19.8; two 45° lines 2 mm apart, from external refs to the slot pocket and U-wall outer edges; fold length `fold_len` and wall `tray_t` now bound to Params) →
     `Sketch004` → `Pad002` (fills the slot corner inside the inner line, Z 19.8 → 11.3) → `Sketch005` → `Pocket001` (cuts the U-wall corner outside the outer line, Z 19.8 → 13.3) →
     `Draft002` / `Draft003` (45° on the pad underside and pocket floor, so both run parallel to the ear's sloped underside). Net −32.6 mm³ per corner; 0.300 mm to HolderV2 at every corner.
  8. `CornerMT_Legs` (MultiTransform of those four features): mirror on `RL_LegAxisPlane` × mirror YZ × mirror XZ → the 8 corner-leg corners.
     `CornerMT_Mid`: `CornerMT_RL2ML` (polar, 2 occurrences, angle `90 − legC_ang`, reversed, about `RL2ML_Axis`) × mirror YZ × mirror XZ → the 4 middle-leg corners (3 copies duplicate corner-leg ones; harmless).
     Datums: `RL_LegLCS` (RL yaw axis, X outward) → `RL_LegAxisPlane` (its XZ); `RL2ML_LCS` (centre of the rotation taking RL onto ML, Params expressions) → `RL2ML_Axis`.
- **`TopShellV2`** (PartDesign), in this order:
  1. `ShellOutline` (binder of `LayoutSketch` at `split_z`) → `ShellPad` → `ShellChamfer` (`top_ch`).
  2. `Hollow`: Boolean cut of the **`TopCavityTool`** body, which is the outline offset by −`top_t` → `CavityPad` → `CavityChamfer` (size `top_ch − top_t·(2−√2)`, so the inner chamfer is parallel to the outer one; 1.6 mm skin everywhere, all planar faces) → pockets where the shell must stay solid:
     - `LedgeBlock`: ear clamp ledges, Z 19.8–25.3, the tray U-wall outline (|t| ≤ `slot_half`, outer fold line s + |t| = `hold_face + clr + slot_in − fold_len/√2 + tray_t·√2`, inboard to `hold_face + clr + tray_t`). `ledge_s` is no longer used.
     - `NotchHousing`: walls round each shoulder notch (flared outline), from the ledge top up.
     - `ColumnHousing`: walls + roof round each servo column, up to `col_top + top_t`; inboard corners cut on the fold line.
  3. `ColumnPocket`: |t| ≤ `ear_t0 + clr`, out to `hold_face + clr`, Z `split_z` → `col_top`.
  4. `ShoulderNotch`: from the ledge top up through the shoulder; |t| ≤ `sweep_t` out to `flare_s`, then 45° flare; inner end at `sweep_s`.
  5. `LedgeInserts2` (flat-bottomed now; the old 118° drill tips reached the ledge top), OLED window, MOTORS OFF sleeve and hole, antenna, USB-C, POWER (copied sketches, same Params).
  6. Opening cap (FL, Archie's design, now Params-driven): `CapSketch` on `FL_NotchEndPlane` (s `sweep_s`) → `Pad003` (10 mm inboard, |t| ≤ `ear_t0 + clr`, Z ledge top → `col_top`); `CapPocketSketch` on `FL_ColumnBackPlane` (s `hold_face + clr + house_t`) → `Pocket002` (back to s `sweep_s + house_t`, |t| ≤ `ear_t0 + clr + house_t`, Z ledge top + `house_t` → `col_top + top_t`). Datums hang off `FL_LegLCS` (FL yaw axis, X outward).
  7. `CapMT_Legs` (mirror YZ × mirror XZ → FL/RL/FR/RR) and `CapMT_Mid` (`CapMT_FL2ML` polar about `FL2ML_Axis`, angle `90 − legC_ang` × mirror XZ → ML/MR; FL/FR copies duplicate, harmless). `Sketch008` is an empty sketch of Archie's, left in place.
  - Leg sketches use `add_leg_rect` / the new `add_leg_poly` (vertices fixed by Params expressions in the leg frame). `build_topshell_v2.py` is the one-off record of how it was built.
- **`PCB`** (PartDesign): offset binder of the outline at `pcb_z` → Pad 1.6 → 4 M3 holes → `PcbHousingNotch` (pocket from `PcbHousingKeepout`, a binder of the top shell's `NotchHousingSketch` + `ColumnHousingSketch` + `LedgeBlockSketch` offset by `pcb_gap2`, so the PCB follows the housings and ledges automatically). About 4230 mm² (4584 in the old design), bounding box 108 × 73.
  - **Assembly rule:** no top-shell material below the PCB top (Z 27.4) may lie inside the PCB outline, or the shell can't be lowered onto the mounted PCB. Checked: 0.000 mm³.
- **`Pack`**: obround PartDesign body.
- **`PCB_Parts`**: keep-out placeholders (Part boxes placed by expressions). Leg JSTs sit on each leg axis at `jst_s` = 30 inboard. Also USB-C, POWER, MOTORS OFF tactile and plunger, OLED (ceiling-mounted), ELRS receiver and antenna, IMU, battery pads, balance JST.
- **Colours** (match the leg models): HolderV2 + BottomTray black `#202020` (like the original holder), TopShellV2 purple `#aa00ff` (like the printed leg brackets), PCB green `#4c930a`, Pack slate `#2f4f6f`. Parts are shown through their assembly links; the raw bodies (and `TopCavityTool`) stay hidden.
- **`BodyAssembly`** (Assembly workbench):
  - TrayLink is grounded.
  - Fixed joints for the top shell, PCB, pack and parts.
  - **Six leg links** (`Leg_FL` … `Leg_RR`) on Fixed joints whose `Offset1` is bound to Params (position and yaw). They now link to `LegStatic` (holder + base servo only).
  - **Articulated legs (2026-11-24):** per leg `Coxa_*` / `Femur_*` / `Tibia_*` links (to `LegCoxa` / `LegFemur` / `LegTibia`) on Revolute joints `CoxaRev_*` (Leg → Coxa), `FemurRev_*` (`Offset1` = `FemurFrame.Placement`), `TibiaRev_*` (`Offset1` = `TibiaFrame.Placement`). Drag them in the Assembly workbench. Coxa limits `coxa_zero ± coxa_limit` are set but a plain `solve()` does not enforce them. `leg_stance.py` puts every leg back in the Params stance and re-solves (also resets the grounded tray to the origin: a bad solve once tilted it 0.19°).
  - Joint references use the **component-rooted form** `[component, ["", ""]]`.
- **`LegTemplate`**: the current leg (links into `Parts.FCStd`) with expression-driven joints (CoxaJoint / FemurJoint / TibiaJoint angles from Params). `FootTip` and `J4Top` marker spheres. No longer shown in the assembly, but still the source of truth: `coxa_sweep_check`, `body_measure` and `export_leg_clouds` read it, the assembly joint frames are bound to it, and `LegStatic` / `LegCoxa` / `LegFemur` / `LegTibia` hold links to the same parts with the same placements (built by `build_leg_joints.py`; re-run it if parts are added to the template).

**Fastening per leg (all from below):**
- 2× M3 up through the tray floor into the **ear bottom inserts**. These hold the leg to the tray.
- 2× M3 up through the tray floor and the **ear through-holes** into the **top-shell ledge inserts**. These clamp the top shell.
- So the top shell comes off without loosening the legs.
- The PCB uses 4× M3 into the tray boss inserts.

## 4. Verified so far (v0.3)

- 26 sketches, all fully constrained with no redundancy. HolderV2, BottomTray, TopShellV2, TopCavityTool, PCB and Pack are each one valid solid.
- TopShellV2: 222 faces (old shell 295, incl. 22 BSplines), all planar except holes; no slivers (remaining sub-1 mm edges are where the angled notch cuts cross the skin).
- Screw holes line up exactly (XY offset 0.000 mm) across all three parts: tray ↔ HolderV2 ear holes ↔ top-shell ledge inserts (re-checked on TopShellV2).
- No overlaps between body parts and component placeholders (re-checked on TopShellV2). Placeholders hanging off the board edge: corner leg JSTs about 0.9 mm into the column notch (move `jst_s` 30 → 31); **USB-C and POWER sit over the MR notch zone** (POWER at s 11.5, t 15 from the MR axis; already cut away in the v0.3 PCB too), so move them along X in the PCB layout. The pack is 0.3 mm from the tray. Leg JSTs 3.3 mm from the shell; `BAT_PADS` only 0.19 mm from the RR column wall (was 0.59), so move the pads about 1 mm on the PCB. OLED glass and ELRS rx touch the roof underside (ceiling-mounted, intended).
- Static leg parts vs TopShellV2: coxa servo 0.37 mm at the column end (the 0.3 fit clearance, same as before), 1.0 mm under the column roof; the holder top touches the ledge underside (the clamp face).
- `layout_sim` (`layout_slots.py check 45 60 55 28`):
  - leg-to-leg gait clearance 20.2 mm (front and rear pairs);
  - stability margin 61 mm;
  - coxa cages within ±30°: 15.1 mm;
  - d_c/d_m 0.59, F_m 0.37 W, F_c 0.31 W.
- Ears against their own leg's moving coxa parts (point clouds, ±30°): 6.9 mm.
- Coxa sweep (`coxa_sweep_check.py`, coxa-level parts only, ±30°): ServoArm ↔ TopShellV2 **1.17 mm** (worst at ±30°), lower Arm ↔ tray **1.00 mm** middle / 2.75 mm corner, coxa ↔ PCB 18.2 mm.
- Split plane (Z 19.8) tray vs top shell: the only shell-only areas are the 12 ear clamp pads; tray-only are the PCB bosses and 0.4 mm strips on the ±X end walls and the long-side walls, where the tray wall (`tray_t` 2) is thicker than the shell skin (`top_t` 1.6). Coxa sweep and static servo clearances unchanged (1.17 / 0.37 mm).
- Volumes: tray 42.6 cm³ (corners folded; 43.0 before), **top shell 30.4 cm³** after the split-plane match + opening caps (31.3 before; 35.0 before the ledge shortening: ledges 10.3, notch walls 6.7, column walls + roof 7.8, skin 9.8; the old patched shell was 26.6 with thinner walls and holes in the roof), ears +3.5 cm³ per leg.
- `layout_slots.py` on the 2026-11-24 Steam Deck re-export: clearance reads 8.1 mm (FL/FR ground/ground, static) instead of 20.2, because the ground cloud now includes the HolderV2 ears (|t| ≤ 15.2), and `layout_slots` also adds the ears again. Stability, d_c/d_m and loads are unchanged. Decide whether the static ear-to-ear figure should count toward the 10 mm gait target.
- Mass estimate **about 229 g** after the shell rebuild (target ≤ 200 g, so mass work is still to do):
  - printed about 80 g (was 76 g; +4.7 cm³ top shell at the same ~0.83 g/cm³ printed density);
  - pack 93 g;
  - PCB about 29 g;
  - harness about 12 g;
  - fasteners about 18 g.

## 5. OPEN ISSUE and next steps (in order)

1. ~~Coxa top bracket graze~~: **fixed 2026-11-24** (see §2, §4). Re-check with `exec(open("<repo>/hardware/CAD/coxa_sweep_check.py").read())` (about 25 s).
2. **Mass down to ≤ 200 g:**
   - tray walls 1.6 or lighter infill (tray is 43 cm³);
   - top shell: column walls + roof are 7.8 cm³ (kept by choice 2026-11-24; dropping them is the biggest single saving), `house_t` 2 → 1.6, ledge blocks now about 6.6 cm³;
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

1. Install the FreeCAD **1.1.x** flatpak and an MCP addon.
   - Laptop: neka-nat/freecad-mcp v0.1.32 (server in `~/Coding/freecad-mcp`, addon `FreeCADMCP` in the flatpak `Mod` folder, start its RPC server).
   - **Steam Deck:** FreeCAD 1.1.4 with the CREATeNG **MCP Bridge** addon (v0.1.30), streamable HTTP at `http://127.0.0.1:39280/mcp` with a bearer token; switch it "MCP On" in the status bar. numpy for `layout_sim` outside FreeCAD: `sudo dnf install python3-numpy` in dev-fedora.
   - Performance on the Deck: the legs are about 2 M triangles (the smart-servo board STEP alone is 134k per leg). `L_smart_servo_v2` is hidden in `LegTemplate` and anti-aliasing is set to MSAA 2×.
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
| `hardware/CAD/build_leg_joints.py`, `leg_stance.py` | One-off build of the articulated legs; reset legs to the Params stance |
| `hardware/CAD/coxa_sweep_check.py` | Quick coxa-yaw sweep: coxa-level parts vs top shell / tray / PCB (about 25 s) |
| `hardware/CAD/body_measure.py` | Mount, connector and harness table (v0.3 route through the slot opening) |
| `hardware/CAD/reference/` | Archie's sketches and `draft_leg_v3_and_socket.step` |
| `hardware/body_board/BODY_CAD_HANDOFF.md`, `BODY_CAD_UPDATE_01_compact_stance.md` | Briefs |
| `hardware/body_board/research/layout_sim/` | Kinematics, gait clearance, stability and load sweeps. `layout_slots.py` is for the slot body; `slots_ym*.json` are the sweep results. |
| `hardware/body_board/research/body_geometry.md`, `body_pcb_outline.dxf` | **v0.2** hand-back (to be refreshed for v0.3) |

The body PCB specification (`SPEC.md`, `HANDOFF.md`, `leg_current_estimate.md`) lives on Archie's laptop with a separate agent and is not in this branch. The key leg-torque numbers are already in §2 and §5.
