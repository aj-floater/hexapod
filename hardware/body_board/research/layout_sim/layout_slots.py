# layout_slots.py - layout search for the "slot" body: holders sit in slots in the body side,
# fixed by two side ears; body wall comes out to s_out from each coxa yaw axis.
#
#   python3 -I layout_slots.py check <ym> <psi> <xc> <yc>
#   python3 -I layout_slots.py sweep <ym> [<ym> ...]      (writes slots_ym<ym>.json)
#
# s = distance along the leg from its yaw axis (negative = inboard), t = sideways (template frame).
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from legsim import *  # noqa: F401,F403

# Section Slot concept geometry (template frame, mm)
HOLD_IN = -21.55            # holder inner face
EAR_S = (HOLD_IN, -9.5)     # ears along the holder side
EAR_T = (8.2, 15.2)         # ear inner/outer |t|
EAR_Z = (-4.0, 19.8)
WALL = 2.0                  # slot side wall
S_OUT = -8.0                # body wall corners, from the yaw axis
W_OUT = EAR_T[1] + 0.3 + WALL   # outline half-width at each slot
PACK = (np.array([-32.8, -18.7, -4.0]), np.array([32.8, 18.7, 15.0]))   # 65 x 36.8 pack + 0.3


def ear_points(step=1.5):
    s = np.arange(EAR_S[0], EAR_S[1] + 1e-6, step)
    t = np.arange(EAR_T[0], EAR_T[1] + 1e-6, step)
    z = np.arange(EAR_Z[0], EAR_Z[1] + 1e-6, step)
    S, T, Z = np.meshgrid(s, t, z, indexing="ij")
    P = np.stack([S.ravel(), T.ravel(), Z.ravel()], 1)
    return np.vstack([P, P * np.array([1, -1, 1])])


def slot_points(step=1.5):
    """2D slot block incl. walls (for neighbour overlap), at z=0."""
    s = np.arange(HOLD_IN - 1.0, S_OUT + 1e-6, step)
    t = np.arange(-W_OUT, W_OUT + 1e-6, step)
    S, T = np.meshgrid(s, t, indexing="ij")
    return np.stack([S.ravel(), T.ravel(), np.zeros(S.size)], 1)


EARS, SLOT = ear_points(), slot_points()
FOOT = np.vstack([D["ground"], EARS])          # holder + servo A + ears (static)


def layout2(ym, psi, xc, yc):
    a = 90 - psi
    return {"FL": (xc, yc, a), "ML": (0, ym, 90), "RL": (-xc, yc, 180 - a),
            "FR": (xc, -yc, -a), "MR": (0, -ym, -90), "RR": (-xc, -yc, -(180 - a))}


def outline2(lay):
    pts = []
    for L in LEGS:
        mx, my, a = lay[L]
        u = np.array([np.cos(np.radians(a)), np.sin(np.radians(a))]); v = np.array([-u[1], u[0]])
        c = np.array([mx, my]) + S_OUT * u
        pts += [c + W_OUT * v, c - W_OUT * v]
    P = np.array(pts); ctr = P.mean(0)
    P = P[np.argsort(np.arctan2(P[:, 1] - ctr[1], P[:, 0] - ctr[0]))]
    area = 0.5 * abs(np.dot(P[:, 0], np.roll(P[:, 1], 1)) - np.dot(P[:, 1], np.roll(P[:, 0], 1)))
    return P, area


def static2(lay):
    """pack clearance, neighbour slot overlap, holder/ear clearance; returns (ok, info)."""
    for L in LEGS:
        g = to_body(FOOT, mount_T(*lay[L]))
        if np.any(np.all((g > PACK[0] - 1.0) & (g < PACK[1] + 1.0), axis=1)):
            return False, "pack"
    pairs = [("FL", "ML"), ("ML", "RL"), ("FR", "MR"), ("MR", "RR"), ("FL", "FR"), ("RL", "RR")]
    for A, B in pairs:
        sa = to_body(SLOT, mount_T(*lay[A]))[:, :2]; sb = to_body(SLOT, mount_T(*lay[B]))[:, :2]
        d = np.sqrt(((sa[:, None, :] - sb[None, :, :]) ** 2).sum(-1)).min()
        if d < 1.0:
            return False, "slots %s/%s" % (A, B)
    c = static_cage_clear(lay, [("FL", "ML"), ("ML", "RL"), ("FL", "FR"), ("RL", "RR")], range(-30, 31, 15))
    return c >= 2.0, c


def evaluate(lay, n=16):
    rl, rb = gait_eval(lay, "leg", n=n), gait_eval(lay, "body", n=n)
    if "fail" in rl or "fail" in rb:
        return None
    P, area = outline2(lay); dm, dc, fm, fc, _ = loads(lay)
    return dict(clr=float(min(rl["clear"][0], rb["clear"][0])), at=rl["clear"][1], stab=float(min(rl["stab"], rb["stab"])),
                area=float(area), Lx=float(np.ptp(P[:, 0])), Wy=float(np.ptp(P[:, 1])), dc_dm=float(dc / dm), Fm=float(fm), Fc=float(fc),
                yaw={k: [round(float(x), 1) for x in v] for k, v in rb["yaw"].items()})


def sweep(ym):
    out = []
    for psi in [45, 50, 55, 60, 65]:
        for xc in range(40, 76, 5):
            for yc in np.arange(10, 70, 3.0):
                lay = layout2(ym, psi, xc, yc)
                ok, info = static2(lay)
                if not ok:
                    continue
                r = evaluate(lay, n=12)
                if r is None or r["clr"] < 10 or r["stab"] < 15:
                    continue
                r.update(ym=ym, psi=psi, xc=xc, yc=float(yc), cage=float(info))
                out.append(r)
                print("ym %4.1f psi %2d xc %2d yc %4.1f | clr %5.1f stab %5.1f cage %4.1f | outline %5.1fx%5.1f (%5.0f) | dc/dm %.2f Fm %.2f"
                      % (ym, psi, xc, yc, r["clr"], r["stab"], r["cage"], r["Lx"], r["Wy"], r["area"], r["dc_dm"], r["Fm"]), flush=True)
                break
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "slots_ym%g.json" % ym), "w"), indent=1)
    print("DONE ym", ym, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "check":
        lay = layout2(*[float(x) for x in sys.argv[2:6]])
        print("static:", static2(lay)); print(evaluate(lay, n=20))
    elif sys.argv[1] == "sweep":
        for ym in sys.argv[2:]:
            sweep(float(ym))
