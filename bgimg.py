"""Backgrounds: har LOCATION ki ek khaali (bina characters) 3D-diorama jaisi image (Pollinations, free, key nahi).
Characters upar se code (rick.py) draw karta hai, isliye har scene mein wahi characters dikhte hain.
Ek location ki image ke alag-alag crops/flip se kai scenes banti hain (kam images = tez + ek jaisi duniya).
Image na mile to code se banaya hua fallback environment (zameen + aasman + ghar)."""
import hashlib
import os
import time
import urllib.parse

import cv2
import numpy as np
import requests

W, H = 1080, 1920
STYLE = ("stylized 3D rendered cartoon diorama, clay-and-plastic toy look, Pixar-like soft global illumination, warm sunny daylight, "
         "rich saturated colours, detailed props and buildings, miniature tilt-shift depth of field, clean readable shapes, "
         "large flat open ground in the lower half of the frame, camera at eye level, EMPTY scene with no people and no characters, "
         "vertical 9:16 composition, no text, no letters, no logo, no watermark")
CACHE = "bgcache"
IMG_BUDGET = float(os.environ.get("IMG_BUDGET_SEC", "900"))     # itne seconds ke baad naye images mangna band (fallback use hoga)
_fails, _t0 = 0, None


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
    q = urllib.parse.quote(f"{prompt[:700]}, {STYLE}")
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
    """Fallback: code se banaya cartoon environment (aasman, baadal, pahaadiyan, ghar, patthar ki zameen). BGR return."""
    rnd = np.random.RandomState(seed)
    hy = int(H * rnd.uniform(0.50, 0.55))
    yy = np.arange(H, dtype=np.float32)[:, None]
    sky_top = np.array([235, 190, 120], np.float32) + rnd.randint(-12, 12, 3)       # BGR: neela aasman
    sky_hor = np.array([250, 232, 205], np.float32)
    k = np.clip(yy / hy, 0, 1)
    img = (sky_top[None, None, :] * (1 - k[..., None]) + sky_hor[None, None, :] * k[..., None]) * np.ones((H, W, 3), np.float32)
    for _ in range(6):                                                              # baadal
        cx, cy, s = rnd.randint(0, W), rnd.randint(120, int(hy * 0.8)), rnd.randint(70, 150)
        for dx, dy, r in ((0, 0, s), (-s * 0.8, s * 0.15, s * 0.7), (s * 0.9, s * 0.2, s * 0.65), (s * 0.2, -s * 0.3, s * 0.7)):
            cv2.circle(img, (int(cx + dx), int(cy + dy)), int(r), (255, 255, 255), -1, cv2.LINE_AA)
    xs = np.arange(W, dtype=np.float32)
    for layer, base in enumerate(((170, 190, 120), (130, 175, 95))):                # door ki pahaadiyan
        prof = hy - (150 - layer * 55) * (0.5 + 0.5 * np.sin(xs / (170 - layer * 40) + rnd.rand() * 6)) - 20 * np.sin(xs / 51 + layer)
        img[yy >= prof[None, :]] = np.array(base, np.float32) + rnd.randint(-8, 8, 3)
    ground = np.array([150, 200, 220], np.float32)                                  # zameen (halki patthar)
    g = np.clip((yy - hy) / (H - hy), 0, 1)
    img[hy:] = ground[None, None, :] * (0.78 + 0.28 * g[hy:][..., None]) * np.ones((H - hy, W, 3), np.float32)
    for r in range(14):                                                             # perspective tile lines
        y = hy + (H - hy) * (r / 14.0) ** 1.8
        cv2.line(img, (0, int(y)), (W, int(y)), (120, 165, 185), max(1, int(1 + r * 0.35)), cv2.LINE_AA)
    for c in range(-8, 9):
        cv2.line(img, (W // 2 + c * 38, hy), (W // 2 + c * 260, H), (125, 168, 188), 2, cv2.LINE_AA)
    for _ in range(rnd.randint(2, 4)):                                              # ghar
        bw, bh = rnd.randint(170, 300), rnd.randint(150, 260)
        bx = rnd.randint(30, W - bw - 30)
        by = hy - bh + rnd.randint(-5, 25)
        wall = (rnd.randint(150, 225), rnd.randint(190, 235), rnd.randint(225, 250))
        cv2.rectangle(img, (bx, by), (bx + bw, by + bh), wall, -1)
        cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (50, 40, 60), 4, cv2.LINE_AA)
        roof = (rnd.randint(40, 90), rnd.randint(60, 110), rnd.randint(170, 225))
        cv2.fillPoly(img, [np.array([(bx - 18, by), (bx + bw + 18, by), (bx + bw // 2, by - bh * 0.45)], np.int32)], roof)
        for wx in range(bx + 30, bx + bw - 40, 70):
            for wy in range(by + 25, by + bh - 50, 75):
                cv2.rectangle(img, (wx, wy), (wx + 36, wy + 46), (235, 200, 140), -1)
                cv2.rectangle(img, (wx, wy), (wx + 36, wy + 46), (50, 40, 60), 3)
    for _ in range(rnd.randint(1, 3)):                                              # ped
        tx, ty = rnd.randint(40, W - 40), hy + rnd.randint(-6, 14)
        cv2.rectangle(img, (tx - 9, ty - 60), (tx + 9, ty), (50, 80, 120), -1)
        cv2.circle(img, (tx, ty - 95), 55, (70, 160, 80), -1, cv2.LINE_AA)
    img = cv2.GaussianBlur(img, (0, 0), 1.3)
    return np.clip(img, 0, 255).astype(np.uint8)


def tiltshift(img):
    """Miniature/3D look: upar-neeche ke kinare halke blur (beech saaf)."""
    h = img.shape[0]
    blur = cv2.GaussianBlur(img, (0, 0), max(3.0, h / 240))
    y = np.linspace(0, 1, h, dtype=np.float32)
    m = np.clip(np.maximum((0.20 - y) / 0.20, (y - 0.90) / 0.10), 0, 1) ** 1.3
    m = (m * 0.85)[:, None, None]
    return (img.astype(np.float32) * (1 - m) + blur.astype(np.float32) * m).astype(np.uint8)


def grade(img):
    """Bright, saaf, saturated cartoon grade (BGR): halka contrast + saturation, garam highlights."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(6, 8)).apply(lab[..., 0])
    f = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR).astype(np.float32) / 255.0
    g = f.mean(axis=2, keepdims=True)
    f = g + (f - g) * 1.14
    f = 0.5 + (f - 0.5) * 1.06
    L = f.mean(axis=2, keepdims=True)
    hi = np.array([0.97, 1.01, 1.05], np.float32)         # garam highlights (BGR)
    f = f * (1 + (hi - 1) * L * 0.6)
    return np.clip(f * 255, 0, 255).astype(np.uint8)


def get_location(prompt, seed):
    """Ek location ki khaali background image (BGR, graded + tilt-shift). Pollinations -> na mile to procedural."""
    img = fetch(prompt, seed)
    if img is None:
        print("  -> fallback procedural bg", flush=True)
        img = procedural(seed)
    return tiltshift(grade(img))


# (zoom, x-anchor 0..1, flip): ek hi location ke alag "camera angle" - bottom-anchored taake zameen frame ke neeche rahe
VIEWS = [(1.0, 0.5, False), (1.32, 0.15, False), (1.32, 0.85, True), (1.55, 0.5, False), (1.0, 0.5, True), (1.32, 0.85, False), (1.32, 0.15, True)]


def view(base, k, shot="medium"):
    """base -> frame se ~1.22x bada RGB crop (taake camera zoom/pan/shake kar sake). shot=close par zyada andar."""
    z, ax, flip = VIEWS[k % len(VIEWS)]
    if shot == "close":
        z = max(z, 1.5)
    elif shot == "wide":
        z = min(z, 1.0)
    v = cv2.flip(base, 1) if flip else base
    h, w = v.shape[:2]
    ch, cw = int(h / z), int(w / z)
    y0 = h - ch
    x0 = int((w - cw) * ax)
    v = v[y0:y0 + ch, x0:x0 + cw]
    h, w = v.shape[:2]
    s = max(W * 1.22 / w, H * 1.22 / h)
    v = cv2.resize(v, (int(w * s), int(h * s)), interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(v, cv2.COLOR_BGR2RGB)
