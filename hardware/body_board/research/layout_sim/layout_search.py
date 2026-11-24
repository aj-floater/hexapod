# layout_search.py - leg layout sweep / single-layout check on the real leg CAD point clouds
#
#   python3 -I layout_search.py check 60 66 26       # psi(deg) xc yc  -> one layout, full report
#   python3 -I layout_search.py sweep 30             # coxa yaw limit (deg) -> sweep psi and xc
#
# Layout model: middle legs at (0, +-legM_y) pointing sideways; corner legs at (+-xc, +-yc) with
# holders splayed psi degrees from lateral (Body.FCStd: legC_ang = 90 - psi). legM_y = W/2 + FACE.
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from legsim import *  # noqa: F401,F403  (kinematics, gait, clearance helpers)

# Section Settings
W = 60.0                                                       # body width at the middle legs
PACK = (np.array([-34.0, -19.0, -4.0]), np.array([34.0, 19.0, 15.0]))   # fixed 2S pack envelope
FACE_H = 12.0                                                  # outline half-width at each holder face


# Section Helpers
def outline(lay):
    """Body outline through the six holder inner faces; returns vertices and area."""
    pts = []
    for L in LEGS:
        mx, my, a = lay[L]
        u = np.array([np.cos(np.radians(a)), np.sin(np.radians(a))])
        v = np.array([-u[1], u[0]])
        c = np.array([mx, my]) - FACE * u
        pts += [c + FACE_H * v, c - FACE_H * v]
    P = np.array(pts)
    ctr = P.mean(0)
    P = P[np.argsort(np.arctan2(P[:, 1] - ctr[1], P[:, 0] - ctr[0]))]
    area = 0.5 * abs(np.dot(P[:, 0], np.roll(P[:, 1], 1)) - np.dot(P[:, 1], np.roll(P[:, 0], 1)))
    return P, area


def static_ok(lay, yaws):
    """Holders clear of the pack, and coxa cages of neighbours clear over the yaw grid."""
    for L in LEGS:
        g = to_body(D["ground"], mount_T(*lay[L]))
        if np.any(np.all((g > PACK[0] - 1) & (g < PACK[1] + 1), axis=1)):
            return False, "pack"
    c = static_cage_clear(lay, [("FL", "ML"), ("ML", "RL"), ("FL", "FR"), ("RL", "RR")], yaws)
    return c >= 2.0, c


def report(lay, yaw_limit):
    rl, rb = gait_eval(lay, "leg", n=20), gait_eval(lay, "body", n=20)
    cage = static_cage_clear(lay, [("FL", "ML"), ("ML", "RL"), ("FL", "FR"), ("RL", "RR")],
                             range(-yaw_limit, yaw_limit + 1, 10))
    P, area = outline(lay)
    dm, dc, fm, fc, nf = loads(lay)
    print("outline %.1f x %.1f mm (%.0f mm2)" % (np.ptp(P[:, 0]), np.ptp(P[:, 1]), area))
    print("coxa cages within +-%d deg: %.1f mm" % (yaw_limit, cage))
    print("gait clearance: leg-frame stride %.1f mm (%s), body-frame stride %.1f mm (%s)"
          % (rl["clear"][0], rl["clear"][1], rb["clear"][0], rb["clear"][1]))
    print("stability margin: %.1f mm (leg-frame) / %.1f mm (body-frame)" % (rl["stab"], rb["stab"]))
    print("d_m %.1f  d_c %.1f  d_c/d_m %.2f  F_m %.2f W  F_c %.2f W" % (dm, dc, dc / dm, fm, fc))
    print("coxa yaw used (body-frame walk):", {k: [round(float(a), 1) for a in v] for k, v in rb["yaw"].items()})


def sweep(yaw_limit):
    yaws = range(-yaw_limit, yaw_limit + 1, max(1, yaw_limit // 2))
    results = []
    for psi in [30, 40, 45, 50, 60]:
        for xc in range(25, 81, 5):
            found = None
            for yc in np.arange(10, 100, 2.0):
                lay = layout(W, psi, xc, yc)
                ok, info = static_ok(lay, yaws)
                if not ok:
                    continue
                rl = gait_eval(lay, "leg", n=12)
                if "fail" in rl or rl["clear"][0] < 10 or rl["stab"] < 15:
                    continue
                rb = gait_eval(lay, "body", n=12)
                if "fail" in rb or rb["clear"][0] < 10 or rb["stab"] < 15:
                    continue
                found = (yc, info, rl, rb)
                break
            if not found:
                print("psi %2d xc %2d  no feasible yc" % (psi, xc), flush=True)
                continue
            yc, info, rl, rb = found
            lay = layout(W, psi, xc, yc)
            P, area = outline(lay)
            dm, dc, fm, fc, _ = loads(lay)
            r = dict(psi=psi, xc=xc, yc=float(yc), cage=float(info), clr=float(min(rl["clear"][0], rb["clear"][0])),
                     stab=float(min(rl["stab"], rb["stab"])), area=float(area), Lx=float(np.ptp(P[:, 0])),
                     Wy=float(np.ptp(P[:, 1])), dc_dm=float(dc / dm), Fm=float(fm), Fc=float(fc))
            results.append(r)
            print("psi %(psi)2d xc %(xc)2d yc %(yc)4.1f | cage %(cage)4.1f | clr %(clr)5.1f | stab %(stab)5.1f | "
                  "outline %(Lx)3.0fx%(Wy)3.0f | dc/dm %(dc_dm).2f Fm %(Fm).2f Fc %(Fc).2f" % r, flush=True)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_yaw%d.json" % yaw_limit)
    json.dump(results, open(out, "w"), indent=1)
    print("wrote", out)


# Section Main
if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "check":
        psi, xc, yc = float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
        report(layout(W, psi, xc, yc), int(sys.argv[5]) if len(sys.argv) > 5 else 30)
    elif len(sys.argv) >= 3 and sys.argv[1] == "sweep":
        sweep(int(sys.argv[2]))
    else:
        print(__doc__ if __doc__ else open(__file__).read().split("\n\n")[0])
