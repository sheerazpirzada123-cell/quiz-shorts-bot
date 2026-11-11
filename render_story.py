"""script.json -> output.mp4 (Short 1080x1920, 30fps): "parable explainer" 2D animation.
Har scene = 3D-diorama background (khaali) + code se draw hue ANIMATED characters (rick.py: chalna, ishare, expressions, lipsync) +
camera move (zoom/pan/shake) + transition + word-by-word captions (bada safed text, kaala outline) + music + sfx."""
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
import rick
import voice

cv2.setNumThreads(2)
HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
W, H = 1080, 1920
SW, SH = W // 4, H // 4
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


# ---------------------------------------------------------------- captions (ek-ek bada word: safed + kaala outline + soft shadow)
_wcache = {}


def word_sprite(word, color, size):
    k = (word, color, size)
    if k in _wcache:
        return _wcache[k]
    if len(_wcache) > 120:
        _wcache.clear()
    f = font(size)
    stroke = max(5, size // 8)
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
    """Scene ke cue (anim) ke hisaab se (zoom, shift_x, shift_y)."""
    p = min(1.0, lt / max(0.1, hold))
    z, dx, dy = 1.0, 0.0, 0.0
    if kind == "zoom_in":
        z = 1.0 + 0.16 * (1 - (1 - p) ** 2.2)
    elif kind == "zoom_out":
        z = 1.16 - 0.16 * ease(p)
    elif kind == "slow_zoom_out":
        z = 1.14 - 0.14 * p
    elif kind == "push_in":
        z = 1.02 + 0.09 * p
    elif kind == "pan_left":
        z, dx = 1.08, 60 * (1 - 2 * p)
    elif kind == "pan_right":
        z, dx = 1.08, -60 * (1 - 2 * p)
    elif kind == "shake":
        amp = 8 + 14 * math.exp(-lt * 4)
        z, dx, dy = 1.06 + 0.04 * p, amp * math.sin(lt * 47 + seed), amp * math.cos(lt * 53 + 2 * seed)
    else:                                                                   # drift
        z, dx = 1.03 + 0.05 * p, 25 * math.sin(lt * 0.8 + seed)
    return z, dx + 3 * math.sin(lt * 1.3 + seed), dy + 3 * math.cos(lt * 1.1 + seed)


def crop(bg, z, dx, dy):
    """Bade bg se frame-size crop. (img, dx, dy) deta hai - dx,dy wahi jo clamp ke baad lage, taake actors bg ke saath chipke rahen."""
    bh, bw = bg.shape[:2]
    mx, my = max(0.0, (bw - W / z) / 2 - 2), max(0.0, (bh - H / z) / 2 - 2)
    dx, dy = max(-mx, min(mx, dx)), max(-my, min(my, dy))
    M = np.array([[z, 0, W / 2 - z * (bw / 2 + dx)], [0, z, H / 2 - z * (bh / 2 + dy)]], np.float32)
    return cv2.warpAffine(bg, M, (W, H), flags=cv2.INTER_LINEAR), dx, dy


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


def post(frame, vig, grain, f, lut, flash=0.0):
    small = cv2.resize(frame, (SW, SH), interpolation=cv2.INTER_AREA).astype(np.float32)
    hi = np.clip(small - 220, 0, None) * 1.2                                  # sirf bahut tez roshni par halka bloom
    glow = cv2.GaussianBlur(hi, (0, 0), 6) + 0.5 * cv2.GaussianBlur(hi, (0, 0), 16)
    layer = cv2.resize(glow * 0.35, (W, H), interpolation=cv2.INTER_LINEAR)
    out = (frame.astype(np.float32) + layer) * vig
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
        self.sub = make_subscribe()
        self.sub_t0 = max(0.0, total - SUB_SECONDS)
        self.view_k, uses = [], {}
        for sc in self.scenes:                                  # ek location ke baar-baar aane par har baar alag camera angle
            uses[sc["loc"]] = uses.get(sc["loc"], -1) + 1
            self.view_k.append(uses[sc["loc"]])
        self.layouts, prev = [], set()
        for i, sc in enumerate(self.scenes):
            self.layouts.append(layout_scene(sc, prev if i else set(), self.chars, info[i]["hold"]))
            prev = {a["id"] for a in sc["cast"]}
        self._bg = (-1, None, None)
        self._spr = {}

    def bg(self, i):
        if self._bg[0] != i:
            sc = self.scenes[i]
            arr = bgimg.view(self.locs[sc["loc"]], self.view_k[i], sc.get("shot", "medium"))
            low = arr[int(arr.shape[0] * 0.55):].reshape(-1, 3).mean(axis=0) / 255.0          # zameen ka rang -> actors ki light us se milti hai
            amb = tuple(float(v) for v in np.clip(0.82 + 0.30 * low, 0.88, 1.10))
            self._bg = (i, arr, amb)
        return self._bg[1], self._bg[2]

    def sprite(self, i, k, a, lt2, x):
        """Actor ka sprite (har 2nd frame par naya = 'animation on twos', speed aadhi)."""
        key = (i, k, int(round(lt2 * FPS)))
        if key in self._spr:
            return self._spr[key]
        if len(self._spr) > 8:
            self._spr.clear()
        nf = self.info[i]
        mouth, vis, talk = 0.0, 0, 0.0
        if a["speaker"]:
            idx = int((lt2 - nf["env_off"]) * FPS)
            if 0 <= idx < len(nf["env"]):
                mouth, vis = float(nf["env"][idx]), int(nf["vis"][idx])
            talk = 1.0
        enter = ease(lt2 / 0.45) if a["new"] else 1.0
        r = rick.render_char(W, H, x, a["fy"], a["H"], a["ch"], a["action"], a["emo"], lt2 + 0.17 * k, mouth, a["dir"], enter, a["seed"],
                             amb=self._bg[2], rim=(0.035, 0.03, 0.02), ls=-1, vis=vis, talk=talk)
        self._spr[key] = (r, x)
        return self._spr[key]

    def draw_actors(self, frame, i, lt, z, dx, dy):
        for k, a in enumerate(self.layouts[i]):
            x = a["x"]
            if a["action"] in ("walk", "run"):                  # asli chalna: speed rick.walk_speed se => paon phisalte nahi
                x += a["dir"] * rick.walk_speed(a["action"]) * a["H"] * (lt - a["hold"] / 2)
            lt2 = (int(lt * FPS) // 2 * 2) / FPS
            xr = x - a["dir"] * rick.walk_speed(a["action"]) * a["H"] * (lt - lt2) if a["action"] in ("walk", "run") else x
            res, xs = self.sprite(i, k, a, lt2, xr)
            pop = (0.84 + 0.16 * back(lt / 0.32)) if a["new"] else 1.0
            ze = z * pop
            fxs, fys = W / 2 + z * (x - W / 2 - dx), H / 2 + z * (a["fy"] - H / 2 - dy)
            # ---- zameen par parchhaai
            if fys < H + 60:
                rw, rh = int(0.30 * a["H"] * ze), int(0.045 * a["H"] * ze)
                x0, y0, x1, y1 = int(fxs - rw * 1.6), int(fys - rh * 2.2), int(fxs + rw * 1.6), int(fys + rh * 2.2)
                xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
                if xb > xa and yb > ya:
                    m = np.zeros((y1 - y0, x1 - x0), np.float32)
                    cv2.ellipse(m, (int(fxs - x0), int(fys - y0)), (max(1, rw), max(1, rh)), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
                    m = cv2.GaussianBlur(m, (0, 0), max(1.0, rh * 0.45))[ya - y0:yb - y0, xa - x0:xb - x0, None] * 0.32
                    frame[ya:yb, xa:xb] = (frame[ya:yb, xa:xb].astype(np.float32) * (1 - m)).astype(np.uint8)
            if res is None:
                continue
            rgb, al, sx0, sy0 = res
            if abs(ze - 1.0) > 1e-3:
                nw, nh = max(2, int(al.shape[1] * ze)), max(2, int(al.shape[0] * ze))
                rgb, al = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LINEAR), cv2.resize(al, (nw, nh), interpolation=cv2.INTER_LINEAR)
            blend_rgba(frame, rgb, al, fxs + (sx0 - xs) * ze, fys + (sy0 - a["fy"]) * ze)

    def frame(self, f):
        tg = f / FPS
        i = max(0, bisect.bisect_right(self.starts, tg + 1e-9) - 1)
        sc, nf = self.scenes[i], self.info[i]
        lt, hold = tg - self.starts[i], max(0.1, nf["hold"])
        last = i == len(self.scenes) - 1
        hook = sc.get("section") == "HOOK"
        z, dx, dy = camera(sc.get("anim", "push_in"), lt, hold, i)
        # ---- transition (scene ki shuruaat)
        trans = sc.get("transition", "cut") if i > 0 else "flash"
        flash, fade, gl = 0.0, 1.0, 0.0
        if trans == "flash" and lt < 0.30:
            q = lt / 0.30
            flash, z = 120.0 * (1 - q) ** 2, z * (1 + 0.03 * (1 - q))
        elif trans == "fade" and lt < 0.40:
            fade = ease(lt / 0.40)
        elif trans == "glitch" and lt < 0.28:
            gl = 1 - lt / 0.28
        elif trans == "cut" and lt < 0.18:
            z *= 1 + 0.04 * (1 - lt / 0.18) ** 2
        if sc.get("sfx") in IMPACT and 0.10 <= lt < 0.55:                    # impact par halka camera jhatka
            a = 14 * math.exp(-(lt - 0.10) * 8)
            dx, dy = dx + a * math.sin(lt * 95), dy + a * math.cos(lt * 83)
        bg, _ = self.bg(i)
        frame, dx, dy = crop(bg, z, dx, dy)
        self.draw_actors(frame, i, lt, z, dx, dy)
        if gl > 0:
            frame = glitch(frame, gl, f)
        vig = self.vig_base
        if last:                                                             # aakhri scene: vignette dheere dheere gehri
            vig = self.vig_base + (self.vig_strong - self.vig_base) * ease(lt / hold)
        frame = post(frame, vig, self.grain, f, self.lut, flash)
        if fade < 1.0:
            frame = (frame.astype(np.float32) * fade).astype(np.uint8)
        # ---- word-by-word caption: ek word, bada, safed (key word peela)
        words = nf["words"]
        started = [k for k, (_, a_, _) in enumerate(words) if a_ <= lt]
        if started:
            k = started[-1]
            w, a_, _ = words[k]
            emph = {tok(x) for x in (sc.get("emph") or "").split()} - {""}
            col = YELLOW if tok(w) in emph else WHITE
            spr = word_sprite(w, col, 150 if hook else 128)
            fit = min(1.0, 960 / spr.shape[1])
            pop = (1.0 + 0.14 * max(0.0, 1 - (lt - a_) / 0.12)) * fit
            if hook:
                blit(frame, spr, W / 2 + 6 * math.sin(tg * 61), 0.21 * H + 5 * math.cos(tg * 53), pop)
            else:
                blit(frame, spr, W / 2, 0.72 * H, pop)
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
