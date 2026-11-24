# leg_stance.py - put the articulated legs in BodyAssembly back to the Params stance and re-solve
#
# Run in FreeCAD with Body.FCStd open (e.g. after dragging legs around in the Assembly workbench):
#   exec(open("/home/deck/Coding/hexapod/hardware/CAD/leg_stance.py").read())
#
# The stance is the LegTemplate chain (CoxaJoint / FemurJoint / TibiaJoint angles from Params:
# coxa_zero + stance_coxa, stance_femur, stance_tibia). Recompute first if you changed those Params.
import FreeCAD as App

bd = App.getDocument("Body")
asm = bd.getObject("BodyAssembly")
LEGS = ("FL", "ML", "RL", "FR", "MR", "RR")
FIXED = ("TrayLink", "TopLink", "PcbLink", "PackLink", "PartsLink")


def _p(name):
    return bd.getObject(name).Placement


def _chain(leg):
    c = leg.multiply(_p("CoxaJoint"))
    f = c.multiply(_p("FemurFrame")).multiply(_p("FemurJoint"))
    t = f.multiply(_p("TibiaFrame")).multiply(_p("TibiaJoint"))
    return c, f, t


def reset_stance(solve=True):
    for o in FIXED:                       # grounded tray and the parts fixed to it sit at the origin
        bd.getObject(o).Placement = App.Placement()
    for L in LEGS:
        m = bd.getObject("Mount_" + L)
        leg = m.Placement1.multiply(m.Placement2.inverse())
        bd.getObject("Leg_" + L).Placement = leg
        c, f, t = _chain(leg)
        bd.getObject("Coxa_" + L).Placement = c
        bd.getObject("Femur_" + L).Placement = f
        bd.getObject("Tibia_" + L).Placement = t
    if solve:
        return asm.solve()


def stance_error():
    """Foot-tip distance (mm) of each assembly leg from the Params stance."""
    out = {}
    for L in LEGS:
        _, _, t = _chain(_p("Leg_" + L))
        want = t.multiply(_p("FootTip")).Base
        have = _p("Tibia_" + L).multiply(_p("FootTip")).Base
        out[L] = (want - have).Length
    return out


res = reset_stance()
print("solve:", res, " foot error from stance (mm):", {k: round(v, 4) for k, v in stance_error().items()})
