"""Gemini se NAYI 'origin story' (RicksClips style) ka script: narration + har scene ka background prompt + actors.
Output: script.json"""
import datetime
import json
import os
import random
import re
import sys
import time

import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"] if m]
HISTORY, OUT = "history.json", "script.json"

AREAS = [
    "why a common everyday object has the shape it has", "how a famous safety rule or law came to exist",
    "why drivers/people started doing a habit (dashcams, seatbelts, helmets...)", "how a food or drink was invented by accident",
    "how a famous rivalry between two inventors changed something we use daily", "the real story behind a rule in sports",
    "why a building / bridge / road is built the way it is", "how a household product was invented from a mistake",
    "how a scam or cheat led to a new rule or technology", "the true origin of a symbol, sign or button we see every day",
    "a disaster that forced engineers to redesign something", "why money / coins / banknotes look the way they do",
]
SHIRTS = ["yellow", "red", "blue", "green", "orange", "purple", "teal", "pink", "gray", "black", "white", "brown", "navy"]
HATS = ["none", "cap", "hardhat", "slick", "messy", "beanie"]
ACTIONS = ["idle", "talk", "point", "shock", "celebrate", "shrug", "think", "facepalm", "laugh", "angry", "hold", "wave",
           "walk", "run", "sad"]
EMOS = ["neutral", "happy", "smug", "angry", "surprised", "scared", "sad", "laughing", "sleepy", "confused", "excited",
        "evil", "worried", "proud", "cry"]
SFX = ["none", "pop", "ding", "thud", "boing", "fail", "tada", "whoosh", "rise", "slide_down", "scratch", "cash", "click",
       "punch", "gulp", "gasp", "bonk", "knock", "sparkle", "alarm", "buzz"]
TONES = ["day", "night", "sunset", "indoor"]
MOODS = ["quirky", "mysterious", "epic", "chill"]

RULES = """You write 45-55 second narrated 2D-animation YouTube Shorts in the style of "RicksClips3000":
a funny, fast, deadpan mini-STORY about the REAL origin of something ("This Shape Saved Roller Coasters", "Why Drivers Started Filming The Road").
Characters are simple stick-men with big round white heads; backgrounds are 3D-rendered scenes.

STRUCTURE (narration is spoken by a voice, ~115-140 words total, simple words, short punchy sentences):
1. HOOK (first scene, <=9 words): a bold claim/question that makes people stay. e.g. "This shape saved roller coasters."
2. SETUP: introduce the hero (a hard-working underdog) and what he wants.
3. CONFLICT: a rival / obstacle / disaster, escalating (rule of three), with small comedy ("Does he know what he's doing? Not really.").
4. TWIST: the surprising turn that really happened.
5. PAYOFF: the real-world result - "and that's why ..." - one clean memorable line. Last line should loop naturally back to the hook.
FACTS: base it on a REAL, verifiable historical origin/fact; do not invent fake history. You may dramatize with simple characters/jokes, but the core fact must be true.

SCENES: 12-15 scenes, each = ONE short narration sentence/phrase (5-12 words) that is shown with visuals. Every scene needs:
 - bg_prompt: concrete description of the 3D-rendered ENVIRONMENT only (place, objects, light, time of day) - NO people, NO text.
 - tone: day|night|sunset|indoor (for lighting/colour grade).
 - shot: wide | medium | close   (close = a big face reaction, use for key emotional beats; vary shots!)
 - camera: push_in | pull_out | pan_left | pan_right | static   (mostly push_in / pan, smooth)
 - cast: 1-3 characters on screen: who (index in characters), x (0.15-0.85 horizontal position), action, emotion, facing (1 right / -1 left).
   Characters must ACT out exactly what the narration says (point at things, shock, walk, hold items, laugh...). Rival smirks while doing evil things.
 - sfx: one sound effect at the key moment (or none).
CHARACTERS: 2-4 characters. The hero: yellow shirt + red cap (hat: cap, hat_color red) works great; rival: black/navy suit, hat: slick, tie true; extras: other shirt colors.
Return JSON only."""


def schema():
    S = lambda **k: {"type": "STRING", **k}
    ch = {"type": "OBJECT", "properties": {"name": S(), "shirt": S(enum=SHIRTS), "hat": S(enum=HATS), "hat_color": S(enum=SHIRTS),
          "hair_color": S(enum=["black", "brown", "blonde", "red", "gray"]), "overalls": {"type": "BOOLEAN"},
          "tie": {"type": "BOOLEAN"}, "glasses": {"type": "BOOLEAN"}, "mustache": {"type": "BOOLEAN"}},
          "required": ["name", "shirt", "hat", "hat_color", "hair_color", "overalls", "tie", "glasses", "mustache"]}
    cast = {"type": "OBJECT", "properties": {"who": {"type": "INTEGER"}, "x": {"type": "NUMBER"}, "action": S(enum=ACTIONS),
            "emotion": S(enum=EMOS), "facing": {"type": "INTEGER"}}, "required": ["who", "x", "action", "emotion", "facing"]}
    sc = {"type": "OBJECT", "properties": {"text": S(), "bg_prompt": S(), "tone": S(enum=TONES),
          "shot": S(enum=["wide", "medium", "close"]), "camera": S(enum=["push_in", "pull_out", "pan_left", "pan_right", "static"]),
          "cast": {"type": "ARRAY", "items": cast}, "sfx": S(enum=SFX)},
          "required": ["text", "bg_prompt", "tone", "shot", "camera", "cast", "sfx"]}
    return {"type": "OBJECT", "properties": {"topic": S(), "title": S(), "description": S(), "tags": {"type": "ARRAY", "items": S()},
            "music_mood": S(enum=MOODS), "characters": {"type": "ARRAY", "items": ch}, "scenes": {"type": "ARRAY", "items": sc}},
            "required": ["topic", "title", "description", "tags", "music_mood", "characters", "scenes"]}


def ask(prompt, sch, max_out=7000, think=1024):
    last = None
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        cfg = {"temperature": 1.0, "maxOutputTokens": max_out, "responseMimeType": "application/json", "responseSchema": sch}
        if "2.5-flash" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": think}
            cfg["maxOutputTokens"] = max_out + think
        for _ in range(2):
            try:
                r = requests.post(url, headers={"x-goog-api-key": API_KEY}, json={"contents": [{"parts": [{"text": prompt}]}],
                                  "generationConfig": cfg}, timeout=240)
                if r.status_code == 200:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    return json.loads(re.sub(r"^```(?:json)?|```$", "", "".join(p.get("text", "") for p in parts).strip(), flags=re.M))
                last = f"{model}: HTTP {r.status_code} {r.text[:160]}"
                if r.status_code == 429:
                    time.sleep(20)
            except Exception as e:
                last = f"{model}: {e}"
            time.sleep(4)
    raise RuntimeError(last)


def load_history():
    try:
        return json.load(open(HISTORY, encoding="utf-8"))
    except Exception:
        return []


def clean(d):
    n = len(d["characters"])
    for sc in d["scenes"]:
        sc["text"] = re.sub(r"\s+", " ", sc["text"]).strip()
        sc["cast"] = [c for c in sc["cast"] if 0 <= c["who"] < n][:3] or [dict(who=0, x=0.5, action="idle", emotion="neutral", facing=1)]
        for c in sc["cast"]:
            c["x"] = min(0.85, max(0.15, float(c["x"])))
            c["facing"] = 1 if c["facing"] >= 0 else -1
    d["scenes"] = [s for s in d["scenes"] if s["text"]]
    words = sum(len(s["text"].split()) for s in d["scenes"])
    if not (8 <= len(d["scenes"]) <= 18 and 70 <= words <= 175):
        raise ValueError(f"bad size: {len(d['scenes'])} scenes / {words} words")
    d["title"] = d["title"][:90]
    return d


FALLBACK = {
    "topic": "why roller coaster loops are teardrop shaped", "title": "This Shape Saved Roller Coasters #Shorts",
    "description": "The real story behind the teardrop loop.\n\n#animation #storytime #facts #shorts", "tags": ["animation", "storytime", "facts", "shorts"],
    "music_mood": "quirky",
    "characters": [dict(name="Hero", shirt="yellow", hat="cap", hat_color="red", hair_color="brown", overalls=True, tie=False, glasses=False, mustache=False),
                   dict(name="Rival", shirt="black", hat="slick", hat_color="black", hair_color="black", overalls=False, tie=True, glasses=False, mustache=False)],
    "scenes": [
        dict(text="This shape saved roller coasters.", bg_prompt="giant steel roller coaster loop under a blue sky, theme park", tone="day", shot="wide", camera="push_in", cast=[dict(who=0, x=0.7, action="point", emotion="happy", facing=-1)], sfx="whoosh"),
        dict(text="Early designers built perfectly round loops.", bg_prompt="old wooden amusement park with a round circular roller coaster loop, sunny", tone="day", shot="medium", camera="pan_right", cast=[dict(who=0, x=0.35, action="talk", emotion="happy", facing=1)], sfx="none"),
        dict(text="But a round loop crushed riders with brutal force.", bg_prompt="roller coaster track tight circular loop, dramatic sky", tone="sunset", shot="close", camera="push_in", cast=[dict(who=0, x=0.5, action="shock", emotion="scared", facing=1)], sfx="gasp"),
        dict(text="So engineers changed it to a teardrop.", bg_prompt="engineer drafting desk with blueprints of a teardrop shaped loop, warm light", tone="indoor", shot="medium", camera="push_in", cast=[dict(who=0, x=0.35, action="think", emotion="smug", facing=1), dict(who=1, x=0.7, action="idle", emotion="smug", facing=-1)], sfx="sparkle"),
        dict(text="Gentler rides, happier riders, and that's why loops look like that.", bg_prompt="modern roller coaster with teardrop loop at golden hour, theme park", tone="sunset", shot="wide", camera="pull_out", cast=[dict(who=0, x=0.3, action="celebrate", emotion="excited", facing=1), dict(who=1, x=0.7, action="laugh", emotion="laughing", facing=-1)], sfx="tada"),
    ],
}


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    hist = load_history()
    recent = [h.get("topic", "") for h in hist[-150:]]
    d, fb = None, False
    if API_KEY:
        for attempt in range(3):
            area = random.choice(AREAS)
            prompt = (f"{RULES}\n\nCategory for this video: {area}\nPick a fresh, specific, surprising topic. "
                      f"Do NOT repeat any of these past topics: {recent[-60:]}\nJSON only.")
            try:
                d = clean(ask(prompt, schema()))
                break
            except Exception as e:
                print(f"story attempt {attempt + 1} failed: {e}")
                time.sleep(3)
    if not d:
        print("Gemini unavailable -> fallback story (history mein save nahi hogi)")
        d, fb = FALLBACK, True
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("SCRIPT:", d["title"], f"({len(d['scenes'])} scenes)")
    if not fb and not any(h.get("topic", "").lower() == d["topic"].lower() for h in hist):
        hist.append({"topic": d["topic"], "title": d["title"], "date": datetime.date.today().isoformat()})
        json.dump(hist[-300:], open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
