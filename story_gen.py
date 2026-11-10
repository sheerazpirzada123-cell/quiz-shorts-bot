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

WORLD (keep it CONSISTENT): pick ONE time_of_day for the whole video (day | sunset | night) and 2-3 locations (a fixed place each, e.g. "workshop", "street", "factory floor").
The story moves in order, so stay in one location for several scenes in a row before changing; NEVER flip between day and night. Each location has a bg_prompt:
a concrete description of the 3D-rendered ENVIRONMENT only (place, objects, light that matches the time_of_day) - NO people, NO text. indoor=true if it is inside a room/building.
SCENES: 12-15 scenes, each = ONE short narration sentence/phrase (5-12 words) that is shown with visuals. Every scene needs:
 - location: index into locations.
 - shot: wide | medium | close   (close = a big face reaction, only for 1-2 key beats; vary shots!)
 - camera: push_in | pull_out | pan_left | pan_right | static   (mostly push_in / pan, smooth)
 - cast: 1-3 characters on screen: who (index in characters), x (0.15-0.85 horizontal position), action, emotion, facing (1 right / -1 left).
 - sfx: one sound effect at the key moment (or none).
ACTING (natural, NOT over the top):
 - A narrator voice tells the story and the characters NEVER lip-sync, so feelings are shown only with face + body.
 - emotion must match what the narration says in THAT scene. Default to neutral / happy / worried / smug / proud / confused.
   Use surprised, scared, laughing, excited, evil, cry at most 2 times in the whole video.
 - action: mostly idle, talk (gentle gesturing), point, think, hold, walk, shrug. shock, celebrate, laugh, angry, facepalm, run, sad: at most once each, only on the big beat.
 - Characters stay standing at about the same x in neighbouring scenes of the same location (move by at most 0.25 unless action is walk/run) - no teleporting.
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
    loc = {"type": "OBJECT", "properties": {"name": S(), "bg_prompt": S(), "indoor": {"type": "BOOLEAN"}}, "required": ["name", "bg_prompt", "indoor"]}
    sc = {"type": "OBJECT", "properties": {"text": S(), "location": {"type": "INTEGER"},
          "shot": S(enum=["wide", "medium", "close"]), "camera": S(enum=["push_in", "pull_out", "pan_left", "pan_right", "static"]),
          "cast": {"type": "ARRAY", "items": cast}, "sfx": S(enum=SFX)},
          "required": ["text", "location", "shot", "camera", "cast", "sfx"]}
    return {"type": "OBJECT", "properties": {"topic": S(), "title": S(), "description": S(), "tags": {"type": "ARRAY", "items": S()},
            "music_mood": S(enum=MOODS), "time_of_day": S(enum=["day", "sunset", "night"]), "locations": {"type": "ARRAY", "items": loc},
            "characters": {"type": "ARRAY", "items": ch}, "scenes": {"type": "ARRAY", "items": sc}},
            "required": ["topic", "title", "description", "tags", "music_mood", "time_of_day", "locations", "characters", "scenes"]}


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


def finalize(d):
    """Location -> bg_prompt/tone (poori video mein ek time-of-day), aur characters same jagah ke scenes mein teleport na karein."""
    tod = d.get("time_of_day") if d.get("time_of_day") in ("day", "sunset", "night") else "day"
    locs = [l for l in (d.get("locations") or []) if l.get("bg_prompt")] or [dict(name="scene", bg_prompt="a simple colorful town street", indoor=False)]
    d["time_of_day"], d["locations"] = tod, locs
    prev = None
    for sc in d["scenes"]:
        li = sc.get("location", 0)
        li = li if isinstance(li, int) and 0 <= li < len(locs) else 0
        sc["location"], sc["bg_prompt"] = li, locs[li]["bg_prompt"]
        sc["tone"] = "indoor" if locs[li].get("indoor") else tod
        if prev and prev["location"] == li:
            pw = {c["who"]: c for c in prev["cast"]}
            for c in sc["cast"]:
                p = pw.get(c["who"])
                if p and c["action"] not in ("walk", "run") and abs(c["x"] - p["x"]) > 0.25:
                    c["x"] = p["x"] + 0.25 * (1 if c["x"] > p["x"] else -1)
        prev = sc
    return d


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
    return finalize(d)


FALLBACK = {
    "topic": "why roller coaster loops are teardrop shaped", "title": "This Shape Saved Roller Coasters #Shorts",
    "description": "The real story behind the teardrop loop.\n\n#animation #storytime #facts #shorts", "tags": ["animation", "storytime", "facts", "shorts"],
    "music_mood": "quirky", "time_of_day": "day",
    "locations": [dict(name="park", bg_prompt="theme park with a giant steel roller coaster loop, open plaza ground", indoor=False),
                  dict(name="office", bg_prompt="engineer drafting room with blueprints on the desk and walls", indoor=True)],
    "characters": [dict(name="Hero", shirt="yellow", hat="cap", hat_color="red", hair_color="brown", overalls=True, tie=False, glasses=False, mustache=False),
                   dict(name="Rival", shirt="black", hat="slick", hat_color="black", hair_color="black", overalls=False, tie=True, glasses=False, mustache=False)],
    "scenes": [
        dict(text="This shape saved roller coasters.", location=0, shot="wide", camera="push_in", cast=[dict(who=0, x=0.6, action="point", emotion="happy", facing=-1)], sfx="whoosh"),
        dict(text="Early designers built perfectly round loops.", location=0, shot="medium", camera="pan_right", cast=[dict(who=0, x=0.55, action="talk", emotion="neutral", facing=-1)], sfx="none"),
        dict(text="But a round loop crushed riders with brutal force.", location=0, shot="close", camera="push_in", cast=[dict(who=0, x=0.5, action="idle", emotion="worried", facing=1)], sfx="gasp"),
        dict(text="So engineers changed it to a teardrop.", location=1, shot="medium", camera="push_in", cast=[dict(who=0, x=0.35, action="think", emotion="neutral", facing=1), dict(who=1, x=0.7, action="idle", emotion="smug", facing=-1)], sfx="sparkle"),
        dict(text="Gentler rides, happier riders, and that's why loops look like that.", location=0, shot="wide", camera="pull_out", cast=[dict(who=0, x=0.35, action="talk", emotion="proud", facing=1), dict(who=1, x=0.65, action="idle", emotion="happy", facing=-1)], sfx="tada"),
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
        import copy
        d, fb = finalize(copy.deepcopy(FALLBACK)), True
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("SCRIPT:", d["title"], f"({len(d['scenes'])} scenes)")
    if not fb and not any(h.get("topic", "").lower() == d["topic"].lower() for h in hist):
        hist.append({"topic": d["topic"], "title": d["title"], "date": datetime.date.today().isoformat()})
        json.dump(hist[-300:], open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
