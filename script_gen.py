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
    "ancient history and how people really lived", "human body and brain", "psychology and human behavior",
    "space and the universe", "deep ocean and sea creatures", "animals and their strange abilities",
    "lost civilizations and mysteries", "science facts that sound fake but are true", "how everyday things were invented",
    "money, economy and why things cost what they cost", "sleep, dreams and the mind", "food and what it does to you",
    "dark and weird history", "nature and extreme weather", "technology and the internet history",
    "famous people and unknown sides of them", "languages, words and where they come from", "survival and extreme human limits",
]

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "topic": {"type": "STRING"},
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "scenes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"narration": {"type": "STRING"}, "image_prompt": {"type": "STRING"}},
                "required": ["narration", "image_prompt"],
            },
        },
    },
    "required": ["topic", "title", "description", "tags", "scenes"],
}

FALLBACK = {
    "topic": "hunter-gatherer work hours",
    "title": "Ancient Humans Worked Only 17 Hours a Week? #Shorts",
    "description": "What did ancient humans actually do all day? #Shorts #history #facts",
    "tags": ["history", "facts", "ancient humans", "shorts"],
    "scenes": [
        {"narration": "Ancient humans worked about seventeen hours a week. Yes, really.",
         "image_prompt": "a hunter-gatherer resting by a fire under a huge starry sky"},
        {"narration": "In nineteen sixty three, an anthropologist walked into the Kalahari with a stopwatch.",
         "image_prompt": "an anthropologist with a notebook walking across the Kalahari desert at sunrise"},
        {"narration": "He timed every hour of daily life, and food took far less time than anyone believed.",
         "image_prompt": "people gathering fruit and roots in the desert, golden light"},
        {"narration": "The rest of the day went to talking, music, and stories around the fire.",
         "image_prompt": "a circle of people laughing and telling stories around a night campfire"},
        {"narration": "Then farming arrived, and free time slowly vanished. So what did they do with all that time?",
         "image_prompt": "a lone farmer working a field under a harsh sun, long shadow"},
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
    assert 5 <= len(scenes) <= 10, f"scene count {len(scenes)}"
    words = sum(len(s["narration"].split()) for s in scenes)
    assert 70 <= words <= 170, f"word count {words}"
    for s in scenes:
        assert s["narration"].strip() and s["image_prompt"].strip()
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
- Total narration 100-125 words (about 40-50 seconds spoken). 7 to 9 scenes, each scene 1-2 short punchy sentences.
- Scene 1 is the HOOK, max 14 words: a shocking claim, a myth-flip or a curiosity gap that makes people unable to swipe away. No greetings, no "did you know", no intro.
- Teenager-friendly, conversational, energetic spoken English. Short sentences. Use commas and dots for rhythm. Include real facts, names, numbers, years. Everything must be factually accurate.
- Create tension: keep a small open loop ("but here's the weird part") and pay it off before the end.
- SEAMLESS LOOP: the very last sentence must flow naturally back into scene 1 when the video restarts (for example end with a question or a half-thought whose answer or continuation is the hook). No "subscribe", no "follow", no goodbye, no outro.
- Narration is plain spoken text only: no emojis, no hashtags, no stage directions, write numbers as they are spoken when it helps ("seventeen hours").
- image_prompt for each scene: English, max 35 words, describes one clear vivid illustrated scene that matches that narration, vertical composition, NO text or letters in the image, no real celebrity faces. Keep the same visual world across scenes.
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
