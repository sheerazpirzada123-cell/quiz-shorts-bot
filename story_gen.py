"""script.json -> output.mp4 (Short 1080x1920, 30fps): dark fantasy / mystery story.
Har scene = ek AI image + camera cue (zoom/shake/pan) + transition (flash/glitch/fade/cut) + word-by-word subtitles (yellow/white, dark box)
+ kinetic text (hook shake, key words) + aakhir mein dramatic vignette, slow zoom-out aur subscribe pop-up."""
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
import voice

cv2.setNumThreads(2)
FPS = 30
W, H = 1080, 1920
SW, SH = W // 4, H // 4
YELLOW, WHITE, DIM = (255, 214, 40), (255, 255, 255), (150, 150, 165)
IMPACT = {"thud", "gasp", "alarm", "knock", "buzz", "scratch"}      # in sfx par camera ko halka jhatka
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]
SUB_SECONDS = 3.8                                                   # video ke aakhri itne seconds subscribe pop-up dikhta hai
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


# ---------------------------------------------------------------- text sprites
_cap = {"key": None, "arr": None}


def caption_sprite(texts, cur, size, maxw):
    """Chunk ke words: bola ja chuka = safed, abhi bol raha = peela, aage wale = dhundhle. Kaale rounded box par."""
    key = (tuple(texts), cur, size, maxw)
    if _cap["key"] == key:
        return _cap["arr"]
    f = font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    space = probe.textlength(" ", font=f)
    wd = [probe.textlength(t, font=f) for t in texts]
    lines, lw = [[]], 0.0
    for k, w in enumerate(wd):
        add = w + (space if lines[-1] else 0)
        if lines[-1] and lw + add > maxw:
            lines.append([k])
            lw = w
        else:
            lines[-1].append(k)
            lw += add
    widths = [sum(wd[k] for k in ln) + space * (len(ln) - 1) for ln in lines]
    lh = int(size * 1.3)
    bw, bh = int(max(widths) + 68), int(lh * len(lines) + 40)
    im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=int(size * 0.36), fill=(8, 8, 14, 205))
    for li, ln in enumerate(lines):
        x, y = (bw - widths[li]) / 2, 20 + li * lh
        for k in ln:
            col = YELLOW if k == cur else (WHITE if k < cur else DIM)
            d.text((x, y), texts[k], font=f, fill=col + (255,), stroke_width=max(2, size // 28), stroke_fill=(0, 0, 0, 255))
            x += wd[k] + space
    arr = np.asarray(im).astype(np.float32)
    _cap["key"], _cap["arr"] = key, arr
    return arr


_wcache = {}


def word_sprite(w, size, color, stroke):
    k = (w, size, color, stroke)
    if k not in _wcache:
        if len(_wcache) > 60:
            _wcache.clear()
        f = font(size)
        tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        l, t, r, b = tmp.textbbox((0, 0), w, font=f, stroke_width=stroke)
        im = Image.new("RGBA", (r - l + 2 * stroke + 40, b - t + 2 * stroke + 40), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((20 + stroke - l, 20 + stroke - t), w, font=f, fill=color + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        _wcache[k] = np.asarray(im).astype(np.float32)
    return _wcache[k]


def make_subscribe():
    im = Image.new("RGBA", (780, 230), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 10, 770, 150], radius=70, fill=(215, 20, 25, 255), outline=(255, 255, 255, 255), width=6)
    d.polygon([(70, 45), (70, 115), (130, 80)], fill=(255, 255, 255, 255))
    d.text((165, 80), "SUBSCRIBE", font=font(66), fill=(255, 255, 255, 255), anchor="lm")
    d.rounded_rectangle([150, 168, 630, 220], radius=24, fill=(8, 8, 14, 215))
    d.text((390, 195), "FOLLOW FOR MORE DARK TALES", font=font(30), fill=YELLOW + (255,), anchor="mm")
    return np.asarray(im).astype(np.float32)


def make_chunks(words, mx=3):
    """Words ko 3-3 ke groups mein (punctuation par bhi tootta hai), taake subtitle chhota aur padhne layak rahe."""
    chunks, cur = [], []
    for k, (w, _, _) in enumerate(words):
        cur.append(k)
        if len(cur) >= mx or w.endswith((".", "!", "?", ",", ";", ":")):
            chunks.append(cur)
            cur = []
    if cur:
        if chunks and len(cur) == 1 and len(chunks[-1]) <= 2:
            chunks[-1] += cur
        else:
            chunks.append(cur)
    return chunks


def tok(w):
    return "".join(c for c in w.lower() if c.isalnum() or c == "'")


# ---------------------------------------------------------------- look: vignette, grade, camera, post
def make_vignettes():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.72)) ** 2 + ((yy - H / 2) / (H * 0.66)) ** 2)
    low = np.clip((yy / H - 0.55) / 0.45, 0, 1) ** 1.5                      # neeche halka andhera: subtitle saaf dikhe
    base = (1 - 0.55 * np.clip(d - 0.30, 0, 1) ** 1.3) * (1 - 0.40 * low)
    strong = (1 - 0.92 * np.clip(d - 0.18, 0, 1) ** 1.15) * (1 - 0.40 * low)
    return np.clip(base, 0, 1)[..., None].astype(np.float32), np.clip(strong, 0, 1)[..., None].astype(np.float32)


def make_lut():
    x = np.linspace(0, 1, 256)
    s = x ** 1.12
    s = s + 0.14 * np.sin(np.pi * s) * (s - 0.5) * 2
    sh, hi = (-0.02, 0.012, 0.045), (0.05, 0.02, -0.04)                    # shadows teal, highlights amber
    ch = [np.clip(s + sh[c] * (1 - s) ** 2 + hi[c] * s ** 2, 0, 1) for c in range(3)]
    return (np.stack(ch, axis=1) * 255).astype(np.uint8).reshape(256, 1, 3)


def camera(kind, lt, hold, seed):
    """Scene ke cue (anim) ke hisaab se (zoom, shift_x, shift_y)."""
    p = min(1.0, lt / max(0.1, hold))
    z, dx, dy = 1.0, 0.0, 0.0
    if kind == "zoom_in":
        z = 1.0 + 0.22 * (1 - (1 - p) ** 2.2)
    elif kind == "zoom_out":
        z = 1.22 - 0.22 * ease(p)
    elif kind == "slow_zoom_out":
        z = 1.18 - 0.18 * p
    elif kind == "push_in":
        z = 1.02 + 0.10 * p
    elif kind == "pan_left":
        z, dx = 1.10, 70 * (1 - 2 * p)
    elif kind == "pan_right":
        z, dx = 1.10, -70 * (1 - 2 * p)
    elif kind == "shake":
        amp = 9 + 16 * math.exp(-lt * 4)
        z, dx, dy = 1.08 + 0.04 * p, amp * math.sin(lt * 47 + seed), amp * math.cos(lt * 53 + 2 * seed)
    else:                                                                   # drift
        z, dx = 1.03 + 0.05 * p, 25 * math.sin(lt * 0.8 + seed)
    return z, dx + 3 * math.sin(lt * 1.3 + seed), dy + 3 * math.cos(lt * 1.1 + seed)


def crop(bg, z, dx, dy):
    """Bade bg se frame-size crop: zoom z + shift (bg ke bahar na jaye)."""
    bh, bw = bg.shape[:2]
    mx, my = max(0.0, (bw - W / z) / 2 - 2), max(0.0, (bh - H / z) / 2 - 2)
    dx, dy = max(-mx, min(mx, dx)), max(-my, min(my, dy))
    M = np.array([[z, 0, W / 2 - z * (bw / 2 + dx)], [0, z, H / 2 - z * (bh / 2 + dy)]], np.float32)
    return cv2.warpAffine(bg, M, (W, H), flags=cv2.INTER_LINEAR)


def glitch(frame, k, f):
    """Glitch transition: RGB channels alag khisakte hain + kuch patties side mein."""
    rnd = np.random.RandomState(f * 7 + 3)
    out = frame.copy()
    sh = int(22 * k)
    out[..., 0] = np.roll(frame[..., 0], sh, axis=1)
    out[..., 2] = np.roll(frame[..., 2], -sh, axis=1)
    for _ in range(6):
        y, h = rnd.randint(0, H - 140), rnd.randint(24, 130)
        out[y:y + h] = np.roll(out[y:y + h], int(rnd.randint(-90, 90) * k), axis=1)
    return out


class Embers:
    """Hawa mein tairte dhool/angaare (low-res add layer, bloom ke saath upscale hota hai)."""

    def __init__(self, seed):
        self.p = np.random.RandomState(seed % 1000 + 5).rand(34, 5)            # x, y, speed, size, phase

    def layer(self, tg):
        dl = np.zeros((SH, SW, 3), np.float32)
        for x, y, sp, sz, ph in self.p:
            cx = ((x + 0.03 * math.sin(tg * 0.6 + ph * 6) + tg * 0.012 * (sp - 0.3)) % 1.0) * SW
            cy = ((y - tg * (0.02 + 0.05 * sp)) % 1.0) * SH
            col = (255, 170, 90) if ph > 0.5 else (170, 200, 255)
            cv2.circle(dl, (int(cx), int(cy)), 1 + int(sz * 2), tuple(float(v) * 0.22 for v in col), -1, cv2.LINE_AA)
        return cv2.GaussianBlur(dl, (0, 0), 1.2)


def post(frame, vig, grain, f, add_small, lut, flash=0.0):
    small = cv2.resize(frame, (SW, SH), interpolation=cv2.INTER_AREA).astype(np.float32)
    hi = np.clip(small - 175, 0, None) * 1.3
    glow = cv2.GaussianBlur(hi, (0, 0), 6) + 0.6 * cv2.GaussianBlur(hi, (0, 0), 16)
    layer = cv2.resize(glow * 0.50 + add_small, (W, H), interpolation=cv2.INTER_LINEAR)
    out = (frame.astype(np.float32) + layer) * vig
    out += grain[(f * 37) % 5] + flash
    return cv2.LUT(np.clip(out, 0, 255).astype(np.uint8), lut)


class Renderer:
    def __init__(self, data, info, bgs, seed, total):
        self.scenes, self.info, self.bgs, self.seed = data["scenes"], info, bgs, seed
        self.starts = [x["start"] for x in info]
        self.chunks = [make_chunks(x["words"]) for x in info]
        self.emph = [{tok(w) for w in (s.get("emph") or "").split()} - {""} for s in self.scenes]
        self.vig_base, self.vig_strong = make_vignettes()
        rng = np.random.RandomState(5)
        self.grain = [(rng.randn(H, W, 1).astype(np.float32) * 1.3) for _ in range(5)]
        self.lut = make_lut()
        self.fx = Embers(seed)
        self.sub = make_subscribe()
        self.sub_t0 = max(0.0, total - SUB_SECONDS)

    def frame(self, f):
        tg = f / FPS
        i = max(0, bisect.bisect_right(self.starts, tg + 1e-9) - 1)
        sc, nf = self.scenes[i], self.info[i]
        lt, hold = tg - self.starts[i], max(0.1, nf["hold"])
        last = i == len(self.scenes) - 1
        hook = sc.get("section") == "HOOK"
        z, dx, dy = camera(sc.get("anim", "push_in"), lt, hold, i)
        # ---- transition (scene ki shuruaat): flash / fade / glitch / cut-punch
        trans = sc.get("transition", "cut") if i > 0 else "flash"
        flash, fade, gl = 0.0, 1.0, 0.0
        if trans == "flash" and lt < 0.30:
            q = lt / 0.30
            flash, z = 150.0 * (1 - q) ** 2, z * (1 + 0.03 * (1 - q))
        elif trans == "fade" and lt < 0.40:
            fade = ease(lt / 0.40)
        elif trans == "glitch" and lt < 0.28:
            gl = 1 - lt / 0.28
        elif trans == "cut" and lt < 0.18:
            z *= 1 + 0.045 * (1 - lt / 0.18) ** 2
        if sc.get("sfx") in IMPACT and 0.10 <= lt < 0.55:                    # impact par halka camera jhatka
            a = 16 * math.exp(-(lt - 0.10) * 8)
            dx, dy = dx + a * math.sin(lt * 95), dy + a * math.cos(lt * 83)
        frame = crop(self.bgs[i], z, dx, dy)
        if gl > 0:
            frame = glitch(frame, gl, f)
        vig = self.vig_base
        if last:                                                             # aakhri scene: vignette dheere dheere gehri
            vig = self.vig_base + (self.vig_strong - self.vig_base) * ease(lt / hold)
        frame = post(frame, vig, self.grain, f, self.fx.layer(tg), self.lut, flash)
        if fade < 1.0:
            frame = (frame.astype(np.float32) * fade).astype(np.uint8)
        # ---- word-by-word subtitles
        words = nf["words"]
        started = [k for k, (_, a_, _) in enumerate(words) if a_ <= lt]
        if started:
            k = started[-1]
            chunk = next(c for c in self.chunks[i] if k in c)
            size, mw = (104, 940) if hook else (80, 920)
            spr = caption_sprite([words[j][0].upper() for j in chunk], chunk.index(k), size, mw)
            pop = 1.0 + 0.10 * max(0.0, 1 - (lt - words[k][1]) / 0.12)
            if hook:                                                         # hook: bada, beech mein, kaanpta hua text
                blit(frame, spr, W / 2 + 7 * math.sin(tg * 61), 0.40 * H + 6 * math.cos(tg * 53), pop)
            else:
                blit(frame, spr, W / 2, 0.69 * H, pop)
        # ---- kinetic text: key word bada peela pop
        if not hook and self.emph[i]:
            for w, a_, b_ in words:
                if tok(w) in self.emph[i] and a_ <= lt < b_ + 0.45:
                    pop = 1 + 0.38 * max(0.0, 1 - (lt - a_) / 0.16)
                    spr = word_sprite(tok(w).upper(), 150, YELLOW, 11)
                    blit(frame, spr, W / 2 + 5 * math.sin(tg * 70), 0.27 * H + 4 * math.cos(tg * 61),
                         min(1.0, 940 / spr.shape[1]) * pop, max(0.0, min(1.0, (b_ + 0.45 - lt) / 0.15)))
                    break
        # ---- subscribe/follow pop-up (aakhir mein)
        if tg >= self.sub_t0:
            p = (tg - self.sub_t0) / 0.45
            blit(frame, self.sub, W / 2, 0.565 * H, max(0.05, back(p)) * (1 + 0.025 * math.sin(tg * 6)), min(1.0, p * 3))
        return frame


def create(data, out_path):
    scenes = data["scenes"]
    tmp = tempfile.mkdtemp()
    t_start = time.time()
    seed = zlib.crc32(data.get("topic", "x").encode()) % 100000
    vox, info, total = voice.build(scenes, tmp, FPS)
    # ---- har scene ki apni image (style_anchor har prompt mein: poori film ek jaisi dikhe)
    anchor = data.get("style_anchor", "")
    bgs = []
    for i, sc in enumerate(scenes):
        print(f"[img] scene {i + 1}/{len(scenes)}: {sc['visual'][:60]}", flush=True)
        bgs.append(bgimg.get_bg(f"{sc['visual']}, {anchor}", seed + i * 31))
    # ---- audio mix (voice + dark music + sfx)
    sub_t0 = max(0.0, total - SUB_SECONDS)
    v44 = np.interp(np.linspace(0, len(vox), int(len(vox) * music.SR / voice.SR), endpoint=False), np.arange(len(vox)), vox).astype(np.float32)
    ev = []
    for i, sc in enumerate(scenes):
        st, trans = info[i]["start"], (sc.get("transition", "cut") if i else "flash")
        ev.append((st + 0.02, "whoosh", 0.45 if trans in ("flash", "glitch") else 0.22))
        if trans == "glitch":
            ev.append((st + 0.02, "buzz", 0.35))
        s = sc.get("sfx", "none")
        if s != "none":
            ev.append((st + (0.05 if s in ("whoosh", "rise") else 0.15), s, 0.9))
        if sc.get("section") == "TWIST" and (i == 0 or scenes[i - 1].get("section") != "TWIST"):
            ev.append((st + 0.05, "thud", 1.0))                              # twist ka dhamaka
    ev.append((sub_t0 + 0.05, "ding", 0.6))
    mixed, credit = music.mix(v44, total, data.get("music_mood", "mysterious"), seed, ev)
    audio_path = os.path.join(tmp, "mix.wav")
    music.write_wav(audio_path, mixed)
    print(f"[render] audio ok ({total:.1f}s, {len(ev)} sfx)", flush=True)

    R = Renderer(data, info, bgs, seed, total)
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
    if not 40 <= total <= 62:
        print(f"NOTE: video {total:.0f}s ki hai (target 45-60s). Zyada farq ho to VOICE_SPEED badal kar dekho.")
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
