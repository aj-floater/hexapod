# body_measure.py - FreeCAD macro for Body.FCStd (compact body, Option A)
# Prints the numbers the body PCB layout and the body IK need: leg mount table,
# leg connector positions and harness lengths, plus key heights.
# Usage (FreeCAD Python console, with Body.FCStd open):
#   exec(open("/home/arjames/Coding/hexapod/hardware/CAD/body_measure.py").read())

import math
import FreeCAD as App

# Section Setup
bd = App.getDocument("Body")
P = bd.getObject("Params")
bd.recompute()
bd.getObject("BodyAssembly").solve()

PCB_TOP = P.pcb_z + P.pcb_t
CONN_TOP = PCB_TOP + 10.0            # mated JST-XH plug top, where the wires leave
NOTCH_Z = P.split_z + P.notch_h / 2  # harness passes the top-shell notch here
CLIP_Z = 40.0                        # strain-relief clip above the coxa horn (horn top z = 36.6)
RISE_IN = 3.5                        # rise outside the wall, between wall and coxa servo (servo at 15.75 from axis)
YAW_LOOP = 2 * math.pi * 10 * (60 / 360.0)     # r = 10 slack loop for +-30 deg coxa yaw
FEMUR_LOOP = 2 * math.pi * 10 * (100 / 360.0)  # r = 10 loop for ~100 deg femur travel
TERMINATIONS = 2 * 10.0


# Section Helpers
def dist(pts):
    return sum((pts[k + 1] - pts[k]).Length for k in range(len(pts) - 1))


def yaw_deg(pl):
    return pl.Rotation.Angle * 180 / math.pi * (1 if pl.Rotation.Axis.z >= 0 else -1)


femur_frame = bd.getObject("FemurFrame").getGlobalPlacement()   # template frame (LegTemplate at origin)
j4_t = bd.getObject("J4Top").getGlobalPlacement().Base
tip_t = bd.getObject("FootTip").getGlobalPlacement().Base

# Section Table
print("Leg | yaw axis (x, y) | holder yaw | J (x, y) on PCB | routed mm | cut length mm | foot (x, y, z)")
for leg in ["FL", "ML", "RL", "FR", "MR", "RR"]:
    L = bd.getObject("Leg_" + leg).Placement            # assembly link placement = mount
    j = bd.getObject("J_" + leg).Placement.Base
    pts = [
        App.Vector(j.x, j.y, CONN_TOP),
        L.multVec(App.Vector(-(P.hold_face - 1), 0, NOTCH_Z)),        # out through the top-shell notch
        L.multVec(App.Vector(-(P.hold_face - RISE_IN), 0, NOTCH_Z)),
        L.multVec(App.Vector(-(P.hold_face - RISE_IN), 0, CLIP_Z)),   # rise outside the wall
        L.multVec(App.Vector(0, 0, CLIP_Z)),                          # yaw-axis clip (slack loop)
        L.multVec(femur_frame.Base),                                  # cross the femur joint at its axis
        L.multVec(j4_t),                                              # leg board J4
    ]
    routed = dist(pts)
    cut = math.ceil((routed + YAW_LOOP + FEMUR_LOOP + TERMINATIONS) / 10.0) * 10
    foot = L.multVec(tip_t)
    print("%s | (%.2f, %.2f) | %.0f | (%.1f, %.1f) | %.0f | %d | (%.1f, %.1f, %.1f)"
          % (leg, L.Base.x, L.Base.y, yaw_deg(L), j.x, j.y, routed, cut, foot.x, foot.y, foot.z))

print("Heights: tray underside %.1f, PCB %.1f-%.1f, top %.1f; foot tip z %.1f (ground clearance %.1f mm)"
      % (P.z_bot, P.pcb_z, PCB_TOP, P.top_z, tip_t.z, P.z_bot - tip_t.z))
