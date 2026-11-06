"""Gemini se har run par bilkul naya explainer script banata hai -> script.json (+ history.json update)."""
import datetime
import json
import os
import random
import re
import time

import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"] if m]
HISTORY = "history.json"

AREAS = [
    "what daily life was really like in ancient civilizations (Egypt, Rome, Greece, Mesopotamia, Indus Valley, China)",
    "history myths that almost everyone believes but are false",
    "forgotten events and people that changed the world",
    "the golden age of Islamic civilization and its inventions",
    "medieval life: castles, plagues, knights and peasants - the real story",
    "empires at their peak and the strange reasons they collapsed",
    "shocking truths about famous wars and battles",
    "how ordinary people lived, ate, worked and slept in the past",
    "weird laws, customs and jobs from history",
    "the real stories behind famous historical figures",
    "Mughal, Ottoman, Persian and South Asian history untold stories",
    "prehistoric humans, hunter-gatherers and the invention of farming",
    "ancient inventions and technology that was far ahead of its time",
    "dark and strange moments in history that textbooks skip",
]

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "topic": {"type": "STRING"},
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "character": {"type": "STRING"},
        "scenes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "narration": {"type": "STRING"},
                    "image_prompt": {"type": "STRING"},
                    "background": {"type": "STRING"},
                },
                "required": ["narration", "image_prompt", "background"],
            },
        },
    },
    "required": ["topic", "title", "description", "tags", "character", "scenes"],
}

FALLBACK = {
    "topic": "hunter-gatherer work hours",
    "title": "Ancient Humans Worked Only 17 Hours a Week? #Shorts",
    "description": "What did ancient humans actually do all day? #Shorts #history #facts",
    "tags": ["history", "facts", "ancient humans", "shorts"],
    "character": "wearing a simple animal-hide loincloth",
    "scenes": [
        {"narration": "Ancient humans worked about seventeen hours a week. Yes, really.",
         "image_prompt": "a hunter-gatherer resting by a fire under a huge starry sky",
         "background": "clean plain white paper background"},
        {"narration": "In nineteen sixty three, an anthropologist walked into the Kalahari with a stopwatch.",
         "image_prompt": "an anthropologist with a notebook walking across the Kalahari desert at sunrise",
         "background": "clean plain white paper background"},
        {"narration": "He timed every hour of daily life, and food took far less time than anyone believed.",
         "image_prompt": "people gathering fruit and roots in the desert, golden light",
         "background": "clean plain white paper background"},
        {"narration": "The rest of the day went to talking, music, and stories around the fire.",
         "image_prompt": "a circle of people laughing and telling stories around a night campfire",
         "background": "clean plain white paper background"},
        {"narration": "Then farming arrived, and free time slowly vanished. So what did they do with all that time?",
         "image_prompt": "a lone farmer working a field under a harsh sun, long shadow",
         "background": "clean plain white paper background"},
    ],
}


def load_history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def ask_gemini(prompt):
    last = None
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 1.0,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }
        for _ in range(2):
            try:
                r = requests.post(url, headers={"x-goog-api-key": API_KEY}, json=body, timeout=90)
                if r.status_code == 200:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
            except Exception as e:  # noqa: BLE001
                last = f"{model}: {e}"
            time.sleep(3)
    raise RuntimeError(last)


def validate(d):
    scenes = d["scenes"]
    assert 8 <= len(scenes) <= 16, f"scene count {len(scenes)}"
    words = sum(len(s["narration"].split()) for s in scenes)
    assert 70 <= words <= 170, f"word count {words}"
    for s in scenes:
        assert s["narration"].strip() and s["image_prompt"].strip()
        s.setdefault("background", "clean plain white paper background")
    d["tags"] = [t for t in d["tags"] if isinstance(t, str)][:12]
    return d


def generate():
    if not API_KEY:
        print("GEMINI_API_KEY missing -> fallback script")
        return FALLBACK
    hist = load_history()
    recent = [h.get("topic", "") for h in hist[-60:]]
    area = random.choice(AREAS)
    prompt = f"""You write viral YouTube Shorts scripts in the style of the animated explainer channel "Ink Explainer"
(example video: "What Did Ancient Humans Actually Do All Day?" - a surprising truth that flips what people believe, explained like a story).

Area for this video: {area}. Pick ONE specific, surprising, TRUE topic inside it. Do NOT repeat or closely resemble any of these earlier topics: {recent}.
Random seed: {random.randint(1, 10**7)}.

Rules:
- Total narration 100-125 words (about 40-45 seconds spoken). 11 to 14 scenes, each scene ONE short punchy sentence (6-13 words). Every sentence gets its OWN picture that shows exactly what that sentence says.
- Scene 1 is the HOOK, max 14 words: a shocking claim, a myth-flip or a curiosity gap that makes people unable to swipe away. No greetings, no "did you know", no intro.
- Teenager-friendly, conversational, high-energy spoken English like an excited storyteller. Short sentences, vary rhythm, occasional exclamation or question. Use commas and dots for rhythm. Include real facts, names, numbers, years. Everything must be factually accurate.
- Create tension: keep a small open loop ("but here's the weird part") and pay it off before the end.
- SEAMLESS LOOP: the very last sentence must flow naturally back into scene 1 when the video restarts (for example end with a question or a half-thought whose answer or continuation is the hook). No "subscribe", no "follow", no goodbye, no outro.
- Narration is plain spoken text only: no emojis, no hashtags, no stage directions, write numbers as they are spoken when it helps ("seventeen hours").
- VISUAL STYLE (very important): the video is a "Mack and Explain in Paint" style stick-man explainer. ONE recurring stick man (big plain white round head, simple dot eyes, expressive eyebrows, thin black line body) acts out the story. Because the same character appears in every scene, first write "character": ONE short phrase for his outfit/look for this video's era (e.g. "wearing a rough animal-hide loincloth", "wearing a Roman toga and laurel wreath", "wearing a knight's helmet and tunic").
- image_prompt for each scene (45-70 words): a DETAILED, concrete description of the picture for that exact sentence: the stick man's pose, facial expression and action; 3 to 6 specific, richly detailed objects/props/buildings/animals around him that belong to the topic and sentence (pyramid under construction, rack of clothes, bubbling pot, burning city, crowd of small stick men, map with route, thought bubble containing icons, lightbulb above head, etc). Show things, do not describe abstractions. Thought bubbles may contain pictures but NEVER words. NO text, letters or numbers in the image.
- background for each scene: 5-12 words, one of the looks: "clean plain white paper background", "flat warm orange wall with a grey floor strip", "green grass field with pale sky", "pale blue sky with ground", "dark night sky with stars and ground" - choose what fits, using plain white for about half of the scenes.
- title: max 70 characters, curiosity-driven, ends with " #Shorts". description: 2 sentences plus 5-8 hashtags. tags: 8-12 short keywords.
- topic: 3-8 words naming the specific topic."""
    for attempt in range(3):
        try:
            text = ask_gemini(prompt)
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            d = validate(json.loads(text))
            hist.append({"topic": d["topic"], "title": d["title"], "date": datetime.date.today().isoformat()})
            with open(HISTORY, "w", encoding="utf-8") as f:
                json.dump(hist[-200:], f, ensure_ascii=False, indent=1)
            return d
        except Exception as e:  # noqa: BLE001
            print(f"Gemini attempt {attempt + 1} failed: {e}")
    print("Gemini failed 3 times -> fallback script")
    return FALLBACK


if __name__ == "__main__":
    d = generate()
    with open("script.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("Topic:", d["topic"])
    print("Hook :", d["scenes"][0]["narration"])
