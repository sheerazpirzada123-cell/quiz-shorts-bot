"""Pollinations AI se free images (koi account/limit nahi; optional POLLINATIONS_API_KEY support)."""
import io
import os
import random
import time
import urllib.parse

import requests
from PIL import Image

STYLE = os.environ.get(
    "IMAGE_STYLE",
    "minimalist stick figure animation style, simple black stick men with round heads and thin line limbs, "
    "expressive poses, clean off-white paper background, simple hand-drawn doodle props, few flat accent colors, "
    "thick clean black ink outlines, 2D explainer video frame, no text, no letters, no watermark",
)
MODELS = ["flux", "turbo"]
KEY = os.environ.get("POLLINATIONS_API_KEY")


def fetch_image(prompt, path, seed=None):
    """True agar image save ho gayi, warna False."""
    full = f"{prompt}, {STYLE}"
    headers = {"Authorization": f"Bearer {KEY}"} if KEY else {}
    for attempt in range(5):
        model = MODELS[0] if attempt < 3 else MODELS[1]
        s = random.randint(1, 10**7) if seed is None or attempt else seed
        url = (
            "https://image.pollinations.ai/prompt/" + urllib.parse.quote(full)
            + f"?width=720&height=1280&seed={s}&model={model}&nologo=true&private=true"
        )
        try:
            r = requests.get(url, headers=headers, timeout=150)
            if r.status_code == 200 and len(r.content) > 10_000:
                img = Image.open(io.BytesIO(r.content))
                img.load()
                img.convert("RGB").save(path)
                return True
            print(f"  pollinations attempt {attempt + 1}: HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            print(f"  pollinations attempt {attempt + 1}: {e}")
        time.sleep(4 * (attempt + 1))
    return False
