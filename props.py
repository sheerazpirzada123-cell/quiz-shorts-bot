"""Flat-vector EXPLAINER PROPS (Kurzgesagt jaisa saaf look): code se draw + animate. Gemini har scene ke liye 'props' list deta hai
(type, place, action, text) aur render_story.py unhe scene mein rakhta hai.

NAYA PROP JODNE KA TAREEQA (3 line):
    @prop("naam", ext=(left, right, upar, neeche))        # ext = window ka size, U (unit) ke multiple mein
    def naam(c): c.ell(0, 0.2, 0.1, 0.1, (255, 0, 0))      # origin = zameen par markaz, x daayen, y UPAR (units mein)
Phir story_gen.py ke PROP_TYPES list mein naam likh do. Bas.

Ctx c ke paas: c.t (scene-time sec), c.d (+1 / -1 facing), c.action, c.txt, c.seed, aur helpers: ell, circ, poly, line, rrect, text, star.
Sab coordinates "unit" mein (U = character ki height). Rang RGB tuples."""
import math
import os
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from rick import INK, Pen, back, ease, rrect_pts, shade

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "fonts", "Poppins-Bold.ttf")
PROPS = {}
_fc = {}


def prop(name, ext, speed=0.0):
    def deco(fn):
        PROPS[name] = dict(fn=fn, ext=ext, speed=speed)
        return fn
    return deco


def _font(px):
    px = max(6, int(px))
    if px not in _fc:
        try:
            _fc[px] = ImageFont.truetype(FONT, px)
        except Exception:
            _fc[px] = ImageFont.load_default()
    return _fc[px]


def text_img(txt, px, color, stroke=0, stroke_color=(20, 20, 24)):
    f = _font(px)
    tmp = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    l, t, r, b = tmp.textbbox((0, 0), txt, font=f, stroke_width=stroke)
    im = Image.new("RGBA", (r - l + 6, b - t + 6), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((3 - l, 3 - t), txt, font=f, fill=color + (255,), stroke_width=stroke, stroke_fill=stroke_color + (255,))
    return im


def paste(pen, im, cx, cy, alpha=1.0):
    """PIL RGBA ko pen par (pen px coords, markaz) chipkata hai. im pehle se supersampled (pen.ss) size mein honi chahiye."""
    arr = np.asarray(im)
    h, w = arr.shape[:2]
    x0, y0 = int(cx * pen.ss - w / 2), int(cy * pen.ss - h / 2)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(pen.w, x0 + w), min(pen.h, y0 + h)
    if xb <= xa or yb <= ya:
        return
    s = arr[ya - y0:yb - y0, xa - x0:xb - x0]
    a = s[..., 3:4].astype(np.float32) / 255.0 * alpha
    pen.rgb[ya:yb, xa:xb] = (pen.rgb[ya:yb, xa:xb].astype(np.float32) * (1 - a) + s[..., :3] * a).astype(np.uint8)
    pen.m[ya:yb, xa:xb] = np.maximum(pen.m[ya:yb, xa:xb], (s[..., 3] * alpha).astype(np.uint8))


class Ctx:
    def __init__(self, pen, cx, cy, U, t, a):
        self.pen, self.cx, self.cy, self.U, self.t = pen, cx, cy, U, t
        self.d = a.get("dir", 1)
        self.action, self.txt, self.seed = a.get("action", "idle"), a.get("text", "") or "", a.get("seed", 0)
        self.ow = max(1.4, 0.011 * U)

    def X(self, x):
        return self.cx + x * self.U

    def Y(self, y):
        return self.cy - y * self.U

    def P(self, p):
        return (self.X(p[0]), self.Y(p[1]))

    def ell(self, x, y, rx, ry, color, ang=0.0, ow=True, a0=0, a1=360):
        self.pen.ellipse(self.P((x, y)), rx * self.U, ry * self.U, color, self.ow if ow else 0, ang, a0, a1)

    def circ(self, x, y, r, color, ow=True):
        self.pen.circle(self.P((x, y)), r * self.U, color, self.ow if ow else 0)

    def poly(self, pts, color, ow=True):
        self.pen.poly([self.P(p) for p in pts], color, self.ow if ow else 0)

    def line(self, pts, w, color=INK, ow=False):
        self.pen.line([self.P(p) for p in pts], max(1.0, w * self.U), color, self.ow * 0.8 if ow else 0)

    def rrect(self, x0, y0, x1, y1, r, color, ow=True):
        self.poly([(x, y) for x, y in _rr(x0, y0, x1, y1, r)], color, ow)

    def text(self, txt, x, y, size, color, stroke=0, rot=0.0, alpha=1.0):
        im = text_img(txt, size * self.U * self.pen.ss, color, int(stroke * self.pen.ss))
        if rot:
            im = im.rotate(rot, expand=True, resample=Image.BICUBIC)
        paste(self.pen, im, self.X(x), self.Y(y), alpha)

    def star(self, x, y, s, color=(255, 252, 205)):
        pts = []
        for k in range(8):
            r = s if k % 2 == 0 else s * 0.28
            a = math.pi / 4 * k - math.pi / 2
            pts.append((x + r * math.cos(a), y + r * math.sin(a)))
        self.poly(pts, color, ow=False)


def _rr(x0, y0, x1, y1, r, n=5):
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def render(name, U, t, a):
    """Prop ka sprite: (rgb float32, alpha 0..1, ox, oy) - ox,oy = sprite ke top-left ka anchor se farq (px)."""
    sp = PROPS[name]
    l, r, up, dn = sp["ext"]
    w, h = int((l + r) * U) + 4, int((up + dn) * U) + 4
    ss = 2.0 if w * h < 900_000 else (1.5 if w * h < 1_800_000 else 1.0)
    pen = Pen(w, h, ss)
    cx, cy = l * U + 2, up * U + 2
    sp["fn"](Ctx(pen, cx, cy, U, t, a))
    bx, by, bw_, bh_ = cv2.boundingRect(pen.m)
    if bw_ == 0 or bh_ == 0:
        return None
    rgb = cv2.resize(pen.rgb, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32)
    al = cv2.resize(pen.m, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    return rgb, al, -cx, -cy


def num_in(text, default, lo=1, hi=12):
    m = re.search(r"\d+", text or "")
    return max(lo, min(hi, int(m.group()))) if m else default


# ============================================================ murgi (walk / peck / flap / idle)
@prop("chicken", ext=(0.50, 0.50, 0.58, 0.08), speed=0.55)
def chicken(c):
    t, d, act = c.t, c.d, c.action
    body_c = [(252, 252, 250), (205, 135, 70), (242, 208, 96)][c.seed % 3]
    wing_c, comb, beak, legc = shade(body_c, 0.90), (222, 48, 52), (246, 168, 42), (236, 160, 52)
    walking = act in ("walk", "run")
    ph = t * (8.5 if act == "run" else 6.5)
    bob = 0.013 * abs(math.sin(ph)) if walking else 0.006 * math.sin(t * 3)
    hop = 0.06 * abs(math.sin(t * 9)) if act == "flap" else 0.0
    peck = 0.0
    if act == "peck":
        cyc = (t * 2.0) % 1.0
        peck = math.sin(cyc / 0.45 * math.pi) ** 2 if cyc < 0.45 else 0.0
    by = 0.17 + bob + hop
    for k in (-1, 1):                                              # tangein
        sw = 0.05 * math.sin(ph + (0 if k < 0 else math.pi)) if walking else 0.0
        lift = 0.03 * max(0.0, math.cos(ph + (0 if k < 0 else math.pi))) if walking else 0.0
        hx = d * (0.02 + 0.03 * k)
        fx_, fy_ = hx + d * sw, 0.015 + lift + hop
        c.line([(hx, by - 0.07), (fx_, fy_)], 0.016, legc, ow=True)
        for tz in (-0.035, 0.0, 0.035):
            c.line([(fx_, fy_), (fx_ + d * 0.05, fy_ + tz * 0.35 - 0.005)], 0.011, legc, ow=False)
    for i, (dx, dy, tx, ty) in enumerate(((-0.12, 0.00, -0.22, 0.10), (-0.12, 0.03, -0.20, 0.17), (-0.11, 0.05, -0.16, 0.20))):   # dum ke par
        c.poly([(d * dx, by + dy), (d * tx, by + ty), (d * (tx + 0.07), by + ty + 0.015), (d * (dx + 0.04), by + dy + 0.07)], shade(body_c, 0.94 - 0.03 * i))
    tilt = d * (-6 + 22 * peck)
    c.ell(0, by, 0.178, 0.130, body_c, ang=tilt)                                              # jism
    flap = abs(math.sin(t * 10)) if act == "flap" else 0.0
    c.ell(-d * 0.015, by + 0.01 + 0.07 * flap, 0.098, 0.062 + 0.05 * flap, wing_c, ang=d * (-12 - 52 * flap))   # par (wing)
    hx, hy = d * (0.15 + 0.07 * peck), by + 0.19 - 0.27 * peck                                    # sar (peck mein neeche)
    c.line([(d * 0.09, by + 0.06), (hx - d * 0.01, hy - 0.02)], 0.052, body_c, ow=True)
    for k in (-1, 0, 1):                                           # kalgi
        c.circ(hx + d * k * 0.026, hy + 0.074 - abs(k) * 0.012, 0.028, comb)
    c.circ(hx, hy, 0.074, body_c)
    c.poly([(hx + d * 0.06, hy + 0.012), (hx + d * 0.135, hy - 0.012), (hx + d * 0.06, hy - 0.030)], beak)
    c.ell(hx + d * 0.045, hy - 0.052, 0.016, 0.026, comb)                                         # wattle
    c.circ(hx + d * 0.030, hy + 0.020, 0.010, INK, ow=False)
    c.line([(hx + d * 0.010, hy + 0.036), (hx + d * 0.050, hy + 0.030)], 0.008, INK)             # aadhi khuli palak (smug)


# ============================================================ barrel (action="occupied" => character andar, sirf samne ka hissa)
@prop("barrel", ext=(0.30, 0.30, 0.52, 0.04))
def barrel(c):
    h = 0.44
    hw = lambda y: 0.150 + 0.030 * math.sin(math.pi * min(1, max(0, y / h)))
    occ = c.action == "occupied"
    wood, dark, steel = (196, 136, 74), (150, 98, 52), (96, 100, 116)
    ys = [i / 14 * h for i in range(15)]
    lip = (lambda x: -0.045 * (1 - (x / 0.18) ** 2)) if occ else (lambda x: 0.0)
    left = [(-hw(y), y) for y in ys]
    right = [(hw(y), y) for y in reversed(ys)]
    top = [(x / 10 * 0.18, h + lip(x / 10 * 0.18)) for x in range(10, -11, -1)]
    if not occ:
        c.ell(0, h, hw(h), 0.05, (70, 46, 28))
    c.poly(left + [(-hw(h), h)] + [(x, h + lip(x)) for x in np.linspace(-hw(h), hw(h), 12)] + right, wood)
    for k in range(-3, 4):                                         # lakdi ki patriyan
        f = k / 3.6
        c.line([(hw(y) * f, y + (lip(hw(y) * f) if y > h * 0.9 else 0)) for y in ys], 0.006, dark)
    for yb in (0.08, h - 0.10):                                    # loha ke hoop
        c.poly([(-hw(yb) - 0.003, yb - 0.022), (hw(yb) + 0.003, yb - 0.022), (hw(yb + 0.04) + 0.003, yb + 0.022), (-hw(yb + 0.04) - 0.003, yb + 0.022)], steel)
    if not occ:
        c.ell(0, h, hw(h), 0.05, (70, 46, 28), ow=True)
        c.ell(0, h - 0.004, hw(h) - 0.018, 0.036, (48, 30, 20), ow=False)
    else:
        c.line([(x, h + lip(x)) for x in np.linspace(-hw(h), hw(h), 12)], 0.014, dark, ow=True)


# ============================================================ chalkboard (likha hua animate hota hai: "2 = (egg)" ya "1|day") -- (egg) (coin) (up) (down) icons
_chalk_cache = {}


def _icon(d, kind, cx, cy, s, col):
    w = max(2, int(s * 0.09))
    if kind == "egg":
        pts = [(cx + s * 0.30 * math.cos(a) * (1 - 0.13 * math.sin(a)), cy - s * 0.40 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 40)]
        d.line(pts + [pts[0]], fill=col, width=w, joint="curve")
    elif kind == "coin":
        d.ellipse([cx - s * 0.36, cy - s * 0.36, cx + s * 0.36, cy + s * 0.36], outline=col, width=w)
        d.ellipse([cx - s * 0.2, cy - s * 0.2, cx + s * 0.2, cy + s * 0.2], outline=col, width=max(1, w // 2))
    elif kind in ("up", "down"):
        k = -1 if kind == "up" else 1
        d.line([(cx, cy + k * -s * 0.4), (cx, cy + k * s * 0.4)], fill=col, width=w)
        d.line([(cx - s * 0.25, cy + k * -s * 0.1), (cx, cy + k * -s * 0.4), (cx + s * 0.25, cy + k * -s * 0.1)], fill=col, width=w, joint="curve")


def chalk_image(text, wpx, hpx):
    key = (text, wpx, hpx)
    if key in _chalk_cache:
        return _chalk_cache[key]
    lines = [ln.strip() for ln in re.split(r"\||\n", text or "") if ln.strip()][:3] or ["?"]
    size = int(hpx / (len(lines) + 0.6))
    while True:
        f = _font(size)
        meas = []
        for ln in lines:
            parts = [p for p in re.split(r"(\((?:egg|coin|up|down)\))", ln) if p]
            wsum = 0
            for p in parts:
                wsum += size * 0.9 if p.startswith("(") else ImageDraw.Draw(Image.new("L", (4, 4))).textlength(p, font=f)
            meas.append((parts, wsum))
        if max(m[1] for m in meas) <= wpx * 0.92 or size < 14:
            break
        size -= 3
    im = Image.new("RGBA", (wpx, hpx), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = (246, 246, 236, 238)
    lh = hpx / len(lines)
    for i, (parts, wsum) in enumerate(meas):
        x, cy = (wpx - wsum) / 2, lh * (i + 0.5)
        for p in parts:
            if p.startswith("("):
                _icon(d, p[1:-1], x + size * 0.45, cy, size, col)
                x += size * 0.9
            else:
                d.text((x, cy), p, font=f, fill=col, anchor="lm")
                x += d.textlength(p, font=f)
    _chalk_cache[key] = im
    return im


@prop("chalkboard", ext=(0.52, 0.52, 1.00, 0.04))
def chalkboard(c):
    for x0, x1 in ((-0.27, -0.33), (0.27, 0.33), (0.0, 0.0)):    # easel ki tangein
        c.line([(x0, 0.48), (x1, 0.0)], 0.022, (120, 80, 46), ow=True)
    c.rrect(-0.36, 0.40, 0.36, 0.95, 0.02, (150, 100, 56))
    c.rrect(-0.32, 0.44, 0.32, 0.91, 0.01, (36, 96, 72), ow=False)
    c.rrect(-0.30, 0.375, 0.30, 0.42, 0.01, (120, 80, 46))
    wpx, hpx = int(0.60 * c.U * c.pen.ss), int(0.42 * c.U * c.pen.ss)
    im = chalk_image(c.txt or "?", wpx, hpx)
    n_ln = max(1, len(re.split(r"\||\n", c.txt or "?")))
    p = ease((c.t - 0.25) / (0.5 + 0.18 * len(c.txt or "?")))               # likhai: left se right wipe
    a = np.array(im)
    for i in range(n_ln):                                                     # har line baari baari
        q = min(1.0, max(0.0, p * n_ln - i))
        y0, y1 = int(hpx * i / n_ln), int(hpx * (i + 1) / n_ln)
        a[y0:y1, int(wpx * q):, 3] = 0
    paste(c.pen, Image.fromarray(a), c.X(0), c.Y(0.675))
    for k in range(3):                                                        # chalk ka dhool
        c.ell(-0.2 + 0.2 * k, 0.405, 0.04, 0.008, (226, 226, 216), ow=False)


# ============================================================ sikke (pop + sparkle) / ande (nest mein pop)
def _pile(n, per_row=4):
    rows, left, k = [], n, per_row
    while left > 0:
        m = min(k, left)
        rows.append(m)
        left -= m
        k = max(1, k - 1)
    pos = []
    for r, m in enumerate(rows):
        for i in range(m):
            pos.append(((i - (m - 1) / 2) * 0.125, 0.07 + r * 0.105))
    return pos


def _fall(act, q, i):
    """pop / fall / rise: (scale, y-offset)"""
    if act == "fall":
        qq = min(1.0, max(0.0, q * 1.2))
        return (1.0 if q > 0 else 0.0), 0.9 * (1 - qq) ** 2 + 0.03 * math.sin(max(0.0, q - 0.8) * 20) * max(0, 1 - q)
    if act == "rise":
        return min(1.0, max(0.0, q * 3)), 0.08 * q * 3
    return back(q), 0.07 * math.sin(math.pi * min(1.0, max(0.0, q)))


@prop("coins", ext=(0.45, 0.45, 1.20, 0.05))
def coins(c):
    n = num_in(c.txt, 3)
    pos = _pile(n)
    for i, (x, y) in enumerate(pos):
        q = (c.t - 0.12 * i) / 0.38
        if q <= 0:
            continue
        sc, dy = _fall(c.action, q, i)
        r = 0.060 * max(0.05, sc)
        sq = abs(math.cos(c.t * 5 + i)) * 0.8 + 0.2 if c.action == "spin" else 1.0
        c.ell(x, y + dy, r * sq, r, (246, 198, 52))
        c.ell(x, y + dy, r * 0.70 * sq, r * 0.70, (214, 150, 26), ow=False, a0=0, a1=360)
        c.ell(x, y + dy, r * 0.58 * sq, r * 0.58, (250, 214, 90), ow=False)
        if sc > 0.8 and sq > 0.6:
            c.text("$", x, y + dy, 0.058, (190, 128, 20))
    for k in range(4):                                                         # sparkle
        s = 0.5 + 0.5 * math.sin(c.t * 6 + k * 1.7)
        if c.t > 0.3 and s > 0.15:
            ang = k * 1.6 + 0.4
            c.star(math.cos(ang) * (0.17 + 0.06 * k), 0.14 + 0.1 * k + 0.08 * math.sin(ang), 0.045 * s)


@prop("eggs", ext=(0.45, 0.45, 0.80, 0.05))
def eggs(c):
    n = num_in(c.txt, 2, 1, 10)
    gold = "gold" in (c.txt or "").lower()
    col, edge = ((250, 204, 58), (206, 150, 20)) if gold else ((252, 248, 236), INK)
    c.ell(0, 0.035, 0.07 * min(4, n) + 0.06, 0.04, (206, 160, 90))             # ghonsla (nest)
    for i, (x, y) in enumerate(_pile(n, 3)):
        q = (c.t - 0.14 * i) / 0.36
        if q <= 0:
            continue
        sc, dy = _fall(c.action, q, i)
        wob = math.radians(7 * math.sin(c.t * 5 + i * 2)) * (1 if c.action == "shake" else 0.3)
        rx, ry = 0.050 * max(0.05, sc), 0.066 * max(0.05, sc)
        pts = []
        for a in np.linspace(0, 2 * math.pi, 30, endpoint=False):
            px, py = rx * math.cos(a) * (1 - 0.14 * math.sin(a)), ry * math.sin(a)
            pts.append((x + 0.012 + px * math.cos(wob) - py * math.sin(wob), y + 0.02 + dy + px * math.sin(wob) + py * math.cos(wob)))
        c.poly(pts, col)
        c.ell(x - 0.016, y + 0.04 + dy, 0.010 * sc, 0.016 * sc, (255, 255, 255), ow=False)
    if gold:
        for k in range(3):
            s = 0.5 + 0.5 * math.sin(c.t * 6 + k * 2)
            c.star(-0.14 + 0.14 * k, 0.20 + 0.08 * (k % 2), 0.04 * s)


# ============================================================ ghar
@prop("house", ext=(0.72, 0.72, 1.20, 0.04))
def house(c):
    wall = [(246, 226, 170), (242, 200, 200), (190, 214, 240), (214, 236, 200)][c.seed % 4]
    shut = [(190, 50, 60), (60, 110, 70), (70, 90, 170)][(c.seed // 4) % 3]
    c.rrect(0.20, 0.80, 0.31, 1.12, 0.01, (176, 84, 62))                       # chimney
    c.rrect(-0.46, 0.0, 0.46, 0.72, 0.015, wall)
    c.poly([(-0.56, 0.68), (0.56, 0.68), (0.38, 1.02), (-0.38, 1.02)], (206, 98, 62))      # chhat
    for k in range(1, 4):
        c.line([(-0.56 + 0.18 * k / 3 * 1.0 + 0.0, 0.68 + 0.34 * k / 4), (0.56 - 0.18 * k / 3, 0.68 + 0.34 * k / 4)], 0.008, (160, 66, 44))
    for wx in (-0.27, 0.27):                                                  # khidkiyan + shutters
        c.rrect(wx - 0.085, 0.38, wx + 0.085, 0.60, 0.01, (156, 204, 238))
        c.line([(wx, 0.38), (wx, 0.60)], 0.009, INK)
        c.line([(wx - 0.085, 0.49), (wx + 0.085, 0.49)], 0.009, INK)
        c.rrect(wx - 0.145, 0.38, wx - 0.095, 0.60, 0.005, shut)
        c.rrect(wx + 0.095, 0.38, wx + 0.145, 0.60, 0.005, shut)
    c.rrect(-0.085, 0.0, 0.085, 0.34, 0.04, (148, 92, 54))
    c.circ(0.05, 0.16, 0.012, (240, 200, 80), ow=False)
    c.rrect(-0.12, -0.0, 0.12, 0.02, 0.005, (170, 170, 176))


@prop("tree", ext=(0.45, 0.45, 1.25, 0.03))
def tree(c):
    sw = 0.012 * math.sin(c.t * 1.7 + c.seed)
    c.rrect(-0.04, 0.0, 0.04, 0.50, 0.01, (140, 92, 54))
    for x, y, r in ((0, 0.85, 0.27), (-0.17, 0.68, 0.19), (0.17, 0.68, 0.19)):
        c.circ(x + sw, y, r, (86, 170, 92))
    c.circ(-0.06 + sw, 0.92, 0.08, (118, 200, 118), ow=False)


# ============================================================ signboard ("UNFAIR!")
@prop("sign", ext=(0.45, 0.45, 1.00, 0.03))
def sign(c):
    ang = (7 * math.sin(c.t * 6) * math.exp(-0.5 * max(0, c.t - 0.2)) + 2.0 * math.sin(c.t * 2)) if c.action == "shake" else 2.0 * math.sin(c.t * 1.8)
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    pivot = (0.0, 0.58)
    rot = lambda x, y: (pivot[0] + (x - pivot[0]) * ca - (y - pivot[1]) * sa, pivot[1] + (x - pivot[0]) * sa + (y - pivot[1]) * ca)
    c.line([(0, 0.0), rot(0, 0.76)], 0.028, (130, 88, 50), ow=True)
    pts = [rot(x, y) for x, y in _rr(-0.31, 0.58, 0.31, 0.92, 0.02)]
    c.poly(pts, (228, 194, 128))
    txt = (c.txt or "UNFAIR!").upper()
    lines = [s.strip() for s in re.split(r"\||\n", txt)] if "|" in txt else ([txt] if len(txt) <= 9 else [" ".join(txt.split()[:len(txt.split()) // 2 + 1]), " ".join(txt.split()[len(txt.split()) // 2 + 1:])])
    lines = [ln for ln in lines if ln][:2] or [txt]
    size = 0.16 if len(lines) == 1 else 0.115
    while max(len(ln) for ln in lines) * size * 0.66 > 0.54 and size > 0.04:
        size -= 0.01
    for i, ln in enumerate(lines):
        y = 0.75 + (0.0 if len(lines) == 1 else (0.055 - 0.11 * i))
        x, yy = rot(0, y)
        c.text(ln, x, yy, size, (70, 44, 30), rot=-ang)


# ============================================================ paise ki bori
@prop("moneybag", ext=(0.32, 0.32, 0.55, 0.03))
def moneybag(c):
    b = 0.03 * abs(math.sin(c.t * 4)) if c.action in ("shake", "pop") else 0.0
    sq = 1 - 0.05 * math.sin(c.t * 8) * (b > 0)
    c.poly([(-0.10, 0.42 + b), (0.10, 0.42 + b), (0.06, 0.32 + b), (-0.06, 0.32 + b)], (200, 156, 92))
    c.ell(0, 0.17 + b / 2, 0.17 * (2 - sq), 0.155 * sq, (216, 174, 108))
    c.ell(0, 0.31 + b, 0.075, 0.04, (200, 156, 92))
    c.line([(-0.07, 0.315 + b), (0.07, 0.315 + b)], 0.03, (150, 92, 52), ow=True)
    c.text("$", 0.0, 0.16 + b / 2, 0.15, (48, 112, 62))


# ============================================================ graph / arrow (bars badhte hain; text mein "down" ho to girta hai)
@prop("graph", ext=(0.58, 0.58, 1.02, 0.03))
def graph(c):
    down = "down" in (c.txt or "").lower() or c.action == "fall"
    good, bad = (86, 176, 92), (214, 72, 62)
    col = bad if down else good
    for x in (-0.38, 0.38):
        c.line([(x, 0.0), (x, 0.36)], 0.02, (120, 80, 46), ow=True)
    c.rrect(-0.52, 0.30, 0.52, 0.98, 0.03, (250, 247, 236))
    c.line([(-0.40, 0.88), (-0.40, 0.40), (0.42, 0.40)], 0.014, INK)
    n = 5
    tops = []
    for i in range(n):
        h0 = 0.10 + 0.085 * (n - 1 - i if down else i)
        g = ease((c.t - 0.25 - 0.13 * i) / 0.5)
        hh = h0 * g
        x = -0.30 + i * 0.145
        if hh > 0.005:
            c.poly([(x - 0.045, 0.40), (x + 0.045, 0.40), (x + 0.045, 0.40 + hh), (x - 0.045, 0.40 + hh)], col)
        tops.append((x, 0.40 + h0 + 0.06))
    if c.t > 1.1:
        p = ease((c.t - 1.1) / 0.5)
        a, b = tops[0], tops[-1]
        e = (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)
        c.line([a, e], 0.022, shade(col, 0.8), ow=False)
        ang = math.atan2(e[1] - a[1], e[0] - a[0])
        c.poly([e, (e[0] - 0.07 * math.cos(ang - 0.5), e[1] - 0.07 * math.sin(ang - 0.5)), (e[0] - 0.07 * math.cos(ang + 0.5), e[1] - 0.07 * math.sin(ang + 0.5))],
               shade(col, 0.8), ow=False)
    lab = re.sub(r"(?i)up|down", "", c.txt or "").strip()
    if lab:
        c.text(lab, 0.0, 0.93, 0.07, (60, 50, 60))


# ============================================================ bada HATH (close-up): upar se aata hai aur cheez pakadta hai. text = coin | egg | bag
@prop("hand", ext=(0.62, 0.62, 1.95, 1.45))
def hand(c):
    skin, sleeve = (246, 214, 180), (74, 112, 192)
    it = (c.txt or "coin").lower()
    c.rrect(-0.27, 0.22, 0.27, 1.95, 0.03, sleeve)                         # aasteen (upar se)
    c.rrect(-0.285, 0.18, 0.285, 0.30, 0.02, shade(sleeve, 0.82))
    c.rrect(-0.23, -0.20, 0.23, 0.24, 0.12, skin)                         # hatheli
    for x, ln in ((-0.15, 0.20), (-0.05, 0.27), (0.05, 0.25), (0.15, 0.18)):   # ungliyan
        c.line([(x, -0.10), (x * 0.9, -0.22 - ln * 0.55), (x * 0.78, -0.30 - ln)], 0.085, skin, ow=True)
    c.line([(-0.19, 0.02), (-0.20, -0.26), (-0.10, -0.46)], 0.09, skin, ow=True)      # angutha
    drop = c.action == "drop"
    y = -0.60 - (max(0.0, c.t - 1.1) ** 2 * 5.0 if drop else 0.0)
    if it.startswith("egg"):
        pts = [(0.05 + 0.13 * math.cos(a) * (1 - 0.14 * math.sin(a)), y + 0.17 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 30, endpoint=False)]
        c.poly(pts, (252, 248, 236))
    elif it.startswith("bag") or it.startswith("money"):
        c.ell(0.05, y - 0.02, 0.16, 0.15, (216, 174, 108))
        c.text("$", 0.05, y - 0.02, 0.17, (48, 112, 62))
    else:
        c.ell(0.05, y, 0.15, 0.15, (246, 198, 52))
        c.ell(0.05, y, 0.105, 0.105, (250, 214, 90), ow=False)
        c.text("$", 0.05, y, 0.13, (190, 128, 20))
        s = 0.5 + 0.5 * math.sin(c.t * 7)
        c.star(0.22, y + 0.13, 0.06 * s)
