# export_leg_clouds.py - FreeCAD macro: export the leg as point clouds for legsim.py
#
# Run in the FreeCAD Python console with hardware/CAD/Body.FCStd open:
#   exec(open("/home/arjames/Coding/hexapod/hardware/body_board/research/layout_sim/export_leg_clouds.py").read())
#
# Writes ~/.cache/hexapod_body/leg_clouds.npz: one point cloud per link (ground/coxa/femur/tibia)
# in that link's own joint frame, plus the femur/tibia frame placements and the foot-tip / J4 points.
# Re-run after changing the leg geometry (e.g. leg v3), then re-run layout_search.py.
import os
import numpy as np
import FreeCAD as App
import Part

# Section Settings
OUT = os.path.expanduser("~/.cache/hexapod_body")
STEP = 2.0                      # sampling / voxel size (mm)
bd = App.getDocument("Body")


# Section Helpers
def sample(shape, step=STEP):
    v, tris = shape.tessellate(0.3)
    V = np.array([[p.x, p.y, p.z] for p in v])
    pts = [V]
    for a, b, c in tris:
        A, B, C = V[a], V[b], V[c]
        n = int(max(np.linalg.norm(B - A), np.linalg.norm(C - A), np.linalg.norm(C - B)) / step) + 1
        if n <= 1:
            continue
        u, w = np.meshgrid(np.linspace(0, 1, n + 1), np.linspace(0, 1, n + 1))
        m = (u + w) <= 1.0
        pts.append(A + np.outer(u[m], B - A) + np.outer(w[m], C - A))
    P = np.vstack(pts)
    keep = np.unique(np.round(P / step).astype(np.int64), axis=0, return_index=True)[1]
    return P[keep]


def matrix(pl):
    return np.array(pl.toMatrix().A).reshape(4, 4)


# Section Export
groups = {"ground": ("LegTemplate", ["L_BaseServoHolder", "L_MG9OD_Micro_Servo_step"]),
          "coxa": ("CoxaJoint", None), "femur": ("FemurJoint", None), "tibia": ("TibiaJoint", None)}
res = {}
for g, (cont, names) in groups.items():
    c = bd.getObject(cont)
    objs = [bd.getObject(n) for n in names] if names else [o for o in c.Group if o.Name.startswith("L_")]
    res[g] = sample(Part.makeCompound([Part.getShape(o) for o in objs]))
    print(g, len(objs), "parts ->", len(res[g]), "points")
res["Mf"] = matrix(bd.getObject("FemurFrame").Placement)
res["Mt"] = matrix(bd.getObject("TibiaFrame").Placement)
res["tip"] = np.array(list(bd.getObject("FootTip").Placement.Base))
res["j4"] = np.array(list(bd.getObject("J4Top").Placement.Base))
os.makedirs(OUT, exist_ok=True)
np.savez(os.path.join(OUT, "leg_clouds.npz"), **res)
print("saved", os.path.join(OUT, "leg_clouds.npz"))
