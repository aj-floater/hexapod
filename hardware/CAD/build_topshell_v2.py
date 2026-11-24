# build_topshell_v2.py - builds TopShellV2 (+ TopCavityTool) in Body.FCStd next to the old TopShell.
#
# Run in FreeCAD with Body.FCStd open:
#   exec(open("<repo>/hardware/CAD/build_topshell_v2.py").read())
#
# Structure (see BODY_CAD_STATUS.md):
#   TopShellV2:    ShellOutline -> ShellPad -> ShellChamfer -> Hollow (cut TopCavityTool)
#                  -> ColumnPocket -> ShoulderNotch -> LedgeInserts -> OLED / stop / antenna / USB / power
#   TopCavityTool: CavityOutline2 (outline offset -top_t) -> CavityPad -> CavityChamfer (parallel to the outer one)
#                  -> LedgeBlock, NotchHousing, ColumnHousing pockets (where the shell stays solid)
# Old TopShell is not touched; the swap is a separate step.
#
# ONE-OFF MIGRATION RECORD (2026-11-24): it copies the opening/insert sketches out of the old TopShell, which has
# since been deleted, so it cannot be re-run as is. Edit TopShellV2 / TopCavityTool in FreeCAD instead.
# After this script: LedgeBlock width -> 2*(sweep_t+house_t), LedgeInserts2 DrillPoint -> Flat, col_top 34.7,
# PCB notches -> PcbHousingKeepout binder (+pcb_gap2) + PcbHousingNotch, TopLink -> TopShellV2, old TopShell deleted.
import os
import math

REPO = os.path.expanduser("~/Coding/hexapod")
exec(open(os.path.join(REPO, "hardware/CAD/body_sketch_helpers.py")).read())

P = bd.getObject("Params")
LD = {l[0]: l for l in LEGDEF}
LEGS = ["FL", "FR", "ML", "MR", "RL", "RR"]


def s0(n):
    return "Params.s_out_m - 2" if n in ("ML", "MR") else "Params.s_out - 2"


# Section Params
NEW = [("sweep_t", "16", "shoulder-notch half-width (coxa top bracket |t| <= 15.5 inboard of s 9.3, 14.8 at s 10)"),
       ("flare_s", "10", "shoulder notch flares out at 45 deg outboard of this s (no knife edges at the corner skin)"),
       ("house_t", "2", "wall thickness round the notch and the servo column (top shell)"),
       ("col_top", "34.5", "servo-column roof underside: coxa servo top Z 33.5 + 1")]
row = max(int(''.join(ch for ch in c if ch.isdigit())) for c in P.getUsedCells()) + 1
for a, v, c in NEW:
    if not P.getCellFromAlias(a):
        P.set("A%d" % row, "'" + a); P.set("B%d" % row, v); P.set("C%d" % row, "'" + c); P.setAlias("B%d" % row, a)
        row += 1
bd.recompute()


# Section Helpers
def new_body(name):
    b = bd.getObject(name)
    if b:
        raise RuntimeError("%s already exists - delete it first" % name)
    return bd.addObject("PartDesign::Body", name)


def outline_binder(body, name, z_expr, offset_expr=None):
    b = body.newObject("PartDesign::SubShapeBinder", name)
    b.Support = [(bd.getObject("LayoutSketch"), "")]
    b.MakeFace = True
    b.setExpression(".Placement.Base.z", z_expr)
    if offset_expr:
        b.setExpression("Offset", offset_expr)
    bd.recompute()
    return b


def top_edges(shape):
    zt = shape.BoundBox.ZMax
    return ["Edge%d" % (i + 1) for i, e in enumerate(shape.Edges)
            if abs(e.BoundBox.ZMin - zt) < 1e-6 and e.BoundBox.ZLength < 1e-6]


def chamfer(body, name, base, size_expr):
    c = body.newObject("PartDesign::Chamfer", name)
    c.Base = (base, top_edges(base.Shape))
    c.setExpression("Size", size_expr)
    bd.recompute()
    if not c.Shape.isValid() or len(c.Shape.Solids) != 1:
        raise RuntimeError("chamfer failed: %s %s" % (name, c.getStatusString()))
    return c


def done(sk):
    bd.recompute()
    ok = sk.solve() == 0 and sk.FullyConstrained and not sk.RedundantConstraints
    if not ok:
        raise RuntimeError("sketch %s not fully constrained" % sk.Name)
    sk.Visibility = False
    return sk


def copy_sketch(body, name):
    """Copy an existing XY sketch (with its expressions) into body, attached to body's XY plane."""
    src = bd.getObject(name)
    c = bd.copyObject(src, False)
    c.MapMode = "Deactivated"
    c.AttachmentSupport = None
    body.addObject(c)
    c.AttachmentSupport = [([f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"][0], "")]
    c.MapMode = "FlatFace"
    for k, v in src.ExpressionEngine:
        if "AttachmentOffset" in k:
            c.setExpression(k, v)
    return done(c)


def copy_feature(body, name, sk):
    src = bd.getObject(name)
    f = body.newObject(src.TypeId, name + "2")
    f.Profile = sk
    for k in ("Type", "Length", "Reversed", "SideType", "Refine"):
        if hasattr(src, k):
            setattr(f, k, getattr(src, k))
    for k, v in src.ExpressionEngine:
        f.setExpression(k, v)
    bd.recompute()
    if not f.Shape.isValid() or len(f.Shape.Solids) != 1:
        raise RuntimeError("feature failed: %s %s" % (f.Name, f.getStatusString()))
    return f


# Section Cavity tool (what gets removed; its pockets are where the shell stays solid)
tool = new_body("TopCavityTool")
cb = outline_binder(tool, "CavityOutline2", "Params.split_z - 1", "-Params.top_t")
cpad = feature(tool, "PartDesign::Pad", "CavityPad", cb, Length="Params.top_z - Params.top_t - Params.split_z + 1")
chamfer(tool, "CavityChamfer", cpad, "Params.top_ch - Params.top_t * (2 - sqrt(2))")

sk = body_sketch(tool, "LedgeBlockSketch", "Params.split_z - 1")
for n in LEGS:
    add_leg_rect(sk, LD[n], s0(n), "Params.hold_face + Params.clr + Params.tray_t", "2 * Params.slot_half")
feature(tool, "PartDesign::Pocket", "LedgeBlock", done(sk), Type="Length", Reversed=True,
        Length="Params.ledge_t + 1")

sk = body_sketch(tool, "NotchHousingSketch", "Params.split_z - 1")
for n in LEGS:
    tA = "Params.sweep_t + (Params.flare_s - (%s)) + Params.house_t * sqrt(2)" % s0(n)
    sB = "Params.flare_s + Params.house_t * (sqrt(2) - 1)"
    tB = "Params.sweep_t + Params.house_t"
    sC = "Params.sweep_s + Params.house_t"
    pts = [(s0(n), tA), (sB, tB), (sC, tB), (sC, "-(%s)" % tB), (sB, "-(%s)" % tB), (s0(n), "-(%s)" % tA)]
    add_leg_poly(sk, LD[n], pts)
feature(tool, "PartDesign::Pocket", "NotchHousing", done(sk), Type="ThroughAll", Reversed=True)

sk = body_sketch(tool, "ColumnHousingSketch", "Params.split_z - 1")
for n in LEGS:
    add_leg_rect(sk, LD[n], s0(n), "Params.hold_face + Params.clr + Params.house_t",
                 "2 * (Params.ear_t0 + Params.clr + Params.house_t)")
feature(tool, "PartDesign::Pocket", "ColumnHousing", done(sk), Type="Length", Reversed=True,
        Length="Params.col_top + Params.top_t - Params.split_z + 1")
tool.Visibility = False

# Section Shell
shell = new_body("TopShellV2")
ob = outline_binder(shell, "ShellOutline", "Params.split_z")
spad = feature(shell, "PartDesign::Pad", "ShellPad", ob, Length="Params.top_z - Params.split_z")
chamfer(shell, "ShellChamfer", spad, "Params.top_ch")
ob.Visibility = False
hol = shell.newObject("PartDesign::Boolean", "Hollow")
hol.Type = "Cut"
hol.addObject(tool)
bd.recompute()
if not hol.Shape.isValid() or len(hol.Shape.Solids) != 1:
    raise RuntimeError("Hollow failed: %s" % hol.getStatusString())

sk = body_sketch(shell, "ColumnPocketSketch", "Params.split_z")
for n in LEGS:
    add_leg_rect(sk, LD[n], s0(n), "Params.hold_face + Params.clr", "2 * (Params.ear_t0 + Params.clr)")
feature(shell, "PartDesign::Pocket", "ColumnPocket", done(sk), Type="Length", Reversed=True,
        Length="Params.col_top - Params.split_z")

sk = body_sketch(shell, "ShoulderNotchSketch", "Params.split_z + Params.ledge_t")
for n in LEGS:
    tA = "Params.sweep_t + (Params.flare_s - (%s))" % s0(n)
    pts = [(s0(n), tA), ("Params.flare_s", "Params.sweep_t"), ("Params.sweep_s", "Params.sweep_t"),
           ("Params.sweep_s", "-Params.sweep_t"), ("Params.flare_s", "-Params.sweep_t"), (s0(n), "-(%s)" % tA)]
    add_leg_poly(sk, LD[n], pts)
feature(shell, "PartDesign::Pocket", "ShoulderNotch", done(sk), Type="ThroughAll", Reversed=True)

# ledge inserts (same sketch, same hole settings as the old TopShell)
sk = copy_sketch(shell, "LedgeInsertSketch")
old = bd.getObject("LedgeInserts")
h = shell.newObject("PartDesign::Hole", "LedgeInserts2")
h.Profile = sk
for k in ("DepthType", "DrillPoint", "DrillPointAngle", "HoleCutType", "Threaded", "Reversed", "Refine"):
    setattr(h, k, getattr(old, k))
for k, v in old.ExpressionEngine:
    h.setExpression(k, v)
bd.recompute()
if not h.Shape.isValid() or len(h.Shape.Solids) != 1:
    raise RuntimeError("LedgeInserts2 failed: %s" % h.getStatusString())

# openings and the stop sleeve (same sketches and settings as the old TopShell)
for fname, skname in [("OledWindow", "OledWindowSketch"), ("StopSleeve", "StopSleeveSketch"),
                      ("StopHole", "StopHoleSketch"), ("AntennaHole", "AntennaSketch"),
                      ("UsbOpening", "UsbOpeningSketch"), ("PowerPinHole", "PowerPinSketch")]:
    copy_feature(shell, fname, copy_sketch(shell, skname))

bd.recompute()
s = shell.Shape
print("TopShellV2: valid %s, solids %d, %.2f cm3, %d faces, %d edges (old TopShell: %.2f cm3, %d faces)"
      % (s.isValid(), len(s.Solids), s.Volume / 1000, len(s.Faces), len(s.Edges),
         bd.getObject("TopShell").Shape.Volume / 1000, len(bd.getObject("TopShell").Shape.Faces)))
