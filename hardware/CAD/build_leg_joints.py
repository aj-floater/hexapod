# build_leg_joints.py - one-off: articulated legs in BodyAssembly (Revolute joints you can drag)
#
# Run once in FreeCAD with Body.FCStd open:
#   exec(open("/home/deck/Coding/hexapod/hardware/CAD/build_leg_joints.py").read())
#
# Splits the leg into four rigid bodies, each an App::Part of links in its own joint frame:
#   LegStatic (holder + base servo, LegTemplate frame), LegCoxa (CoxaJoint frame),
#   LegFemur (FemurJoint frame), LegTibia (TibiaJoint frame).
# LegTemplate is left untouched (coxa_sweep_check, body_measure and export_leg_clouds read it).
# In BodyAssembly the Leg_* links now point at LegStatic, and each leg gets Coxa_/Femur_/Tibia_ links
# joined by Revolute joints whose frames are bound by expression to the template's
# CoxaJoint / FemurFrame / TibiaFrame placements. Coxa limits: coxa_zero +- coxa_limit.
import FreeCAD as App
import JointObject

bd = App.getDocument("Body")
asm = bd.getObject("BodyAssembly")
jg = bd.getObject("Joints")
LEGS = ("FL", "ML", "RL", "FR", "MR", "RR")


def body_part(name, src, skip=()):
    """App::Part of links mirroring src's children (same placements), minus `skip`."""
    p = bd.getObject(name) or bd.addObject("App::Part", name)
    for o in src.Group:
        if o.TypeId == "App::Origin" or o.Name in skip:
            continue
        target = o.LinkedObject if o.TypeId == "App::Link" else o
        lk = bd.addObject("App::Link", "%s_%s" % (name, o.Name))
        lk.setLink(target)
        lk.Placement = o.Placement
        lk.Label = o.Label
        p.addObject(lk)
        lk.Visibility = o.Visibility
    p.Visibility = False
    return p


static = body_part("LegStatic", bd.getObject("LegTemplate"), skip=("CoxaJoint",))
coxa = body_part("LegCoxa", bd.getObject("CoxaJoint"), skip=("FemurFrame",))
femur = body_part("LegFemur", bd.getObject("FemurJoint"), skip=("TibiaFrame",))
tibia = body_part("LegTibia", bd.getObject("TibiaJoint"))
bd.recompute()


def joint(name, ref1, ref2, off1_expr, off1=None):
    j = jg.newObject("App::FeaturePython", name)
    JointObject.Joint(j, JointObject.JointTypes.index("Revolute"))
    JointObject.ViewProviderJoint(j.ViewObject)
    j.Reference1 = [ref1, ["", ""]]
    j.Reference2 = [ref2, ["", ""]]
    if off1_expr:
        j.setExpression(".Offset1", off1_expr)
    return j


for L in LEGS:
    leg = bd.getObject("Leg_" + L)
    leg.setLink(static)
    comps = {}
    for kind, part in (("Coxa", coxa), ("Femur", femur), ("Tibia", tibia)):
        c = bd.addObject("App::Link", "%s_%s" % (kind, L))
        c.setLink(part)
        asm.addObject(c)
        comps[kind] = c
    # start in the Params stance: same chain as LegTemplate
    cj, ff, fj, tf, tj = (bd.getObject(n).Placement for n in ("CoxaJoint", "FemurFrame", "FemurJoint", "TibiaFrame", "TibiaJoint"))
    comps["Coxa"].Placement = leg.Placement.multiply(cj)
    comps["Femur"].Placement = comps["Coxa"].Placement.multiply(ff).multiply(fj)
    comps["Tibia"].Placement = comps["Femur"].Placement.multiply(tf).multiply(tj)

    jc = joint("CoxaRev_" + L, leg, comps["Coxa"], None)
    jc.EnableAngleMin = jc.EnableAngleMax = True
    jc.setExpression("AngleMin", "(Params.coxa_zero - Params.coxa_limit) * 1 deg")
    jc.setExpression("AngleMax", "(Params.coxa_zero + Params.coxa_limit) * 1 deg")
    joint("FemurRev_" + L, comps["Coxa"], comps["Femur"], "FemurFrame.Placement")
    joint("TibiaRev_" + L, comps["Femur"], comps["Tibia"], "TibiaFrame.Placement")

bd.recompute()
# Creating the joints snaps parts together before Offset1 is set, so the first solve starts from a bad
# guess (it flipped a femur axis and tilted the grounded tray). Reset everything to the stance, then solve.
exec(open("/home/deck/Coding/hexapod/hardware/CAD/leg_stance.py").read())
print("errors:", [(o.Name, o.getStatusString()) for o in bd.Objects if 'rror' in o.getStatusString() or o.isValid() is False])
