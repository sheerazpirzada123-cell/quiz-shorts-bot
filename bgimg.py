"""Backgrounds: Pollinations (free, key nahi) se 3D-render jaisi tasveerein; na mil sakein to code se fallback."""
import hashlib
import os
import time
import urllib.parse

import cv2
import numpy as np
import requests

W, H = 1080, 1920
STYLE = ("stylized 3D render, Unreal Engine 5 look, vibrant saturated colors, soft cinematic lighting, depth of field, "
         "clean detailed environment, vertical 9:16, no people, no characters, no text, no watermark, empty open ground in lower third")
CACHE = "bgcache"
TONE_WORDS = {"day": "bright daytime, clear blue sky, sunlight", "night": "nighttime, dark night sky, moonlight, lamps glowing",
              "sunset": "golden hour sunset, warm orange sky, long soft shadows", "indoor": "indoors, interior room, warm lamp light"}


_fails = 0


def fetch(prompt, seed, tries=2):
    global _fails
    if _fails >= 2:      # Pollinations down hai -> baaqi scenes mein waqt zaya nahi
        return None
    if os.environ.get("BG_OFFLINE"):
        return None
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(f"{prompt}{seed}".encode()).hexdigest()[:12]
    path = os.path.join(CACHE, key + ".jpg")
    if os.path.exists(path):
        return cv2.imread(path)
    q = urllib.parse.quote(f"{prompt}, {STYLE}")
    for k in range(tries):
        url = (f"https://image.pollinations.ai/prompt/{q}?width=768&height=1344&seed={seed + k * 17}"
               f"&model=flux&nologo=true&enhance=false")
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 20000:
                img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None and img.shape[0] > 400:
                    cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    _fails = 0
                    return img
        except Exception as e:
            print("  bg fetch err:", str(e)[:80])
        time.sleep(3)
    _fails += 1
    return None


def procedural(tone, seed):
    """Fallback: soft 3D jaisa gradient sky + door pahaadiyan + zameen (RGB banake BGR return)."""
    rnd = np.random.RandomState(seed)
    pal = {"day": ((70, 140, 235), (190, 225, 250), (86, 150, 70)), "night": ((14, 18, 55), (60, 70, 130), (30, 46, 60)),
           "sunset": ((70, 70, 150), (250, 170, 110), (80, 90, 60)), "indoor": ((150, 120, 100), (205, 180, 150), (120, 85, 60))}
    top, hor, gr = pal.get(tone, pal["day"])
    img = np.zeros((H, W, 3), np.float32)
    hy = int(H * 0.55)
    for y in range(hy):
        k = (y / hy) ** 1.3
        img[y] = np.array(top) * (1 - k) + np.array(hor) * k
    for y in range(hy, H):
        k = (y - hy) / (H - hy)
        img[y] = np.array(gr) * (0.85 + 0.25 * k) + np.array(hor) * 0.15 * (1 - k)
    for layer in range(3):
        base = hy - 40 * (3 - layer)
        xs = np.arange(W)
        prof = base - (60 + 40 * layer) * (0.5 + 0.5 * np.sin(xs / (180 - layer * 40) + rnd.rand() * 6)) - 25 * np.sin(xs / 61 + layer)
        shade = np.array(gr) * (0.55 + 0.15 * layer)
        for x in range(0, W):
            y0 = int(prof[x])
            img[y0:hy + 6, x] = shade * 0.8 + np.array(hor) * 0.2 * (1 - layer / 3)
    if tone in ("day", "sunset"):
        for _ in range(4):
            cx, cy = rnd.randint(100, W - 100), rnd.randint(150, hy - 250)
            for _ in range(7):
                cv2.circle(img, (cx + rnd.randint(-110, 110), cy + rnd.randint(-25, 25)), rnd.randint(40, 85), (250, 250, 255), -1)
        img = cv2.GaussianBlur(img, (0, 0), 9)
    elif tone == "night":
        for _ in range(90):
            cv2.circle(img, (rnd.randint(0, W), rnd.randint(0, hy - 200)), rnd.randint(1, 3), (255, 255, 235), -1)
        cv2.circle(img, (780, 330), 70, (240, 240, 225), -1)
    img = cv2.GaussianBlur(img, (0, 0), 2.0)
    return np.clip(img[..., ::-1], 0, 255).astype(np.uint8)


TONE_GRADE = {   # (shadow tint BGR->RGB below, highlight tint, saturation, contrast)
    "day": ((0.93, 1.0, 1.10), (1.06, 1.02, 0.94), 1.10, 1.08),
    "night": ((0.80, 0.92, 1.25), (0.92, 1.0, 1.18), 1.06, 1.12),
    "sunset": ((0.90, 0.92, 1.12), (1.14, 1.0, 0.82), 1.14, 1.10),
    "indoor": ((0.95, 0.95, 1.05), (1.10, 1.03, 0.88), 1.08, 1.08),
}


def grade(img, tone):
    """Cinematic grade (ek baar per scene): local contrast, S-curve, saturation, teal/orange tint, centre pop."""
    sh, hi, sat, con = TONE_GRADE.get(tone, TONE_GRADE["day"])
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(6, 8)).apply(lab[..., 0])
    f = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR).astype(np.float32) / 255.0
    g = f.mean(axis=2, keepdims=True)
    f = g + (f - g) * sat
    f = 0.5 + (f - 0.5) * con
    f = f + 0.12 * np.sin(np.clip(f, 0, 1) * np.pi) * (f - 0.5)            # soft S-curve
    L = np.clip(f.mean(axis=2, keepdims=True), 0, 1)
    shr, hir = np.array(sh[::-1], np.float32), np.array(hi[::-1], np.float32)    # RGB -> BGR
    f = f * (1 + (shr - 1) * (1 - L) * 0.9) * (1 + (hir - 1) * L * 0.9)
    h, w = f.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    pool = np.exp(-(((xx - w / 2) / (w * 0.55)) ** 2 + ((yy - h * 0.72) / (h * 0.30)) ** 2))   # zameen par halka roshni ka daayra
    f = f * (0.94 + 0.12 * pool[..., None])
    return np.clip(f * 255, 0, 255).astype(np.uint8)


def find_horizon(crop):
    """Frame mein zameen/aasmaan ki line (0..1). Row-average rang mein sabse bada badlaav (0.38-0.74 ke beech)."""
    sm = cv2.resize(crop, (108, 192), interpolation=cv2.INTER_AREA).astype(np.float32)[:, 12:96].mean(axis=1)
    sm = np.stack([np.convolve(np.pad(sm[:, c], 3, mode="edge"), np.ones(5) / 5, mode="valid")[:192] for c in range(3)], axis=1)
    k = 6
    diff = np.abs(sm[2 * k:] - sm[:-2 * k]).sum(axis=1)                     # index i <-> row i + k
    ys = (np.arange(len(diff)) + k) / 192.0
    score = diff * (1 - 0.9 * np.abs(ys - 0.56))
    ok = (ys > 0.38) & (ys < 0.74)
    if not ok.any() or diff[ok].max() < 22:
        return 0.56
    return float(ys[ok][np.argmax(score[ok])])


def analyze(crop, seed):
    """Frame-size crop se: horizon, light ki taraf (ls: +1 daayen se), teen hisson ka zameen-rang + roshni."""
    hy = find_horizon(crop)
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    up = g[: int(H * 0.5)]
    l, r = up[:, : W // 2].mean(), up[:, W // 2:].mean()
    ls = 1 if r > l else -1
    if abs(r - l) < 0.04 * max(l, r, 1):
        ls = 1 if seed % 2 else -1
    y0, y1 = int(min(0.9, hy + 0.04) * H), int(0.97 * H)
    zones = []
    for i in range(3):
        z = crop[y0:y1, i * W // 3:(i + 1) * W // 3].reshape(-1, 3).mean(axis=0)[::-1]    # RGB
        zones.append(tuple(float(v) for v in z))
    return dict(horizon=hy, ls=ls, zones=zones, lum=float(g.mean() / 255.0))


def get_bg(prompt, tone, seed):
    """Returns (bg_image RGB, meta). meta: horizon (frame fraction), ls, zones, lum."""
    img = fetch(f"{prompt}, {TONE_WORDS.get(tone, '')}", seed)      # time-of-day lafz har baar, taake din/raat na badle
    if img is None:
        print("  -> fallback procedural bg")
        img = procedural(tone, seed)
    # cover-resize to slightly larger than frame so camera can move
    h, w = img.shape[:2]
    s = max(W * 1.22 / w, H * 1.22 / h)
    img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_CUBIC)
    img = grade(img, tone)
    bh, bw = img.shape[:2]
    oy, ox = (bh - H) // 2, (bw - W) // 2
    meta = analyze(img[oy:oy + H, ox:ox + W], seed)
    print(f"  bg: horizon={meta['horizon']:.2f} light={'right' if meta['ls'] > 0 else 'left'}", flush=True)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB), meta      # RGB (ffmpeg rgb24 + characters RGB)
