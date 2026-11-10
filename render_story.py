"""script.json -> output.mp4 (Short 1080x1920, 30fps): 3D-style backgrounds + stick-man actors + voice-over + word-by-word captions."""
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
SHOT = {"wide": (0.30, 0.80), "medium": (0.50, 0.93), "close": (1.06, 0.36)}   # (height/frame, feet y / frame) ; close: gk = head-centre y / frame
LIGHT = {"day": ((1.0, 1.0, 1.0), (1.0, 0.92, 0.75)), "night": ((0.62, 0.72, 1.0), (0.45, 0.6, 1.0)),
         "sunset": ((1.0, 0.86, 0.76), (1.0, 0.65, 0.35)), "indoor": ((1.0, 0.95, 0.86), (1.0, 0.85, 0.6))}
SFX_AT = {"gasp": 0.2, "thud": 0.1, "punch": 0.1, "bonk": 0.1, "fail": 0.3}
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


def word_sprite(w):
    if w not in _word_cache:
        f = font(118)
        tmp = Image.new("RGBA", (10, 10))
        l, t, r, b = ImageDraw.Draw(tmp).textbbox((0, 0), w, font=f, stroke_width=9)
        im = Image.new("RGBA", (r - l + 40, b - t + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((24, 24), w, font=f, fill=(0, 0, 0, 120), stroke_width=9, stroke_fill=(0, 0, 0, 120))
        d.text((20, 20 - t), w, font=f, fill=(255, 255, 255, 255), stroke_width=9, stroke_fill=(0, 0, 0, 255))
        _word_cache[w] = np.asarray(im).astype(np.float32)
    return _word_cache[w]


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
    """Upar ke 2 lines: kaale box + safed text (reference jaisa)."""
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
        d.rectangle([x0 - 10, 8 + i * 68, x0 + tw + 10, 8 + i * 68 + 64], fill=(0, 0, 0, 215))
        d.text((x0, 12 + i * 68), ln, font=f, fill=(255, 255, 255, 255))
    arr = np.asarray(im).astype(np.float32)
    if len(_box_cache) > 400:
        _box_cache.clear()
    _box_cache[key] = arr
    return arr


def shadow(frame, cx, cy, rx, ry, k=0.45):
    ry = max(4, int(ry))
    rx = max(8, int(rx))
    pad = 30
    m = np.zeros((ry * 2 + pad * 2, rx * 2 + pad * 2), np.float32)
    cv2.ellipse(m, (rx + pad, ry + pad), (rx, ry), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    m = cv2.GaussianBlur(m, (0, 0), max(3, ry * 0.45)) * k
    x0, y0 = int(cx - rx - pad), int(cy - ry - pad)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + m.shape[1]), min(H, y0 + m.shape[0])
    if xb <= xa or yb <= ya:
        return
    mm = m[ya - y0:yb - y0, xa - x0:xb - x0, None]
    frame[ya:yb, xa:xb] = (frame[ya:yb, xa:xb].astype(np.float32) * (1 - mm)).astype(np.uint8)


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
    return (1 - 0.38 * np.clip(d - 0.35, 0, 1) ** 1.4)[..., None].astype(np.float32)


def camera(kind, lt, hold, seed):
    p = lt / max(0.1, hold)
    p = 0.5 * p + 0.5 * ease(p)
    z0, z1, px0, px1, py0, py1 = 1.0, 1.0, 0, 0, 0, 0
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
    z = z0 + (z1 - z0) * p
    px = px0 + (px1 - px0) * p
    return z, px, 0.25 * math.sin(lt * 0.9 + seed)


def warp(img, z, tx, ty, cx=None, cy=None):
    cx = W / 2 if cx is None else cx
    cy = H / 2 if cy is None else cy
    M = np.array([[z, 0, cx - z * cx + tx], [0, z, cy - z * cy + ty]], np.float32)
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def bg_frame(bg, z, px, py, lt, seed):
    bh, bw = bg.shape[:2]
    mx, my = (bw - W) / 2, (bh - H) / 2
    cxs = bw / 2 + px * mx * 0.8 + 3 * math.sin(lt * 1.3 + seed)
    cys = bh / 2 + py * my + 3 * math.cos(lt * 1.1 + seed)
    M = np.array([[z, 0, W / 2 - z * cxs], [0, z, H / 2 - z * cys]], np.float32)
    return cv2.warpAffine(bg, M, (W, H), flags=cv2.INTER_LINEAR)


def post(frame, vig, grain, f):
    small = cv2.resize(frame, (W // 4, H // 4), interpolation=cv2.INTER_AREA).astype(np.float32)
    hi = np.clip(small - 175, 0, None) * 1.6
    bloom = cv2.resize(cv2.GaussianBlur(hi, (0, 0), 9), (W, H), interpolation=cv2.INTER_LINEAR)
    out = frame.astype(np.float32) + bloom * 0.55
    out *= vig
    g = grain[(f * 37) % 5]
    out += g
    return np.clip(out, 0, 255).astype(np.uint8)


def create(data, out_path):
    chars = data["characters"]
    scenes = data["scenes"]
    tmp = tempfile.mkdtemp()
    t_start = time.time()
    seed = zlib.crc32(data.get("topic", "x").encode()) % 100000
    vox, info, total = voice.build(scenes, tmp, FPS)
    # ---- backgrounds
    bgs = []
    for i, sc in enumerate(scenes):
        print(f"[bg] {i + 1}/{len(scenes)}: {sc['bg_prompt'][:60]}", flush=True)
        bgs.append(bgimg.get_bg(sc["bg_prompt"], sc.get("tone", "day"), seed + i * 31))
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

    vig = make_vignette()
    rng = np.random.RandomState(5)
    grain = [(rng.randn(H, W, 1).astype(np.float32) * 1.4) for _ in range(5)]
    n_frames = int(round(total * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-b:a", "192k", "-shortest", "-movflags", "+faststart", os.path.abspath(out_path)]
    faulthandler.dump_traceback_later(300, repeat=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    starts = [x["start"] for x in info]
    try:
        for f in range(n_frames):
            tg = f / FPS
            i = max(k for k in range(len(scenes)) if starts[k] <= tg + 1e-9)
            sc, nf = scenes[i], info[i]
            lt = tg - starts[i]
            tone = sc.get("tone", "day")
            amb, rim = LIGHT.get(tone, LIGHT["day"])
            z, px, py = camera(sc.get("camera", "push_in"), lt, nf["hold"], i)
            frame = bg_frame(bgs[i], 1.0 + 0.0 * z, px, py, lt, i)
            # ---- characters
            hk, gk = SHOT.get(sc.get("shot", "medium"), SHOT["medium"])
            cast = sc["cast"]
            if sc.get("shot") == "close":
                cast = cast[:1]
            ei = int((lt - nf["env_off"]) * FPS)
            speaking = 0 <= ei < len(nf["env"])
            mouth0 = float(nf["env"][ei]) if speaking else 0.0
            order = sorted(range(len(cast)), key=lambda k: cast[k]["x"])
            for k in order:
                c = cast[k]
                ch = chars[c["who"]]
                Hc = hk * H * (0.92 if len(cast) >= 3 else 1.0)
                if sc.get("shot") == "close":
                    fx, fy = W * (0.5 + (c["x"] - 0.5) * 0.4), gk * H + 0.775 * Hc
                else:
                    fx, fy = c["x"] * W, gk * H
                enter = (lt - 0.06 * k) / 0.32
                Hs = Hc * (0.86 + 0.14 * rick.back(enter)) if enter < 1 else Hc
                if sc.get("shot") != "close":
                    shadow(frame, fx, fy + 0.004 * Hs, 0.16 * Hs, 0.028 * Hs)
                r = rick.render_char(W, H, fx, fy, Hs, ch, c["action"], c["emotion"], lt + k * 0.4,
                                     mouth0 if k == 0 else 0.0, c.get("facing", 1), enter, seed % 7 + k * 1.3, amb, tuple(v * 0.16 for v in rim))
                if r is None:
                    continue
                rgb, a, x0, y0 = r
                h, w = a.shape
                reg = frame[y0:y0 + h, x0:x0 + w].astype(np.float32)
                frame[y0:y0 + h, x0:x0 + w] = (reg * (1 - a[..., None]) + rgb * a[..., None]).astype(np.uint8)
            # ---- camera zoom + shake on whole frame
            shk = 0.0
            if sc.get("sfx") in SFX_AT and 0 <= lt - 0.3 < 0.35:
                shk = 14 * math.exp(-(lt - 0.3) * 9)
            cz = 1.0 + (z - 1.0) * 0.5
            frame = warp(frame, cz, shk * math.sin(lt * 90), shk * math.cos(lt * 77))
            frame = post(frame, vig, grain, f)
            # ---- captions
            seen = [w for w, a_, b_ in nf["words"] if a_ <= lt]
            if seen:
                top = top_caption(seen[-8:])
                blit(frame, top, W / 2, 255)
                cur = [(w, a_, b_) for w, a_, b_ in nf["words"] if a_ <= lt < b_ + 0.12]
                if cur:
                    w, a_, b_ = cur[0]
                    pop = 1.0 + 0.28 * max(0.0, 1 - (lt - a_) / 0.11)
                    blit(frame, word_sprite(w.strip(".,!?;:\"")), W / 2, 1385, pop)
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                break
            if f % 90 == 0:
                print(f"[render] frame {f}/{n_frames} ({time.time() - t_start:.0f}s)", flush=True)
        proc.stdin.close()
    finally:
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
