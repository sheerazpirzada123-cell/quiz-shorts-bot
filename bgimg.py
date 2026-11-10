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


def get_bg(prompt, tone, seed):
    img = fetch(prompt, seed)
    if img is None:
        print("  -> fallback procedural bg")
        img = procedural(tone, seed)
    # cover-resize to slightly larger than frame so camera can move
    h, w = img.shape[:2]
    s = max(W * 1.22 / w, H * 1.22 / h)
    img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_CUBIC)
    # gentle contrast/saturation punch (renders ka 'rich' look)
    f = img.astype(np.float32)
    g = f.mean(axis=2, keepdims=True)
    f = g + (f - g) * 1.12
    f = (f - 128) * 1.06 + 128
    return np.clip(f, 0, 255).astype(np.uint8)
