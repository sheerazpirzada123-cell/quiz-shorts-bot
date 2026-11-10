"""Stick-man character (RicksClips style): bada gol safed sar, mote kaale outline, patli tangen/baazu, shirt/overalls/cap.
Sab kuch code se draw hota hai (free). Supersampling + soft shading + rim light => smooth, 'rendered' look."""
import math

import cv2
import numpy as np

INK = (38, 30, 44)
SKIN = (250, 246, 244)
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
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def shade(c, k):
    return tuple(int(min(255, max(0, v * k))) for v in c)


def ik(s, t, l1, l2, bend):
    """2-segment limb: shoulder s -> hand t. Returns elbow point."""
    dx, dy = t[0] - s[0], t[1] - s[1]
    d = max(1e-6, math.hypot(dx, dy))
    d = min(d, l1 + l2 - 1e-3)
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, l1 * l1 - a * a))
    mx, my = s[0] + dx / math.hypot(dx, dy) * a, s[1] + dy / math.hypot(dx, dy) * a
    return (mx - dy / math.hypot(dx, dy) * h * bend, my + dx / math.hypot(dx, dy) * h * bend)


class Pen:
    """RGB + mask par ek saath draw (supersampled window)."""

    def __init__(self, w, h, ss):
        self.ss = ss
        self.w, self.h = int(w * ss), int(h * ss)
        self.rgb = np.zeros((self.h, self.w, 3), np.uint8)
        self.m = np.zeros((self.h, self.w), np.uint8)

    def P(self, p):
        return (int(round(p[0] * self.ss * 16)), int(round(p[1] * self.ss * 16)))

    def _both(self, fn):
        fn(self.rgb, True)
        fn(self.m, False)

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

    def line(self, pts, w, color=INK):
        s = self.ss
        a = np.array([self.P(p) for p in pts], np.int32)
        cv2.polylines(self.rgb, [a], False, color, max(1, int(w * s)), cv2.LINE_AA, 4)
        cv2.polylines(self.m, [a], False, 255, max(1, int(w * s)), cv2.LINE_AA, 4)

    def blend_in_mask(self, draw_fn, alpha):
        """Mask ke andar hi shade/highlight (soft shading)."""
        tmp = self.rgb.copy()
        draw_fn(tmp)
        a = (self.m.astype(np.float32) / 255.0 * alpha)[..., None]
        self.rgb = (self.rgb * (1 - a) + tmp * a).astype(np.uint8)


def rrect_pts(x0, y0, x1, y1, r, n=6):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


EMO = {  # brow_tilt (+ = angry), brow_lift, eye_open, mouth(base): smile/flat/frown/o
    "neutral": (0, 0, 1.0, "flat"), "happy": (-0.1, 0.1, 0.9, "smile"), "smug": (0.35, -0.1, 0.55, "smirk"),
    "angry": (0.8, -0.2, 0.8, "frown"), "surprised": (-0.2, 0.7, 1.35, "o"), "scared": (-0.7, 0.5, 1.25, "wobble"),
    "sad": (-0.8, 0.0, 0.8, "frown"), "laughing": (-0.2, 0.2, 0.15, "bigsmile"), "sleepy": (0, -0.2, 0.15, "flat"),
    "confused": (-0.3, 0.3, 1.0, "wobble"), "excited": (-0.2, 0.4, 1.2, "bigsmile"), "evil": (0.7, -0.1, 0.5, "bigsmile"),
    "worried": (-0.6, 0.3, 1.1, "wobble"), "proud": (0.1, 0.1, 0.7, "smile"), "cry": (-0.8, 0.0, 0.6, "frown"),
}


def pose(action, t, talk, d):
    """Returns hand/foot targets in H-units relative to feet-centre (x right, y up) before facing flip d."""
    s = math.sin
    p = dict(lh=(-0.13, 0.33), rh=(0.13, 0.33), lf=(-0.06, 0.0), rf=(0.06, 0.0), bob=0.004 * s(t * 2.6), tilt=0.0, hup=0.0,
             lean=0.0, nod=0.0)
    if action in ("talk", "idle", "smile"):
        g = 0.5 + 0.5 * s(t * 5.3 + 0.7)
        if action == "talk" or talk > 0.1:
            p["rh"] = (0.19 + 0.04 * s(t * 6.1), 0.40 + 0.12 * g)
            p["lh"] = (-0.12, 0.33 + 0.02 * s(t * 3))
            p["nod"] = 0.012 * s(t * 7.7)
    elif action == "point":
        p["rh"] = (0.34, 0.66 + 0.02 * s(t * 4))
        p["lh"] = (-0.1, 0.3)
        p["lean"] = 0.02
    elif action in ("shock", "scream"):
        k = ease(t / 0.18)
        p["lh"] = (-0.26, 0.70 + 0.03 * s(t * 20) * k)
        p["rh"] = (0.26, 0.70 + 0.03 * s(t * 20 + 1) * k)
        p["bob"] = 0.025 * k * (1 - ease((t - 0.1) / 0.3)) + 0.004 * s(t * 30)
    elif action == "celebrate":
        p["lh"] = (-0.28, 0.80 + 0.06 * s(t * 9))
        p["rh"] = (0.28, 0.80 + 0.06 * s(t * 9 + 3))
        p["bob"] = abs(0.03 * s(t * 6))
    elif action == "shrug":
        p["lh"] = (-0.24, 0.46)
        p["rh"] = (0.24, 0.46)
        p["tilt"] = 0.05 * s(t * 3)
    elif action == "think":
        p["rh"] = (0.07, 0.69)
        p["lh"] = (-0.10, 0.34)
    elif action == "facepalm":
        p["rh"] = (0.02, 0.80)
        p["lh"] = (-0.12, 0.32)
        p["tilt"] = -0.05
        p["lean"] = -0.03
    elif action == "laugh":
        p["lh"] = (-0.07, 0.38)
        p["rh"] = (0.07, 0.38)
        p["bob"] = abs(0.02 * s(t * 17))
        p["tilt"] = 0.04 * s(t * 17)
    elif action == "angry":
        p["lh"] = (-0.16, 0.38 + 0.02 * s(t * 24))
        p["rh"] = (0.16, 0.38 + 0.02 * s(t * 24 + 1))
        p["lean"] = 0.03
        p["bob"] = 0.004 * s(t * 24)
    elif action == "hold":      # kuch pakde hue (wallet, tools) - dono haath saamne
        p["lh"] = (-0.10, 0.40)
        p["rh"] = (0.10, 0.40)
    elif action == "wave":
        p["rh"] = (0.24, 0.78 + 0.04 * s(t * 11))
    elif action in ("walk", "run"):
        f = 11 if action == "run" else 7.5
        ph = t * f
        amp = 0.09 if action == "run" else 0.065
        p["lf"] = (-0.02 + amp * s(ph), max(0.0, 0.05 * s(ph + 1.57)))
        p["rf"] = (0.02 - amp * s(ph), max(0.0, 0.05 * s(ph - 1.57)))
        p["lh"] = (-0.10 - 0.08 * s(ph), 0.33)
        p["rh"] = (0.10 + 0.08 * s(ph), 0.33)
        p["bob"] = abs(0.012 * s(ph))
        p["lean"] = 0.03 if action == "run" else 0.01
    elif action == "sad":
        p["lh"] = (-0.10, 0.28)
        p["rh"] = (0.10, 0.28)
        p["nod"] = -0.02
        p["tilt"] = 0.03
    elif action == "sleep":
        p["tilt"] = 0.1
    return p


def draw_char(pen, fx, fy, H, ch, action, emo, t, mouth, facing=1, enter=1.0, blink_seed=0.0):
    """pen: Pen window; (fx,fy) = pairon ka markaz (window coords, px); H = qad px; facing +1 right / -1 left."""
    d = 1 if facing >= 0 else -1
    shirt = col(ch.get("shirt", "yellow"), SHIRTS, SHIRTS["yellow"])
    hat = ch.get("hat", "none")
    hat_c = col(ch.get("hat_color", "red"), SHIRTS, SHIRTS["red"])
    hair_c = col(ch.get("hair_color", "brown"), HAIRS, HAIRS["brown"])
    pants = col(ch.get("pants", "navy" if not ch.get("overalls") else "blue"), SHIRTS, SHIRTS["navy"])
    ow = max(1.2, 0.012 * H)
    lw = max(1.4, 0.016 * H)
    po = pose(action, t, mouth, d)
    ent = back(enter)
    sq = 1.0 + 0.0 * ent
    bob = po["bob"] * H
    jump = (1 - ent) * -0.0 * H
    X = lambda x: fx + d * x * H
    Y = lambda y: fy - y * H - bob + jump
    sc_y = sq
    # ---- shadow handled by caller
    hip = (0.0, 0.345)
    lean = po["lean"]
    sh_y = 0.585
    neck = (lean * 0.6 + 0.0, 0.60)
    hip_pt = (0.0 + 0.0, hip[1])
    lsh, rsh = (-0.075 + lean * 0.4, sh_y), (0.075 + lean * 0.4, sh_y)
    # ---- legs
    for side, key in ((-1, "lf"), (1, "rf")):
        foot = (po[key][0] + side * 0.0, po[key][1])
        hp = (side * 0.04, hip[1])
        knee = ik(hp, foot, 0.17, 0.18, -side * 0.0 + 0.4 * (1 if foot[0] * side > 0 else -1) * 0.0 + (1 if d > 0 else -1) * -1 * 0.0 + 0.0)
        # knee bend forward (towards facing = +x)
        kn = ik((hp[0], hip[1]), foot, 0.17, 0.18, -1.0)
        pen.line([(X(hp[0]), Y(hp[1])), (X(kn[0]), Y(kn[1])), (X(foot[0]), Y(foot[1] + 0.012))], lw * 1.25, INK)
        pen.ellipse((X(foot[0] + 0.022), Y(foot[1] + 0.008)), 0.034 * H, 0.016 * H, (240, 240, 240), ow * 0.7)
    # ---- back arm (the far one) first
    def arm(sh, hand, bend, sleeve=True):
        hand = (hand[0] + lean * 0.4, hand[1])
        el = ik(sh, hand, 0.14, 0.15, bend)
        pen.line([(X(sh[0]), Y(sh[1])), (X(el[0]), Y(el[1])), (X(hand[0]), Y(hand[1]))], lw, INK)
        pen.circle((X(hand[0]), Y(hand[1])), 0.020 * H, SKIN, ow * 0.7)
    arm(lsh, po["lh"], 1.0)
    # ---- torso
    tw0, tw1 = 0.098, 0.088
    tp = rrect_pts(-tw0 + lean * 0.4, 0.60, tw0 + lean * 0.4, 0.33, 0.045, 5)
    pen.poly([(X(x), Y(y)) for x, y in tp], shirt, ow)
    if ch.get("overalls"):
        bib = rrect_pts(-0.075, 0.50, 0.075, 0.33, 0.02, 4)
        pen.poly([(X(x), Y(y)) for x, y in bib], pants, ow * 0.6)
        for sx in (-0.055, 0.055):
            pen.line([(X(sx), Y(0.50)), (X(sx * 0.95), Y(0.60))], lw * 1.6, pants)
            pen.circle((X(sx), Y(0.505)), 0.011 * H, (240, 200, 70), ow * 0.4)
    elif ch.get("tie"):
        pen.poly([(X(-0.014), Y(0.60)), (X(0.014), Y(0.60)), (X(0.02), Y(0.45)), (X(0), Y(0.42)), (X(-0.02), Y(0.45))], (170, 30, 40), ow * 0.4)
    # torso shading (right side darker) + highlight (left)
    pen.blend_in_mask(lambda im: cv2.rectangle(im, (pen.P((X(0.02 * d), 0))[0], 0), (pen.w, pen.h), (0, 0, 20), -1), 0.0)
    def torso_shade(im):
        x0 = int(X(0.015) * pen.ss) if d > 0 else 0
        x1 = pen.w if d > 0 else int(X(-0.015) * pen.ss)
        sub = im[:, x0:x1]
        sub[:] = (sub * 0.78).astype(np.uint8)
    # restrict shading to torso+overall region using a y band
    y0b, y1b = int(Y(0.60) * pen.ss), int(Y(0.33) * pen.ss)
    band = pen.rgb[max(0, y0b):max(0, y1b)].copy()
    if band.size:
        m = pen.m[max(0, y0b):max(0, y1b)].astype(np.float32)[..., None] / 255
        xs = np.arange(pen.w, dtype=np.float32)[None, :, None]
        k = np.clip((xs - X(0.0) * pen.ss * 1.0) / (0.1 * H * pen.ss) * d, 0, 1) * 0.28
        pen.rgb[max(0, y0b):max(0, y1b)] = (band * (1 - k * m)).astype(np.uint8)
    # ---- legs hip joint cover (pants)
    pen.ellipse((X(0), Y(0.345)), 0.07 * H, 0.025 * H, pants if ch.get("overalls") else shade(pants, 1.0), ow * 0.5)
    # ---- head
    hx = lean * 0.9 + po["tilt"] * 0.6
    hc = (X(hx), Y(0.775 + po["nod"]))
    r = 0.165 * H
    pen.circle(hc, r, SKIN, ow)
    # head soft shading: lavender on far side, white highlight top
    x0, x1 = int(hc[0] * pen.ss - r * pen.ss - 4), int(hc[0] * pen.ss + r * pen.ss + 4)
    y0, y1 = int(hc[1] * pen.ss - r * pen.ss - 4), int(hc[1] * pen.ss + r * pen.ss + 4)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(pen.w, x1), min(pen.h, y1)
    if x1 > x0 and y1 > y0:
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        cxp, cyp = hc[0] * pen.ss, hc[1] * pen.ss
        rr = r * pen.ss
        lx, ly = cxp - 0.35 * d * rr, cyp - 0.4 * rr
        dist = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / (1.55 * rr)
        k = np.clip(dist, 0, 1)[..., None] ** 1.6
        base = np.array(SKIN, np.float32)
        far = np.array((196, 190, 222), np.float32)
        tone = base * (1 - k * 0.9) + far * (k * 0.9)
        mm = pen.m[y0:y1, x0:x1].astype(np.float32)[..., None] / 255
        inner = ((xx - cxp) ** 2 + (yy - cyp) ** 2 < (rr - ow * pen.ss * 0.4) ** 2)[..., None]
        reg = pen.rgb[y0:y1, x0:x1].astype(np.float32)
        pen.rgb[y0:y1, x0:x1] = np.where(inner, tone, reg).astype(np.uint8)
    # hair / hat (behind face features)
    ex = 0.062
    if hat in ("cap", "hardhat", "beanie"):
        capr = r * 1.02
        top = [(hc[0] + d * 0.0 + math.cos(math.radians(a)) * capr, hc[1] - 0.085 * H + math.sin(math.radians(a)) * capr * 0.82)
               for a in range(185, 356, 12)]
        pen.poly(top + [(hc[0] + capr * 0.97, hc[1] - 0.09 * H), (hc[0] - capr * 0.97, hc[1] - 0.09 * H)], hat_c, ow)
        pen.poly([(hc[0] + d * capr * 0.2, hc[1] - 0.097 * H), (hc[0] + d * capr * 1.3, hc[1] - 0.085 * H),
                  (hc[0] + d * capr * 1.25, hc[1] - 0.066 * H), (hc[0] + d * capr * 0.2, hc[1] - 0.076 * H)], shade(hat_c, 0.82), ow * 0.7)
        pen.circle((hc[0], hc[1] - 0.085 * H - capr * 0.82), 0.012 * H, shade(hat_c, 0.7), ow * 0.4)
    elif hat in ("slick", "hair"):
        pts = [(hc[0] + math.cos(math.radians(a)) * r * 1.03, hc[1] - 0.012 * H + math.sin(math.radians(a)) * r * 1.03)
               for a in range(188, 353, 10)]
        pen.poly(pts + [(hc[0] + d * r * 0.65, hc[1] - r * 0.62), (hc[0] - d * r * 0.2, hc[1] - r * 0.55), (hc[0] - d * r * 0.8, hc[1] - r * 0.4)], hair_c, ow)
    elif hat == "messy":
        for k in range(5):
            a = math.radians(205 + k * 32)
            pen.line([(hc[0] + math.cos(a) * r * 0.95, hc[1] + math.sin(a) * r * 0.95), (hc[0] + math.cos(a) * r * 1.25, hc[1] + math.sin(a) * r * 1.3)], lw * 1.2, hair_c)
    # ---- face
    brow_t, brow_l, eye_o, mshape = EMO.get(emo, EMO["neutral"])
    ey = hc[1] + 0.012 * H
    blink = 1.0
    ph = (t * 0.4 + blink_seed) % 3.2
    if ph < 0.12 and eye_o > 0.5:
        blink = 0.08
    fxs = d * 0.018 * H  # face shifts towards facing
    for sgn in (-1, 1):
        cx = hc[0] + sgn * ex * H + fxs
        if eye_o < 0.3 or blink < 0.5:
            pen.line([(cx - 0.02 * H, ey), (cx, ey + 0.008 * H), (cx + 0.02 * H, ey)], lw * 0.9)
        else:
            pen.ellipse((cx, ey), 0.017 * H, 0.03 * H * min(1.35, eye_o) * blink, (30, 24, 34), 0)
            pen.circle((cx + 0.005 * H, ey - 0.008 * H), 0.006 * H, (255, 255, 255))
        ba = brow_t * 0.5 * sgn * -1 * d * -1
        by = ey - 0.052 * H - brow_l * 0.022 * H
        ang = (brow_t * 0.45) * (1 if sgn * d > 0 else -1)
        pen.line([(cx - 0.026 * H, by + math.sin(-ang) * 0.026 * H), (cx + 0.026 * H, by + math.sin(ang) * 0.026 * H)], lw * 0.85)
    mc = (hc[0] + fxs, hc[1] + 0.085 * H)
    mo = mouth
    if mshape == "o":
        mo = max(mo, 0.7)
    if mo > 0.12 and mshape not in ("bigsmile",):
        pen.ellipse(mc, 0.03 * H * (1.0 + 0.2 * mo), 0.012 * H + 0.034 * H * mo, (45, 20, 30), ow * 0.6)
        pen.ellipse((mc[0], mc[1] + 0.02 * H * mo), 0.02 * H, 0.012 * H * mo, (200, 90, 100), 0)
    elif mshape == "bigsmile" or (mshape == "smile" and mo > 0.05):
        pen.poly([(mc[0] - 0.06 * H, mc[1] - 0.012 * H), (mc[0] + 0.06 * H, mc[1] - 0.012 * H),
                  (mc[0] + 0.05 * H, mc[1] + 0.028 * H * (1 + mo)), (mc[0], mc[1] + 0.05 * H * (1 + mo * 0.5)),
                  (mc[0] - 0.05 * H, mc[1] + 0.028 * H * (1 + mo))], (250, 250, 250), ow * 0.8)
        pen.line([(mc[0] - 0.045 * H, mc[1] + 0.012 * H), (mc[0] + 0.045 * H, mc[1] + 0.012 * H)], lw * 0.5)
    elif mshape == "smile":
        pen.line([(mc[0] - 0.045 * H, mc[1]), (mc[0], mc[1] + 0.028 * H), (mc[0] + 0.045 * H, mc[1])], lw)
    elif mshape == "smirk":
        pen.line([(mc[0] - 0.04 * H, mc[1] + 0.012 * H), (mc[0] + 0.01 * H, mc[1] + 0.014 * H), (mc[0] + 0.05 * H * d * d, mc[1] - 0.012 * H)], lw)
    elif mshape == "frown":
        pen.line([(mc[0] - 0.04 * H, mc[1] + 0.02 * H), (mc[0], mc[1] - 0.004 * H), (mc[0] + 0.04 * H, mc[1] + 0.02 * H)], lw)
    elif mshape == "wobble":
        pts = [(mc[0] + (i - 3) * 0.015 * H, mc[1] + 0.008 * H * math.sin(i * 2 + t * 18)) for i in range(7)]
        pen.line(pts, lw)
    else:
        pen.line([(mc[0] - 0.035 * H, mc[1] + 0.006 * H), (mc[0] + 0.035 * H, mc[1] + 0.006 * H)], lw)
    if ch.get("glasses"):
        for sgn in (-1, 1):
            pen.ellipse((hc[0] + sgn * ex * H + fxs, ey), 0.036 * H, 0.036 * H, (70, 70, 85), fill=False, ow=lw * 0.7)
    if ch.get("mustache"):
        pen.ellipse((mc[0] - 0.02 * H, mc[1] - 0.026 * H), 0.03 * H, 0.012 * H, hair_c, 0)
        pen.ellipse((mc[0] + 0.02 * H, mc[1] - 0.026 * H), 0.03 * H, 0.012 * H, hair_c, 0)
    if emo in ("scared", "worried", "cry") or action in ("shock",):
        sx_ = hc[0] - d * r * 0.78
        pen.poly([(sx_, hc[1] - r * 0.1), (sx_ + 0.012 * H, hc[1] + r * 0.08), (sx_, hc[1] + r * 0.22), (sx_ - 0.012 * H, hc[1] + r * 0.08)], (130, 190, 240), ow * 0.3)
    # ---- front arm
    arm(rsh, po["rh"], -1.0)


def render_char(frame_w, frame_h, fx, fy, H, ch, action, emo, t, mouth, facing, enter, seed, amb=(1, 1, 1), rim=(0, 0, 0)):
    """Char ko frame-size window mein (clipped bbox) draw karke (rgb, alpha, x0, y0) deta hai."""
    x0 = int(max(0, fx - 0.7 * H))
    x1 = int(min(frame_w, fx + 0.7 * H))
    y0 = int(max(0, fy - 1.2 * H))
    y1 = int(min(frame_h, fy + 0.12 * H))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    ss = 2.0 if H < 800 else 1.5
    pen = Pen(x1 - x0, y1 - y0, ss)
    draw_char(pen, fx - x0, fy - y0, H, ch, action, emo, t, mouth, facing, enter, seed)
    rgb = cv2.resize(pen.rgb, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA).astype(np.float32)
    a = cv2.resize(pen.m, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    rgb *= np.array(amb, np.float32)[None, None, :]
    if any(rim):
        edge = cv2.GaussianBlur(a, (0, 0), max(1.0, H * 0.004))
        rimk = np.clip(a - edge, 0, 1)[..., None] * 2.2
        rgb = rgb + rimk * np.array(rim, np.float32)[None, None, :] * 255
    return np.clip(rgb, 0, 255), a, x0, y0
