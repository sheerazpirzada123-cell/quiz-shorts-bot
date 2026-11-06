"""Pollinations AI se free, detailed stick-man images (koi account/limit nahi; optional POLLINATIONS_API_KEY)."""
import io
import os
import random
import time
import urllib.parse

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
    "simple soft shading. Vertical 9:16 composition, stick man large in the center, props and details above, below and beside him. "
    "No text, no letters, no words, no numbers, no watermark.",
)
MODELS = ["flux", "turbo"]
KEY = os.environ.get("POLLINATIONS_API_KEY")


def build_prompt(scene, character="", background=""):
    parts = [STYLE_HEAD]
    if character:
        parts.append(f"The stick man is {character.strip().rstrip('.')}.")
    parts.append(f"Scene: {scene.strip().rstrip('.')}.")
    if background:
        parts.append(f"Background: {background.strip().rstrip('.')}.")
    parts.append(STYLE_TAIL)
    return " ".join(parts)


def fetch_image(scene, path, character="", background="", seed=None):
    """True agar image save ho gayi, warna False."""
    full = build_prompt(scene, character, background)
    headers = {"Authorization": f"Bearer {KEY}"} if KEY else {}
    for attempt in range(5):
        model = MODELS[0] if attempt < 3 else MODELS[1]
        # Pehli koshish mein video ka common seed (character ek jaisa rahe), retry par naya seed
        s = seed if (seed is not None and attempt == 0) else random.randint(1, 10**7)
        url = (
            "https://image.pollinations.ai/prompt/" + urllib.parse.quote(full)
            + f"?width=864&height=1536&seed={s}&model={model}&nologo=true&private=true&enhance=false"
        )
        try:
            r = requests.get(url, headers=headers, timeout=180)
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
