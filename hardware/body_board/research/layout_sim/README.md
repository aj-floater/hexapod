# layout_sim: leg layout, gait clearance and load checks

These scripts produced the Option A leg layout in `../body_geometry.md`. They use the **real leg CAD** as point clouds (about 2 mm spacing), not a stick model.

| File | What it does |
|---|---|
| `export_leg_clouds.py` | FreeCAD macro. Exports the leg links (ground, coxa, femur, tibia) and their joint frames from `hardware/CAD/Body.FCStd` to `~/.cache/hexapod_body/leg_clouds.npz`. |
| `legsim.py` | Leg kinematics (forward and numeric inverse kinematics on the CAD geometry), the firmware gait path, and the clearance, stability and load helpers. |
| `layout_search.py` | `check <psi> <xc> <yc> [yaw_limit]` gives a full report for one layout. `sweep <yaw_limit>` sweeps splay angle and corner position. |

## Model and assumptions
- Stance y = 95 mm, z = −80 mm, in the leg frame used by the firmware: y is radial from the coxa yaw axis, z is relative to the femur-axis plane.
- Tripod gait with 60% stance, ±25 mm stride, 15 mm outward arc and 50 mm lift in swing. The stride runs two ways:
  - in each leg's own frame (the firmware's canonical path);
  - along the body X axis (straight-line walking).
- Clearance is the minimum point-cloud distance between neighbouring legs (FL/ML, ML/RL, FR/MR, MR/RR, FL/FR, RL/RR) through the gait. Target ≥ 10 mm.
- Coxa cages (holder + coxa link) of neighbouring legs must clear over the whole coxa yaw range (±30° soft limit; ±50° is the old servo range).
- Stability is the minimum distance from the centre of mass (body origin) to the support-polygon edges. Target ≥ 15 mm.
- Load split is tripod roll balance:
  - F_m = W·d_c/(d_m+d_c) on the middle leg;
  - F_c = W·d_m/(2(d_m+d_c)) on each corner leg;
  - d_m and d_c are the lateral distances of the middle and corner feet.

## Usage
```
# in FreeCAD, with Body.FCStd open (only needed when the leg geometry changes)
exec(open(".../layout_sim/export_leg_clouds.py").read())
# then, from this folder
python3 -I layout_search.py check 60 66 26 30
python3 -I layout_search.py sweep 30
```
Requires numpy. A sweep takes roughly 30–60 minutes.
