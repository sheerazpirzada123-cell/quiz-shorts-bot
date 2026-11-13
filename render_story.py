"""script.json -> output.mp4 (Short 1080x1920, 30fps): "parable explainer" 2.5D animation.
Har scene = khaali AI background + uska DEPTH MAP (depth.py) -> camera dolly/orbit mein pixels depth ke hisaab se alag speed se hilte hain (parallax)
+ code se draw ANIMATED characters (rick.py) aur flat-vector PROPS (props.py: murgi, barrel, chalkboard, sikke...) jo usi parallax ke saath chalte hain
+ tilt-shift/DOF, light-shaft, dust, bloom + hard cuts + word-by-word captions + music + sfx.
v4: characters har frame par naye (animation on ones, ANIM_STEP=2 se purana 'on twos'), sprites sub-pixel position par (1px jhatka nahi),
awaaz ki smooth energy se gesture, aur HELD props (action 'hold' wale character ke haathon mein) rick.py ke andar draw hote hain."""
import bisect
import faulthandler
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import zlib

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import bgimg
import music
import props
import rick
import voice
from depth import Warper

cv2.setNumThreads(2)
HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
W, H = 1080, 1920
SW, SH = W // 4, H // 4
ANIM_STEP = max(1, int(os.environ.get("ANIM_STEP", "1")))           # 1 = har frame par nayi pose (smooth); 2 = purana 'on twos' (tez render)
YELLOW, WHITE = (255, 214, 40), (255, 255, 255)
IMPACT = {"thud", "gasp", "alarm", "knock", "buzz", "scratch"}      # in sfx par camera ko halka jhatka
FONTS = [os.path.join(HERE, "fonts", "Poppins-Bold.ttf"), "/usr/share/fonts/opentype/montserrat/Montserrat-ExtraBold.otf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]
SUB_SECONDS = 3.6                                                   # video ke aakhri itne seconds follow pop-up dikhta hai
POS_ORDER = {"left": 0, "center": 1, "right": 2}
# shot -> character height (px) jab 1 / 2 / 3 characters hon
SHOT_H = {"wide": (560, 520, 460), "medium": (900, 780, 640), "close": (1900, 1350, 1000)}
SHOT_TOP = {"medium": 0.34, "close": 0.17}                           # sar ka upar wala hissa (frame ka fraction); wide = zameen par (fy=1690)
SLOTS = {1: {"left": 0.32, "center": 0.5, "right": 0.68}, 2: [0.27, 0.73], 3: [0.19, 0.5, 0.81]}
# Jo props haathon mein pakde ja sakte hain: h = prop ki unchai (character H ka hissa), gx/gy = grip point (prop bbox ka fraction, upar-baayen se),
# hy = haathon ki unchai (H-units), fwd = prop ka markaz body se kitna aage. Prop ka asli size sprite se naapa jata hai (props.py nahi badla).
HOLD = {
    "barrel": dict(h=0.34, gx=0.5, gy=0.50, hy=0.40, fwd=0.11),
    "chicken": dict(h=0.26, gx=0.5, gy=0.60, hy=0.39, fwd=0.12),
    "eggs": dict(h=0.17, gx=0.5, gy=0.75, hy=0.37, fwd=0.12),
    "coins": dict(h=0.15, gx=0.5, gy=0.80, hy=0.37, fwd=0.12),
    "moneybag": dict(h=0.28, gx=0.5, gy=0.62, hy=0.39, fwd=0.11),
}
_fonts = {}


def font(sz):
    if sz not in _fonts:
        for f in FONTS:
            try:
                _fonts[sz] = ImageFont.truetype(f, sz)
                break
            except Exception:
                pass
        else:
            _fonts[sz] = ImageFont.load_default()
    return _fonts[sz]


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def back(x):
    x = min(1.0, max(0.0, x)) - 1.0
    return 1 + 2.70158 * x ** 3 + 1.70158 * x ** 2


def quant(t):
    """Animation ka waqt: ANIM_STEP=1 mein bilkul continuous (har frame nayi pose), warna har ANIM_STEP-wi frame par."""
    if ANIM_STEP <= 1:
        return t
    return (int(t * FPS) // ANIM_STEP * ANIM_STEP) / FPS


def blit(frame, spr, cx, cy, scale=1.0, alpha=1.0):
    if scale != 1.0:
        spr = cv2.resize(spr, (max(2, int(spr.shape[1] * scale)), max(2, int(spr.shape[0] * scale))), interpolation=cv2.INTER_LINEAR)
    h, w = spr.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xb <= xa or yb <= ya:
        return
    s = spr[ya - y0:yb - y0, xa - x0:xb - x0]
    a = s[..., 3:4] / 255.0 * alpha
    reg = frame[ya:yb, xa:xb].astype(np.float32)
    frame[ya:yb, xa:xb] = (reg * (1 - a) + s[..., :3] * a).astype(np.uint8)


def blend_rgba(frame, rgb, a, X0, Y0, alpha=1.0):
    """Float rgb (h,w,3) + alpha (h,w) ko frame par (X0,Y0) se milata hai (frame se bahar ka hissa kaat deta hai)."""
    h, w = a.shape
    x0, y0 = int(round(X0)), int(round(Y0))
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xb <= xa or yb <= ya:
        return
    aa = a[ya - y0:yb - y0, xa - x0:xb - x0, None] * alpha
    reg = frame[ya:yb, xa:xb].astype(np.float32)
    frame[ya:yb, xa:xb] = np.clip(reg * (1 - aa) + rgb[ya - y0:yb - y0, xa - x0:xb - x0] * aa, 0, 255).astype(np.uint8)


def place(frame, rgb, a, X0, Y0, ze=1.0, alpha=1.0):
    """Sprite ko SUB-PIXEL position + scale ze par frame mein milata hai (ek hi resample). Pehle position integer pixel par round hoti thi
    => chalte/hilte character mein 1px ka jhatka (jitter) aata tha."""
    h, w = a.shape
    ix, iy = int(math.floor(X0)), int(math.floor(Y0))
    fx_, fy_ = X0 - ix, Y0 - iy
    nw, nh = int(math.ceil(w * ze + fx_)) + 1, int(math.ceil(h * ze + fy_)) + 1
    if nw < 2 or nh < 2 or nw > 4 * W or nh > 4 * H:
        return
    if ix >= W or iy >= H or ix + nw <= 0 or iy + nh <= 0:
        return
    M = np.array([[ze, 0, fx_ + 0.5 * (ze - 1)], [0, ze, fy_ + 0.5 * (ze - 1)]], np.float32)
    rgb2 = cv2.warpAffine(np.ascontiguousarray(rgb, np.float32), M, (nw, nh), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    a2 = cv2.warpAffine(np.ascontiguousarray(a, np.float32), M, (nw, nh), flags=cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    blend_rgba(frame, rgb2, np.clip(a2, 0.0, 1.0), ix, iy, alpha)


# ---------------------------------------------------------------- captions (ek-ek bada word: safed + kaala outline + soft shadow)
_wcache = {}


def word_sprite(word, color, size):
    k = (word, color, size)
    if k in _wcache:
        return _wcache[k]
    if len(_wcache) > 120:
        _wcache.clear()
    f = font(size)
    stroke = max(5, size // 10)
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    l, t, r, b = tmp.textbbox((0, 0), word, font=f, stroke_width=stroke)
    pad = 36
    w, h = r - l + 2 * pad, b - t + 2 * pad
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((pad - l, pad - t + size // 14), word, font=f, fill=(0, 0, 0, 170), stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
    sh = sh.filter(ImageFilter.GaussianBlur(size // 18))
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad - l, pad - t), word, font=f, fill=color + (255,), stroke_width=stroke, stroke_fill=(12, 10, 16, 255))
    out = Image.alpha_composite(sh, im)
    _wcache[k] = np.asarray(out).astype(np.float32)
    return _wcache[k]


def group_sprite(words, emph, size):
    """1-2 words ka caption: har word apne rang mein (key word peela), kaale outline + soft shadow ke saath."""
    sps = [word_sprite(w, YELLOW if tok(w) in emph else WHITE, size) for w in words]
    if len(sps) == 1:
        return sps[0]
    gap, pad = int(size * 0.26), 36
    wsum = sum(sp.shape[1] for sp in sps) - 2 * pad * (len(sps) - 1) + gap * (len(sps) - 1)
    hmax = max(sp.shape[0] for sp in sps)
    out = np.zeros((hmax, wsum, 4), np.float32)
    x = 0
    for sp in sps:
        h, w = sp.shape[:2]
        y0 = (hmax - h) // 2
        reg = out[y0:y0 + h, x:x + w]
        a = sp[..., 3:4] / 255.0
        out[y0:y0 + h, x:x + w, :3] = reg[..., :3] * (1 - a) + sp[..., :3] * a
        out[y0:y0 + h, x:x + w, 3] = np.maximum(reg[..., 3], sp[..., 3])
        x += w - 2 * pad + gap
    return out


def caption_groups(words):
    """Words ko 1-2 ke tukdon mein todta hai (punctuation par ruk jaata hai): [(start, [words])]"""
    groups, cur = [], []
    for w, a_, _ in words:
        if cur and (len(" ".join(x for x, _ in cur)) + len(w) > 13 or len(cur) >= 2):
            groups.append(cur)
            cur = []
        cur.append((w, a_))
        if w[-1:] in ".,?!:;":
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return [(g[0][1], [x for x, _ in g]) for g in groups]


def make_subscribe():
    im = Image.new("RGBA", (780, 230), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 10, 770, 150], radius=70, fill=(215, 20, 25, 255), outline=(255, 255, 255, 255), width=6)
    d.polygon([(70, 45), (70, 115), (130, 80)], fill=(255, 255, 255, 255))
    d.text((165, 80), "SUBSCRIBE", font=font(66), fill=(255, 255, 255, 255), anchor="lm")
    d.rounded_rectangle([150, 168, 630, 220], radius=24, fill=(8, 8, 14, 215))
    d.text((390, 195), "FOLLOW FOR MORE STORIES", font=font(30), fill=YELLOW + (255,), anchor="mm")
    return np.asarray(im).astype(np.float32)


def tok(w):
    return "".join(c for c in w.lower() if c.isalnum() or c == "'")


# ---------------------------------------------------------------- look: halka vignette, bright warm grade, camera, post
def make_vignettes():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.72)) ** 2 + ((yy - H / 2) / (H * 0.66)) ** 2)
    low = np.clip((yy / H - 0.70) / 0.30, 0, 1) ** 1.5
    base = (1 - 0.26 * np.clip(d - 0.35, 0, 1) ** 1.3) * (1 - 0.10 * low)
    strong = (1 - 0.85 * np.clip(d - 0.20, 0, 1) ** 1.15) * (1 - 0.15 * low)
    return np.clip(base, 0, 1)[..., None].astype(np.float32), np.clip(strong, 0, 1)[..., None].astype(np.float32)


def make_lut():
    x = np.linspace(0, 1, 256)
    s = x + 0.10 * np.sin(np.pi * x) * (x - 0.5) * 2                    # halka S-curve
    sh, hi = (0.0, 0.0, 0.012), (0.018, 0.008, -0.012)                  # shadows thode thande, highlights thode garam
    ch = [np.clip(s + sh[c] * (1 - s) ** 2 + hi[c] * s ** 2, 0, 1) for c in range(3)]
    return (np.stack(ch, axis=1) * 255).astype(np.uint8).reshape(256, 1, 3)


def camera(kind, lt, hold, seed):
    """Scene ke cue (anim) ke hisaab se camera: dict(z zoom, dolly depth-wise zoom farq, pan (px), orbit (px, depth ke saath badhta shift)).
    z hamesha >= 1.07 taake parallax mein bg ke kinare na dikhen."""
    p = min(1.0, lt / max(0.1, hold))
    z, dol, px, py, orb = 1.08, 0.0, 0.0, 0.0, 0.0
    if kind == "zoom_in":
        z, dol = 1.07 + 0.13 * (1 - (1 - p) ** 2.2), 0.14 * p
    elif kind == "zoom_out":
        z, dol = 1.20 - 0.12 * ease(p), 0.14 * (1 - p)
    elif kind == "slow_zoom_out":
        z, dol = 1.19 - 0.11 * p, 0.12 * (1 - p)
    elif kind == "push_in":
        z, dol = 1.08 + 0.09 * p, 0.12 * p
    elif kind == "pan_left":                                                # orbit: paas wali cheezein zyada hilti hain
        z, orb, px = 1.10, 70 * (1 - 2 * p), 14 * (1 - 2 * p)
    elif kind == "pan_right":
        z, orb, px = 1.10, -70 * (1 - 2 * p), -14 * (1 - 2 * p)
    elif kind == "shake":
        amp = 8 + 14 * math.exp(-lt * 4)
        z, dol, px, py = 1.10 + 0.04 * p, 0.05, amp * math.sin(lt * 47 + seed), amp * math.cos(lt * 53 + 2 * seed)
    else:                                                                   # drift
        z, dol, orb = 1.09 + 0.04 * p, 0.05 * p, 50 * math.sin(lt * 0.9 + seed)
    px += 3 * math.sin(lt * 1.3 + seed)
    py += 3 * math.cos(lt * 1.1 + seed)
    return dict(z=z, dolly=dol, pan=(px, py), orbit=orb)


def glitch(frame, k, f):
    rnd = np.random.RandomState(f * 7 + 3)
    out = frame.copy()
    sh = int(22 * k)
    out[..., 0] = np.roll(frame[..., 0], sh, axis=1)
    out[..., 2] = np.roll(frame[..., 2], -sh, axis=1)
    for _ in range(6):
        y, h = rnd.randint(0, H - 140), rnd.randint(24, 130)
        out[y:y + h] = np.roll(out[y:y + h], int(rnd.randint(-90, 90) * k), axis=1)
    return out


def make_atmos_masks():
    """Low-res (SW x SH) pre-computed cheezein: tilt-shift mask (upar/neeche soft blur)."""
    y = np.linspace(0, 1, H, dtype=np.float32)
    ts = np.clip(np.maximum((0.13 - y) / 0.13, (y - 0.86) / 0.14), 0, 1) ** 1.4
    return (ts * 0.75)[:, None, None].astype(np.float32)


def atmos(tg, orbit, seed):
    """Low-res light-shaft (garam, dheere hilti dhoop ki kirnein) + dust particles (halki parallax ke saath). (SH,SW,3) float, 0..255 units."""
    yy, xx = np.mgrid[0:SH, 0:SW].astype(np.float32)
    sh = np.zeros((SH, SW), np.float32)
    for k, (x0, wd, amp) in enumerate(((0.12, 0.05, 1.0), (0.38, 0.07, 0.8), (0.66, 0.045, 0.9), (0.92, 0.06, 0.7))):
        cx = (x0 + 0.04 * math.sin(tg * 0.35 + k * 1.9)) * SW + 0.55 * yy                    # tirchi kirn
        tw = 0.8 + 0.2 * math.sin(tg * 0.9 + k * 2.3)
        sh += amp * tw * np.exp(-((xx - cx) / (wd * SW)) ** 2) * np.clip(1.0 - yy / (SH * 0.85), 0, 1)
    light = np.empty((SH, SW, 3), np.float32)
    for c, tint in enumerate((1.0, 0.90, 0.68)):                                              # garam rang
        light[..., c] = sh * 22.0 * tint
    rnd = np.random.RandomState(seed % 997 + 5)
    dust = np.zeros((SH, SW), np.float32)
    for n in range(38):
        lay = 0.3 + 0.7 * rnd.rand()
        x = (rnd.rand() * SW + (6 + 5 * lay) * tg * (1 if n % 2 else -1) * 0.4 - orbit * 0.04 * lay * 4 + 4 * math.sin(tg * 0.7 + n)) % SW
        y = (rnd.rand() * SH - (2.5 + 3 * lay) * tg + 3 * math.sin(tg * 0.5 + n * 2)) % SH
        tw = 0.5 + 0.5 * math.sin(tg * 2.2 + n * 1.3)
        cv2.circle(dust, (int(x), int(y)), 1 if lay < 0.7 else 2, float(0.45 + 0.55 * tw) * (0.5 + 0.5 * lay), -1, cv2.LINE_AA)
    dust = cv2.GaussianBlur(dust, (0, 0), 0.9)
    for c, tint in enumerate((1.0, 0.95, 0.80)):
        light[..., c] += dust * 70.0 * tint
    return light


def post(frame, vig, grain, f, lut, ts, extra, flash=0.0):
    small = cv2.resize(frame, (SW, SH), interpolation=cv2.INTER_AREA).astype(np.float32)
    hi = np.clip(small - 205, 0, None) * 1.25                                 # sirf tez roshni par bloom (garam rang ka)
    glow = cv2.GaussianBlur(hi, (0, 0), 6) + 0.5 * cv2.GaussianBlur(hi, (0, 0), 16)
    glow *= np.array((1.0, 0.94, 0.80), np.float32)
    soft = cv2.resize(cv2.GaussianBlur(small, (0, 0), 2.0), (W, H), interpolation=cv2.INTER_LINEAR)   # tilt-shift ka blur
    layer = cv2.resize(glow * 0.42 + extra, (W, H), interpolation=cv2.INTER_LINEAR)
    base = frame.astype(np.float32)
    out = (base * (1 - ts) + soft * ts + layer) * vig
    out += grain[(f * 37) % 5] + flash
    return cv2.LUT(np.clip(out, 0, 255).astype(np.uint8), lut)


# ---------------------------------------------------------------- actors
def layout_scene(sc, prev_ids, chars, hold):
    """Scene ke cast ko screen par rakhta hai: (character, action, emo, x, fy, H, facing, ...)."""
    cast = sorted(sc["cast"], key=lambda a: POS_ORDER.get(a["pos"], 1))
    n = len(cast)
    shot = sc.get("shot", "medium")
    Hc = SHOT_H[shot][n - 1]
    fy = 1690.0 if shot == "wide" else SHOT_TOP[shot] * H + 0.97 * Hc
    out = []
    for k, a in enumerate(cast):
        if n == 1:
            fx = 0.5 if shot == "close" else SLOTS[1].get(a["pos"], 0.5)
        else:
            fx = SLOTS[n][k]
        d = 1 if a.get("facing", "right") == "right" else -1
        out.append(dict(id=a["id"], ch=chars[a["id"]], action=a["action"], emo=a["emo"], x=fx * W, fy=fy, H=Hc, dir=d,
                        speaker=(sc.get("speaker") == a["id"]), new=a["id"] not in prev_ids, hold=hold,
                        seed=zlib.crc32(a["id"].encode()) % 1000))
    return out


# ---------------------------------------------------------------- props layout (props.py ke items scene mein rakhna)
PROP_K = dict(chicken=1.35, barrel=1.0, chalkboard=1.0, coins=1.15, eggs=1.25, house=1.25, tree=1.2, sign=1.0, moneybag=1.3, graph=1.0, hand=0.0)
PLANE_ROW = {"front": 0.12, "back": -0.07}       # char ki zameen se farq (frame height ka fraction)
BACK_TYPES = {"house", "tree"}                    # inhe default mein peeche rakhte hain (chhota + door)
MOVE_SPEED = {"walk": 1.0, "run": 2.2}


def layout_props(sc, actors, Hc):
    """sc['props'] -> list of dict(type, x, fy, U, plane, dir, action, text, seed, delay, speed). Characters se takrao se bachta hai."""
    out = []
    shot = sc.get("shot", "medium")
    Ub = min(Hc, 640)
    base_fy = actors[0]["fy"] if actors else 1690.0
    if shot == "close":
        base_fy, Ub = 1560.0, 700
    base_fy = min(base_fy, 1740.0)
    taken = [a["x"] for a in actors]
    slots = {"left": 0.17 * W, "center": 0.5 * W, "right": 0.83 * W}
    occupied_ids = set()
    for j, p in enumerate(sc.get("props") or []):
        t, place_, act, txt = p["type"], p.get("place", "right"), p.get("action", "idle"), p.get("text", "")
        seed = zlib.crc32((t + txt + str(j)).encode()) % 1000
        if t == "hand":
            x = {"left": 0.30, "center": 0.5, "right": 0.70}.get(place_, 0.5) * W
            out.append(dict(type=t, x=x, fy=0.30 * H, U=0.42 * W, plane="hand", dir=1, action=act, text=txt, seed=seed, delay=0.0, speed=0.0, d=0.93))
            continue
        plane = "back" if (place_ == "back" or (t in BACK_TYPES and place_ not in ("front",))) else ("front" if place_ == "front" else "side")
        U = Ub * PROP_K.get(t, 1.0) * (0.75 if plane == "back" else 1.0)
        if t == "barrel" and act == "occupied":                              # character barrel ke andar
            cands = [a for a in actors if a["id"] == txt.strip().lower() and a["id"] not in occupied_ids] or \
                    [a for a in actors if a["id"] not in occupied_ids] or actors
            a = min(cands, key=lambda a_: abs(a_["x"] - slots.get(place_, a_["x"])))
            occupied_ids.add(a["id"])
            out.append(dict(type=t, x=a["x"], fy=a["fy"] + 0.012 * a["H"], U=a["H"], plane="front", dir=1, action=act, text="", seed=seed, delay=0.0, speed=0.0))
            continue
        if plane == "front":
            cands = [0.5 * W, 0.24 * W, 0.76 * W]
        else:
            cands = [slots.get(place_, slots["right"])] + [v for k_, v in slots.items() if k_ != place_]
        x = max(cands, key=lambda c_: (min([abs(c_ - tx) for tx in taken] + [W]) >= (0.17 * W if plane != "front" else 0.12 * W)) * 10000
                - cands.index(c_) * 100 + min([abs(c_ - tx) for tx in taken] + [W]) * 0.01)
        taken.append(x)
        fy = base_fy + PLANE_ROW.get(plane, 0.0) * H
        d = 1 if x < W / 2 else -1
        out.append(dict(type=t, x=x, fy=min(fy, 1860.0), U=U, plane=plane, dir=d, action=act, text=txt, seed=seed, delay=0.12 * (j + 1),
                        speed=props.PROPS[t]["speed"] * MOVE_SPEED.get(act, 0.0) if act in MOVE_SPEED else 0.0))
    return out


def assign_held(sc, actors, plist):
    """Jo character 'hold' action mein hai (ya prop mein held_by: "<character id>" likha ho) uske haathon mein sabse qareeb ka holdable prop
    (HOLD mein) de deta hai. Aisa prop alag se draw nahi hota - rick.py usse haathon ke saath draw karta hai.
    plist[j] sc['props'][j] se match karta hai (layout_props har prop ke liye ek entry banata hai)."""
    raw = sc.get("props") or []
    busy = set()

    def pick(p, pr):
        hb = str(pr.get("held_by", "")).strip().lower()
        if hb:
            for k, a in enumerate(actors):
                if a["id"].lower() == hb and k not in busy:
                    return k
        cands = [k for k, a in enumerate(actors) if a["action"] == "hold" and k not in busy]
        if not cands:
            return None
        return min(cands, key=lambda k: abs(actors[k]["x"] - p["x"]))

    for j, p in enumerate(plist):
        pr = raw[j] if j < len(raw) else {}
        if p["type"] not in HOLD or p["action"] == "occupied" or p.get("speed"):
            continue
        k = pick(p, pr)
        if k is None:
            continue
        busy.add(k)
        p["held"] = k
        actors[k]["held"] = j


def shadow(frame, fxs, fys, rw, rh, strength=0.32):
    """Zameen par naram parchhaai (ellipse)."""
    if fys > H + 60 or rw < 2:
        return
    rw, rh = int(rw), max(2, int(rh))
    x0, y0, x1, y1 = int(fxs - rw * 1.6), int(fys - rh * 2.2), int(fxs + rw * 1.6), int(fys + rh * 2.2)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if xb > xa and yb > ya:
        m = np.zeros((y1 - y0, x1 - x0), np.float32)
        cv2.ellipse(m, (int(fxs - x0), int(fys - y0)), (max(1, rw), max(1, rh)), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
        m = cv2.GaussianBlur(m, (0, 0), max(1.0, rh * 0.45))[ya - y0:yb - y0, xa - x0:xb - x0, None] * strength
        frame[ya:yb, xa:xb] = (frame[ya:yb, xa:xb].astype(np.float32) * (1 - m)).astype(np.uint8)


class Renderer:
    def __init__(self, data, info, locs, seed, total):
        self.scenes, self.info, self.seed = data["scenes"], info, seed
        self.chars = {c["id"]: c for c in data["characters"]}
        self.locs = locs
        self.starts = [x["start"] for x in info]
        self.vig_base, self.vig_strong = make_vignettes()
        rng = np.random.RandomState(5)
        self.grain = [(rng.randn(H, W, 1).astype(np.float32) * 1.1) for _ in range(5)]
        self.lut = make_lut()
        self.ts = make_atmos_masks()
        self.sub = make_subscribe()
        self.sub_t0 = max(0.0, total - SUB_SECONDS)
        self.view_k, uses = [], {}
        for sc in self.scenes:                                  # ek location ke baar-baar aane par har baar alag camera angle
            uses[sc["loc"]] = uses.get(sc["loc"], -1) + 1
            self.view_k.append(uses[sc["loc"]])
        self.layouts, self.player, prev = [], [], set()
        for i, sc in enumerate(self.scenes):
            lay = layout_scene(sc, prev if i else set(), self.chars, info[i]["hold"])
            self.layouts.append(lay)
            self.player.append(layout_props(sc, lay, lay[0]["H"]))
            assign_held(sc, lay, self.player[-1])               # hold wale character ke haathon mein prop
            prev = {a["id"] for a in sc["cast"]}
        self._bg = (-1, None, None)
        self._spr, self._pspr, self._hU = {}, {}, {}
        self.groups = [caption_groups(nf["words"]) for nf in info]

    def bg(self, i):
        """Scene ka Warper (bg + depth) + ambient light. Har scene mein ek baar bante hain."""
        if self._bg[0] != i:
            sc = self.scenes[i]
            arr, dep = bgimg.view(self.locs[sc["loc"]], self.view_k[i], sc.get("shot", "medium"))
            low = arr[int(arr.shape[0] * 0.55):].reshape(-1, 3).mean(axis=0) / 255.0          # zameen ka rang -> actors ki light us se milti hai
            amb = tuple(float(v) for v in np.clip(0.82 + 0.30 * low, 0.88, 1.10))
            wp = Warper(arr, dep)
            for a in self.layouts[i]:                                                          # har actor/prop ki zameen wali depth (ek baar)
                a["d"] = float(np.clip(wp.depth_at(a["x"], min(a["fy"], H - 4)), 0.25, 1.0))
            for p in self.player[i]:
                if "d" not in p:
                    p["d"] = float(np.clip(wp.depth_at(p["x"], min(p["fy"], H - 4)), 0.25, 1.0))
            self._bg = (i, wp, amb)
        return self._bg[1], self._bg[2]

    def held_U(self, typ, Hc, p):
        """Held prop ka U (props.render ka size) jisse uski unchai character ki H ka HOLD[typ]['h'] hissa ho. Ek baar probe render se naapta hai."""
        key = (typ, int(Hc))
        if key not in self._hU:
            u = None
            try:
                r = props.render(typ, 400.0, 0.0, dict(dir=1, action=p["action"], text="", seed=p["seed"]))
                if r is not None:
                    al = np.asarray(r[1], np.float32)
                    if al.size and al.max() > 1.5:
                        al = al / 255.0
                    ys = np.where(al.max(axis=1) > 0.08)[0] if al.size else []
                    hb = (int(ys.max()) - int(ys.min()) + 1) if len(ys) else 0
                    if hb > 4:
                        u = 400.0 * HOLD[typ]["h"] * Hc / hb
            except Exception as e:
                print("  held prop probe err:", str(e)[:80])
            self._hU[key] = u
        return self._hU[key]

    def held_spec(self, i, a, lt2):
        """Actor ke haathon mein jo prop hai uska spec (rick.render_char ke liye). Haath shuru se grip par rehte hain; prop delay ke baad pop hota hai."""
        j = a.get("held")
        if j is None:
            return None
        p = self.player[i][j]
        U = self.held_U(p["type"], a["H"], p)
        if not U:
            return None
        tp = lt2 - p["delay"]
        spec = dict(HOLD[p["type"]])
        spec["appear"] = min(1.0, max(0.0, back(tp / 0.32)))

        def rend(scale, U=U, p=p, tp=tp, d=a["dir"]):
            return props.render(p["type"], U * scale, max(0.0, tp), dict(dir=d, action=p["action"], text=p["text"], seed=p["seed"]))

        spec["render"] = rend
        return spec

    def sprite(self, i, k, a, lt2, x):
        """Actor ka sprite (har frame naya; ANIM_STEP=2 par har 2nd frame)."""
        key = (i, k, int(round(lt2 * 1000)))
        if key in self._spr:
            return self._spr[key]
        if len(self._spr) > 8:
            self._spr.clear()
        nf = self.info[i]
        mouth, vis, talk, energy = 0.0, 0, 0.0, 0.0
        if a["speaker"]:
            idx = int((lt2 - nf["env_off"]) * FPS)
            env = nf["env"]
            if 0 <= idx < len(env):
                mouth, vis = float(env[idx]), int(nf["vis"][idx])
                energy = float(np.mean(env[max(0, idx - 9): idx + 1]))      # ~0.3s ka average: haath/sar awaaz ke saath jhatke nahi
            talk = 1.0
        enter = ease(lt2 / 0.45) if a["new"] else 1.0
        held = self.held_spec(i, a, lt2)
        r = rick.render_char(W, H, x, a["fy"], a["H"], a["ch"], a["action"], a["emo"], lt2 + 0.17 * k, mouth, a["dir"], enter, a["seed"],
                             amb=self._bg[2], rim=(0.035, 0.03, 0.02), ls=-1, vis=vis, talk=talk, energy=energy, held=held)
        self._spr[key] = (r, x)
        return self._spr[key]

    def prop_sprite(self, i, j, p, t2):
        key = (i, j, int(round(t2 * 1000)))
        if key in self._pspr:
            return self._pspr[key]
        if len(self._pspr) > 12:
            self._pspr.clear()
        r = props.render(p["type"], p["U"], max(0.0, t2), dict(dir=p["dir"], action=p["action"], text=p["text"], seed=p["seed"]))
        self._pspr[key] = r
        return r

    def draw_actors(self, frame, i, lt, cam):
        wp = self._bg[1]
        for k, a in enumerate(self.layouts[i]):
            x = a["x"]
            walking = a["action"] in ("walk", "run")
            if walking:                                         # asli chalna: speed rick.walk_speed se => paon phisalte nahi
                x += a["dir"] * rick.walk_speed(a["action"]) * a["H"] * (lt - a["hold"] / 2)
            lt2 = quant(lt)
            xr = x - a["dir"] * rick.walk_speed(a["action"]) * a["H"] * (lt - lt2) if walking else x
            res, xs = self.sprite(i, k, a, lt2, xr)
            pop = (0.84 + 0.16 * back(lt / 0.32)) if a["new"] else 1.0
            fxs, fys, sc = wp.project(x, a["fy"], a["d"], cam["z"], cam["dolly"], cam["pan"], cam["orbit"])     # bg jaisi hi parallax
            ze = sc * pop
            shadow(frame, fxs, fys, 0.30 * a["H"] * ze, 0.045 * a["H"] * ze)
            if res is None:
                continue
            rgb, al, sx0, sy0 = res
            place(frame, rgb, al, fxs + (sx0 - xs) * ze, fys + (sy0 - a["fy"]) * ze, ze)

    def draw_props(self, frame, i, lt, cam, planes):
        wp, amb = self._bg[1], self._bg[2]
        amb_a = np.array(amb, np.float32)[None, None, :] * 0.5 + 0.5
        hold = self.info[i]["hold"]
        for j, p in enumerate(self.player[i]):
            if p["plane"] not in planes:
                continue
            if p.get("held") is not None:                                        # haathon mein hai: rick.py draw karta hai
                continue
            t = lt - p["delay"]
            if t < 0:
                continue
            x, fy = p["x"], p["fy"]
            if p["speed"]:
                x += p["dir"] * p["speed"] * p["U"] * (lt - hold / 2)
            if p["type"] == "hand":                                              # upar se utarta hai
                fy = p["fy"] - (1 - ease(t / 0.5)) * 0.95 * H + 6 * math.sin(lt * 2.3)
                x += 10 * math.sin(lt * 1.7)
                pop = 1.0
            else:
                pop = back(t / 0.32)
            if pop <= 0.02:
                continue
            fxs, fys, sc = wp.project(x, fy, p["d"], cam["z"], cam["dolly"], cam["pan"], cam["orbit"])
            ze = sc * pop
            t2 = quant(t)
            res = self.prop_sprite(i, j, p, t2)
            if p["type"] != "hand":
                shadow(frame, fxs, fys, 0.20 * p["U"] * ze * (1.6 if p["type"] in ("house", "chalkboard", "graph") else 1.0), 0.03 * p["U"] * ze, 0.28)
            if res is None:
                continue
            rgb, al, ox, oy = res
            rgb = rgb * amb_a
            place(frame, rgb, al, fxs + ox * ze, fys + oy * ze, ze)

    def frame(self, f):
        tg = f / FPS
        i = max(0, bisect.bisect_right(self.starts, tg + 1e-9) - 1)
        sc, nf = self.scenes[i], self.info[i]
        lt, hold = tg - self.starts[i], max(0.1, nf["hold"])
        last = i == len(self.scenes) - 1
        hook = sc.get("section") == "HOOK"
        cam = camera(sc.get("anim", "push_in"), lt, hold, i)
        # ---- transition (scene ki shuruaat)
        trans = sc.get("transition", "cut") if i > 0 else "flash"
        flash, fade, gl = 0.0, 1.0, 0.0
        if trans == "flash" and lt < 0.30:
            q = lt / 0.30
            flash, cam["z"] = 120.0 * (1 - q) ** 2, cam["z"] * (1 + 0.03 * (1 - q))
        elif trans == "fade" and lt < 0.40:
            fade = ease(lt / 0.40)
        elif trans == "glitch" and lt < 0.28:
            gl = 1 - lt / 0.28
        elif trans == "cut" and lt < 0.18:
            cam["z"] *= 1 + 0.04 * (1 - lt / 0.18) ** 2
        if sc.get("sfx") in IMPACT and 0.10 <= lt < 0.55:                    # impact par halka camera jhatka
            a = 14 * math.exp(-(lt - 0.10) * 8)
            cam["pan"] = (cam["pan"][0] + a * math.sin(lt * 95), cam["pan"][1] + a * math.cos(lt * 83))
        wp, _ = self.bg(i)
        frame = wp.render(cam["z"], cam["dolly"], cam["pan"], cam["orbit"])      # 2.5D parallax
        self.draw_props(frame, i, lt, cam, ("back",))
        self.draw_actors(frame, i, lt, cam)
        self.draw_props(frame, i, lt, cam, ("side", "front", "hand"))
        if gl > 0:
            frame = glitch(frame, gl, f)
        vig = self.vig_base
        if last:                                                             # aakhri scene: vignette dheere dheere gehri
            vig = self.vig_base + (self.vig_strong - self.vig_base) * ease(lt / hold)
        extra = atmos(tg, cam["orbit"], self.seed + i)
        frame = post(frame, vig, self.grain, f, self.lut, self.ts, extra, flash)
        if fade < 1.0:
            frame = (frame.astype(np.float32) * fade).astype(np.uint8)
        # ---- caption: 1-2 words ka group, bold safed + kaala outline (key word peela)
        gs = [g for g in self.groups[i] if g[0] <= lt]
        if gs:
            a_, ws = gs[-1]
            emph = {tok(x) for x in (sc.get("emph") or "").split()} - {""}
            spr = group_sprite(ws, emph, 132 if hook else 116)
            fit = min(1.0, 980 / spr.shape[1])
            pop = (1.0 + 0.12 * max(0.0, 1 - (lt - a_) / 0.10)) * fit
            if hook:
                blit(frame, spr, W / 2 + 5 * math.sin(tg * 61), 0.21 * H + 4 * math.cos(tg * 53), pop)
            else:
                blit(frame, spr, W / 2, 0.70 * H, pop)
        # ---- subscribe/follow pop-up (aakhir mein)
        if tg >= self.sub_t0:
            p = (tg - self.sub_t0) / 0.45
            blit(frame, self.sub, W / 2, 0.20 * H, max(0.05, back(p)) * (1 + 0.025 * math.sin(tg * 6)), min(1.0, p * 3))
        return frame


def create(data, out_path):
    scenes = data["scenes"]
    tmp = tempfile.mkdtemp()
    t_start = time.time()
    seed = zlib.crc32(data.get("topic", "x").encode()) % 100000
    vox, info, total = voice.build(scenes, tmp, FPS)
    # ---- har location ki ek khaali background image (world style har prompt mein: poori film ek jaisi dikhe)
    world = data.get("world", "")
    used = {s["loc"] for s in scenes}
    locs = {}
    for j, l in enumerate(data["locations"]):
        if l["id"] not in used:
            continue
        print(f"[img] location {l['id']}: {l['prompt'][:60]}", flush=True)
        locs[l["id"]] = bgimg.get_location(f"{l['prompt']}, {world}", seed + j * 31)
    # ---- audio mix (voice + music + sfx)
    sub_t0 = max(0.0, total - SUB_SECONDS)
    v44 = np.interp(np.linspace(0, len(vox), int(len(vox) * music.SR / voice.SR), endpoint=False), np.arange(len(vox)), vox).astype(np.float32)
    ev = []
    for i, sc in enumerate(scenes):
        st, trans = info[i]["start"], (sc.get("transition", "cut") if i else "flash")
        ev.append((st + 0.02, "whoosh", 0.40 if trans in ("flash", "glitch") else 0.18))
        if trans == "glitch":
            ev.append((st + 0.02, "buzz", 0.30))
        s = sc.get("sfx", "none")
        if s != "none":
            ev.append((st + (0.05 if s in ("whoosh", "rise") else 0.15), s, 0.9))
        if sc.get("section") == "TWIST" and (i == 0 or scenes[i - 1].get("section") != "TWIST"):
            ev.append((st + 0.05, "thud", 1.0))                              # twist ka dhamaka
    ev.append((sub_t0 + 0.05, "ding", 0.6))
    mixed, credit = music.mix(v44, total, data.get("music_mood", "quirky"), seed, ev)
    audio_path = os.path.join(tmp, "mix.wav")
    music.write_wav(audio_path, mixed)
    print(f"[render] audio ok ({total:.1f}s, {len(ev)} sfx)", flush=True)

    R = Renderer(data, info, locs, seed, total)
    n_frames = int(round(total * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path, "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-b:a", "192k", "-shortest", "-movflags", "+faststart", os.path.abspath(out_path)]
    faulthandler.dump_traceback_later(300, repeat=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last = None
    try:
        for f in range(n_frames):
            try:
                frame = R.frame(f)
            except Exception:
                import traceback
                traceback.print_exc()
                if last is None:
                    raise
                frame = last
            last = frame
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                break
            if f % 90 == 0:
                print(f"[render] frame {f}/{n_frames} ({time.time() - t_start:.0f}s)", flush=True)
        proc.stdin.close()
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        rc = proc.wait()
        faulthandler.cancel_dump_traceback_later()
    if rc != 0:
        sys.exit(f"ERROR: ffmpeg fail (code {rc})")
    print(f"Video created: {out_path} ({total:.1f}s, {len(scenes)} scenes, {time.time() - t_start:.0f}s lagay)")
    if not 50 <= total <= 90:
        print(f"NOTE: video {total:.0f}s ki hai (target 60-80s). Zyada farq ho to VOICE_SPEED badal kar dekho.")
    if total > 179:
        print("WARNING: 3 minute se lamba hai; YouTube ise Short nahi manega")
    return credit


def main():
    if not os.path.exists("script.json"):
        sys.exit("script.json nahi mila (pehle story_gen.py chalayein)")
    data = json.load(open("script.json", encoding="utf-8"))
    credit = create(data, "output.mp4")
    if credit:
        data["description"] = (data.get("description", "") + "\n\n" + credit).strip()
        json.dump(data, open("script.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
