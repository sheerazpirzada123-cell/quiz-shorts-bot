"""Code se bana stick-man animation (koi image API nahi, koi internet nahi, kabhi fail nahi hota).

Female characters ke lambe baal, male ke chhote baal ya ganje. Har scene mein: background, props (pop-in animation),
characters (chalna, daudna, kudna, sochna, shock...), lip-sync wala munh, label sticker, camera zoom/shake.
"""
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SH = 4
K = 1 << SH
BLACK = (22, 22, 22)
WHITE = (255, 255, 255)


def rgb(h):
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))  # BGR


COL = {n: rgb(h) for n, h in dict(
    red="#e53935", blue="#1e88e5", green="#43a047", orange="#fb8c00", purple="#8e24aa", brown="#8d5a2b",
    yellow="#fdd835", teal="#00897b", pink="#ec407a", gray="#78909c", gold="#f9c80e", sky="#9fd8f5",
    wood="#8b5a2b", skin="#f5d0a9", grass="#6cc04a", dark="#2b2b3a", stone="#9e9e9e", water="#4aa3e0",
    fire1="#ff7a00", fire2="#ffd000", parch="#f3e2b3", paper="#f8f8f6").items()}


# ------------------------------------------------------------------ drawing helpers
def _p(x, y):
    return (int(round(x * K)), int(round(y * K)))


def line(img, p, q, w, c=BLACK):
    cv2.line(img, _p(*p), _p(*q), c, max(1, int(round(w))), cv2.LINE_AA, SH)


def circ(img, c, r, col, th=-1):
    cv2.circle(img, _p(*c), max(1, int(round(r * K))), col, th if th < 0 else max(1, int(round(th))), cv2.LINE_AA, SH)


def ell(img, c, ax, ang, a0, a1, col, th=-1):
    cv2.ellipse(img, _p(*c), (max(1, int(ax[0] * K)), max(1, int(ax[1] * K))), ang, a0, a1, col,
                th if th < 0 else max(1, int(round(th))), cv2.LINE_AA, SH)


def poly(img, pts, fill=None, out=None, w=3):
    arr = np.array([_p(*p) for p in pts], np.int32)
    if fill is not None:
        cv2.fillPoly(img, [arr], fill, cv2.LINE_AA, SH)
    if out is not None:
        cv2.polylines(img, [arr], True, out, max(1, int(round(w))), cv2.LINE_AA, SH)


def pline(img, pts, w, c=BLACK):
    arr = np.array([_p(*p) for p in pts], np.int32)
    cv2.polylines(img, [arr], False, c, max(1, int(round(w))), cv2.LINE_AA, SH)


def rect(img, x0, y0, x1, y1, fill=None, out=None, w=3):
    poly(img, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill, out, w)


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def pop_scale(t):
    """0 -> 1 with a little overshoot (bouncy pop-in)."""
    if t <= 0:
        return 0.0
    if t >= 0.45:
        return 1.0
    x = t / 0.45
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


# ------------------------------------------------------------------ text sprites
_FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
_spr_cache = {}


def _font(size):
    for p in _FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def text_sprite(text, size, fill=(255, 255, 255), stroke=(0, 0, 0), sw=None, box=None, max_w=900):
    """BGRA sprite (cached). box=(r,g,b) rakhne par rounded sticker banta hai."""
    key = (text, size, fill, stroke, box, max_w)
    if key in _spr_cache:
        return _spr_cache[key]
    f = _font(size)
    d0 = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d0.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    lh = int(size * 1.2)
    tw = int(max(d0.textlength(l, font=f) for l in lines))
    pad = int(size * 0.45) if box else int(size * 0.25)
    sw = sw if sw is not None else max(2, size // 10)
    W, H = tw + 2 * pad + 2 * sw, lh * len(lines) + 2 * pad
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if box:
        d.rounded_rectangle([sw, sw, W - sw, H - sw], radius=int(size * 0.4), fill=box + (255,), outline=(20, 20, 20, 255),
                            width=max(3, size // 9))
    for i, l in enumerate(lines):
        x = (W - d0.textlength(l, font=f)) / 2
        d.text((x, pad + i * lh), l, font=f, fill=fill, stroke_width=0 if box else sw, stroke_fill=stroke)
    a = np.array(im)
    out = np.dstack([a[:, :, 2], a[:, :, 1], a[:, :, 0], a[:, :, 3]])
    _spr_cache[key] = out
    return out


def blit(img, spr, cx, cy, scale=1.0, alpha=1.0):
    if scale <= 0.01:
        return
    h, w = spr.shape[:2]
    nw, nh = max(2, int(w * scale)), max(2, int(h * scale))
    s = cv2.resize(spr, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    x0, y0 = int(cx - nw / 2), int(cy - nh / 2)
    X0, Y0, X1, Y1 = max(0, x0), max(0, y0), min(img.shape[1], x0 + nw), min(img.shape[0], y0 + nh)
    if X0 >= X1 or Y0 >= Y1:
        return
    s = s[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0]
    a = (s[:, :, 3:4].astype(np.float32) / 255.0) * alpha
    roi = img[Y0:Y1, X0:X1].astype(np.float32)
    img[Y0:Y1, X0:X1] = (roi * (1 - a) + s[:, :, :3].astype(np.float32) * a).astype(np.uint8)


# ------------------------------------------------------------------ stage
class Stage:
    def __init__(self, W, H, portrait):
        self.W, self.H, self.portrait = W, H, portrait
        self.s = 0.8 if portrait else 1.0          # prop scale
        self.ground = int(H * (0.67 if portrait else 0.80))
        self.char_h = 470 if portrait else 340

    def char_x(self, n, i):
        """n characters (1 ya 2), i-th ka x."""
        if n == 1:
            return self.W * 0.5
        return self.W * ([0.34, 0.68] if self.portrait else [0.38, 0.64])[i]

    def sky_slots(self):
        if self.portrait:
            return [(0.24, 0.23), (0.76, 0.23), (0.5, 0.17)]
        return [(0.20, 0.34), (0.80, 0.34), (0.5, 0.22)]

    def ground_slots(self):
        return [(0.13, 1), (0.87, 1), (0.5, 1)] if not self.portrait else [(0.14, 1), (0.86, 1), (0.5, 1)]


# ------------------------------------------------------------------ backgrounds
def _grad(H, W, top, bot, y0=0, y1=None):
    y1 = y1 or H
    a = np.zeros((H, W, 3), np.uint8)
    n = max(1, y1 - y0)
    t = np.linspace(0, 1, n)[:, None]
    c = (np.array(top)[None, :] * (1 - t) + np.array(bot)[None, :] * t).astype(np.uint8)
    a[y0:y1] = c[:, None, :]
    return a


def make_bg(st, kind, seed=0):
    W, H, g = st.W, st.H, st.ground
    rnd = np.random.RandomState(seed % 100000)
    s = st.s
    if kind == "orange":
        img = np.full((H, W, 3), (95, 170, 240), np.uint8)
        img[g - int(20 * s):] = (150, 150, 150)
        cv2.line(img, (0, g - int(20 * s)), (W, g - int(20 * s)), (60, 60, 60), 3, cv2.LINE_AA)
    elif kind == "grass":
        img = _grad(H, W, (250, 215, 150), (255, 240, 205), 0, g)
        img[g:] = COL["grass"]
        for cx, r in [(0.2, 0.28), (0.62, 0.35), (0.95, 0.25)]:
            cv2.ellipse(img, (int(W * cx), g), (int(W * r), int(H * 0.12)), 0, 180, 360, (90, 170, 70), -1, cv2.LINE_AA)
        img[g:] = (95, 185, 100)
        img[g + int((H - g) * 0.5):] = (80, 165, 90)
    elif kind == "sky":
        img = _grad(H, W, (245, 190, 110), (255, 235, 200), 0, g)
        img[g:] = (110, 150, 190)
        img[g + int((H - g) * 0.5):] = (95, 135, 175)
    elif kind == "night":
        img = _grad(H, W, (60, 25, 15), (110, 60, 40), 0, g)
        img[g:] = (45, 35, 30)
    elif kind == "desert":
        img = _grad(H, W, (170, 215, 250), (200, 235, 255), 0, g)
        img[g:] = (130, 190, 235)
        for cx, r in [(0.15, 0.3), (0.7, 0.4)]:
            cv2.ellipse(img, (int(W * cx), g), (int(W * r), int(H * 0.08)), 0, 180, 360, (140, 200, 240), -1, cv2.LINE_AA)
        img[g:] = (130, 190, 235)
    elif kind == "cave":
        img = np.full((H, W, 3), (45, 55, 75), np.uint8)
        for x in range(0, W, int(70 * s)):
            hh = int(rnd.randint(40, 150) * s)
            cv2.fillPoly(img, [np.array([[x, 0], [x + int(60 * s), 0], [x + int(30 * s), hh]])], (30, 38, 55), cv2.LINE_AA)
        img[g:] = (85, 100, 120)
    elif kind == "ocean":
        img = _grad(H, W, (250, 215, 150), (255, 240, 205), 0, int(g * 0.8))
        img[int(g * 0.8):g] = (190, 140, 50)
        for i in range(8):
            y = int(g * 0.8) + (g - int(g * 0.8)) * i // 8
            cv2.line(img, (0, y), (W, y), (205, 160, 70), 2, cv2.LINE_AA)
        img[g:] = (150, 205, 235)
    elif kind == "snow":
        img = _grad(H, W, (225, 215, 200), (250, 245, 240), 0, g)
        img[g:] = (250, 248, 245)
        cv2.ellipse(img, (int(W * 0.3), g), (int(W * 0.35), int(H * 0.09)), 0, 180, 360, (245, 235, 225), -1, cv2.LINE_AA)
        img[g + int((H - g) * 0.45):] = (235, 225, 215)
    elif kind == "city":
        img = _grad(H, W, (235, 215, 190), (250, 240, 230), 0, g)
        x = 0
        while x < W:
            bw, bh = int(rnd.randint(70, 150) * s), int(rnd.randint(110, 300) * s)
            c = int(rnd.randint(150, 195))
            cv2.rectangle(img, (x, g - bh), (x + bw, g), (c, c - 10, c - 20), -1)
            for wy in range(g - bh + 14, g - 20, int(30 * s)):
                for wx in range(x + 10, x + bw - 14, int(26 * s)):
                    cv2.rectangle(img, (wx, wy), (wx + int(12 * s), wy + int(16 * s)), (200, 235, 250), -1)
            x += bw + int(rnd.randint(0, 20))
        img[g:] = (120, 120, 125)
        cv2.line(img, (0, g + int((H - g) * 0.5)), (W, g + int((H - g) * 0.5)), (200, 200, 200), 4)
    else:  # white paper
        img = np.full((H, W, 3), (246, 248, 248), np.uint8)
        img[g:] = (240, 242, 242)
        cv2.line(img, (0, g), (W, g), (205, 205, 205), 2, cv2.LINE_AA)
    return img


def ambient(st, img, kind, t, seed):
    W, H, s = st.W, st.H, st.s
    if kind in ("grass", "sky", "desert", "ocean"):
        for i in range(3):
            x = (W * (0.15 + 0.38 * i) + t * (18 + 9 * i) + seed * 13) % (W + 300) - 150
            y = H * (0.12 + 0.07 * ((i + seed) % 3))
            for dx, dy, r in [(0, 0, 38), (40, 8, 32), (-40, 10, 30), (14, -18, 30)]:
                circ(img, (x + dx * s, y + dy * s), r * s, WHITE)
            ell(img, (x, y + 22 * s), (78 * s, 18 * s), 0, 0, 360, WHITE)
    elif kind == "night":
        rnd = np.random.RandomState(seed % 1000)
        for i in range(45):
            x, y = rnd.rand() * W, rnd.rand() * st.ground * 0.9
            b = 140 + 115 * abs(math.sin(t * 2 + i))
            circ(img, (x, y), (1.2 + (i % 3) * 0.7) * s, (b, b, b + 20))
    elif kind == "snow":
        rnd = np.random.RandomState(seed % 1000)
        for i in range(60):
            x = (rnd.rand() * W + 25 * math.sin(t * 1.3 + i)) % W
            y = (rnd.rand() * H + t * (60 + (i % 4) * 25)) % H
            circ(img, (x, y), (2 + (i % 3)) * s, (255, 255, 255))
        pass


# ------------------------------------------------------------------ props
def _star5(img, c, r, col, rot=0.0):
    pts = []
    for i in range(10):
        a = rot + i * math.pi / 5 - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((c[0] + rr * math.cos(a), c[1] + rr * math.sin(a)))
    poly(img, pts, col, BLACK, 2)


def _stick_mini(img, x, y, h, t, ph, hair=False):
    """crowd ke chhote stick men (kood-te hue)."""
    j = abs(math.sin(t * 5 + ph)) * h * 0.18
    y = y - j
    r = h * 0.14
    head = (x, y - h * 0.8)
    w = max(2, h * 0.045)
    line(img, (x, y - h * 0.62), (x, y - h * 0.28), w)
    sw = math.sin(t * 5 + ph)
    line(img, (x, y - h * 0.28), (x - h * 0.14 + sw * 5, y), w)
    line(img, (x, y - h * 0.28), (x + h * 0.14 - sw * 5, y), w)
    line(img, (x, y - h * 0.55), (x - h * 0.2, y - h * (0.78 + 0.1 * sw)), w)
    line(img, (x, y - h * 0.55), (x + h * 0.2, y - h * (0.78 - 0.1 * sw)), w)
    circ(img, head, r, WHITE)
    circ(img, head, r, BLACK, max(2, w))
    circ(img, (head[0] - r * 0.35, head[1] - r * 0.1), max(1, r * 0.12), BLACK)
    circ(img, (head[0] + r * 0.35, head[1] - r * 0.1), max(1, r * 0.12), BLACK)
    if hair:
        ell(img, head, (r * 1.05, r * 1.05), 0, 180, 360, BLACK)


def prop_sun(img, x, y, u, t):
    for i in range(10):
        a = t * 0.8 + i * math.pi / 5
        line(img, (x + math.cos(a) * u * 0.7, y + math.sin(a) * u * 0.7), (x + math.cos(a) * u * 1.0, y + math.sin(a) * u * 1.0), u * 0.07, COL["fire1"])
    circ(img, (x, y), u * 0.58, COL["gold"])
    circ(img, (x, y), u * 0.58, BLACK, 3)


def prop_moon(img, x, y, u, t):
    circ(img, (x, y), u * 0.6, (200, 235, 245))
    for dx, dy, r in [(-0.2, -0.15, 0.13), (0.22, 0.1, 0.1), (-0.05, 0.3, 0.08)]:
        circ(img, (x + dx * u, y + dy * u), r * u, (165, 205, 220))
    circ(img, (x, y), u * 0.6, BLACK, 3)


def prop_stars(img, x, y, u, t):
    for i, (dx, dy, r) in enumerate([(-0.7, 0.1, 0.28), (0, -0.35, 0.36), (0.7, 0.15, 0.25), (0.2, 0.45, 0.2)]):
        _star5(img, (x + dx * u, y + dy * u), r * u * (1 + 0.12 * math.sin(t * 4 + i)), COL["gold"], t * 0.5)


def prop_cloud(img, x, y, u, t):
    for dx, dy, r in [(-0.45, 0.05, 0.38), (0, -0.12, 0.5), (0.45, 0.05, 0.36)]:
        circ(img, (x + dx * u, y + dy * u), r * u, BLACK, 3)
    for dx, dy, r in [(-0.45, 0.05, 0.38), (0, -0.12, 0.5), (0.45, 0.05, 0.36)]:
        circ(img, (x + dx * u, y + dy * u), r * u - 1, WHITE)
    rect(img, x - 0.55 * u, y + 0.1 * u, x + 0.55 * u, y + 0.42 * u, WHITE)


def prop_tree(img, x, y, u, t):  # y = ground
    sw = math.sin(t * 1.5) * 0.03
    rect(img, x - 0.09 * u, y - 0.8 * u, x + 0.09 * u, y, COL["wood"], BLACK, 3)
    for dx, dy, r in [(-0.3, -1.0, 0.42), (0.3, -1.0, 0.42), (0, -1.35, 0.5)]:
        circ(img, (x + (dx + sw * (1 + dy)) * u, y + dy * u), r * u, COL["green"])
        circ(img, (x + (dx + sw * (1 + dy)) * u, y + dy * u), r * u, BLACK, 3)


def prop_hut(img, x, y, u, t):
    rect(img, x - 0.7 * u, y - 0.7 * u, x + 0.7 * u, y, COL["parch"], BLACK, 3)
    poly(img, [(x - 0.9 * u, y - 0.7 * u), (x, y - 1.3 * u), (x + 0.9 * u, y - 0.7 * u)], COL["red"], BLACK, 3)
    rect(img, x - 0.18 * u, y - 0.45 * u, x + 0.18 * u, y, COL["wood"], BLACK, 3)


def prop_cave(img, x, y, u, t):
    poly(img, [(x - 1.1 * u, y), (x - 0.7 * u, y - 0.9 * u), (x, y - 1.2 * u), (x + 0.8 * u, y - 0.85 * u), (x + 1.1 * u, y)], COL["stone"], BLACK, 3)
    ell(img, (x, y), (0.45 * u, 0.6 * u), 0, 180, 360, (30, 30, 40))
    ell(img, (x, y), (0.45 * u, 0.6 * u), 0, 180, 360, BLACK, 3)


def prop_mountain(img, x, y, u, t):
    poly(img, [(x - 1.2 * u, y), (x - 0.3 * u, y - 1.3 * u), (x + 0.5 * u, y)], (150, 130, 110), BLACK, 3)
    poly(img, [(x - 0.1 * u, y), (x + 0.6 * u, y - 1.0 * u), (x + 1.3 * u, y)], (170, 150, 130), BLACK, 3)
    poly(img, [(x - 0.3 * u, y - 1.3 * u), (x - 0.5 * u, y - 0.95 * u), (x - 0.3 * u, y - 1.0 * u), (x - 0.1 * u, y - 0.92 * u)], WHITE, BLACK, 2)


def prop_fire(img, x, y, u, t):
    line(img, (x - 0.45 * u, y - 0.05 * u), (x + 0.45 * u, y - 0.2 * u), u * 0.12, COL["wood"])
    line(img, (x + 0.45 * u, y - 0.05 * u), (x - 0.45 * u, y - 0.2 * u), u * 0.12, COL["wood"])
    for i, (dx, hh, c) in enumerate([(-0.22, 0.8, COL["fire1"]), (0.2, 0.7, COL["fire1"]), (0, 1.1, COL["fire1"]), (0, 0.65, COL["fire2"])]):
        f = 1 + 0.18 * math.sin(t * 11 + i * 2)
        poly(img, [(x + dx * u - 0.22 * u, y - 0.2 * u), (x + dx * u + 0.06 * u * math.sin(t * 9 + i), y - (0.2 + hh * f) * u),
                   (x + dx * u + 0.22 * u, y - 0.2 * u)], c, BLACK if i < 3 else None, 2)


def prop_lightbulb(img, x, y, u, t):
    f = 0.75 + 0.25 * math.sin(t * 9)
    for i in range(8):
        a = i * math.pi / 4 + 0.2
        line(img, (x + math.cos(a) * u * 0.62, y + math.sin(a) * u * 0.62 - 0.1 * u),
             (x + math.cos(a) * u * (0.62 + 0.22 * f), y + math.sin(a) * u * (0.62 + 0.22 * f) - 0.1 * u), u * 0.06, COL["fire1"])
    circ(img, (x, y - 0.1 * u), 0.45 * u, COL["fire2"])
    circ(img, (x, y - 0.1 * u), 0.45 * u, BLACK, 3)
    rect(img, x - 0.2 * u, y + 0.3 * u, x + 0.2 * u, y + 0.55 * u, COL["stone"], BLACK, 3)


def prop_question(img, x, y, u, t):
    blit(img, text_sprite("?", int(u * 1.6), fill=(60, 200, 255), sw=int(u * 0.1)), x, y + 4 * math.sin(t * 3), 1.0)


def prop_exclaim(img, x, y, u, t):
    blit(img, text_sprite("!", int(u * 1.6), fill=(60, 60, 255), sw=int(u * 0.1)), x, y + 4 * math.sin(t * 8), 1.0)


def prop_coin(img, x, y, u, t):
    w = abs(math.cos(t * 3)) * 0.55 + 0.05
    ell(img, (x, y), (w * u, 0.55 * u), 0, 0, 360, COL["gold"])
    ell(img, (x, y), (w * u, 0.55 * u), 0, 0, 360, BLACK, 3)
    ell(img, (x, y), (w * u * 0.65, 0.36 * u), 0, 0, 360, (60, 170, 230), 2)


def prop_book(img, x, y, u, t):
    poly(img, [(x - 0.7 * u, y - 0.4 * u), (x, y - 0.3 * u), (x, y + 0.45 * u), (x - 0.7 * u, y + 0.35 * u)], (255, 245, 235), BLACK, 3)
    poly(img, [(x + 0.7 * u, y - 0.4 * u), (x, y - 0.3 * u), (x, y + 0.45 * u), (x + 0.7 * u, y + 0.35 * u)], (255, 245, 235), BLACK, 3)
    for i in range(4):
        line(img, (x - 0.6 * u, y - 0.2 * u + i * 0.15 * u), (x - 0.1 * u, y - 0.12 * u + i * 0.15 * u), 2, (150, 150, 150))
        line(img, (x + 0.6 * u, y - 0.2 * u + i * 0.15 * u), (x + 0.1 * u, y - 0.12 * u + i * 0.15 * u), 2, (150, 150, 150))


def prop_scroll(img, x, y, u, t):
    rect(img, x - 0.5 * u, y - 0.6 * u, x + 0.5 * u, y + 0.6 * u, COL["parch"], BLACK, 3)
    for yy in (-0.65, 0.65):
        rect(img, x - 0.6 * u, y + (yy - 0.08) * u, x + 0.6 * u, y + (yy + 0.08) * u, COL["wood"], BLACK, 3)
    for i in range(5):
        line(img, (x - 0.32 * u, y - 0.4 * u + i * 0.2 * u), (x + 0.32 * u - (i % 2) * 0.15 * u, y - 0.4 * u + i * 0.2 * u), 3, (120, 90, 60))


def prop_boat(img, x, y, u, t):
    b = math.sin(t * 2) * 0.06
    pts = [(x - 0.9 * u, y - 0.35 * u), (x + 0.9 * u, y - 0.35 * u), (x + 0.6 * u, y), (x - 0.6 * u, y)]
    poly(img, pts, COL["wood"], BLACK, 3)
    line(img, (x, y - 0.35 * u), (x, y - 1.5 * u), 5, BLACK)
    poly(img, [(x + 0.05 * u, y - 1.45 * u), (x + 0.75 * u, y - 0.5 * u), (x + 0.05 * u, y - 0.5 * u)], WHITE, BLACK, 3)
    for i in range(4):
        pline(img, [(x - 1.1 * u + i * 0.55 * u + j * 0.14 * u, y - 0.02 * u + (0.06 if j % 2 else -0.06) * u * math.sin(t * 3 + i)) for j in range(5)], 3, COL["water"])


def prop_wheel(img, x, y, u, t):
    circ(img, (x, y), 0.6 * u, COL["wood"], max(6, int(u * 0.14)))
    circ(img, (x, y), 0.6 * u, BLACK, 3)
    for i in range(6):
        a = t * 2 + i * math.pi / 3
        line(img, (x, y), (x + math.cos(a) * 0.55 * u, y + math.sin(a) * 0.55 * u), 5, COL["wood"])
    circ(img, (x, y), 0.1 * u, BLACK)


def prop_sword(img, x, y, u, t):
    a = math.radians(-35 + 6 * math.sin(t * 3))
    c, s = math.cos(a), math.sin(a)
    def P(l, w=0):
        return (x + c * l * u - s * w * u, y + s * l * u + c * w * u)
    poly(img, [P(-0.9, -0.07), P(0.5, -0.07), P(0.7, 0), P(0.5, 0.07), P(-0.9, 0.07)], (225, 225, 230), BLACK, 3)
    line(img, P(-0.9, -0.25), P(-0.9, 0.25), u * 0.1, COL["gold"])
    line(img, P(-0.9, 0), P(-1.2, 0), u * 0.13, COL["wood"])


def prop_crown(img, x, y, u, t):
    poly(img, [(x - 0.6 * u, y + 0.3 * u), (x - 0.7 * u, y - 0.4 * u), (x - 0.3 * u, y - 0.1 * u), (x, y - 0.55 * u),
               (x + 0.3 * u, y - 0.1 * u), (x + 0.7 * u, y - 0.4 * u), (x + 0.6 * u, y + 0.3 * u)], COL["gold"], BLACK, 3)
    for dx in (-0.3, 0, 0.3):
        circ(img, (x + dx * u, y + 0.1 * u), 0.07 * u, COL["red"])


def prop_pot(img, x, y, u, t):
    ell(img, (x, y), (0.6 * u, 0.55 * u), 0, 0, 360, (70, 70, 80))
    ell(img, (x, y), (0.6 * u, 0.55 * u), 0, 0, 360, BLACK, 3)
    rect(img, x - 0.62 * u, y - 0.45 * u, x + 0.62 * u, y - 0.33 * u, (70, 70, 80), BLACK, 3)
    for i in range(3):
        pline(img, [(x + (i - 1) * 0.3 * u + 0.06 * u * math.sin(t * 4 + j + i), y - 0.5 * u - j * 0.13 * u) for j in range(6)], 3, (200, 200, 200))


def prop_clock(img, x, y, u, t):
    circ(img, (x, y), 0.6 * u, WHITE)
    circ(img, (x, y), 0.6 * u, BLACK, 4)
    for i in range(12):
        a = i * math.pi / 6
        line(img, (x + math.cos(a) * 0.5 * u, y + math.sin(a) * 0.5 * u), (x + math.cos(a) * 0.56 * u, y + math.sin(a) * 0.56 * u), 3)
    line(img, (x, y), (x + math.cos(t * 4) * 0.45 * u, y + math.sin(t * 4) * 0.45 * u), 4)
    line(img, (x, y), (x + math.cos(t * 0.33) * 0.3 * u, y + math.sin(t * 0.33) * 0.3 * u), 6)


def prop_map(img, x, y, u, t):
    rect(img, x - 0.8 * u, y - 0.55 * u, x + 0.8 * u, y + 0.55 * u, COL["parch"], BLACK, 3)
    pline(img, [(x - 0.55 * u, y + 0.3 * u), (x - 0.2 * u, y - 0.1 * u), (x + 0.15 * u, y + 0.2 * u), (x + 0.5 * u, y - 0.25 * u)], 3, COL["red"])
    line(img, (x + 0.42 * u, y - 0.33 * u), (x + 0.58 * u, y - 0.17 * u), 5, COL["red"])
    line(img, (x + 0.58 * u, y - 0.33 * u), (x + 0.42 * u, y - 0.17 * u), 5, COL["red"])


def prop_bed(img, x, y, u, t):
    rect(img, x - 0.9 * u, y - 0.45 * u, x + 0.9 * u, y - 0.05 * u, COL["blue"], BLACK, 3)
    rect(img, x - 0.9 * u, y - 0.75 * u, x - 0.8 * u, y, COL["wood"], BLACK, 3)
    ell(img, (x - 0.55 * u, y - 0.52 * u), (0.3 * u, 0.12 * u), 0, 0, 360, WHITE)
    ell(img, (x - 0.55 * u, y - 0.52 * u), (0.3 * u, 0.12 * u), 0, 0, 360, BLACK, 2)


def prop_shoe(img, x, y, u, t):
    poly(img, [(x - 0.5 * u, y - 0.5 * u), (x - 0.1 * u, y - 0.5 * u), (x - 0.05 * u, y - 0.1 * u), (x + 0.6 * u, y + 0.05 * u),
               (x + 0.6 * u, y + 0.3 * u), (x - 0.5 * u, y + 0.3 * u)], COL["brown"], BLACK, 3)
    line(img, (x - 0.5 * u, y + 0.22 * u), (x + 0.6 * u, y + 0.22 * u), u * 0.08, (60, 60, 60))


def prop_bread(img, x, y, u, t):
    ell(img, (x, y), (0.7 * u, 0.4 * u), 0, 0, 360, (80, 160, 215))
    ell(img, (x, y), (0.7 * u, 0.4 * u), 0, 0, 360, BLACK, 3)
    for dx in (-0.3, 0, 0.3):
        line(img, (x + dx * u - 0.08 * u, y - 0.22 * u), (x + dx * u + 0.08 * u, y + 0.1 * u), 4, (50, 110, 170))


def prop_water(img, x, y, u, t):
    for r in range(3):
        pline(img, [(x - 0.8 * u + j * 0.2 * u, y + r * 0.3 * u + 0.08 * u * math.sin(t * 3 + j + r)) for j in range(9)], 6, COL["water"])
    poly(img, [(x, y - 0.8 * u), (x - 0.25 * u, y - 0.4 * u), (x + 0.25 * u, y - 0.4 * u)], COL["water"], BLACK, 2)
    circ(img, (x, y - 0.35 * u), 0.25 * u, COL["water"])


def prop_snowflake(img, x, y, u, t):
    for i in range(6):
        a = t + i * math.pi / 3
        line(img, (x, y), (x + math.cos(a) * 0.6 * u, y + math.sin(a) * 0.6 * u), 5, (230, 170, 90))
        mx, my = x + math.cos(a) * 0.35 * u, y + math.sin(a) * 0.35 * u
        line(img, (mx, my), (mx + math.cos(a + 0.8) * 0.17 * u, my + math.sin(a + 0.8) * 0.17 * u), 4, (230, 170, 90))
        line(img, (mx, my), (mx + math.cos(a - 0.8) * 0.17 * u, my + math.sin(a - 0.8) * 0.17 * u), 4, (230, 170, 90))


def prop_heart(img, x, y, u, t):
    u = u * (1 + 0.1 * abs(math.sin(t * 5)))
    for dx in (-0.25, 0.25):
        circ(img, (x + dx * u, y - 0.15 * u), 0.3 * u, COL["red"])
    poly(img, [(x - 0.52 * u, y - 0.02 * u), (x + 0.52 * u, y - 0.02 * u), (x, y + 0.6 * u)], COL["red"])
    pline(img, [(x - 0.55 * u, y), (x, y + 0.62 * u), (x + 0.55 * u, y)], 3)


def prop_skull(img, x, y, u, t):
    circ(img, (x, y - 0.1 * u), 0.5 * u, WHITE)
    circ(img, (x, y - 0.1 * u), 0.5 * u, BLACK, 3)
    rect(img, x - 0.25 * u, y + 0.25 * u, x + 0.25 * u, y + 0.55 * u, WHITE, BLACK, 3)
    for dx in (-0.2, 0.2):
        circ(img, (x + dx * u, y - 0.1 * u), 0.14 * u, BLACK)
    poly(img, [(x, y + 0.05 * u), (x - 0.06 * u, y + 0.17 * u), (x + 0.06 * u, y + 0.17 * u)], BLACK)


def prop_chart(img, x, y, u, t, k=1.0):
    line(img, (x - 0.8 * u, y + 0.6 * u), (x + 0.8 * u, y + 0.6 * u), 5)
    line(img, (x - 0.8 * u, y + 0.6 * u), (x - 0.8 * u, y - 0.7 * u), 5)
    for i, (h, c) in enumerate([(0.4, "blue"), (0.75, "green"), (0.55, "orange"), (1.1, "red")]):
        hh = h * min(1.0, t * 1.2 + 0.0) * u
        rect(img, x - 0.6 * u + i * 0.35 * u, y + 0.6 * u - hh, x - 0.4 * u + i * 0.35 * u, y + 0.6 * u, COL[c], BLACK, 2)


def prop_calendar(img, x, y, u, t):
    rect(img, x - 0.6 * u, y - 0.6 * u, x + 0.6 * u, y + 0.6 * u, WHITE, BLACK, 3)
    rect(img, x - 0.6 * u, y - 0.6 * u, x + 0.6 * u, y - 0.3 * u, COL["red"], BLACK, 3)
    for r in range(3):
        for c in range(4):
            circ(img, (x - 0.38 * u + c * 0.25 * u, y - 0.08 * u + r * 0.25 * u), 0.05 * u, (90, 90, 90))
    circ(img, (x + 0.12 * u, y + 0.17 * u), 0.13 * u, COL["red"], 3)


def prop_crowd(img, x, y, u, t):
    for i, dx in enumerate([-0.9, -0.45, 0, 0.45, 0.9]):
        _stick_mini(img, x + dx * u, y - (0.0 if i % 2 else 0.06) * u, 0.75 * u, t, i * 1.3, hair=(i % 2 == 1))


def prop_animal(img, x, y, u, t):
    sw = math.sin(t * 6)
    body = (x, y - 0.55 * u)
    for dx, ph in ((-0.35, 0), (-0.2, 1.5), (0.25, 3), (0.4, 4.5)):
        line(img, (x + dx * u, y - 0.45 * u), (x + dx * u + 0.12 * u * math.sin(t * 6 + ph), y), 6, BLACK)
    ell(img, body, (0.55 * u, 0.28 * u), 0, 0, 360, COL["brown"])
    ell(img, body, (0.55 * u, 0.28 * u), 0, 0, 360, BLACK, 3)
    circ(img, (x + 0.6 * u, y - 0.8 * u), 0.22 * u, COL["brown"])
    circ(img, (x + 0.6 * u, y - 0.8 * u), 0.22 * u, BLACK, 3)
    circ(img, (x + 0.68 * u, y - 0.84 * u), 0.03 * u, BLACK)
    poly(img, [(x + 0.55 * u, y - 0.97 * u), (x + 0.5 * u, y - 1.15 * u), (x + 0.68 * u, y - 1.0 * u)], COL["brown"], BLACK, 2)
    pline(img, [(x - 0.55 * u, y - 0.6 * u), (x - 0.8 * u, y - 0.75 * u + 0.1 * u * sw)], 5)


def prop_bird(img, x, y, u, t):
    x = x + 30 * math.sin(t * 1.2)
    f = math.sin(t * 9)
    pline(img, [(x - 0.7 * u, y - 0.1 * u + 0.35 * u * f), (x - 0.3 * u, y - 0.2 * u * f), (x, y)], 6)
    pline(img, [(x + 0.7 * u, y - 0.1 * u + 0.35 * u * f), (x + 0.3 * u, y - 0.2 * u * f), (x, y)], 6)
    circ(img, (x, y), 0.1 * u, BLACK)


def prop_fish(img, x, y, u, t):
    x = x + 15 * math.sin(t * 2)
    ell(img, (x, y), (0.6 * u, 0.32 * u), 0, 0, 360, COL["orange"])
    ell(img, (x, y), (0.6 * u, 0.32 * u), 0, 0, 360, BLACK, 3)
    poly(img, [(x - 0.55 * u, y), (x - 0.95 * u, y - 0.3 * u + 0.1 * u * math.sin(t * 8)), (x - 0.95 * u, y + 0.3 * u)], COL["orange"], BLACK, 3)
    circ(img, (x + 0.3 * u, y - 0.07 * u), 0.06 * u, BLACK)


def prop_bone(img, x, y, u, t):
    line(img, (x - 0.55 * u, y), (x + 0.55 * u, y), u * 0.16, (225, 235, 240))
    for sx in (-1, 1):
        for sy in (-1, 1):
            circ(img, (x + sx * 0.62 * u, y + sy * 0.1 * u), 0.12 * u, (225, 235, 240))
            circ(img, (x + sx * 0.62 * u, y + sy * 0.1 * u), 0.12 * u, BLACK, 2)


def prop_key(img, x, y, u, t):
    circ(img, (x - 0.5 * u, y), 0.25 * u, COL["gold"], max(5, int(u * 0.12)))
    circ(img, (x - 0.5 * u, y), 0.25 * u, BLACK, 2)
    line(img, (x - 0.25 * u, y), (x + 0.6 * u, y), u * 0.1, COL["gold"])
    line(img, (x + 0.4 * u, y), (x + 0.4 * u, y + 0.25 * u), u * 0.1, COL["gold"])
    line(img, (x + 0.6 * u, y), (x + 0.6 * u, y + 0.2 * u), u * 0.1, COL["gold"])


def prop_door(img, x, y, u, t):
    rect(img, x - 0.45 * u, y - 0.8 * u, x + 0.45 * u, y + 0.2 * u, COL["wood"], BLACK, 3)
    rect(img, x - 0.3 * u, y - 0.65 * u, x + 0.3 * u, y - 0.15 * u, (110, 80, 50), BLACK, 2)
    circ(img, (x + 0.3 * u, y - 0.15 * u), 0.05 * u, COL["gold"])


def prop_castle(img, x, y, u, t):
    rect(img, x - 0.9 * u, y - 0.9 * u, x + 0.9 * u, y, COL["stone"], BLACK, 3)
    for tx in (-0.9, 0.9):
        rect(img, x + tx * u - 0.25 * u, y - 1.3 * u, x + tx * u + 0.25 * u, y, (170, 170, 170), BLACK, 3)
        for k in (-0.2, 0, 0.2):
            rect(img, x + (tx + k) * u - 0.06 * u, y - 1.45 * u, x + (tx + k) * u + 0.06 * u, y - 1.3 * u, (170, 170, 170), BLACK, 2)
    ell(img, (x, y), (0.25 * u, 0.45 * u), 0, 180, 360, (40, 40, 50))
    line(img, (x, y - 1.3 * u), (x, y - 1.9 * u), 3)
    poly(img, [(x, y - 1.9 * u), (x + 0.4 * u + 0.05 * u * math.sin(t * 5), y - 1.75 * u), (x, y - 1.6 * u)], COL["red"], BLACK, 2)


def prop_flag(img, x, y, u, t):
    line(img, (x - 0.4 * u, y + 0.7 * u), (x - 0.4 * u, y - 0.8 * u), 6, COL["wood"])
    pts = [(x - 0.4 * u + i * 0.1 * u, y - 0.8 * u + 0.05 * u * math.sin(t * 6 + i)) for i in range(9)]
    pts2 = [(px, py + 0.55 * u) for px, py in reversed(pts)]
    poly(img, pts + pts2, COL["red"], BLACK, 3)


def prop_gem(img, x, y, u, t):
    pts = [(x - 0.5 * u, y - 0.15 * u), (x - 0.25 * u, y - 0.5 * u), (x + 0.25 * u, y - 0.5 * u), (x + 0.5 * u, y - 0.15 * u), (x, y + 0.55 * u)]
    poly(img, pts, (235, 215, 120), BLACK, 3)
    line(img, pts[0], pts[3], 3)
    line(img, pts[1], (x - 0.1 * u, y - 0.15 * u), 2)
    line(img, pts[2], (x + 0.1 * u, y - 0.15 * u), 2)
    _star5(img, (x + 0.4 * u, y - 0.6 * u), 0.14 * u * (0.6 + 0.4 * abs(math.sin(t * 5))), WHITE, 0)


def prop_spear(img, x, y, u, t):
    a = math.radians(-60)
    c, s = math.cos(a), math.sin(a)
    line(img, (x - c * 0.9 * u, y - s * 0.9 * u), (x + c * 0.8 * u, y + s * 0.8 * u), 6, COL["wood"])
    tip = (x + c * 1.0 * u, y + s * 1.0 * u)
    poly(img, [tip, (x + c * 0.7 * u - s * 0.1 * u, y + s * 0.7 * u + c * 0.1 * u), (x + c * 0.7 * u + s * 0.1 * u, y + s * 0.7 * u - c * 0.1 * u)], COL["stone"], BLACK, 2)


def prop_magnifier(img, x, y, u, t):
    a = 0.1 * math.sin(t * 3)
    cx, cy = x - 0.1 * u + 0.08 * u * math.sin(t * 2), y - 0.1 * u
    line(img, (cx + 0.4 * u, cy + 0.4 * u), (cx + 0.8 * u, cy + 0.8 * u), u * 0.14, COL["wood"])
    circ(img, (cx, cy), 0.5 * u, (250, 240, 215))
    circ(img, (cx, cy), 0.5 * u, COL["gray"], max(5, int(u * 0.1)))
    circ(img, (cx, cy), 0.5 * u, BLACK, 2)


# name -> (fn, ground?, base size)
PROP_TABLE = {
    "sun": (prop_sun, False, 95), "moon": (prop_moon, False, 90), "stars": (prop_stars, False, 100), "cloud": (prop_cloud, False, 95),
    "tree": (prop_tree, True, 130), "hut": (prop_hut, True, 130), "cave": (prop_cave, True, 130), "mountain": (prop_mountain, True, 150),
    "fire": (prop_fire, True, 120), "lightbulb": (prop_lightbulb, False, 105), "question": (prop_question, False, 95),
    "exclaim": (prop_exclaim, False, 95), "coin": (prop_coin, False, 95), "book": (prop_book, False, 105), "scroll": (prop_scroll, False, 105),
    "boat": (prop_boat, True, 120), "wheel": (prop_wheel, False, 100), "sword": (prop_sword, False, 110), "crown": (prop_crown, False, 100),
    "pot": (prop_pot, True, 110), "clock": (prop_clock, False, 100), "map": (prop_map, False, 105), "bed": (prop_bed, True, 125),
    "shoe": (prop_shoe, False, 105), "bread": (prop_bread, False, 100), "water": (prop_water, False, 100), "snowflake": (prop_snowflake, False, 100),
    "heart": (prop_heart, False, 100), "skull": (prop_skull, False, 100), "chart": (prop_chart, False, 110), "calendar": (prop_calendar, False, 100),
    "crowd": (prop_crowd, True, 120), "animal": (prop_animal, True, 130), "bird": (prop_bird, False, 100), "fish": (prop_fish, False, 100),
    "bone": (prop_bone, False, 100), "key": (prop_key, False, 105), "door": (prop_door, True, 150), "castle": (prop_castle, True, 120),
    "flag": (prop_flag, False, 110), "gem": (prop_gem, False, 100), "spear": (prop_spear, False, 105), "magnifier": (prop_magnifier, False, 105),
}


# ------------------------------------------------------------------ character poses
def pose(action, t, ph):
    s, pi2 = math.sin, 2 * math.pi
    w = pi2 * t
    P = dict(aF=8, eF=12, aB=-8, eB=12, lF=0, kF=0, lB=0, kB=0, lean=0, dx=0.0, dy=0.004 * s(w * 0.9 + ph), tilt=0)
    if action == "talk":
        P.update(aF=38 + 26 * s(w * 1.15 + ph), eF=45 + 30 * s(w * 1.15 + ph + 1.2), aB=-12 + 14 * s(w * 0.7 + ph + 2),
                 eB=25 + 15 * s(w * 0.7 + ph), tilt=3 * s(w * 0.8 + ph))
    elif action == "wave":
        P.update(aF=135, eF=32 * s(w * 3.2), tilt=4 * s(w * 1.6))
    elif action == "point":
        P.update(aF=95 + 5 * s(w * 2), eF=3, lean=4)
    elif action in ("walk", "run"):
        fast = action == "run"
        f = w * (2.5 if fast else 1.5)
        amp, kn = (50, 70) if fast else (30, 40)
        P.update(lF=amp * s(f), lB=-amp * s(f), kF=kn * max(0, math.cos(f)), kB=kn * max(0, -math.cos(f)),
                 aF=-(55 if fast else 24) * s(f), eF=(80 if fast else 18), aB=(55 if fast else 24) * s(f), eB=(80 if fast else 18),
                 lean=14 if fast else 5, dy=(-0.03 if fast else 0.012) * abs(s(f)) * (1 if not fast else -1),
                 dx=min(0.45, max(-0.35, -0.35 + (0.32 if fast else 0.1) * t)))
    elif action == "jump":
        u = abs(s(w * 0.8))
        P.update(dy=-0.2 * u, aF=20 + 110 * u, eF=20, aB=-20 - 110 * u, eB=-20, kF=35 * (1 - u), kB=35 * (1 - u), lF=8, lB=-8)
    elif action == "celebrate":
        P.update(dy=-0.09 * abs(s(w * 1.6)), aF=150 + 10 * s(w * 3), eF=10, aB=-150 - 10 * s(w * 3), eB=-10, kF=20, kB=20, tilt=5 * s(w))
    elif action == "shock":
        e = ease_out(t / 0.25)
        P.update(dx=-0.1 * e + 0.004 * s(w * 18), lean=-12 * e, aF=110 * e + 8, eF=40 * e, aB=-100 * e - 8, eB=-40 * e,
                 dy=-0.03 * e * (1 - e) * 4 + 0.003 * s(w * 20))
    elif action == "think":
        P.update(aF=35, eF=140, aB=15, eB=75, tilt=6 * s(w * 0.5), lean=3)
    elif action == "shrug":
        k = 0.5 + 0.5 * s(w * 1.2)
        P.update(aF=60, eF=55, aB=-60, eB=-55, tilt=8, dy=-0.01 * k)
    elif action == "sad":
        P.update(lean=14, tilt=14, aF=4, eF=6, aB=-4, eB=6, dy=0.01 + 0.004 * s(w * 0.5))
    elif action == "dance":
        f = w * 2
        P.update(dy=0.02 * abs(s(f)), lF=22 * s(f), lB=-22 * s(f), kF=30 * max(0, s(f)), kB=30 * max(0, -s(f)),
                 aF=70 + 60 * s(f), eF=40, aB=-70 - 60 * s(f + math.pi), eB=-40, tilt=6 * s(f))
    elif action == "hide":
        P.update(dy=0.1, lean=16, lF=40, lB=40, kF=70, kB=70, aF=150, eF=30, aB=-150, eB=-30, dx=0.004 * s(w * 20))
    elif action == "work":
        f = w * 1.6
        P.update(aF=80 + 60 * s(f), eF=30, aB=20 + 30 * s(f), eB=40, lean=8 + 6 * s(f))
    return P


def _limb(o, a1, bend, l1, l2, f):
    a = math.radians(a1)
    p1 = (o[0] + math.sin(a) * l1 * f, o[1] + math.cos(a) * l1)
    a2 = math.radians(a1 + bend)
    p2 = (p1[0] + math.sin(a2) * l2 * f, p1[1] + math.cos(a2) * l2)
    return p1, p2


def draw_char(st, img, ch, x, scale, action, emo, t, mouth, f, ph, ground=None):
    """ch: dict(gender, hair, garment, accessory, color). f = +1 (right) ya -1 (left) dekhta hai."""
    h = st.char_h * scale
    g = ground if ground is not None else st.ground
    P = pose(action, t, ph)
    th = max(4.0, 0.024 * h)
    thigh = shin = 0.235 * h
    hip = (x + P["dx"] * h * f, g - (thigh + shin) * 0.985 + P["dy"] * h)
    tl = 0.30 * h
    lean = math.radians(P["lean"])
    sho = (hip[0] + math.sin(lean) * tl * f, hip[1] - math.cos(lean) * tl)
    hr = 0.118 * h
    tilt = math.radians(P["lean"] + P["tilt"])
    hc = (sho[0] + math.sin(tilt) * (hr + 0.03 * h) * f, sho[1] - math.cos(tilt) * (hr + 0.03 * h))
    col = COL.get(ch.get("color", "blue"), COL["blue"])
    garment, acc = ch.get("garment", "none"), ch.get("accessory", "none")
    female = ch.get("gender") == "female"

    # shadow
    sc = tuple(int(c * 0.82) for c in img[min(img.shape[0] - 1, int(g + 4)), int(min(max(x, 0), img.shape[1] - 1))])
    ell(img, (x + P["dx"] * h * f, g + 3), (0.26 * h * (1 - 0.25 * (-P["dy"] if P["dy"] < 0 else 0) * 4), 0.035 * h), 0, 0, 360, sc)

    # cape (back)
    if garment == "cape":
        sw = math.sin(t * 3 + ph) * 0.05 * h
        poly(img, [(sho[0], sho[1]), (sho[0] - f * 0.32 * h + sw, hip[1] + 0.2 * h), (sho[0] - f * 0.08 * h, hip[1] + 0.26 * h)], col, BLACK, 2)

    aBp1, aBp2 = _limb(sho, P["aB"], P["eB"], 0.16 * h, 0.15 * h, f)
    aFp1, aFp2 = _limb(sho, P["aF"], P["eF"], 0.16 * h, 0.15 * h, f)
    lBp1, lBp2 = _limb(hip, P["lB"], -P["kB"], thigh, shin, f)
    lFp1, lFp2 = _limb(hip, P["lF"], -P["kF"], thigh, shin, f)

    def limb_draw(o, p1, p2, hand=False, foot=False):
        line(img, o, p1, th)
        line(img, p1, p2, th)
        circ(img, p1, th * 0.5, BLACK)
        if hand:
            circ(img, p2, th * 1.15, WHITE)
            circ(img, p2, th * 1.15, BLACK, 2)
        if foot:
            line(img, p2, (p2[0] + f * 0.075 * h, p2[1]), th)

    limb_draw(sho, aBp1, aBp2, hand=True)
    limb_draw(hip, lBp1, lBp2, foot=True)
    line(img, hip, sho, th)
    line(img, sho, (hc[0] - math.sin(tilt) * hr * 0.9 * f, hc[1] + math.cos(tilt) * hr * 0.9), th)
    # garments
    if garment in ("tunic", "robe", "dress"):
        hem = hip[1] + (0.07 * h if garment == "tunic" else 0.40 * h)
        wd = 0.085 * h if garment != "dress" else 0.07 * h
        hw = (0.14 if garment == "tunic" else 0.20 if garment == "robe" else 0.25) * h
        poly(img, [(sho[0] - wd, sho[1]), (sho[0] + wd, sho[1]), (hip[0] + f * 0.02 * h + hw, hem), (hip[0] + f * 0.02 * h - hw, hem)], col, BLACK, 2)
    elif garment == "loincloth":
        poly(img, [(hip[0] - 0.07 * h, hip[1] - 0.02 * h), (hip[0] + 0.07 * h, hip[1] - 0.02 * h), (hip[0] + 0.04 * h, hip[1] + 0.12 * h),
                   (hip[0] - 0.04 * h, hip[1] + 0.12 * h)], col, BLACK, 2)
    limb_draw(hip, lFp1, lFp2, foot=True)
    # hair back (female long)
    sway = math.sin(t * 2 + ph) * 0.18 * hr
    if female:
        poly(img, [(hc[0] - 1.12 * hr, hc[1] - 0.2 * hr), (hc[0] - 1.18 * hr - f * 0.3 * hr + sway, hc[1] + 2.5 * hr),
                   (hc[0] + 1.18 * hr - f * 0.3 * hr + sway, hc[1] + 2.5 * hr), (hc[0] + 1.12 * hr, hc[1] - 0.2 * hr)], BLACK)
        circ(img, hc, hr * 1.12, BLACK)
    # head
    circ(img, hc, hr, WHITE)
    # hair front
    if female:
        pts = [(hc[0] + hr * 1.06 * math.cos(math.radians(a)), hc[1] - hr * 1.06 * math.sin(math.radians(a))) for a in range(180, -1, -12)]
        inner = [(hc[0] + f * hr * 0.2 + hr * 0.62 * math.cos(math.radians(a)), hc[1] - hr * 0.1 - hr * 0.7 * math.sin(math.radians(a))) for a in range(0, 181, 12)]
        poly(img, pts + inner, BLACK)
    elif ch.get("hair", "short") != "bald":
        outer = [(hc[0] + hr * 1.04 * math.cos(math.radians(a)), hc[1] - hr * 1.04 * math.sin(math.radians(a))) for a in range(12, 169, 12)]
        inner = [(hc[0] + hr * 0.97 * math.cos(math.radians(a)), hc[1] - hr * (0.05 + 0.5 * math.sin(math.radians(a)))) for a in range(168, 11, -12)]
        poly(img, outer + inner, BLACK)
        poly(img, [(hc[0] - 0.35 * hr, hc[1] - 0.98 * hr), (hc[0] - f * 0.05 * hr, hc[1] - 1.32 * hr), (hc[0] + 0.3 * hr, hc[1] - 1.0 * hr)], BLACK)
    circ(img, hc, hr, BLACK, max(3, th * 0.75))
    # face
    fx = hc[0] + f * 0.16 * hr
    blink = (t + ph) % 3.4 < 0.12
    ey = hc[1] - 0.06 * hr
    big_eye = emo in ("surprised", "scared")
    for sgn in (-1, 1):
        ex = fx + sgn * 0.36 * hr
        if blink and not big_eye:
            line(img, (ex - 0.1 * hr, ey), (ex + 0.1 * hr, ey), max(2, th * 0.4))
        elif big_eye:
            circ(img, (ex, ey), 0.2 * hr, WHITE)
            circ(img, (ex, ey), 0.2 * hr, BLACK, 2)
            circ(img, (ex + f * 0.06 * hr, ey), 0.08 * hr, BLACK)
        else:
            circ(img, (ex + f * 0.03 * hr, ey), 0.095 * hr, BLACK)
        if female and not big_eye:
            line(img, (ex + sgn * 0.1 * hr, ey - 0.02 * hr), (ex + sgn * 0.22 * hr, ey - 0.12 * hr), max(2, th * 0.3))
        by = ey - (0.46 if emo in ("surprised", "scared", "excited") else 0.3) * hr
        tilt_b = {"angry": (0.14, -0.1), "sad": (-0.12, 0.1), "scared": (-0.12, 0.08), "curious": (0.0, 0.0)}.get(emo, (0.0, 0.0))
        inner_dy, outer_dy = (tilt_b[0] * hr * 1.0, tilt_b[1] * hr * 1.0) if emo != "curious" else (0, 0)
        if emo == "curious" and sgn == 1:
            by -= 0.14 * hr
        if emo == "angry":
            line(img, (ex - sgn * 0.2 * hr, by + 0.12 * hr), (ex + sgn * 0.2 * hr, by - 0.08 * hr), max(2, th * 0.45))
        elif emo in ("sad", "scared"):
            line(img, (ex - sgn * 0.2 * hr, by - 0.1 * hr), (ex + sgn * 0.2 * hr, by + 0.08 * hr), max(2, th * 0.45))
        else:
            line(img, (ex - 0.2 * hr, by), (ex + 0.2 * hr, by - (0.04 * hr if sgn > 0 else 0)), max(2, th * 0.45))
    my = hc[1] + 0.44 * hr
    op = mouth
    wth = max(2, th * 0.45)
    if op > 0.1:
        ell(img, (fx, my), (0.2 * hr + 0.08 * hr * op, 0.04 * hr + 0.22 * hr * op), 0, 0, 360, (40, 40, 140))
        ell(img, (fx, my), (0.2 * hr + 0.08 * hr * op, 0.04 * hr + 0.22 * hr * op), 0, 0, 360, BLACK, wth)
    elif emo in ("happy", "excited"):
        ell(img, (fx, my - 0.06 * hr), (0.28 * hr, 0.2 * hr), 0, 15, 165, BLACK, wth)
    elif emo in ("sad", "scared"):
        ell(img, (fx, my + 0.12 * hr), (0.22 * hr, 0.14 * hr), 0, 195, 345, BLACK, wth)
    elif emo == "surprised":
        circ(img, (fx, my), 0.11 * hr, BLACK, wth)
    elif emo == "angry":
        line(img, (fx - 0.2 * hr, my + 0.03 * hr), (fx + 0.2 * hr, my - 0.03 * hr), wth)
    else:
        line(img, (fx - 0.15 * hr, my), (fx + 0.15 * hr, my), wth)
    # accessories
    if acc == "beard":
        poly(img, [(hc[0] + hr * 0.95 * math.cos(math.radians(a)), hc[1] + hr * 0.95 * math.sin(math.radians(a))) for a in range(15, 166, 10)] +
             [(hc[0] + f * 0.05 * hr, hc[1] + 1.55 * hr)], (115, 115, 125), BLACK, 2)
        # redraw mouth on top
        line(img, (fx - 0.15 * hr, my), (fx + 0.15 * hr, my), wth)
    elif acc == "glasses":
        for sgn in (-1, 1):
            circ(img, (fx + sgn * 0.36 * hr, ey), 0.27 * hr, BLACK, max(2, th * 0.35))
        line(img, (fx - 0.1 * hr, ey), (fx + 0.1 * hr, ey), max(2, th * 0.3))
    elif acc == "crown":
        poly(img, [(hc[0] - 0.7 * hr, hc[1] - 0.8 * hr), (hc[0] - 0.8 * hr, hc[1] - 1.55 * hr), (hc[0] - 0.35 * hr, hc[1] - 1.2 * hr),
                   (hc[0], hc[1] - 1.7 * hr), (hc[0] + 0.35 * hr, hc[1] - 1.2 * hr), (hc[0] + 0.8 * hr, hc[1] - 1.55 * hr), (hc[0] + 0.7 * hr, hc[1] - 0.8 * hr)], COL["gold"], BLACK, 2)
    elif acc == "hat":
        ell(img, (hc[0], hc[1] - 0.75 * hr), (1.4 * hr, 0.22 * hr), 0, 0, 360, COL["brown"])
        rect(img, hc[0] - 0.7 * hr, hc[1] - 1.55 * hr, hc[0] + 0.7 * hr, hc[1] - 0.78 * hr, COL["brown"], BLACK, 2)
        ell(img, (hc[0], hc[1] - 0.75 * hr), (1.4 * hr, 0.22 * hr), 0, 0, 360, BLACK, 2)
    elif acc == "headband":
        line(img, (hc[0] - 0.98 * hr, hc[1] - 0.42 * hr), (hc[0] + 0.98 * hr, hc[1] - 0.42 * hr), max(4, th * 0.9), COL["red"])
    elif acc == "helmet":
        ell(img, (hc[0], hc[1] - 0.15 * hr), (1.12 * hr, 1.1 * hr), 0, 180, 360, COL["stone"])
        ell(img, (hc[0], hc[1] - 0.15 * hr), (1.12 * hr, 1.1 * hr), 0, 180, 360, BLACK, 3)
        line(img, (hc[0] - 1.14 * hr, hc[1] - 0.15 * hr), (hc[0] + 1.14 * hr, hc[1] - 0.15 * hr), max(4, th * 0.8))
    elif acc == "flower":
        for i in range(5):
            a = i * 2 * math.pi / 5
            circ(img, (hc[0] - f * 0.55 * hr + math.cos(a) * 0.2 * hr, hc[1] - 0.95 * hr + math.sin(a) * 0.2 * hr), 0.16 * hr, COL["pink"])
        circ(img, (hc[0] - f * 0.55 * hr, hc[1] - 0.95 * hr), 0.12 * hr, COL["gold"])
    elif acc == "turban":
        ell(img, (hc[0], hc[1] - 0.55 * hr), (1.1 * hr, 0.8 * hr), 0, 180, 360, WHITE)
        ell(img, (hc[0], hc[1] - 0.55 * hr), (1.1 * hr, 0.8 * hr), 0, 180, 360, BLACK, 2)
        circ(img, (hc[0], hc[1] - 0.95 * hr), 0.14 * hr, COL["red"])
    # front arm
    limb_draw(sho, aFp1, aFp2, hand=True)
    return hc, hr


# ------------------------------------------------------------------ scene
def prop_layout(st, props):
    """Har prop ko position do. Zameen wale props neeche, baaqi upar."""
    out = []
    gs, ss = st.ground_slots(), st.sky_slots()
    gi = si = 0
    for name in props[:3]:
        if name not in PROP_TABLE:
            continue
        fn, is_ground, base = PROP_TABLE[name]
        if is_ground and gi < len(gs):
            fx, _ = gs[gi]
            gi += 1
            out.append((name, fn, fx * st.W, st.ground - 4, True, base))
        else:
            if si >= len(ss):
                continue
            fx, fy = ss[si]
            si += 1
            out.append((name, fn, fx * st.W, fy * st.H, False, base))
    return out


class SceneRenderer:
    def __init__(self, st, bg_kind, seed):
        self.st, self.kind, self.seed = st, bg_kind if bg_kind in __import__("vocab").BGS else "white", seed
        self.bg = make_bg(st, self.kind, seed)

    def frame(self, sc, cast, i, t, mouth, total):
        """sc: scene dict, cast: characters list, i: scene index, t: scene ke andar second."""
        st = self.st
        img = self.bg.copy()
        ambient(st, img, self.kind, t, self.seed)
        # props
        for n, (name, fn, x, y, is_g, base) in enumerate(prop_layout(st, sc.get("props", []))):
            k = pop_scale(t - 0.2 - 0.2 * n)
            if k <= 0:
                continue
            u = base * st.s * k * (1.0 if not st.portrait else 1.0)
            yy = y if is_g else y + 7 * math.sin(t * 2 + n)
            fn(img, x, yy, u, t) if name != "chart" else fn(img, x, yy, u, max(0.0, t - 0.2 - 0.2 * n))
        # characters
        fi = min(max(int(sc.get("focus", 0)), 0), len(cast) - 1)
        oi = sc.get("other")
        two = oi is not None and 0 <= int(oi) < len(cast) and int(oi) != fi
        action = sc.get("action", "talk")
        if action == "idle":
            action = "talk"
        emo = sc.get("emotion", "neutral")
        walking = action in ("walk", "run")
        if two:
            xs = [st.char_x(2, 0), st.char_x(2, 1)]
            draw_char(st, img, cast[int(oi)], xs[1], 0.93, sc.get("other_action", "idle") if sc.get("other_action", "idle") != "talk" else "idle",
                      sc.get("other_emotion", emo if emo in ("surprised", "scared", "happy", "sad", "angry") else "curious"), t, 0.0, -1, 2.1)
            draw_char(st, img, cast[fi], xs[0], 1.0, action, emo, t, mouth, 1, 0.0)
        else:
            f = 1 if (walking or i % 2 == 0) else -1
            draw_char(st, img, cast[fi], st.char_x(1, 0), 1.0, action, emo, t, mouth, f, 0.0)
        # label sticker
        lab = (sc.get("label") or "").strip()
        if lab:
            kk = pop_scale(t - 0.35)
            spr = text_sprite(lab.upper(), 44 if not st.portrait else 40, fill=(20, 20, 20), box=(60, 220, 255), max_w=int(st.W * 0.62))
            blit(img, spr, st.W / 2, st.H * (0.09 if not st.portrait else 0.1) + 3 * math.sin(t * 2.5), kk)
        # camera
        z = 1.0 + (0.05 * ease_out(t / 0.4) * -1 + 0.05) if t < 0.4 else 1.0
        kind = i % 4
        zz = 1.0 + 0.07 * min(t / max(total, 1), 1.0) if kind in (0, 2) else 1.07 - 0.07 * min(t / max(total, 1), 1.0)
        zoom = zz * (1.0 + 0.06 * (1 - ease_out(t / 0.35)))
        dxp = (0.012 * st.W * (t / max(total, 1) - 0.5)) * (1 if kind == 2 else -1 if kind == 3 else 0)
        if action == "shock" and t < 0.7:
            dxp += 10 * math.sin(t * 60) * (1 - t / 0.7)
        M = np.float32([[zoom, 0, st.W / 2 * (1 - zoom) + dxp], [0, zoom, st.H * 0.55 * (1 - zoom)]])
        return cv2.warpAffine(img, M, (st.W, st.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
