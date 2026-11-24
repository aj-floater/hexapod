# legsim.py - hexapod layout analysis on real leg CAD point clouds
# Frames: "template" = leg frame used in Body.FCStd (yaw axis at origin, leg along +X at neutral,
# Z = holder datum). Joint angles are deltas from the LegAssembly saved pose (as in Body.FCStd).
import numpy as np

import os
CLOUDS = os.environ.get("LEG_CLOUDS", os.path.expanduser("~/.cache/hexapod_body/leg_clouds.npz"))
D = np.load(CLOUDS)   # written by export_leg_clouds.py (FreeCAD)
COXA_ZERO = -3.9
FEMUR_Z = 15.75          # femur axis height in template frame
PLANE_Y = 8.27           # foot plane lateral offset at neutral (template y)

# Section Kinematics
def Rz(deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    M = np.eye(4); M[0, 0], M[0, 1], M[1, 0], M[1, 1] = c, -s, s, c
    return M

def frames(qc, qf, qt):
    Tc = Rz(qc)
    Tf = Tc @ D["Mf"] @ Rz(qf)
    Tt = Tf @ D["Mt"] @ Rz(qt)
    return Tc, Tf, Tt

def tip(q):
    return (frames(*q)[2] @ np.append(D["tip"], 1))[:3]

def ik(target, q0):
    q = np.array(q0, float)
    for _ in range(50):
        e = target - tip(q)
        if np.linalg.norm(e) < 1e-3: return q, True
        J = np.zeros((3, 3)); h = 1e-3
        for k in range(3):
            dq = np.zeros(3); dq[k] = h; J[:, k] = (tip(q + dq) - tip(q)) / h
        q += np.clip(np.linalg.lstsq(J, e, rcond=None)[0], -10, 10)
    return q, np.linalg.norm(target - tip(q)) < 0.05

def fw_to_template(x, y, z):
    """firmware leg frame (x tangential, y radial, z rel. femur-axis plane) -> template"""
    return np.array([y, PLANE_Y - x, FEMUR_Z + z])

def leg_points(q, parts=("ground", "coxa", "femur", "tibia")):
    Tc, Tf, Tt = frames(*q); out = {}
    for p, T in [("ground", np.eye(4)), ("coxa", Tc), ("femur", Tf), ("tibia", Tt)]:
        if p in parts:
            P = D[p]; out[p] = P @ T[:3, :3].T + T[:3, 3]
    return out

def mount_T(mx, my, ang):
    T = Rz(ang); T[0, 3], T[1, 3] = mx, my; return T

def to_body(P, T): return P @ T[:3, :3].T + T[:3, 3]

def min_dist(A, B, chunk=1500, cutoff=40.0):
    best = np.inf
    # keep only points that can be within cutoff of the other cloud's AABB
    A = A[np.all((A > B.min(0) - cutoff) & (A < B.max(0) + cutoff), axis=1)]
    B = B[np.all((B > A.min(0) - cutoff) & (B < A.max(0) + cutoff), axis=1)] if len(A) else B[:0]
    if len(A) == 0 or len(B) == 0: return np.inf
    A = A.astype(np.float32); B = B.astype(np.float32)
    for i in range(0, len(A), chunk):
        a = A[i:i + chunk]
        d = ((a[:, None, :] - B[None, :, :]) ** 2).sum(-1)
        best = min(best, d.min())
    return np.sqrt(best)

def cloud_dist(CA, CB, cutoff=40.0):
    """min distance between two dicts of link clouds, skipping far-apart AABB pairs"""
    best, where = np.inf, None
    for ka, A in CA.items():
        for kb, B in CB.items():
            gap = np.maximum(0, np.maximum(A.min(0) - B.max(0), B.min(0) - A.max(0)))
            if np.linalg.norm(gap) > min(cutoff, best): continue
            d = min_dist(A, B, cutoff=min(cutoff, best))
            if d < best: best, where = d, (ka, kb)
    return best, where

# Section Firmware DH (for servo-range check), lengths as firmware or CAD
def fw_ik(y, z, L=(36.0, 62.0, 87.0)):
    L1, L2, L3 = L; px = y - L1; vz = -z
    ck = (px * px + vz * vz - L2 * L2 - L3 * L3) / (2 * L2 * L3)
    if abs(ck) > 1: return []
    sols = []
    for kap in [np.degrees(np.arccos(ck)), -np.degrees(np.arccos(ck))]:
        k = np.radians(kap)
        beta = np.arctan2(vz, px) - np.arctan2(L3 * np.sin(k), L2 + L3 * np.cos(k))
        sols.append((90.0, np.degrees(beta) + 90.0, kap + 20.0))
    return sols

# Section Layout + gait evaluation
FACE = 22.05                       # holder inner face (21.55) + 0.5 gap, from yaw axis
Y0, Z0, HW, YARC, LIFT, STANCE = 95.0, -80.0, 25.0, 15.0, 50.0, 0.6
LEGS = ["FL", "ML", "RL", "FR", "MR", "RR"]
GROUP_A = {"FL", "MR", "RL"}

def layout(W, psi, xc, yc):
    ym = W / 2 + FACE
    a = 90 - psi
    return {"FL": (xc, yc, a), "ML": (0, ym, 90), "RL": (-xc, yc, 180 - a),
            "FR": (xc, -yc, -a), "MR": (0, -ym, -90), "RR": (-xc, -yc, -(180 - a))}

def path(u, mode, T):
    """foot target in template frame for phase u; mode 'leg' (firmware canonical) or 'body' (walk along body X)"""
    u = u % 1.0
    if u <= STANCE:
        s = HW - 2 * HW * u / STANCE; arc = 0.0
    else:
        sp = (u - STANCE) / (1 - STANCE); s = -HW + 2 * HW * sp; arc = np.sin(np.pi * sp)
    if mode == "leg":
        return fw_to_template(s, Y0 + YARC * arc, Z0 + LIFT * arc)
    N = T @ np.append(fw_to_template(0, Y0 + YARC * arc, Z0 + LIFT * arc), 1)
    N[0] += s                                   # stride along body X
    return (np.linalg.inv(T) @ N)[:3]

def feet_body(lay, u, mode):
    out = {}
    for L in LEGS:
        T = mount_T(*lay[L]); uu = u + (0 if L in GROUP_A else 0.5)
        out[L] = (to_body(path(uu, mode, T)[None], T)[0], (uu % 1.0) <= STANCE)
    return out

def hull_margin(pts, c=np.zeros(2)):
    P = np.array(pts)[:, :2]; ctr = P.mean(0)
    P = P[np.argsort(np.arctan2(P[:, 1] - ctr[1], P[:, 0] - ctr[0]))]
    m = np.inf
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]; e = b - a; n = np.array([e[1], -e[0]]) / np.linalg.norm(e)
        m = min(m, -np.dot(c - a, n))          # positive inside for CCW order
    return m

def static_cage_clear(lay, pairs, yaws=range(-50, 51, 10)):
    """ground+coxa of adjacent legs over the full yaw grid -> min distance"""
    best = np.inf
    for A, B in pairs:
        TA, TB = mount_T(*lay[A]), mount_T(*lay[B])
        gA = to_body(D["ground"], TA); gB = to_body(D["ground"], TB)
        for ya in yaws:
            cA = to_body(leg_points([COXA_ZERO + ya, 0, 0], ("coxa",))["coxa"], TA)
            for yb in yaws:
                cB = to_body(leg_points([COXA_ZERO + yb, 0, 0], ("coxa",))["coxa"], TB)
                d, _ = cloud_dist({"g": gA, "c": cA}, {"g": gB, "c": cB}, cutoff=15)
                best = min(best, d)
    return best

PAIRS = [("FL", "ML"), ("ML", "RL"), ("FR", "MR"), ("MR", "RR"), ("FL", "FR"), ("RL", "RR")]

def gait_eval(lay, mode, n=20):
    q0 = {L: [COXA_ZERO, -33.4, -4.9] for L in LEGS}
    minclr = (np.inf, None); yaw = {L: [np.inf, -np.inf] for L in LEGS}; stab = np.inf
    for u in np.linspace(0, 1, n, endpoint=False):
        clouds = {}
        for L in LEGS:
            T = mount_T(*lay[L]); uu = u + (0 if L in GROUP_A else 0.5)
            q, ok = ik(path(uu, mode, T), q0[L]); q0[L] = q
            if not ok: return {"fail": "IK %s u=%.2f" % (L, u)}
            y_ = q[0] - COXA_ZERO; yaw[L] = [min(yaw[L][0], y_), max(yaw[L][1], y_)]
            clouds[L] = {k: to_body(v, T) for k, v in leg_points(q).items()}
        for A, B in PAIRS:
            d, w = cloud_dist(clouds[A], clouds[B], cutoff=30)
            if d < minclr[0]: minclr = (d, "%s/%s %s u=%.2f" % (A, B, w, u))
        F = feet_body(lay, u, mode)
        sup = [p for p, st in F.values() if st]
        stab = min(stab, hull_margin(sup))
    return {"clear": minclr, "yaw": yaw, "stab": stab}

def loads(lay):
    F = feet_body(lay, 0.0, "leg")
    # neutral (x=0) feet
    nf = {L: to_body(fw_to_template(0, Y0, Z0)[None], mount_T(*lay[L]))[0] for L in LEGS}
    dm, dc = abs(nf["ML"][1]), abs(nf["FL"][1])
    return dm, dc, dc / (dm + dc), dm / (2 * (dm + dc)), nf
