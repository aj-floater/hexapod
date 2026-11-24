# body_sketch_helpers.py - helpers for building fully constrained, Params-driven sketches in Body.FCStd
# Usage (FreeCAD console, Body.FCStd open):
#   exec(open("/home/arjames/Coding/hexapod/hardware/CAD/body_sketch_helpers.py").read())
# Every helper adds geometry *and* the constraints that fix it, with dimensions bound to Params expressions.
import math
import re
import FreeCAD as App
import Part
import Sketcher

bd = App.getDocument("Body")
V = App.Vector
C = Sketcher.Constraint

# Section Legs: name, yaw-axis x / y expressions, inward direction (deg) expression
LEGDEF = [
    ("FR", "Params.legC_x", "-Params.legC_y", "180 - Params.legC_ang"),
    ("FL", "Params.legC_x", "Params.legC_y", "180 + Params.legC_ang"),
    ("ML", "0", "Params.legM_y", "270"),
    ("RL", "-Params.legC_x", "Params.legC_y", "360 - Params.legC_ang"),
    ("RR", "-Params.legC_x", "-Params.legC_y", "Params.legC_ang"),
    ("MR", "0", "-Params.legM_y", "90"),
]


def ev(expr):
    """Evaluate a Params expression numerically (for initial geometry)."""
    P = bd.getObject("Params")
    s = re.sub(r"Params\.(\w+)", lambda m: repr(float(getattr(P, m.group(1)))), expr)
    return float(eval(s))


def cname(sk, c, name, expr=None):
    i = sk.addConstraint(c)
    if name:
        sk.renameConstraint(i, name)
        if expr:
            sk.setExpression("Constraints." + name, expr)
    return i


def body_sketch(body, name, zexpr):
    """Sketch on the body's XY plane, offset in Z by an expression."""
    xy = [f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"][0]
    s = body.newObject("Sketcher::SketchObject", name)
    s.AttachmentSupport = [(xy, "")]
    s.MapMode = "FlatFace"
    s.setExpression(".AttachmentOffset.Base.z", zexpr)
    return s


def axis_and_dir(sk, tag, xe, ye, ae, length_expr):
    """Construction point at a leg yaw axis + construction line along the inward direction."""
    x = ev(xe) if xe != "0" else 0.0
    y, a, L = ev(ye), math.radians(ev(ae)), ev(length_expr)
    A = V(x, y, 0); u = V(math.cos(a), math.sin(a), 0)
    gA = sk.addGeometry(Part.Point(A), True)
    gD = sk.addGeometry(Part.LineSegment(A, A + u * L), True)
    if xe == "0":
        sk.addConstraint(C("PointOnObject", gA, 1, -2))
    else:
        cname(sk, C("DistanceX", -1, 1, gA, 1, x), tag + "_ax", xe)
    cname(sk, C("DistanceY", -1, 1, gA, 1, y), tag + "_ay", ye)
    sk.addConstraint(C("Coincident", gD, 1, gA, 1))
    cname(sk, C("Angle", gD, a), tag + "_ang", "(%s) * 1 deg" % ae)
    cname(sk, C("Distance", gD, L), tag + "_len", length_expr)
    return gA, gD, A, u


def add_leg_rect(sk, leg, s_near, s_far, width, sfx=""):
    """Rectangle in a leg's frame: from s_near to s_far inward of the yaw axis, centred on the leg axis."""
    n, xe, ye, ae = leg
    tag = "%s_%s%s" % (sk.Name[:6], n, sfx)
    gA, gD, A, u = axis_and_dir(sk, tag, xe, ye, ae, s_far)
    v = V(-u.y, u.x, 0); sn, w, sf = ev(s_near), ev(width), ev(s_far)
    M = A + u * sn; Fm = A + u * sf
    gM = sk.addGeometry(Part.Point(M), True)
    sk.addConstraint(C("PointOnObject", gM, 1, gD))
    cname(sk, C("Distance", gA, 1, gM, 1, sn), tag + "_near", s_near)
    p1, p2, p3, p4 = M - v * w / 2, M + v * w / 2, Fm + v * w / 2, Fm - v * w / 2
    L = [sk.addGeometry(Part.LineSegment(a, b)) for a, b in [(p1, p2), (p2, p3), (p3, p4), (p4, p1)]]
    for i in range(4):
        sk.addConstraint(C("Coincident", L[i], 2, L[(i + 1) % 4], 1))
    sk.addConstraint(C("Symmetric", L[2], 1, L[2], 2, gD, 2))
    sk.addConstraint(C("Perpendicular", L[2], gD))
    cname(sk, C("Distance", L[2], w), tag + "_w", width)
    sk.addConstraint(C("Parallel", L[1], gD))
    sk.addConstraint(C("Perpendicular", L[0], gD))
    sk.addConstraint(C("Symmetric", L[0], 1, L[0], 2, gM, 1))


def add_leg_circles(sk, leg, s, t, d, sfx=""):
    """Two circles in a leg's frame at distance s inward, +-t either side of the leg axis."""
    n, xe, ye, ae = leg
    tag = "%s_%s%s" % (sk.Name[:6], n, sfx)
    gA, gD, A, u = axis_and_dir(sk, tag, xe, ye, ae, s)
    v = V(-u.y, u.x, 0); tt, dd = ev(t), ev(d); Cc = A + u * ev(s)
    c1 = sk.addGeometry(Part.Circle(Cc - v * tt, V(0, 0, 1), dd / 2))
    c2 = sk.addGeometry(Part.Circle(Cc + v * tt, V(0, 0, 1), dd / 2))
    gT = sk.addGeometry(Part.LineSegment(Cc - v * tt, Cc + v * tt), True)
    sk.addConstraint(C("Coincident", gT, 1, c1, 3)); sk.addConstraint(C("Coincident", gT, 2, c2, 3))
    sk.addConstraint(C("Symmetric", gT, 1, gT, 2, gD, 2)); sk.addConstraint(C("Perpendicular", gT, gD))
    cname(sk, C("Distance", gT, 2 * tt), tag + "_t", "2 * (%s)" % t)
    cname(sk, C("Diameter", c1, dd), tag + "_d", d)
    sk.addConstraint(C("Equal", c1, c2))


def add_circle(sk, tag, xe, ye, d):
    x = ev(xe) if xe != "0" else 0.0
    y = ev(ye) if ye != "0" else 0.0
    g = sk.addGeometry(Part.Circle(V(x, y, 0), V(0, 0, 1), ev(d) / 2))
    if xe == "0": sk.addConstraint(C("PointOnObject", g, 3, -2))
    else: cname(sk, C("DistanceX", -1, 1, g, 3, x), tag + "_x", xe)
    if ye == "0": sk.addConstraint(C("PointOnObject", g, 3, -1))
    else: cname(sk, C("DistanceY", -1, 1, g, 3, y), tag + "_y", ye)
    cname(sk, C("Diameter", g, ev(d)), tag + "_d", d)


def add_rect_at(sk, tag, cx, cy, w, h):
    """Axis-aligned rectangle centred on (cx, cy)."""
    x = ev(cx) if cx != "0" else 0.0
    y = ev(cy) if cy != "0" else 0.0
    W, H = ev(w), ev(h)
    cp = sk.addGeometry(Part.Point(V(x, y, 0)), True)
    if cx == "0": sk.addConstraint(C("PointOnObject", cp, 1, -2))
    else: cname(sk, C("DistanceX", -1, 1, cp, 1, x), tag + "_cx", cx)
    if cy == "0": sk.addConstraint(C("PointOnObject", cp, 1, -1))
    else: cname(sk, C("DistanceY", -1, 1, cp, 1, y), tag + "_cy", cy)
    pts = [V(x - W / 2, y - H / 2, 0), V(x + W / 2, y - H / 2, 0), V(x + W / 2, y + H / 2, 0), V(x - W / 2, y + H / 2, 0)]
    L = [sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4])) for i in range(4)]
    for i in range(4):
        sk.addConstraint(C("Coincident", L[i], 2, L[(i + 1) % 4], 1))
    for i, t in enumerate(["Horizontal", "Vertical", "Horizontal", "Vertical"]):
        sk.addConstraint(C(t, L[i]))
    sk.addConstraint(C("Symmetric", L[0], 1, L[1], 2, cp, 1))
    cname(sk, C("DistanceX", L[0], 1, L[0], 2, W), tag + "_w", w)
    cname(sk, C("DistanceY", L[1], 1, L[1], 2, H), tag + "_h", h)


def add_centered_rect(sk, tag, w, h):
    add_rect_at(sk, tag, "0", "0", w, h)


def check_sketches(body):
    out = []
    for o in body.Group:
        if o.TypeId == "Sketcher::SketchObject":
            ok = o.solve() == 0 and o.FullyConstrained and not o.RedundantConstraints
            out.append("%s:%s" % (o.Name, "OK" if ok else "NOT-FULL"))
    return out


def feature(body, typ, name, profile, **exprs):
    """Create a PartDesign feature, set props/expressions, recompute, and fail loudly if invalid."""
    f = body.newObject(typ, name)
    f.Profile = profile
    for k, v in exprs.items():
        if isinstance(v, str) and k not in ("Type", "HoleCutType", "DepthType", "DrillPoint", "SideType", "Type2", "Join", "Mode"):
            f.setExpression(k, v)
        else:
            setattr(f, k, v)
    bd.recompute()
    s = f.Shape
    if s.isNull() or not s.isValid() or len(s.Solids) != 1:
        raise RuntimeError("feature failed: %s (%s)" % (name, f.getStatusString()))
    return f


def place(name, x, y, rot="0"):
    o = bd.getObject(name)
    o.setExpression(".Placement.Base.x", str(x)); o.setExpression(".Placement.Base.y", str(y))
    o.setExpression(".Placement.Rotation.Angle", "(%s) * 1 deg" % rot)
