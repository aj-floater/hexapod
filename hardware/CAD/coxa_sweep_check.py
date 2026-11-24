# coxa_sweep_check.py - quick check: coxa-level leg parts vs the body shells over the coxa yaw range
#
# Run in FreeCAD with Body.FCStd open:
#   exec(open("<repo>/hardware/CAD/coxa_sweep_check.py").read())
#
# Only the small parts that ride on CoxaJoint (brackets, arms, horns; not the femur/tibia subtree)
# are used, so it takes seconds. Do NOT extend this to whole legs (see BODY_CAD_STATUS.md §6).
# Prints the worst clearance per leg and body part; overlaps report the common volume.
import time
import FreeCAD as App
import Part

bd = App.getDocument("Body")
YAWS = (-30, -15, 0, 15, 30)                  # coxa yaw offsets from stance (deg)
BODY = ("TopShellV2", "BottomTray", "PCB")
LEGS = ("Leg_FL", "Leg_ML", "Leg_RL", "Leg_FR", "Leg_MR", "Leg_RR")


def coxa_parts():
    """CoxaJoint direct children (minus the femur subtree), in LegTemplate coordinates at yaw 0."""
    lt, cj = bd.getObject("LegTemplate"), bd.getObject("CoxaJoint")
    out = {}
    for o in cj.Group:
        if o.Name == "FemurFrame":
            continue
        s = Part.getShape(lt, "CoxaJoint.%s." % o.Name, transform=False)
        if s is not None and not s.isNull() and s.Volume > 1e-6:
            out[o.Label] = s
    return out


def check(yaws=YAWS, verbose=True, body_names=BODY):
    t0 = time.time()
    parts = coxa_parts()
    body = {n: bd.getObject(n).Shape for n in body_names}
    worst = {}
    for L in LEGS:
        Lp = bd.getObject(L).Placement
        for y in yaws:
            rot = App.Placement(App.Vector(), App.Rotation(App.Vector(0, 0, 1), y))
            M = Lp.multiply(rot)
            for pn, s in parts.items():
                sp = s.transformed(M.toMatrix())
                for bn, b in body.items():
                    if not sp.BoundBox.intersect(b.BoundBox):
                        continue
                    d = sp.distToShape(b)[0]
                    vol = 0.0
                    if d < 1e-6:
                        vol = sp.common(b).Volume
                    key = (L, bn)
                    if key not in worst or (d, -vol) < (worst[key][0], -worst[key][1]):
                        worst[key] = (d, vol, y, pn)
    if verbose:
        for (L, bn), (d, vol, y, pn) in sorted(worst.items()):
            print("%-6s %-10s min %6.2f mm  overlap %6.3f mm3  @yaw %+3d  %s" % (L, bn, d, vol, y, pn))
        print("checked %d parts x %d yaws x %d legs in %.1f s" % (len(parts), len(yaws), len(LEGS), time.time() - t0))
    return worst


res = check()
