"""Scene images: Pollinations (free, key nahi) se dark-fantasy tasveerein, har scene ki apni.
Na mil sakein to pichli image ka variation, aur wo bhi na ho to code se banaya dark moonlit fallback."""
import hashlib
import os
import time
import urllib.parse

import cv2
import numpy as np
import requests

W, H = 1080, 1920
STYLE = ("polished 2D storybook cartoon animation frame, the same visual language as high-quality hand-drawn YouTube moral-story cartoons, "
         "cute stylized chibi human characters with oversized round heads and compact but clearly drawn full bodies, visible neck shoulders torso arms hands legs and feet, "
         "expressive readable faces with large eyes eyebrows and mouth, clean bold dark-brown/black ink outlines, smooth cel shading with soft gradients, "
         "warm key light, gentle cast shadows under chin and clothing folds, subtle rim highlights on face hair and body, dimensional skin shading, "
         "rich colored clothes with fabric folds and highlights, detailed illustrated environments, warm cinematic daylight, balanced saturated colors, "
         "consistent character proportions and design across scenes, professional 2D animation background art, vertical 9:16 composition, "
         "no text, no letters, no subtitles, no watermark, no logo")
CACHE = "bgcache"
IMG_BUDGET = float(os.environ.get("IMG_BUDGET_SEC", "900"))     # itne seconds ke baad naye images mangna band (fallback use hoga)
_fails, _t0, _last = 0, None, None


def fetch(prompt, seed, tries=3):
    global _fails, _t0
    if os.environ.get("BG_OFFLINE") or _fails >= 3:      # Pollinations down hai -> baaqi scenes mein waqt zaya nahi
        return None
    _t0 = _t0 or time.time()
    if time.time() - _t0 > IMG_BUDGET:
        return None
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(f"{prompt}{seed}".encode()).hexdigest()[:12]
    path = os.path.join(CACHE, key + ".jpg")
    if os.path.exists(path):
        img = cv2.imread(path)
        if img is not None:
            return img
    q = urllib.parse.quote(f"{prompt[:600]}, {STYLE}")
    for k in range(tries):
        url = (f"https://image.pollinations.ai/prompt/{q}?width=768&height=1344&seed={seed + k * 17}"
               f"&model=flux&nologo=true&enhance=false")
        try:
            r = requests.get(url, timeout=75)
            if r.status_code == 200 and len(r.content) > 20000:
                img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None and img.shape[0] > 400:
                    cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    _fails = 0
                    return img
            elif r.status_code == 429:                   # rate limit -> thoda ruk kar dobara
                time.sleep(12 * (k + 1))
                continue
        except Exception as e:
            print("  img fetch err:", str(e)[:80])
        time.sleep(4)
    _fails += 1
    return None


def procedural(seed):
    """Fallback illustrated warm storybook environment. BGR return."""
    rnd = np.random.RandomState(seed)
    top = np.array([170, 205, 238], np.float32)
    hor = np.array([125, 185, 220], np.float32) + rnd.randint(-10, 18, 3)
    hy = int(H * rnd.uniform(0.50, 0.62))
    yy = np.arange(H, dtype=np.float32)[:, None]
    k = np.clip(yy / hy, 0, 1) ** 1.4
    img = (top[None, None, :] * (1 - k[..., None]) + hor[None, None, :] * k[..., None]) * np.ones((H, W, 3), np.float32)
    mx, my = int(rnd.randint(260, 820)), int(rnd.randint(260, 620))
    glow = np.zeros((H, W), np.float32)
    cv2.circle(glow, (mx, my), 95, 1.0, -1, cv2.LINE_AA)
    img += cv2.GaussianBlur(glow, (0, 0), 70)[..., None] * np.array([16, 22, 30], np.float32)
    cv2.circle(img, (mx, my), 80, (245, 238, 218), -1, cv2.LINE_AA)
    xs = np.arange(W, dtype=np.float32)
    for layer in range(3):                                # door se paas: halki -> gehri pahaadiyan
        prof = hy - (170 - layer * 40) * (0.5 + 0.5 * np.sin(xs / (150 - layer * 30) + rnd.rand() * 6)) - 35 * np.sin(xs / 47 + layer * 2) + layer * 70
        shade = np.array([105, 145, 175], np.float32) * (1 - 0.12 * layer)
        img[yy >= prof[None, :]] = shade
    fog = cv2.resize(cv2.GaussianBlur(rnd.rand(H // 8, W // 8).astype(np.float32), (0, 0), 5), (W, H), interpolation=cv2.INTER_CUBIC)
    img += 12 * fog[..., None] * np.array([0.8, 0.9, 1.0], np.float32)
    img = cv2.GaussianBlur(img, (0, 0), 1.5)
    return np.clip(img[..., ::-1], 0, 255).astype(np.uint8)


def variation(img, seed):
    """Image na mile to pichli image ka alag crop (zoom + kabhi flip) taake scene dikhne mein alag lage."""
    v = cv2.flip(img, 1) if seed % 2 else img
    h, w = v.shape[:2]
    z = 1.15 + 0.10 * (seed % 3)
    ch, cw = int(h / z), int(w / z)
    y0 = int((h - ch) * (0.2 + 0.6 * ((seed // 3) % 3) / 2))
    x0 = int((w - cw) * (0.2 + 0.6 * ((seed // 7) % 3) / 2))
    return v[y0:y0 + ch, x0:x0 + cw]


def grade(img):
    """Soft warm storybook grade (BGR): retain rich colors, gentle contrast and clean highlights."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=1.4, tileGridSize=(6, 8)).apply(lab[..., 0])
    f = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR).astype(np.float32) / 255.0
    g = f.mean(axis=2, keepdims=True)
    f = g + (f - g) * 1.04
    f = 0.5 + (f - 0.5) * 1.04
    f = np.clip(f, 0, 1) ** 0.98
    L = f.mean(axis=2, keepdims=True)
    sh = np.array([1.03, 1.00, 0.96], np.float32)         # gentle cool shadows
    hi = np.array([0.98, 1.02, 1.06], np.float32)         # warm soft highlights
    f = f * (1 + (sh - 1) * (1 - L) * 0.45) * (1 + (hi - 1) * L * 0.55)
    return np.clip(f * 255, 0, 255).astype(np.uint8)


def get_bg(prompt, seed):
    """Returns RGB image (frame se ~1.22x bada, taake camera zoom/pan/shake kar sake)."""
    global _last
    img = fetch(prompt, seed)
    if img is not None:
        _last = img
    elif _last is not None:
        print("  -> pichli image ka variation", flush=True)
        img = variation(_last, seed)
    else:
        print("  -> fallback procedural bg", flush=True)
        img = procedural(seed)
    h, w = img.shape[:2]
    s = max(W * 1.22 / w, H * 1.22 / h)
    img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(grade(img), cv2.COLOR_BGR2RGB)
