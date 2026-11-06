"""Free AI images with automatic fallback (stick-man explainer style).

Order (IMAGE_PROVIDERS env se badal sakte hain):
  1. cloudflare   - FLUX.1-schnell, free daily quota (CF_ACCOUNT_ID + CF_API_TOKEN secrets ho to)
  2. pollinations - anonymous ya POLLINATIONS_API_KEY ke saath
  3. horde        - AI Horde, anonymous aur unlimited (slow, lekin kabhi khatam nahi hota)
Koi provider fail/quota-out ho jaye to agla chalta hai. Sab fail ho to False return hota hai.
"""
import base64
import io
import os
import random
import time
import urllib.parse

import numpy as np
import requests
from PIL import Image

# Reference style: "Mack and Explain In Paint" - ek hi stick man, bada safed sir, detailed hand-drawn props.
STYLE_HEAD = os.environ.get(
    "IMAGE_STYLE_HEAD",
    "Flat 2D stick figure explainer animation frame, hand-drawn in MS Paint style. One main stick man character: "
    "big plain white circular head with thick black outline, two small black dot eyes, expressive eyebrows and a tiny mouth, "
    "thin thick-black-line neck, body, arms and legs, round white mitten hands, no hair.",
)
STYLE_TAIL = os.environ.get(
    "IMAGE_STYLE_TAIL",
    "All objects, props and scenery are richly detailed hand-drawn illustrations with thick black outlines, flat colors and "
    "simple soft shading. {layout} "
    "No text, no letters, no words, no numbers, no watermark.",
)
LAYOUTS = {
    "portrait": "Vertical 9:16 composition, stick man large in the center, props and details above, below and beside him.",
    "landscape": "Wide horizontal 16:9 composition, stick man large in the center, props and details on both sides of him.",
    "square": "Square composition, stick man large in the center, props and details all around him.",
}
# Chhota style (CLIP 77-token limit wale SD models ke liye: scene pehle, style baad mein)
STYLE_SHORT = (
    "flat 2D stick figure cartoon, MS Paint style, big plain white round head, dot eyes, thin black line body, "
    "thick black outlines, flat colors, richly detailed props, no text"
)
HORDE_NEG = "text, letters, words, numbers, watermark, signature, photo, realistic, 3d render, blurry, deformed, extra limbs"

SIZES = {"portrait": (864, 1536), "landscape": (1536, 864)}  # pollinations/horde native size (w, h)
ORDER = [p.strip() for p in os.environ.get("IMAGE_PROVIDERS", "cloudflare,pollinations,horde").split(",") if p.strip()]
CF_STEPS = int(os.environ.get("CF_STEPS", "4"))
HORDE_TIMEOUT = int(os.environ.get("HORDE_TIMEOUT", "420"))  # seconds, per image
MAX_FAILS = 3  # itni image-failures ke baad provider is run mein band

_dead = set()
_fails = {}
_last_call = {}


class QuotaOut(Exception):
    """Provider ka free quota khatam - is run mein dobara try na karo."""


# ------------------------------------------------------------------ prompts
def build_prompt(scene, character="", background="", orient="portrait"):
    parts = [STYLE_HEAD]
    if character:
        parts.append(f"The stick man is {character.strip().rstrip('.')}.")
    parts.append(f"Scene: {scene.strip().rstrip('.')}.")
    if background:
        parts.append(f"Background: {background.strip().rstrip('.')}.")
    parts.append(STYLE_TAIL.format(layout=LAYOUTS.get(orient, LAYOUTS["square"])) if "{layout}" in STYLE_TAIL else STYLE_TAIL)
    return " ".join(parts)


def build_prompt_short(scene, character="", background=""):
    who = f"stick man {character.strip().rstrip('.')}, " if character else "stick man, "
    bg = f", {background.strip().rstrip('.')}" if background else ""
    return f"{who}{scene.strip().rstrip('.')}{bg}. {STYLE_SHORT}"


# ------------------------------------------------------------------ image helpers
def fit_to_aspect(img, w, h):
    """img ko w x h bana do. Aspect thoda alag ho to crop; bohat alag ho to flat background ko edges se extend karo
    (explainer art mein background flat hota hai, isliye extend natural dikhta hai; stick man cut nahi hota)."""
    img = img.convert("RGB")
    ta, ia = w / h, img.width / img.height
    if abs(ta - ia) / ta < 0.04:
        return img.resize((w, h), Image.LANCZOS)
    if ia > ta:  # image zyada chaudi: height barhao (neeche/upar extend)
        nw, nh = w, round(w / ia)
    else:  # image zyada lambi: width barhao (side par extend)
        nw, nh = round(h * ia), h
    small = img.resize((nw, nh), Image.LANCZOS)
    arr = np.asarray(small)
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    x0, y0 = (w - nw) // 2, (h - nh) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = arr
    k = 6  # edge strip ki motai
    if y0 > 0:
        top = np.median(arr[:k], axis=0).astype(np.uint8)  # (nw, 3)
        bot = np.median(arr[-k:], axis=0).astype(np.uint8)
        canvas[:y0, x0:x0 + nw] = top[None, :, :]
        canvas[y0 + nh:, x0:x0 + nw] = bot[None, :, :]
        # corners: edge pixel ka rang
        canvas[:y0, :x0] = top[0]
        canvas[:y0, x0 + nw:] = top[-1]
        canvas[y0 + nh:, :x0] = bot[0]
        canvas[y0 + nh:, x0 + nw:] = bot[-1]
    if x0 > 0:
        left = np.median(arr[:, :k], axis=1).astype(np.uint8)  # (nh, 3)
        right = np.median(arr[:, -k:], axis=1).astype(np.uint8)
        canvas[y0:y0 + nh, :x0] = left[:, None, :]
        canvas[y0:y0 + nh, x0 + nw:] = right[:, None, :]
        canvas[:y0, :x0] = left[0]
        canvas[:y0, x0 + nw:] = right[0]
        canvas[y0 + nh:, :x0] = left[-1]
        canvas[y0 + nh:, x0 + nw:] = right[-1]
    return Image.fromarray(canvas)


def looks_valid(img):
    """Khali/error image reject karo (bilkul flat ya bohat chhoti)."""
    if img.width < 256 or img.height < 256:
        return False
    g = np.asarray(img.convert("L").resize((128, 128)), dtype=np.float32)
    return float(g.std()) > 8.0


def _throttle(name, min_gap):
    wait = _last_call.get(name, 0) + min_gap - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[name] = time.time()


# ------------------------------------------------------------------ providers
def _cloudflare(scene, character, background, w, h, seed, orient):
    acc = os.environ.get("CF_ACCOUNT_ID", "").strip()
    tok = os.environ.get("CF_API_TOKEN", "").strip()
    if not (acc and tok):
        raise QuotaOut("CF secrets not set")
    prompt = build_prompt(scene, character, background, orient="square")[:2000]  # FLUX schnell: square output
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    r = requests.post(url, headers={"Authorization": f"Bearer {tok}"},
                      json={"prompt": prompt, "steps": CF_STEPS, "seed": seed % 2_000_000_000 + 1}, timeout=120)
    if r.status_code != 200:
        txt = r.text[:300]
        if "daily free allocation" in txt or "4006" in txt:
            raise QuotaOut("cloudflare daily free quota finished")
        if r.status_code in (401, 403):
            raise QuotaOut(f"cloudflare auth error {r.status_code} (token/account id check karein)")
        raise RuntimeError(f"HTTP {r.status_code} {txt}")
    raw = base64.b64decode(r.json()["result"]["image"])
    return Image.open(io.BytesIO(raw))


def _pollinations(scene, character, background, w, h, seed, orient):
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    _throttle("pollinations", 0 if key else 16)  # anonymous: ~1 request / 15 sec
    prompt = build_prompt(scene, character, background, orient=orient)
    q = urllib.parse.quote(prompt)
    model = "flux" if _fails.get("poll_try", 0) < 2 else "turbo"
    if key:
        url = f"https://gen.pollinations.ai/image/{q}?model={model}&width={w}&height={h}&seed={seed}&nologo=true&enhance=false"
        headers = {"Authorization": f"Bearer {key}"}
    else:
        url = (f"https://image.pollinations.ai/prompt/{q}?width={w}&height={h}&seed={seed}"
               f"&model={model}&nologo=true&private=true&enhance=false")
        headers = {}
    r = requests.get(url, headers=headers, timeout=180)
    if r.status_code == 429:
        time.sleep(16)
        raise RuntimeError("HTTP 429 (rate limit)")
    if r.status_code in (401, 402, 403):
        raise QuotaOut(f"pollinations HTTP {r.status_code} (key/credits)")
    if r.status_code != 200 or len(r.content) < 10_000:
        raise RuntimeError(f"HTTP {r.status_code}")
    return Image.open(io.BytesIO(r.content))


_horde_models = None


def _horde_pick_models(base, hdr):
    """Jin SDXL models par abhi worker maujood hain unme se sabse tez wale (warna None = koi bhi)."""
    global _horde_models
    if _horde_models is not None:
        return _horde_models or None
    try:
        r = requests.get(f"{base}/status/models?type=image&min_count=1", headers=hdr, timeout=30)
        rows = [m for m in r.json() if m.get("count", 0) > 0 and "xl" in m.get("name", "").lower()
                and "inpaint" not in m["name"].lower()]
        rows.sort(key=lambda m: (m.get("eta", 9999), -m.get("count", 0)))
        _horde_models = [m["name"] for m in rows[:3]]
    except Exception:  # noqa: BLE001
        _horde_models = []
    return _horde_models or None


def _horde(scene, character, background, w, h, seed, orient):
    base = "https://aihorde.net/api/v2"
    hdr = {"apikey": os.environ.get("HORDE_API_KEY", "").strip() or "0000000000",
           "Client-Agent": "shorts-bot:1.0:github-actions", "Content-Type": "application/json"}
    W = max(384, min(1024, round(w / 64) * 64))
    H = max(384, min(1024, round(h / 64) * 64))
    if W * H > 1024 * 1024:  # anonymous limit ~1MP
        s = (1024 * 1024 / (W * H)) ** 0.5
        W, H = round(W * s / 64) * 64, round(H * s / 64) * 64
    body = {
        "prompt": build_prompt_short(scene, character, background) + " ### " + HORDE_NEG,
        "params": {"sampler_name": "k_euler_a", "cfg_scale": 6.5, "width": W, "height": H, "steps": 25, "n": 1,
                   "seed": str(seed)},
        "nsfw": False, "censor_nsfw": True, "slow_workers": True, "r2": True,
    }
    models = _horde_pick_models(base, hdr)
    if models:
        body["models"] = models
    r = requests.post(f"{base}/generate/async", headers=hdr, json=body, timeout=60)
    if r.status_code not in (200, 202):
        raise RuntimeError(f"horde submit HTTP {r.status_code} {r.text[:200]}")
    job = r.json()["id"]
    t0 = time.time()
    while time.time() - t0 < HORDE_TIMEOUT:
        time.sleep(6)
        c = requests.get(f"{base}/generate/check/{job}", timeout=30).json()
        if c.get("faulted"):
            raise RuntimeError("horde job faulted")
        if c.get("is_possible") is False:
            raise RuntimeError("horde: no worker available for this request")
        if c.get("done"):
            break
    else:
        requests.delete(f"{base}/generate/status/{job}", timeout=30)
        raise RuntimeError(f"horde timeout {HORDE_TIMEOUT}s")
    st = requests.get(f"{base}/generate/status/{job}", timeout=60).json()
    gen = (st.get("generations") or [{}])[0]
    if gen.get("censored") or not gen.get("img"):
        raise RuntimeError("horde returned censored/empty image")
    img_r = requests.get(gen["img"], timeout=120)
    img_r.raise_for_status()
    return Image.open(io.BytesIO(img_r.content))


PROVIDERS = {"cloudflare": _cloudflare, "pollinations": _pollinations, "horde": _horde}


# ------------------------------------------------------------------ main entry
def fetch_image(scene, path, character="", background="", seed=None, orient="portrait"):
    """True agar image save ho gayi, warna False. orient: 'portrait' (Short) ya 'landscape' (long video)."""
    w, h = SIZES[orient]
    out_w, out_h = (1080, 1920) if orient == "portrait" else (1920, 1080)
    for name in ORDER:
        if name in _dead or name not in PROVIDERS:
            continue
        tries = 3 if name != "horde" else 2
        for attempt in range(tries):
            # Pehli koshish mein video ka common seed (character ek jaisa rahe), retry par naya seed
            s = seed if (seed is not None and attempt == 0) else random.randint(1, 10**7)
            _fails["poll_try"] = attempt
            try:
                img = PROVIDERS[name](scene, character, background, w, h, s, orient)
                img.load()
                img = fit_to_aspect(img, out_w, out_h)
                if not looks_valid(img):
                    raise RuntimeError("blank/invalid image")
                img.save(path)
                _fails[name] = 0
                return True
            except QuotaOut as e:
                print(f"  [{name}] disabled for this run: {e}")
                _dead.add(name)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  [{name}] attempt {attempt + 1}/{tries}: {e}")
                time.sleep(3 * (attempt + 1))
        else:
            _fails[name] = _fails.get(name, 0) + 1
            if _fails[name] >= MAX_FAILS:
                print(f"  [{name}] {MAX_FAILS} images in a row failed -> skipping it for the rest of this run")
                _dead.add(name)
    return False
