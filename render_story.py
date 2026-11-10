"""script.json -> output.mp4 (Short 1080x1920, 30fps): 3D-style backgrounds + stick-man actors + voice-over + captions.
v2: characters bg ki zameen/perspective par khade hote hain (size match), scene ki light/rang unpar padta hai,
cast shadow, god-rays + dust, cinematic grade, speaker ka asli lipsync, walk/run mein asli movement, scene transitions."""
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
from PIL import Image, ImageDraw, ImageFont

import bgimg
import music
import rick
import voice

cv2.setNumThreads(2)
FPS = 30
W, H = 1080, 1920
SW, SH = W // 4, H // 4
SHOT = {"wide": 0.33, "medium": 0.48, "close": 1.06}     # character ki height / frame
NARRATOR = os.environ.get("NARRATOR_AVATAR", "1") != "0"        # 0 = narrator ka chehra na dikhao
NARR_CH = dict(name="Narrator", shirt="teal", hat="none", hat_color="red", hair_color="black", overalls=False, tie=False,
               glasses=True, mustache=False)
NB_C, NB_R, NB_H = (170, 1610), 120, 600                  # narrator badge: centre, radius, qad
VIEWS = [0.0, -0.5, 0.5, -0.25, 0.25]                      # same jagah ke scenes mein bg ka alag hissa
CLOSE_GK = 0.36                                           # close: head-centre y / frame
PERSP = 1.25                                              # char height ~ (feet_y - horizon) * PERSP
TONE = {
    "day": dict(amb=(1.0, 1.0, 1.0), rim=(1.0, 0.92, 0.75), key=(1.04, 1.0, 0.90), bounce=(0.55, 0.75, 0.45),
                shadow=(0.50, 0.55, 0.72), ray=(255, 236, 190), rays=0.55, lut=((-0.01, 0.0, 0.03), (0.03, 0.015, -0.02))),
    "night": dict(amb=(0.82, 0.88, 1.0), rim=(0.45, 0.62, 1.0), key=(0.92, 0.98, 1.10), bounce=(0.2, 0.3, 0.5),
                  shadow=(0.30, 0.36, 0.58), ray=(150, 185, 255), rays=0.30, lut=((-0.02, 0.0, 0.05), (-0.01, 0.01, 0.04))),
    "sunset": dict(amb=(1.0, 0.88, 0.78), rim=(1.0, 0.66, 0.36), key=(1.15, 0.95, 0.75), bounce=(0.7, 0.45, 0.25),
                   shadow=(0.45, 0.38, 0.58), ray=(255, 172, 100), rays=0.80, lut=((0.02, -0.01, 0.04), (0.05, 0.02, -0.04))),
    "indoor": dict(amb=(1.0, 0.95, 0.88), rim=(1.0, 0.85, 0.6), key=(1.1, 1.0, 0.85), bounce=(0.6, 0.45, 0.3),
                   shadow=(0.50, 0.45, 0.52), ray=(255, 216, 150), rays=0.45, lut=((0.01, 0.0, 0.01), (0.04, 0.02, -0.03))),
}
SFX_AT = {"gasp": 0.2, "thud": 0.1, "punch": 0.1, "bonk": 0.1, "fail": 0.3}
PRIO = {"talk": 0, "point": 1, "angry": 2, "laugh": 3, "celebrate": 3, "shock": 3, "wave": 3, "shrug": 4, "think": 5,
        "hold": 5, "sad": 5, "facepalm": 6, "idle": 7, "walk": 8, "run": 8}
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]


def font(sz):
    for f in FONTS:
        try:
            return ImageFont.truetype(f, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


_word_cache = {}


def word_sprite(w, color=(255, 255, 255)):
    k = (w, color)
    if k not in _word_cache:
        f = font(118)
        tmp = Image.new("RGBA", (10, 10))
        l, t, r, b = ImageDraw.Draw(tmp).textbbox((0, 0), w, font=f, stroke_width=9)
        im = Image.new("RGBA", (r - l + 40, b - t + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((24, 24), w, font=f, fill=(0, 0, 0, 120), stroke_width=9, stroke_fill=(0, 0, 0, 120))
        d.text((20, 20 - t), w, font=f, fill=color + (255,), stroke_width=9, stroke_fill=(0, 0, 0, 255))
        _word_cache[k] = np.asarray(im).astype(np.float32)
    return _word_cache[k]


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


_box_cache = {}


def top_caption(words):
    """Upar ke 2 lines: kaale box + safed text."""
    key = " ".join(words)
    if key in _box_cache:
        return _box_cache[key]
    f = font(50)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if probe.textlength(t, font=f) > 860 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    lines = lines[-2:]
    im = Image.new("RGBA", (W, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        tw = probe.textlength(ln, font=f)
        x0 = (W - tw) / 2
        d.rounded_rectangle([x0 - 12, 8 + i * 68, x0 + tw + 12, 8 + i * 68 + 64], radius=10, fill=(0, 0, 0, 215))
        d.text((x0, 12 + i * 68), ln, font=f, fill=(255, 255, 255, 255))
    arr = np.asarray(im).astype(np.float32)
    if len(_box_cache) > 400:
        _box_cache.clear()
    _box_cache[key] = arr
    return arr


def soft_blob(frame, cx, cy, rx, ry, k, tint):
    """Rang-daar naram parchhai (frame ko multiply karti hai): tint jitna chhota, utna gehra."""
    ry, rx = max(4, int(ry)), max(8, int(rx))
    pad = 30
    m = np.zeros((ry * 2 + pad * 2, rx * 2 + pad * 2), np.float32)
    cv2.ellipse(m, (rx + pad, ry + pad), (rx, ry), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    m = cv2.GaussianBlur(m, (0, 0), max(3, ry * 0.5)) * k
    x0, y0 = int(cx - rx - pad), int(cy - ry - pad)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + m.shape[1]), min(H, y0 + m.shape[0])
    if xb <= xa or yb <= ya:
        return
    mm = m[ya - y0:yb - y0, xa - x0:xb - x0, None]
    mult = 1.0 - mm * (1.0 - np.array(tint, np.float32)[None, None, :])
    frame[ya:yb, xa:xb] = (frame[ya:yb, xa:xb].astype(np.float32) * mult).astype(np.uint8)


def cast_shadow(frame, fx, fy, Hs, ls, tint):
    """Contact shadow (gehri, chhoti) + light se door girta lamba shadow."""
    soft_blob(frame, fx - ls * 0.20 * Hs, fy + 0.006 * Hs, 0.26 * Hs, 0.030 * Hs, 0.55, tint)
    soft_blob(frame, fx, fy + 0.004 * Hs, 0.14 * Hs, 0.020 * Hs, 0.70, tint)


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
    return (1 - 0.36 * np.clip(d - 0.35, 0, 1) ** 1.4)[..., None].astype(np.float32)


def make_lut(tone):
    sh, hi = TONE[tone]["lut"]
    x = np.linspace(0, 1, 256)
    s = x + 0.10 * np.sin(np.pi * x) * (x - 0.5) * 2
    ch = [np.clip(s + sh[c] * (1 - s) ** 2 + hi[c] * s ** 2, 0, 1) for c in range(3)]
    return (np.stack(ch, axis=1) * 255).astype(np.uint8).reshape(256, 1, 3)


def camera(kind, lt, hold, seed):
    p = lt / max(0.1, hold)
    p = 0.5 * p + 0.5 * ease(p)
    z0, z1, px0, px1 = 1.0, 1.0, 0, 0
    if kind == "push_in":
        z0, z1 = 1.0, 1.10
    elif kind == "pull_out":
        z0, z1 = 1.10, 1.0
    elif kind == "pan_left":
        z0, z1, px0, px1 = 1.04, 1.07, 0.7, -0.7
    elif kind == "pan_right":
        z0, z1, px0, px1 = 1.04, 1.07, -0.7, 0.7
    else:
        z0, z1 = 1.02, 1.045
    return z0 + (z1 - z0) * p, px0 + (px1 - px0) * p, 0.08 * math.sin(lt * 0.9 + seed)


def warp(img, z, tx, ty):
    M = np.array([[z, 0, W / 2 - z * W / 2 + tx], [0, z, H / 2 - z * H / 2 + ty]], np.float32)
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def bg_frame(bg, px, py, lt, seed):
    """Bg ka frame-size crop + (shift_x, shift_y): characters ko bhi itna hi hilana hai taake bg se chipke rahein."""
    bh, bw = bg.shape[:2]
    mx, my = (bw - W) / 2, (bh - H) / 2
    dx = px * mx * 0.8 + 3 * math.sin(lt * 1.3 + seed)
    dy = py * my + 3 * math.cos(lt * 1.1 + seed)
    M = np.array([[1, 0, W / 2 - (bw / 2 + dx)], [0, 1, H / 2 - (bh / 2 + dy)]], np.float32)
    return cv2.warpAffine(bg, M, (W, H), flags=cv2.INTER_LINEAR), -dx, -dy


class Light:
    """Per-scene light: sun/window/moon corner se god-rays + dust particles (sab low-res, bloom ke saath upscale hote hain)."""

    def __init__(self, tone, ls, seed):
        T = TONE[tone]
        self.col = np.array(T["ray"], np.float32)
        self.k = T["rays"]
        self.seed = seed
        yy, xx = np.mgrid[0:SH, 0:SW].astype(np.float32)
        sx, sy = SW * (0.5 + 0.62 * ls), -0.06 * SH
        self.theta = np.arctan2(yy - sy, xx - sx)
        self.dist = np.hypot(yy - sy, xx - sx) / SH
        self.fall = np.exp(-self.dist * 1.7)
        self.glow = np.exp(-(self.dist * 2.2) ** 2)
        rnd = np.random.RandomState(seed * 7 + 1)
        self.dust = rnd.rand(26, 5)           # x, y, speed, size, phase

    def layer(self, lt, tg, flicker=1.0):
        beams = (0.5 + 0.5 * np.sin(self.theta * 13 + 0.35 * lt + self.seed)) ** 3
        beams *= 0.6 + 0.4 * np.sin(self.theta * 5.0 - 0.2 * lt + 1.0)
        a = (beams * self.fall * 0.55 + self.glow * 0.45) * self.k * 0.55 * flicker
        out = a[..., None] * self.col[None, None, :]
        dl = np.zeros((SH, SW, 3), np.float32)
        for x, y, sp, sz, ph in self.dust:
            cx = ((x + 0.02 * math.sin(tg * 0.7 + ph * 6) + tg * 0.01 * (sp - 0.5)) % 1.0) * SW
            cy = ((y - tg * (0.015 + 0.03 * sp)) % 1.0) * SH
            cv2.circle(dl, (int(cx), int(cy)), 1 + int(sz * 2.2), tuple(float(v) * 0.10 for v in self.col), -1, cv2.LINE_AA)
        return out + cv2.GaussianBlur(dl, (0, 0), 1.2)


def post(frame, vig, grain, f, add_small, lut, flash=0.0):
    small = cv2.resize(frame, (SW, SH), interpolation=cv2.INTER_AREA).astype(np.float32)
    hi = np.clip(small - 190, 0, None) * 1.4
    glow = cv2.GaussianBlur(hi, (0, 0), 6) + 0.6 * cv2.GaussianBlur(hi, (0, 0), 16)
    layer = cv2.resize(glow * 0.55 + add_small, (W, H), interpolation=cv2.INTER_LINEAR)
    out = frame.astype(np.float32) + layer
    out *= vig
    out += grain[(f * 37) % 5] + flash
    return cv2.LUT(np.clip(out, 0, 255).astype(np.uint8), lut)


def narrator_badge(frame, tg, mouth, vis):
    """Sirf narrator lipsync karta hai: gol badge mein, awaaz ke saath."""
    cx, cy = NB_C
    R = NB_R
    xa, ya, xb, yb = cx - R - 8, cy - R - 8, cx + R + 8, cy + R + 8
    yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    inside = np.clip(R - dist, 0, 1)[..., None]
    ring = (np.clip(R + 6 - dist, 0, 1) - np.clip(R - dist, 0, 1))[..., None]
    reg = frame[ya:yb, xa:xb].astype(np.float32)
    reg = reg * (1 - inside) + np.array((52, 62, 92), np.float32) * inside
    reg = reg * (1 - ring) + 255.0 * ring
    frame[ya:yb, xa:xb] = reg.astype(np.uint8)
    r = rick.render_char(W, H, cx, cy + 0.775 * NB_H, NB_H, NARR_CH, "talk", "neutral", tg + 5.0, mouth, 1, 2.0, 3.3, vis=vis, talk=1.0, look=0.3)
    if r is None:
        return
    rgb, a, x0, y0 = r
    h, w = a.shape
    yy, xx = np.mgrid[y0:y0 + h, x0:x0 + w].astype(np.float32)
    a = a * np.clip(R - np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2), 0, 1)
    reg = frame[y0:y0 + h, x0:x0 + w].astype(np.float32)
    frame[y0:y0 + h, x0:x0 + w] = (reg * (1 - a[..., None]) + rgb * a[..., None]).astype(np.uint8)


class Renderer:
    def __init__(self, data, info, bgs, metas, seed, views=None):
        self.views = views or [0.0] * len(bgs)
        self.chars, self.scenes, self.info, self.bgs, self.metas, self.seed = data["characters"], data["scenes"], info, bgs, metas, seed
        self.starts = [x["start"] for x in info]
        self.vig = make_vignette()
        rng = np.random.RandomState(5)
        self.grain = [(rng.randn(H, W, 1).astype(np.float32) * 1.3) for _ in range(5)]
        self.luts = {t: make_lut(t) for t in TONE}
        self.lights = {}

    def light(self, i, tone, ls):
        if i not in self.lights:
            self.lights = {i: Light(tone, ls, self.seed % 97 + i)}      # sirf current scene yaad rakho
        return self.lights[i]

    def frame(self, f):
        tg = f / FPS
        i = max(0, bisect.bisect_right(self.starts, tg + 1e-9) - 1)
        sc, nf, meta = self.scenes[i], self.info[i], self.metas[i]
        lt = tg - self.starts[i]
        tone = sc.get("tone", "day")
        if tone not in TONE:
            tone = "day"
        T = TONE[tone]
        ls = meta["ls"]
        z, px, py = camera(sc.get("camera", "push_in"), lt, nf["hold"], i)
        px = max(-1.2, min(1.2, px + self.views[i]))
        frame, sdx, sdy = bg_frame(self.bgs[i], px, py, lt, i)
        # ---- characters: bg ki zameen par, perspective size ke saath
        shot = sc.get("shot", "medium")
        cast = sc["cast"][:1] if shot == "close" else sc["cast"]
        n = len(cast)
        pc = {}                                              # pichhle scene ke wahi characters (same jagah) => teleport/re-entry nahi
        if (i > 0 and sc.get("location") is not None and self.scenes[i - 1].get("location") == sc.get("location")
                and shot != "close" and self.scenes[i - 1].get("shot") != "close"):
            pc = {p["who"]: p for p in self.scenes[i - 1]["cast"]}
        ei = int((lt - nf["env_off"]) * FPS)
        speaking = 0 <= ei < len(nf["env"])
        mouth = float(nf["env"][ei]) if speaking else 0.0
        vis = int(nf["vis"][ei]) if speaking and "vis" in nf else 2
        hy = meta["horizon"] * H + sdy
        Hc = SHOT.get(shot, SHOT["medium"]) * H * (0.92 if n >= 3 else 1.0)
        if shot == "close":
            fy0 = CLOSE_GK * H + 0.775 * Hc + sdy
        else:
            fy0 = min(0.93 * H, max(0.70 * H, hy + Hc / PERSP))
        offs = [0.0, -0.014 * H, 0.014 * H]
        plan = []
        for k, c in enumerate(cast):
            fyk = fy0 + (offs[k % 3] if n > 1 and shot != "close" else 0.0)
            sc_k = min(1.15, max(0.86, (fyk - hy) / max(1.0, fy0 - hy))) if (n > 1 and shot != "close") else 1.0
            plan.append((fyk, k, sc_k))
        for fyk, k, sc_k in sorted(plan):                  # door wale pehle
            c = cast[k]
            ch = self.chars[c["who"]]
            act = c["action"]
            d = 1 if c.get("facing", 1) >= 0 else -1
            Hk = Hc * sc_k
            p0 = pc.get(c["who"])
            cont = p0 is not None
            cxn = p0["x"] + (c["x"] - p0["x"]) * ease(lt / 0.5) if cont else c["x"]
            tt = (tg + 5.0 + k * 0.4) if (cont and p0["action"] == act) else (lt + k * 0.4)
            if shot == "close":
                fx = W * (0.5 + (c["x"] - 0.5) * 0.4) + sdx
            else:
                fx = cxn * W + sdx
                sp = rick.walk_speed(act)
                if sp > 0:                                 # walk/run: asli movement (feet slide nahi)
                    fx += d * sp * Hk * (lt - nf["hold"] / 2)
                fx = min(0.92 * W, max(0.08 * W, fx))
            enter = 2.0 if cont else (lt - 0.06 * k) / 0.32
            Hs = Hk * (0.92 + 0.08 * rick.back(enter)) if enter < 1 else Hk
            zi = min(2, int(min(0.999, max(0.0, fx / W)) * 3))
            zc = np.array(meta["zones"][zi], np.float32)
            zn = np.clip(zc / (zc.mean() + 1e-6), 0.8, 1.2)
            expo = float(np.clip(0.80 + 0.45 * zc.mean() / 255.0, 0.85, 1.08))
            amb = tuple(float(v) for v in np.array(T["amb"], np.float32) * (0.62 + 0.38 * zn) * expo)
            if shot != "close":
                cast_shadow(frame, fx, fyk, Hs, ls, T["shadow"])
            r = rick.render_char(W, H, fx, fyk, Hs, ch, act, c["emotion"], tt, 0.0, d, enter,
                                 self.seed % 7 + k * 1.3, amb, tuple(v * 0.10 for v in T["rim"]), ls, 0,
                                 1.0 if act == "talk" else 0.0, 1.0 if n > 1 else 0.3, T["key"], T["bounce"])
            if r is None:
                continue
            rgb, a, x0, y0 = r
            a = a * min(1.0, max(0.0, enter * 4))
            h, w = a.shape
            reg = frame[y0:y0 + h, x0:x0 + w].astype(np.float32)
            frame[y0:y0 + h, x0:x0 + w] = (reg * (1 - a[..., None]) + rgb * a[..., None]).astype(np.uint8)
        # ---- camera zoom + shake + scene-start punch
        shk = 0.0
        if sc.get("sfx") in SFX_AT and 0 <= lt - 0.3 < 0.35:
            shk = 7 * math.exp(-(lt - 0.3) * 9)
        cz = 1.0 + (z - 1.0) * 0.8
        flash = 0.0
        if i > 0 and lt < 0.22:
            q = lt / 0.22
            cz *= 1.0 + 0.035 * (1 - ease(q))
            flash = 10.0 * (1 - q) ** 2
        frame = warp(frame, cz, shk * math.sin(lt * 90), shk * math.cos(lt * 77))
        lg = self.light(i, tone, ls).layer(lt, tg, 0.93 + 0.07 * math.sin(tg * 9.0 + i) if tone == "indoor" else 1.0)
        frame = post(frame, self.vig, self.grain, f, lg, self.luts[tone], flash)
        if NARRATOR:
            narrator_badge(frame, tg, mouth, vis)
        # ---- captions
        seen = [w for w, a_, b_ in nf["words"] if a_ <= lt]
        if seen:
            blit(frame, top_caption(seen[-8:]), W / 2, 255)
            cur = [(w, a_, b_) for w, a_, b_ in nf["words"] if a_ <= lt < b_ + 0.12]
            if cur:
                w, a_, b_ = cur[0]
                pop = 1.0 + 0.28 * max(0.0, 1 - (lt - a_) / 0.11)
                clean = w.strip(".,!?;:\"")
                hot = len(clean) >= 8 or w.endswith(("!", "?"))
                blit(frame, word_sprite(clean, (255, 224, 60) if hot else (255, 255, 255)), W / 2, 1385, pop)
        return frame


def create(data, out_path):
    scenes = data["scenes"]
    tmp = tempfile.mkdtemp()
    t_start = time.time()
    seed = zlib.crc32(data.get("topic", "x").encode()) % 100000
    vox, info, total = voice.build(scenes, tmp, FPS)
    # ---- backgrounds
    # har LOCATION ka bg sirf ek baar banta hai; us jagah ke saare scenes wahi bg (alag hissa) use karte hain => din/raat/jagah consistent
    bgs, metas, views, made, seen = [], [], [], {}, {}
    has_locs = bool(data.get("locations"))
    for i, sc in enumerate(scenes):
        key = sc.get("location", 0) if has_locs else i
        if key not in made:
            print(f"[bg] location {key} ({len(made) + 1}): {sc['bg_prompt'][:60]}", flush=True)
            made[key] = bgimg.get_bg(sc["bg_prompt"], sc.get("tone", "day"), seed + key * 31)
        bgs.append(made[key][0])
        metas.append(made[key][1])
        views.append(VIEWS[seen.get(key, 0) % len(VIEWS)] if has_locs else 0.0)
        seen[key] = seen.get(key, 0) + 1
    # ---- audio mix (voice + soft music + sfx)
    v44 = np.interp(np.linspace(0, len(vox), int(len(vox) * music.SR / voice.SR), endpoint=False), np.arange(len(vox)), vox).astype(np.float32)
    ev = []
    for i, sc in enumerate(scenes):
        st = info[i]["start"]
        ev.append((st + 0.02, "whoosh", 0.35 if i else 0.2))
        ev.append((st + 0.12, "pop", 0.25))
        if sc.get("sfx", "none") != "none":
            ev.append((st + min(info[i]["hold"] * 0.45, 1.4), sc["sfx"], 0.9))
    mixed, credit = music.mix(v44, total, data.get("music_mood", "quirky"), seed, ev)
    audio_path = os.path.join(tmp, "mix.wav")
    music.write_wav(audio_path, mixed)
    print(f"[render] audio ok ({total:.1f}s, {len(ev)} sfx)", flush=True)

    R = Renderer(data, info, bgs, metas, seed, views)
    n_frames = int(round(total * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
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
    if total > 59:
        print("WARNING: 59s se lamba hai; Short shayad Short na rahe")
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
