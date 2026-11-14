"""Stick-man character v2 (RicksClips style): bada gol safed sar, mote outline, kapde, sneakers.
Sab kuch code se draw hota hai (free). v3: asli haath (palm+angutha+ungliyan, point mein ungli), skin-colour forearm + sleeves,
collar/polo/hoodie/stripe shirts, belt, jeans cuff, shoes (toe cap + laces). Pichhle version mein:
 - IK fix (elbow bahar, knee aage), eyebrows ka emotion bug fix
 - lipsync: 4 mouth shapes (band / oh / ah / ee) + teeth + tongue, audio se aate hain
 - animation: anticipation/overshoot, breathing, weight shift, hop, squash&stretch, proper walk cycle
 - light: scene ki light direction (ls), key/fill, ground bounce, directional rim light
v4: smooth motion (overshoot naram, sar/gardan ka follow-through, awaaz ki smooth energy se gesture), asli saans (seena phoolta hai),
natural blink (random waqt, naram band/khulna, kabhi double-blink) + aankhon ki halki harkat, aur HELD PROPS: prop haathon ke
bilkul beech grip point par, peeche wala haath prop ke peeche, aage wala haath prop ke upar (barrel/murgi/andey/sikke/moneybag)"""
import math
import zlib

import cv2
import numpy as np

INK = (34, 28, 42)
SKIN = (247, 224, 198)                          # reference jaisa halka peach/beige rang
SHIRTS = dict(yellow=(238, 190, 48), red=(205, 55, 50), blue=(70, 110, 190), green=(70, 150, 80), orange=(235, 140, 50),
              purple=(120, 85, 170), teal=(50, 150, 150), pink=(225, 120, 160), gray=(130, 130, 140),
              black=(45, 45, 55), white=(238, 238, 238), brown=(130, 85, 55), navy=(40, 55, 100))
HAIRS = dict(black=(35, 30, 35), brown=(130, 82, 50), blonde=(225, 190, 90), red=(190, 80, 40), gray=(150, 150, 155),
             orange=(215, 120, 50))


def col(name, table, default):
    if isinstance(name, (list, tuple)):
        return tuple(int(v) for v in name)
    return table.get(str(name).lower(), default)


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def back(x):
    x = min(1.0, max(0.0, x))
    c = 1.25                                    # pehle 1.9 (bohot zyada overshoot = jhatka); ab naram
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def shade(c, k):
    return tuple(int(min(255, max(0, v * k))) for v in c)


def lerp(a, b, k):
    return a + (b - a) * k


def lerp2(a, b, k):
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)


def blink_open(t, seed):
    """Aankh kitni khuli hai (1 = poori, ~0.06 = band). Har character ka apna rhythm, har blink ka apna waqt (3-4 sec),
    kabhi kabhi double-blink; band hona tez, khulna thoda dheere (sine curve) => robotic nahi lagta."""
    seed = int(seed)
    P = 3.2 + 0.8 * ((seed * 7) % 10) / 10.0
    tt = t + (seed % 23) * 0.37
    n = int(tt // P)
    r = ((n * 2654435761 + seed * 40503) % 65536) / 65536.0
    u = tt - n * P - (0.35 + r * (P - 1.0))
    dur = 0.18
    for s0 in ((0.0, 0.26) if r > 0.8 else (0.0,)):
        k = (u - s0) / dur
        if 0.0 <= k < 1.0:
            return 1.0 - 0.94 * math.sin(math.pi * k)
    return 1.0


def ik(s, t, l1, l2, score):
    """2-segment limb: s -> t. Dono elbow candidates mein se wo chunta hai jiska score(ex, ey) zyada ho
    (arm: bahar+neeche, leg: knee aage). Pehle ka bend-sign approach hand upar/neeche hone par ulta ho jata tha."""
    dx, dy = t[0] - s[0], t[1] - s[1]
    dist = max(1e-6, math.hypot(dx, dy))
    d = min(dist, l1 + l2 - 1e-3)
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, l1 * l1 - a * a))
    ux, uy = dx / dist, dy / dist
    mx, my = s[0] + ux * a, s[1] + uy * a
    c1 = (mx - uy * h, my + ux * h)
    c2 = (mx + uy * h, my - ux * h)
    return c1 if score(*c1) >= score(*c2) else c2


class Pen:
    """RGB + mask par ek saath draw (supersampled window)."""

    def __init__(self, w, h, ss):
        self.ss = ss
        self.w, self.h = int(w * ss), int(h * ss)
        self.rgb = np.zeros((self.h, self.w, 3), np.uint8)
        self.m = np.zeros((self.h, self.w), np.uint8)

    def P(self, p):
        return (int(round(p[0] * self.ss * 16)), int(round(p[1] * self.ss * 16)))

    def circle(self, c, r, color, ow=0.0):
        s = self.ss
        if ow > 0:
            cv2.circle(self.rgb, self.P(c), int((r + ow) * s * 16), INK, -1, cv2.LINE_AA, 4)
        cv2.circle(self.rgb, self.P(c), int(r * s * 16), color, -1, cv2.LINE_AA, 4)
        cv2.circle(self.m, self.P(c), int((r + ow) * s * 16), 255, -1, cv2.LINE_AA, 4)

    def ellipse(self, c, rx, ry, color, ow=0.0, ang=0.0, a0=0, a1=360, fill=True):
        s = self.ss
        t = -1 if fill else max(1, int(ow * s))
        if ow > 0 and fill:
            cv2.ellipse(self.rgb, self.P(c), (int((rx + ow) * s * 16), int((ry + ow) * s * 16)), ang, a0, a1, INK, -1, cv2.LINE_AA, 4)
        cv2.ellipse(self.rgb, self.P(c), (int(rx * s * 16), int(ry * s * 16)), ang, a0, a1, color, t, cv2.LINE_AA, 4)
        cv2.ellipse(self.m, self.P(c), (int((rx + ow) * s * 16), int((ry + ow) * s * 16)), ang, a0, a1, 255, t, cv2.LINE_AA, 4)

    def poly(self, pts, color, ow=0.0):
        s = self.ss
        a = np.array([self.P(p) for p in pts], np.int32)
        if ow > 0:
            cv2.polylines(self.rgb, [a], True, INK, max(1, int(ow * 2 * s)), cv2.LINE_AA, 4)
        cv2.fillPoly(self.rgb, [a], color, cv2.LINE_AA, 4)
        cv2.fillPoly(self.m, [a], 255, cv2.LINE_AA, 4)
        if ow > 0:
            cv2.polylines(self.m, [a], True, 255, max(1, int(ow * 2 * s)), cv2.LINE_AA, 4)

    def line(self, pts, w, color=INK, ow=0.0):
        """Poori polyline ek saath (pehle outline, phir rang) => joints par kaala daag nahi banta."""
        s = self.ss
        a = np.array([self.P(p) for p in pts], np.int32)
        if ow > 0:
            cv2.polylines(self.rgb, [a], False, INK, max(1, int((w + 2 * ow) * s)), cv2.LINE_AA, 4)
        cv2.polylines(self.rgb, [a], False, color, max(1, int(w * s)), cv2.LINE_AA, 4)
        cv2.polylines(self.m, [a], False, 255, max(1, int((w + 2 * ow) * s)), cv2.LINE_AA, 4)

    def paste(self, rgb, al, x, y):
        """Float sprite (rgb 0..255, alpha 0..1, pen ke supersampled px mein) ko (x, y) top-left par blend karta hai.
        Mask bhi badhta hai (taake bounding box/rim light prop ko bhi shamil karein)."""
        h, w = al.shape
        X0, Y0 = int(round(x)), int(round(y))
        xa, ya, xb, yb = max(0, X0), max(0, Y0), min(self.w, X0 + w), min(self.h, Y0 + h)
        if xb <= xa or yb <= ya:
            return
        a = al[ya - Y0:yb - Y0, xa - X0:xb - X0]
        c = rgb[ya - Y0:yb - Y0, xa - X0:xb - X0]
        reg = self.rgb[ya:yb, xa:xb].astype(np.float32)
        self.rgb[ya:yb, xa:xb] = np.clip(reg * (1 - a[..., None]) + c * a[..., None], 0, 255).astype(np.uint8)
        self.m[ya:yb, xa:xb] = np.maximum(self.m[ya:yb, xa:xb], (a * 255).astype(np.uint8))

    def blend_in_mask(self, draw_fn, alpha, c, r):
        """Mask ke andar hi shade/highlight (soft shading). Sirf (c, r) ke aas-paas ka box process hota hai (tez)."""
        x0, y0 = max(0, int((c[0] - r) * self.ss)), max(0, int((c[1] - r) * self.ss))
        x1, y1 = min(self.w, int((c[0] + r) * self.ss) + 1), min(self.h, int((c[1] + r) * self.ss) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        sub = self.rgb[y0:y1, x0:x1]
        tmp = sub.copy()
        draw_fn(tmp, (x0 * 16, y0 * 16))
        a = (self.m[y0:y1, x0:x1].astype(np.float32) / 255.0 * alpha)[..., None]
        self.rgb[y0:y1, x0:x1] = (sub * (1 - a) + tmp * a).astype(np.uint8)


def rrect_pts(x0, y0, x1, y1, r, n=6):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# brow_tilt (+ = angry, inner end neeche), brow_lift, eye_open, mouth(base)
EMO = {
    "neutral": (0, 0, 1.0, "flat"), "happy": (-0.15, 0.1, 0.9, "smile"), "smug": (0.35, -0.1, 0.55, "smirk"),
    "angry": (0.9, -0.2, 0.8, "frown"), "surprised": (-0.2, 0.8, 1.35, "o"), "scared": (-0.8, 0.5, 1.25, "wobble"),
    "sad": (-0.9, 0.0, 0.8, "frown"), "laughing": (-0.2, 0.2, 0.15, "bigsmile"), "sleepy": (0, -0.2, 0.15, "flat"),
    "confused": (-0.3, 0.3, 1.0, "wobble"), "excited": (-0.2, 0.5, 1.2, "bigsmile"), "evil": (0.8, -0.1, 0.5, "bigsmile"),
    "worried": (-0.7, 0.3, 1.1, "wobble"), "proud": (0.1, 0.1, 0.7, "smile"), "cry": (-0.9, 0.0, 0.6, "frown"),
}
# mouth rest shapes: (half-width, open, corner_drop(+neeche), asym)
MOUTH = {"flat": (0.035, 0.0, 0.0, 0.0), "smile": (0.046, 0.0, -0.016, 0.0), "bigsmile": (0.056, 0.040, -0.018, 0.0),
         "smirk": (0.040, 0.0, -0.002, 1.0), "frown": (0.040, 0.0, 0.017, 0.0), "o": (0.024, 0.055, 0.0, 0.0),
         "wobble": (0.040, 0.0, 0.0, 0.0)}
# vis: 0 band, 1 'oh', 2 'ah', 3 'ee'
VIS_SHAPE = {1: (0.021, 0.012, 0.050), 2: (0.031, 0.014, 0.068), 3: (0.050, 0.008, 0.026)}   # (hw, ho_min, ho_gain)


EXPR = 0.6      # chehre ke expression ki shiddat (1.0 = purana, bohot zyada)


def walk_speed(action):
    """Zameen par pair ki average speed (H units / sec) - render_story isi se body ko chalata hai => feet slide nahi karte."""
    if action == "run":
        return 0.64 * 0.105 * 10.5
    if action == "walk":
        return 0.64 * 0.058 * 7.0
    return 0.0


REST = dict(lh=(-0.13, 0.33), rh=(0.13, 0.33), lf=(-0.065, 0.0), rf=(0.065, 0.0))


def pose(action, t, talk, mouth, grip=None):
    """Hand/foot targets (H-units, feet-centre se, x: facing ki taraf +, y upar +). talk: speaker abhi bol raha hai?
    mouth yahan SMOOTH energy hai (gesture ke liye), raw lip-sync nahi. grip: {lh, rh} => haath prop pakadne ki jagah par."""
    s = math.sin
    p = dict(REST)
    p.update(bob=0.003 * s(t * 2.3), tilt=0.006 * s(t * 0.8 + 1.3), lean=0.012 * s(t * 1.1), nod=0.0, jump=0.0)
    tgt = dict(lh=None, rh=None)
    k = back(t / 0.30)          # action shuru hone par rest -> pose, thoda overshoot ke saath
    if action in ("talk", "idle", "smile", "listen"):
        tgt["lh"] = (-0.13 + 0.006 * s(t * 1.7), 0.33 + 0.008 * s(t * 2.1 + 1))
        tgt["rh"] = (0.13 + 0.006 * s(t * 1.5 + 2), 0.33 + 0.008 * s(t * 2.3))
        if talk and action != "idle":
            g = 0.5 + 0.5 * s(t * 4.4 + 0.7)
            h2 = 0.5 + 0.5 * s(t * 2.7 + 2.0)
            amp = 0.55 + 0.45 * mouth
            tgt["rh"] = (0.20 + 0.05 * s(t * 3.7), 0.40 + 0.15 * g * amp)
            tgt["lh"] = (-0.19 + 0.02 * s(t * 3.1), 0.35 + 0.07 * h2 * amp)
            p["nod"] = 0.010 * s(t * 6.4) + 0.012 * mouth
            p["tilt"] = 0.02 * s(t * 2.1)
            p["bob"] += 0.004 * mouth
        elif talk:
            p["nod"] = 0.006 * s(t * 5.5) + 0.008 * mouth
        else:
            p["nod"] = 0.006 * s(t * 1.8)
    elif action == "point":
        tgt["rh"] = (0.36, 0.66 + 0.02 * s(t * 4))
        tgt["lh"] = (-0.12, 0.31)
        p["lean"] += 0.025
    elif action in ("shock", "scream"):
        q = ease(t / 0.18)
        tgt["lh"] = (-0.22, 0.58 + 0.008 * s(t * 14) * q)
        tgt["rh"] = (0.22, 0.58 + 0.008 * s(t * 14 + 1) * q)
        p["jump"] = 0.022 * s(min(1.0, t / 0.38) * math.pi) if t < 0.38 else 0.0
        p["bob"] = 0.004 * s(t * 30)
        p["lean"] -= 0.02 * q
        k = ease(t / 0.12)
    elif action == "celebrate":
        tgt["lh"] = (-0.26, 0.70 + 0.03 * s(t * 5))
        tgt["rh"] = (0.26, 0.70 + 0.03 * s(t * 5 + 3))
        p["jump"] = abs(0.018 * s(t * 4))
        p["tilt"] = 0.015 * s(t * 4)
    elif action == "shrug":
        sh = ease(t / 0.25) * (0.7 + 0.3 * s(t * 2.6))
        tgt["lh"] = (-0.25, 0.44 + 0.02 * sh)
        tgt["rh"] = (0.25, 0.44 + 0.02 * sh)
        p["tilt"] = 0.05 * s(t * 3)
        p["bob"] += 0.012 * sh
    elif action == "think":
        tgt["rh"] = (0.085, 0.625)
        tgt["lh"] = (-0.10, 0.36)
        p["tilt"] = 0.03 * s(t * 1.4)
        p["lean"] += 0.01
    elif action == "facepalm":
        tgt["rh"] = (0.02, 0.80)
        tgt["lh"] = (-0.12, 0.32)
        p["tilt"] = -0.05
        p["lean"] -= 0.03
        p["nod"] = -0.02
    elif action == "laugh":
        tgt["lh"] = (-0.08, 0.40 + 0.005 * s(t * 8))
        tgt["rh"] = (0.08, 0.40 + 0.005 * s(t * 8 + 1))
        p["jump"] = abs(0.008 * s(t * 9))
        p["tilt"] = 0.02 * s(t * 8)
        p["lean"] -= 0.015
    elif action == "angry":
        tgt["lh"] = (-0.17, 0.38 + 0.006 * s(t * 8))
        tgt["rh"] = (0.17, 0.38 + 0.006 * s(t * 8 + 1))
        p["lean"] += 0.035
        p["bob"] += 0.002 * s(t * 8)
        p["nod"] = -0.01
    elif action == "hold":
        tgt["lh"] = (-0.10, 0.41 + 0.004 * s(t * 3))
        tgt["rh"] = (0.10, 0.41 + 0.004 * s(t * 3 + 1))
    elif action == "wave":
        tgt["rh"] = (0.25 + 0.03 * s(t * 11), 0.80 + 0.04 * s(t * 11 + 1.5))
        tgt["lh"] = (-0.13, 0.33)
        p["tilt"] = 0.02 * s(t * 5.5)
    elif action in ("walk", "run"):
        run = action == "run"
        f, amp, lift = (10.5, 0.105, 0.075) if run else (7.0, 0.058, 0.045)
        ph = t * f
        p["lf"] = (-0.04 + amp * s(ph), max(0.0, lift * s(ph + 1.57)))
        p["rf"] = (0.04 - amp * s(ph), max(0.0, lift * s(ph - 1.57)))
        sw = (0.10 if run else 0.07) * s(ph)
        tgt["lh"] = (-0.12 + sw, 0.33 + (0.06 if run else 0.0))
        tgt["rh"] = (0.12 - sw, 0.33 + (0.06 if run else 0.0))
        p["bob"] = abs((0.016 if run else 0.011) * s(ph)) - 0.004
        p["jump"] = max(0.0, 0.02 * s(ph * 2 + 0.6)) if run else 0.0
        p["lean"] += 0.05 if run else 0.012
        p["nod"] = 0.006 * s(ph * 2)
        k = ease(t / 0.18)
    elif action == "sad":
        tgt["lh"] = (-0.10, 0.27)
        tgt["rh"] = (0.10, 0.27)
        p["nod"] = -0.025
        p["tilt"] = 0.03
        p["bob"] -= 0.004
    elif action == "sleep":
        p["tilt"] = 0.1
    if action not in ("walk", "run"):          # halki, natural harkat (over-acting nahi)
        for key_ in ("jump", "tilt", "nod", "lean"):
            p[key_] *= 0.75
    if grip is not None and action not in ("walk", "run"):      # prop pakda hua hai: haath grip par, overshoot ke bina
        tgt["lh"], tgt["rh"] = grip["lh"], grip["rh"]
        k = ease(t / 0.30)
    for key in ("lh", "rh"):
        if tgt[key] is not None:
            p[key] = lerp2(REST[key], tgt[key], k)
    return p


def mouth_draw(pen, mc, H, ow, lw, mshape, mo, vis, d, t, ek=1.0):
    """Mouth ek parametric closed shape: upar/neeche lip curve + corner drop. Speaking mein vis shape (oh/ah/ee)."""
    hw, ho, cd, asym = MOUTH.get(mshape, MOUTH["flat"])
    hw, ho, cd, asym = lerp(MOUTH["flat"][0], hw, ek), ho * ek, cd * ek, asym * ek      # halka expression
    if mo > 0.06:
        v = vis if vis in VIS_SHAPE else 2
        vhw, hmin, hg = VIS_SHAPE[v]
        ho = max(ho * 0.6, hmin + hg * mo)
        hw = vhw * (1 + 0.05 * mo) if mshape not in ("bigsmile", "smile") else lerp(vhw, hw, 0.35)
        if mshape == "o":
            ho = max(ho, 0.05)
        cd *= 0.7
    wob = 0.0
    if mshape == "wobble" and mo <= 0.06:
        wob = 0.003 * math.sin(t * 9)
    n = 11
    xs = np.linspace(-1, 1, n)
    base = [(cd * x * x + asym * 0.011 * x * d + wob * math.sin(x * 4 + t * 10)) for x in xs]
    if ho < 0.004:
        pts = [(mc[0] + x * hw * H, mc[1] + b * H) for x, b in zip(xs, base)]
        pen.line(pts, lw, INK)
        return
    up = [(mc[0] + x * hw * H, mc[1] + (b - 0.30 * ho * (1 - x * x)) * H) for x, b in zip(xs, base)]
    lo = [(mc[0] + x * hw * H, mc[1] + (b + 0.70 * ho * (1 - x * x)) * H) for x, b in zip(xs, base)]
    pen.poly(up + lo[::-1], (64, 24, 38), ow * 0.75)
    if ho > 0.03:
        pen.ellipse((mc[0], mc[1] + (base[n // 2] + 0.50 * ho) * H), hw * 0.50 * H, 0.17 * ho * H, (208, 96, 108), 0)
    if ho > 0.018:
        th = min(0.30 * ho, 0.017)
        tu = [(mc[0] + x * 0.80 * hw * H, mc[1] + (base[i] - 0.30 * ho * (1 - (x * 0.8) ** 2) + 0.004) * H) for i, x in enumerate(xs)]
        td = [(px, py + th * H) for px, py in tu]
        pen.poly(tu + td[::-1], (252, 252, 252), 0)


def hand(pen, c, dv, R, ow, pointing=False):
    """Asli haath: ungliyan + palm + angutha. c = haath ka markaz (px), dv = forearm ki direction (unit), R = haath ka radius (px)."""
    ang = math.degrees(math.atan2(dv[1], dv[0]))
    nx, ny = -dv[1], dv[0]
    side = -1 if ny > 0 else 1                                   # angutha hamesha upar ki taraf
    pc = (c[0] + dv[0] * R * 0.55, c[1] + dv[1] * R * 0.55)
    if pointing:
        tip = (pc[0] + dv[0] * R * 2.3, pc[1] + dv[1] * R * 2.3)
        pen.line([pc, tip], R * 0.50, SKIN, ow * 0.8)
        for j in (0.45, 0.85):                                   # baaki ungliyan mudi hui
            pen.ellipse((pc[0] + dv[0] * R * 0.55 - nx * side * R * j, pc[1] + dv[1] * R * 0.55 - ny * side * R * j), R * 0.42, R * 0.30, SKIN, ow * 0.7, ang)
    else:
        for j in (-1, 0, 1):
            fc = (pc[0] + dv[0] * R * 0.95 + nx * j * R * 0.55, pc[1] + dv[1] * R * 0.95 + ny * j * R * 0.55)
            pen.ellipse(fc, R * 0.55, R * 0.30, SKIN, ow * 0.7, ang)
    pen.ellipse(pc, R * 1.05, R * 0.85, SKIN, ow, ang)
    tb = (pc[0] + side * nx * R * 0.80 + dv[0] * R * 0.15, pc[1] + side * ny * R * 0.80 + dv[1] * R * 0.15)
    pen.ellipse(tb, R * 0.55, R * 0.30, SKIN, ow * 0.8, ang + side * 45)
    pen.ellipse((pc[0] - dv[0] * R * 0.2 - side * nx * R * 0.2, pc[1] - dv[1] * R * 0.2 - side * ny * R * 0.2), R * 0.35, R * 0.22, (255, 255, 255), 0, ang)


def prep_held(held, pen, H):
    """Held prop ka sprite (pen ke supersampled scale par), uska grip point aur haathon ke target.
    held = dict(render(scale)->(rgb, al, ox, oy), gx, gy (bbox fraction, upar se), hy (haath ki unchai, H-units),
    fwd (prop ka markaz body se aage, H-units), appear 0..1). Prop ka asli size sprite ke alpha bbox se naapa jata hai."""
    try:
        rgb, al, _, _ = held["render"](pen.ss)
    except Exception:
        return None
    if rgb is None or al is None:
        return None
    al = np.asarray(al, np.float32)
    if al.size == 0:
        return None
    if al.max() > 1.5:
        al = al / 255.0
    rgb = np.asarray(rgb, np.float32)
    ys, xs = np.where(al > 0.08)
    if len(xs) < 4:
        return None
    bx0, bx1, by0, by1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    bw = (bx1 - bx0) / pen.ss                                    # prop ki chaurai (window px)
    hw = min(0.185, max(0.075, 0.5 * bw * held.get("reach", 1.0) / H))     # haath prop ke dono kinaron par (arm ki lambai ke andar)
    gx = bx0 + held.get("gx", 0.5) * (bx1 - bx0)
    gy = by0 + held.get("gy", 0.5) * (by1 - by0)
    ap = float(held.get("appear", 1.0))
    if ap < 0.999:                                               # prop nazar aate waqt grip point se chhota -> bada
        if ap <= 0.03:
            rgb = al = None
        else:
            nw, nh = max(2, int(al.shape[1] * ap)), max(2, int(al.shape[0] * ap))
            rgb = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
            al = cv2.resize(al, (nw, nh), interpolation=cv2.INTER_AREA)
            gx, gy = gx * ap, gy * ap
    fwd, hy = held.get("fwd", 0.11), held.get("hy", 0.40)
    return dict(rgb=rgb, al=al, gx=gx, gy=gy, grip=dict(lh=(fwd - hw, hy), rh=(fwd + hw, hy)))


def draw_char(pen, fx, fy, H, ch, action, emo, t, mouth, vis, talk, look, facing, enter, blink_seed, ls, energy=None, held=None):
    """pen: Pen window; (fx,fy) = pairon ka markaz (window coords, px); H = qad px; facing +1 right / -1 left;
    ls = light ki taraf (+1 light daayen se, -1 baayen se). energy = awaaz ki smooth energy (gesture ke liye);
    held = prop jo haathon mein hai (prep_held dekhein)."""
    d = 1 if facing >= 0 else -1
    shirt = col(ch.get("shirt", "yellow"), SHIRTS, SHIRTS["yellow"])
    hat = ch.get("hat", "none")
    hat_c = col(ch.get("hat_color", "red"), SHIRTS, SHIRTS["red"])
    hair_c = col(ch.get("hair_color", "brown"), HAIRS, HAIRS["brown"])
    pants = col(ch.get("pants", "navy" if not ch.get("overalls") else "blue"), SHIRTS, SHIRTS["navy"])
    style = ch.get("style") or ("tee", "polo", "stripe", "hoodie")[zlib.crc32(str(ch.get("name", "x")).encode()) % 4]
    ow = max(1.3, 0.011 * H)
    lw = max(1.6, 0.017 * H)
    en = mouth if energy is None else energy                         # gesture smooth energy se, lip-sync raw mouth se
    hd = prep_held(held, pen, H) if held else None
    grip = hd["grip"] if hd else None
    po = pose(action, t, talk, en, grip)
    po_l = pose(action, max(0.0, t - 0.07), talk, en, grip)         # sar/gardan body se thoda late (follow-through)
    br = math.sin(t * 1.75)                                          # saans (~3.6 sec ka chakkar)
    # ---- entrance squash & stretch (girte waqt lamba, utarte hi chapta)
    sx = sy = 1.0
    if enter < 1.0:
        e = max(0.0, 1 - enter)
        sx, sy = 1 - 0.04 * e, 1 + 0.06 * e
    elif enter < 1.6:
        q = (enter - 1.0) / 0.6
        sq = 0.04 * math.sin(q * math.pi) * (1 - q)
        sx, sy = 1 + 0.8 * sq, 1 - sq
    bob, jump = po["bob"], po["jump"]
    lean = po["lean"]
    X = lambda x: fx + d * x * H * sx
    Yb = lambda y: fy - (y + bob + jump) * H * sy          # body (bob + jump)
    Yf = lambda y: fy - (y + jump) * H * sy                # feet (sirf jump)
    shear = lambda x, y: x + lean * 0.9 * (y - 0.33) / 0.27   # torso ka jhukaav (neeche hip, upar lean)
    hip_y = 0.345
    sh_y = 0.585 + 0.0025 * br                              # saans mein kandhe halke uthte hain
    lsh = (-0.075 + lean * 0.85, sh_y)
    rsh = (0.075 + lean * 0.85, sh_y)
    # ---- legs (jeans + cuff, sneakers: toe cap + sole + laces)
    for side, key in ((-1, "lf"), (1, "rf")):
        foot = po[key]
        hp = (side * 0.04, hip_y + bob)
        kn = ik(hp, (foot[0], foot[1]), 0.17, 0.18, lambda ex, ey: ex)    # knee hamesha aage
        pts_l = [(X(hp[0]), Yf(hp[1] - bob)), (X(kn[0]), Yf(kn[1] - bob * 0.5)), (X(foot[0]), Yf(foot[1] + 0.014))]
        pen.line(pts_l, 0.016 * H, pants, ow * 0.8)
        cf = lerp2(pts_l[1], pts_l[2], 0.72)
        fxp, fyp = X(foot[0] + 0.024), Yf(foot[1] + 0.010)
        pen.ellipse((fxp + d * 0.006 * H, fyp), 0.034 * H * sx, 0.016 * H, (66, 50, 46), ow * 0.8)       # chhota kaala joota
        pen.ellipse((fxp + d * 0.016 * H, fyp - 0.004 * H), 0.016 * H * sx, 0.008 * H, (108, 88, 80), 0)

    # ---- arms: skin forearm + sleeve (hoodie = poori aasteen) + asli haath
    long_sl = style == "hoodie"

    def arm(sh, hand_p, side, pointing=False):
        hand_p = (hand_p[0] + lean * 0.5, hand_p[1])
        el = ik(sh, hand_p, 0.14, 0.15, lambda ex, ey: side * ex - 0.7 * ey)      # elbow bahar + neeche
        pts = [(X(sh[0]), Yb(sh[1])), (X(el[0]), Yb(el[1])), (X(hand_p[0]), Yb(hand_p[1]))]
        pen.line(pts, 0.014 * H, SKIN, ow * 0.9)                                  # skin wali bazu (outline ke saath)
        if long_sl:
            wr = lerp2(pts[1], pts[2], 0.78)
            pen.line([pts[0], pts[1], wr], 0.026 * H, shirt, ow * 0.8)
            pen.line([lerp2(pts[1], pts[2], 0.70), wr], 0.030 * H, shade(shirt, 0.78), ow * 0.6)      # cuff
        else:
            sl = lerp2(pts[0], pts[1], 0.78)
            pen.line([pts[0], sl], 0.030 * H, shirt, ow * 0.8)
            pen.line([lerp2(pts[0], pts[1], 0.66), sl], 0.032 * H, shade(shirt, 0.82), ow * 0.5)      # sleeve ka kinara
        fv = (pts[2][0] - pts[1][0], pts[2][1] - pts[1][1])
        fl = max(1e-6, math.hypot(*fv))
        hand(pen, pts[2], (fv[0] / fl, fv[1] / fl), 0.021 * H, ow * 0.7, pointing)

    arm(lsh, po["lh"], -1)
    # ---- torso
    tbw, tbh = 0.108 * (1 + 0.018 * br), 0.150 * (1 + 0.030 * br)            # saans: seena halka phoolta/sikudta hai
    tp = []                                                                  # aloo/bean jaisa potato torso (super-ellipse)
    for k_ in range(40):
        th = 2 * math.pi * k_ / 40
        cs, sn = math.cos(th), math.sin(th)
        tp.append((shear(tbw * math.copysign(abs(cs) ** (2 / 3), cs), 0.465 + tbh * math.copysign(abs(sn) ** (2 / 3), sn)), 0.465 + tbh * math.copysign(abs(sn) ** (2 / 3), sn)))
    pen.poly([(X(x), Yb(y)) for x, y in tp], shirt, ow)
    if ch.get("overalls"):
        bib = [(shear(x, y), y) for x, y in rrect_pts(-0.060, 0.50, 0.060, 0.33, 0.02, 4)]
        pen.poly([(X(x), Yb(y)) for x, y in bib], pants, ow * 0.6)
        for sx_ in (-0.045, 0.045):
            pen.line([(X(shear(sx_, 0.50)), Yb(0.50)), (X(shear(sx_ * 1.1, 0.60)), Yb(0.60))], 0.016 * H, pants)
            pen.circle((X(shear(sx_, 0.505)), Yb(0.505)), 0.011 * H, (240, 200, 70), ow * 0.4)
    elif ch.get("tie"):
        pen.poly([(X(shear(-0.014, 0.60)), Yb(0.60)), (X(shear(0.014, 0.60)), Yb(0.60)), (X(shear(0.02, 0.45)), Yb(0.45)),
                  (X(shear(0, 0.42)), Yb(0.42)), (X(shear(-0.02, 0.45)), Yb(0.45))], (170, 30, 40), ow * 0.4)
    if not ch.get("overalls"):
        dk = shade(shirt, 0.80)
        if style == "stripe":
            for yy_ in (0.55, 0.49, 0.43, 0.37):
                pen.line([(X(shear(-0.094, yy_)), Yb(yy_)), (X(shear(0.094, yy_)), Yb(yy_))], 0.017 * H, dk)
        elif style == "polo":
            for sg in (-1, 1):                                                  # collar
                pen.poly([(X(shear(sg * 0.012, 0.600)), Yb(0.600)), (X(shear(sg * 0.060, 0.600)), Yb(0.595)), (X(shear(sg * 0.030, 0.545)), Yb(0.545))],
                         shade(shirt, 1.12), ow * 0.5)
            pen.line([(X(shear(0, 0.56)), Yb(0.56)), (X(shear(0, 0.44)), Yb(0.44))], max(1.2, 0.005 * H), dk)
            for yb_ in (0.53, 0.47):
                pen.circle((X(shear(0, yb_)), Yb(yb_)), 0.006 * H, (245, 245, 245), 0)
        elif style == "hoodie":
            pen.ellipse((X(shear(0, 0.585)), Yb(0.585)), 0.078 * H * sx, 0.028 * H, dk, ow * 0.5)      # hood neck par
            pen.poly([(X(shear(x, y)), Yb(y)) for x, y in rrect_pts(-0.062, 0.455, 0.062, 0.345, 0.018, 3)], shade(shirt, 0.88), ow * 0.5)
            for sg in (-1, 1):
                pen.line([(X(shear(sg * 0.02, 0.57)), Yb(0.57)), (X(shear(sg * 0.026, 0.50)), Yb(0.50))], max(1.2, 0.005 * H), (235, 235, 235))
        else:                                                                    # tee: seene par jeb + crew neckline
            pen.poly([(X(shear(x, y)), Yb(y)) for x, y in rrect_pts(0.020, 0.52, 0.074, 0.45, 0.01, 3)], shade(shirt, 0.90), ow * 0.4)
            pen.ellipse((X(shear(0, 0.600)), Yb(0.600)), 0.040 * H * sx, 0.018 * H, shade(shirt, 0.72), 0)
        pen.line([(X(shear(-0.086, 0.352)), Yb(0.352)), (X(shear(0.086, 0.352)), Yb(0.352))], max(1.2, 0.006 * H), dk)       # hem
        for fx_, fy_ in ((-0.05, 0.50), (0.04, 0.42)):                           # kapde ki silwatein (folds)
            pen.line([(X(shear(fx_, fy_)), Yb(fy_)), (X(shear(fx_ + 0.018, fy_ - 0.05)), Yb(fy_ - 0.05)), (X(shear(fx_ - 0.004, fy_ - 0.09)), Yb(fy_ - 0.09))],
                     max(1.0, 0.004 * H), shade(shirt, 0.86))
    # torso shading: light ki ulti taraf andhera, light wali taraf halka highlight
    y0b, y1b = max(0, int(Yb(0.60) * pen.ss)), max(0, int(Yb(0.33) * pen.ss))
    if y1b > y0b:
        band = pen.rgb[y0b:y1b].astype(np.float32)
        m = pen.m[y0b:y1b].astype(np.float32)[..., None] / 255
        xs = (np.arange(pen.w, dtype=np.float32)[None, :, None] - fx * pen.ss) / (0.10 * H * pen.ss)
        dark = np.clip(-ls * xs, 0, 1) * 0.30
        lit = np.clip(ls * xs - 0.2, 0, 1) * 0.10
        pen.rgb[y0b:y1b] = np.clip(band * (1 - dark * m) + 255 * lit * m * 0.5, 0, 255).astype(np.uint8)
    # hip joint cover
    pen.ellipse((X(0), Yb(0.340)), 0.066 * H * sx, 0.015 * H, pants, ow * 0.35)
    if not ch.get("overalls") and style != "hoodie":                              # belt + buckle
        pen.line([(X(shear(-0.078, 0.343)), Yb(0.343)), (X(shear(0.078, 0.343)), Yb(0.343))], 0.016 * H, (58, 42, 34), ow * 0.5)
        pen.poly([(X(shear(x, y)), Yb(y)) for x, y in rrect_pts(-0.014, 0.352, 0.014, 0.334, 0.004, 2)], (226, 190, 80), ow * 0.3)
    # ---- held prop: grip point dono haathon ke beech ke markaz par (peeche wala haath prop ke peeche, aage wala upar)
    if hd and hd["al"] is not None:
        lh_, rh_ = po["lh"], po["rh"]
        mx = (X(lh_[0] + lean * 0.5) + X(rh_[0] + lean * 0.5)) / 2
        my = (Yb(lh_[1]) + Yb(rh_[1])) / 2
        pen.paste(hd["rgb"], hd["al"], mx * pen.ss - hd["gx"], my * pen.ss - hd["gy"])
    # ---- head (thoda lag ke saath => secondary motion)
    hx = shear(0.0, 0.60) * 1.0 + po_l["tilt"] * 0.6 - lean * 0.15 + (po_l["lean"] - lean) * 0.35
    hc = (X(hx), fy - (0.77 + po["nod"] + 0.0025 * br + po_l["bob"] + jump) * H * sy)
    r = 0.188 * H
    pen.circle(hc, r, SKIN, ow)
    x0, x1 = int(hc[0] * pen.ss - r * pen.ss - 4), int(hc[0] * pen.ss + r * pen.ss + 4)
    y0, y1 = int(hc[1] * pen.ss - r * pen.ss - 4), int(hc[1] * pen.ss + r * pen.ss + 4)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(pen.w, x1), min(pen.h, y1)
    if x1 > x0 and y1 > y0:
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        cxp, cyp = hc[0] * pen.ss, hc[1] * pen.ss
        rr = r * pen.ss
        lx, ly = cxp + 0.38 * ls * rr, cyp - 0.42 * rr          # light source = scene ki light side
        dist = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / (1.6 * rr)
        k = np.clip(dist, 0, 1)[..., None] ** 1.5
        far = np.array((214, 168, 138), np.float32)
        tone = np.array(SKIN, np.float32) * (1 - k * 0.6) + far * (k * 0.6)
        # glossy specular spot
        sp = np.clip(1 - np.sqrt((xx - lx * 0.35 - cxp * 0.65) ** 2 + (yy - ly * 0.55 - cyp * 0.45) ** 2) / (0.22 * rr), 0, 1)[..., None] ** 2
        tone = np.minimum(255, tone + sp * 40)
        inner = ((xx - cxp) ** 2 + (yy - cyp) ** 2 < (rr - ow * pen.ss * 0.4) ** 2)[..., None]
        reg = pen.rgb[y0:y1, x0:x1].astype(np.float32)
        pen.rgb[y0:y1, x0:x1] = np.where(inner, tone, reg).astype(np.uint8)
    # hair / hat
    ex = 0.070
    if hat in ("cap", "hardhat", "beanie"):
        capr = r * 1.02
        top = [(hc[0] + math.cos(math.radians(a)) * capr, hc[1] - 0.085 * H + math.sin(math.radians(a)) * capr * 0.82)
               for a in range(185, 356, 12)]
        pen.poly(top + [(hc[0] + capr * 0.97, hc[1] - 0.09 * H), (hc[0] - capr * 0.97, hc[1] - 0.09 * H)], hat_c, ow)
        hl = (hc[0] + ls * capr * 0.35, hc[1] - 0.085 * H - capr * 0.5)
        pen.blend_in_mask(lambda im, o: cv2.ellipse(im, (pen.P(hl)[0] - o[0], pen.P(hl)[1] - o[1]),
                                                    (int(capr * 0.45 * pen.ss * 16), int(capr * 0.22 * pen.ss * 16)), -12 * ls, 0, 360,
                                                    tuple(min(255, int(v * 1.35 + 30)) for v in hat_c), -1, cv2.LINE_AA, 4), 0.55, hl, capr * 0.5)
        pen.poly([(hc[0] + d * capr * 0.2, hc[1] - 0.097 * H), (hc[0] + d * capr * 1.3, hc[1] - 0.085 * H),
                  (hc[0] + d * capr * 1.25, hc[1] - 0.066 * H), (hc[0] + d * capr * 0.2, hc[1] - 0.076 * H)], shade(hat_c, 0.80), ow * 0.7)
        pen.circle((hc[0], hc[1] - 0.085 * H - capr * 0.82), 0.012 * H, shade(hat_c, 0.7), ow * 0.4)
    elif hat in ("slick", "hair"):
        pts = [(hc[0] + math.cos(math.radians(a)) * r * 1.03, hc[1] - 0.012 * H + math.sin(math.radians(a)) * r * 1.03)
               for a in range(188, 353, 10)]
        pen.poly(pts + [(hc[0] + d * r * 0.65, hc[1] - r * 0.62), (hc[0] - d * r * 0.2, hc[1] - r * 0.55), (hc[0] - d * r * 0.8, hc[1] - r * 0.4)], hair_c, ow)
        pen.line([(hc[0] - d * r * 0.5, hc[1] - r * 0.86), (hc[0] + d * r * 0.2, hc[1] - r * 0.92), (hc[0] + d * r * 0.6, hc[1] - r * 0.75)],
                 max(1.2, 0.006 * H), shade(hair_c, 1.7))
    elif hat == "messy":
        for k_ in range(5):
            a = math.radians(205 + k_ * 32 + 4 * math.sin(t * 2 + k_))
            pen.line([(hc[0] + math.cos(a) * r * 0.95, hc[1] + math.sin(a) * r * 0.95), (hc[0] + math.cos(a) * r * 1.25, hc[1] + math.sin(a) * r * 1.3)], lw * 1.2, hair_c)
    # ---- face
    brow_t, brow_l, eye_o, mshape = EMO.get(emo, EMO["neutral"])
    ek = EXPR * ease(t / 0.35)                  # expression dheere ubharta hai, poora nahi (subtle)
    brow_t, brow_l, eye_o = brow_t * ek, brow_l * ek, 1.0 + (eye_o - 1.0) * ek
    if action in ("shock", "scream") and t < 0.5:
        eye_o, brow_l = max(eye_o, 1.12), max(brow_l, 0.3)
    ey = hc[1] + 0.012 * H
    blink = blink_open(t, blink_seed) if eye_o > 0.5 else 1.0       # natural blink: random waqt, naram band/khulna
    fxs = d * 0.018 * H            # chehra facing ki taraf (3D turn effect)
    lk = d * 0.010 * H * look + d * 0.0035 * H * math.sin(t * 0.9 + blink_seed)       # nazar mein halki, dheemi harkat
    for sgn in (-1, 1):
        cx = hc[0] + sgn * ex * H + fxs
        if eye_o < 0.3 or blink < 0.22:
            pen.line([(cx - 0.02 * H, ey), (cx, ey + 0.008 * H), (cx + 0.02 * H, ey)], lw * 0.9)
        else:
            pen.ellipse((cx + lk, ey), 0.0125 * H, 0.0155 * H * min(1.5, eye_o) * blink, (30, 24, 34), 0)
            if blink > 0.5:
                pen.circle((cx + lk + 0.003 * H, ey - 0.004 * H * eye_o), 0.0032 * H, (255, 255, 255))
        by = ey - 0.054 * H - brow_l * 0.024 * H - (0.006 * H if mouth > 0.5 else 0) + (1.0 - blink) * 0.005 * H
        outer = (cx + sgn * 0.027 * H, by - brow_t * 0.010 * H)
        inner = (cx - sgn * 0.027 * H, by + brow_t * 0.016 * H)
        pen.line([outer, inner], lw * 0.9)
    mc = (hc[0] + fxs, hc[1] + 0.088 * H)
    mo = float(mouth)
    if action in ("scream",):
        mo = max(mo, 0.8)
    mouth_draw(pen, mc, H, ow, lw, mshape, mo, vis, d, t, ek)
    if emo in ("happy", "excited", "proud", "laughing"):
        for sgn in (-1, 1):
            c_ = (hc[0] + sgn * 0.105 * H + fxs, hc[1] + 0.058 * H)
            pen.blend_in_mask(lambda im, o, c_=c_: cv2.circle(im, (pen.P(c_)[0] - o[0], pen.P(c_)[1] - o[1]), int(0.028 * H * pen.ss * 16),
                                                              (255, 150, 165), -1, cv2.LINE_AA, 4), 0.20, c_, 0.03 * H)
    if ch.get("glasses"):
        for sgn in (-1, 1):
            pen.ellipse((hc[0] + sgn * ex * H + fxs, ey), 0.036 * H, 0.036 * H, (70, 70, 85), fill=False, ow=lw * 0.7)
        pen.line([(hc[0] - ex * H + fxs + 0.036 * H, ey), (hc[0] + ex * H + fxs - 0.036 * H, ey)], lw * 0.6, (70, 70, 85))
    if ch.get("monocle"):                                                  # ek aankh par sunehri monocle + chain
        mx_, my_ = hc[0] + ex * H + fxs, ey
        pen.ellipse((mx_, my_), 0.045 * H, 0.045 * H, (240, 205, 90), fill=False, ow=lw * 0.8)
        pen.line([(mx_ + 0.03 * H, my_ + 0.04 * H), (mx_ + 0.05 * H, my_ + 0.16 * H), (mx_ + 0.03 * H, my_ + 0.24 * H)], max(1.0, 0.004 * H), (240, 205, 90))
    if ch.get("mustache"):
        pen.ellipse((mc[0] - 0.02 * H, mc[1] - 0.030 * H), 0.03 * H, 0.012 * H, hair_c, 0)
        pen.ellipse((mc[0] + 0.02 * H, mc[1] - 0.030 * H), 0.03 * H, 0.012 * H, hair_c, 0)
    if emo in ("scared", "cry"):
        sx_ = hc[0] - d * r * 0.78
        sd = (t * 1.2) % 1.0 * 0.05 * H if emo == "cry" else 0.0
        pen.poly([(sx_, hc[1] - r * 0.1 + sd), (sx_ + 0.012 * H, hc[1] + r * 0.08 + sd), (sx_, hc[1] + r * 0.22 + sd), (sx_ - 0.012 * H, hc[1] + r * 0.08 + sd)], (130, 190, 240), ow * 0.3)
    # ---- front arm (prop ke upar, taake haath prop ko pakadta dikhe)
    arm(rsh, po["rh"], 1, action == "point" and hd is None)


def shift_mask(a, dx, dy):
    M = np.array([[1, 0, dx], [0, 1, dy]], np.float32)
    return cv2.warpAffine(a, M, (a.shape[1], a.shape[0]), flags=cv2.INTER_LINEAR)


def render_char(frame_w, frame_h, fx, fy, H, ch, action, emo, t, mouth, facing, enter, seed, amb=(1, 1, 1), rim=(0, 0, 0),
                ls=-1, vis=0, talk=0.0, look=0.0, key=(1.0, 0.95, 0.85), bounce=(0.6, 0.5, 0.4), energy=None, held=None):
    """Char ko frame-size window mein (clipped bbox) draw karke (rgb, alpha, x0, y0) deta hai. Light: amb (rang+exposure),
    key (light wali taraf ka rang), bounce (zameen se wapas aati roshni), rim (kinare ki chamak, light ki taraf).
    energy: awaaz ki smooth energy (gesture ke liye), held: haathon mein prop (draw_char/prep_held dekhein)."""
    x0 = int(max(0, fx - 0.7 * H))
    x1 = int(min(frame_w, fx + 0.7 * H))
    y0 = int(max(0, fy - 1.25 * H))
    y1 = int(min(frame_h, fy + 0.12 * H))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    ss = 2.0 if H < 800 else 1.5
    pen = Pen(x1 - x0, y1 - y0, ss)
    draw_char(pen, fx - x0, fy - y0, H, ch, action, emo, t, mouth, vis, talk, look, facing, enter, seed, ls, energy=energy, held=held)
    bx, by, bw_, bh_ = cv2.boundingRect(pen.m)
    if bw_ == 0 or bh_ == 0:
        return None
    pad = 8
    cx0, cy0 = max(0, int(bx / ss) - pad), max(0, int(by / ss) - pad)
    cx1, cy1 = min(x1 - x0, int((bx + bw_) / ss) + pad), min(y1 - y0, int((by + bh_) / ss) + pad)
    sl = (slice(int(cy0 * ss), int(cy1 * ss)), slice(int(cx0 * ss), int(cx1 * ss)))
    x0, y0 = x0 + cx0, y0 + cy0
    rgb = cv2.resize(pen.rgb[sl], (cx1 - cx0, cy1 - cy0), interpolation=cv2.INTER_AREA).astype(np.float32)
    a = cv2.resize(pen.m[sl], (cx1 - cx0, cy1 - cy0), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    h, w = a.shape
    rgb *= np.array(amb, np.float32)[None, None, :]
    # key light (light wali taraf roshan) / fill
    xs = (np.arange(w, dtype=np.float32) + x0 - fx) / (0.28 * H)
    side = np.clip(0.5 + 0.5 * ls * xs, 0, 1)[None, :, None]
    rgb *= 0.80 + 0.30 * side
    rgb *= 1.0 + (np.array(key, np.float32)[None, None, :] - 1.0) * 0.7 * side
    # zameen se bounce: pairon ki taraf halka garam rang
    ys = np.clip((np.arange(h, dtype=np.float32) + y0 - (fy - 0.45 * H)) / (0.45 * H), 0, 1)[:, None, None]
    rgb += ys * np.array(bounce, np.float32)[None, None, :] * 26 * a[..., None]
    # rim: light ki taraf ka kinara tez, baaqi poore silhouette par halki chamak
    rr = max(2.0, 0.011 * H)
    near = np.clip(a - shift_mask(a, -ls * rr * 1.4, rr * 0.5), 0, 1)[..., None]
    soft = np.clip(a - cv2.GaussianBlur(a, (0, 0), max(1.0, H * 0.004)), 0, 1)[..., None]
    if any(rim):
        rgb = rgb + (near * 2.4 + soft * 0.8) * np.array(rim, np.float32)[None, None, :] * 255
    return np.clip(rgb, 0, 255), a, x0, y0
