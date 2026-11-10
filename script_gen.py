"""Gemini se har run par NAYI relatable Short ka script banata hai -> script.json

Flow:
  1) IDEAS : Gemini 8 nayi relatable situations sochta hai (hook + punchline + scores); code best chunta hai.
  2) WRITE : 1-2 characters ki chhoti baat-cheet (8-12 lines), har line ke saath emotion / action / background / prop.
  3) POLISH: "script doctor" pass - hook aur punchline tez karta hai (fail ho to original script chalti hai).
Har run alag topic: history.json mein purane topics save hote hain, naye mein repeat nahi hota.
Gemini na chale to ek fallback skit banti hai (history mein save nahi hoti).
"""
import datetime
import json
import os
import random
import re
import sys
import time

import requests

from vocab import (ACCESSORIES, ACTIONS, BGS, EMOTIONS, HAIR_COLORS, HAIR_STYLES, MOODS, PROPS, SFX, SHIRTS, SKINS,
                   VOICES)

API_KEY = os.environ.get("GEMINI_API_KEY")
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"] if m]
HISTORY = "history.json"
OUT = "script.json"
THINK = int(os.environ.get("GEMINI_THINK", "1024"))

AREAS = [
    "school and college life", "exams and last-minute studying", "parents and family at home", "friends and group chats",
    "phone, wifi and social media", "waking up, alarms and sleep", "food, cooking and hunger", "money, shopping and being broke",
    "work, office and meetings", "crushes and awkward moments", "siblings fighting", "weekends and plans that never happen",
    "procrastination and deadlines", "gym, diets and new-year promises", "travel, traffic and being late",
    "desi household moments (mom, dad, relatives, guests)", "gadgets, battery and charger drama", "saying 'I'm fine' when you're not",
]

FALLBACK = {
    "topic": "just five more minutes of phone",
    "title": "Me at 3 AM: 'Just 5 more minutes' #Shorts",
    "description": "Every night, same story. Tag the friend who does this too.\n\n#relatable #funny #shorts #animation #sleep",
    "tags": ["relatable", "funny", "shorts", "animation", "sleep", "phone", "memes"],
    "music_mood": "quirky",
    "characters": [
        dict(name="Me", gender="male", hair="spiky", hair_color="black", skin="tan", shirt="blue", accessory="none", voice="m1"),
        dict(name="Brain", gender="female", hair="bun", hair_color="brown", skin="light", shirt="purple", accessory="glasses", voice="f1"),
    ],
    "scenes": [
        dict(speaker=0, line="Okay, I'm sleeping at ten tonight. For real.", emotion="happy", action="talk", bg="bedroom", prop="bed", label="POV: it's 10 PM", listener_emotion="smug", listener_action="idle", sfx="pop"),
        dict(speaker=1, line="Sure. Just check your phone one last time.", emotion="smug", action="point", bg="bedroom", prop="phone", label="", listener_emotion="neutral", listener_action="idle", sfx="none"),
        dict(speaker=0, line="One minute. That's it.", emotion="neutral", action="phone", bg="bedroom", prop="none", label="", listener_emotion="smug", listener_action="idle", sfx="none"),
        dict(speaker=1, line="Look, a video about how bridges are built!", emotion="excited", action="talk", bg="bedroom", prop="tv", label="", listener_emotion="confused", listener_action="think", sfx="ding"),
        dict(speaker=0, line="Wait, why are there birds on a bridge?", emotion="confused", action="think", bg="night", prop="question", label="", listener_emotion="smug", listener_action="idle", sfx="none"),
        dict(speaker=1, line="It's three AM, by the way.", emotion="smug", action="point", bg="night", prop="clock", label="", listener_emotion="surprised", listener_action="shock", sfx="thud"),
        dict(speaker=0, line="What?! My alarm is in three hours!", emotion="scared", action="shock", bg="night", prop="alarm", label="", listener_emotion="laughing", listener_action="laugh", sfx="boing"),
        dict(speaker=1, line="You said ten, I said nothing.", emotion="laughing", action="laugh", bg="night", prop="none", label="", listener_emotion="sad", listener_action="sad", sfx="fail"),
        dict(speaker=0, line="Okay, sleeping at ten tonight. For real.", emotion="tired", action="sleep", bg="bedroom", prop="none", label="", listener_emotion="smug", listener_action="idle", sfx="none"),
    ],
}


# ------------------------------------------------------------------ Gemini
def load_history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def ask_gemini(prompt, sch=None, max_out=6000, think=None):
    last = None
    budget = THINK if think is None else think
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        cfg = {"temperature": 1.0 if sch else 0.8, "maxOutputTokens": max_out}
        if sch:
            cfg["responseMimeType"] = "application/json"
            cfg["responseSchema"] = sch
        if "2.5-flash" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": budget}
            cfg["maxOutputTokens"] = max_out + budget
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
        for _ in range(2):
            try:
                r = requests.post(url, headers={"x-goog-api-key": API_KEY}, json=body, timeout=240)
                if r.status_code == 200:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    return "".join(p.get("text", "") for p in parts)
                last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
                if r.status_code == 429:
                    time.sleep(20)
            except Exception as e:
                last = f"{model}: {e}"
            time.sleep(4)
    raise RuntimeError(last)


def parse(text):
    return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())


def with_retries(label, fn, tries=3):
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:
            print(f"{label} attempt {attempt + 1} failed: {e}")
            time.sleep(3)
    return None


def S(**kw):
    return {"type": "STRING", **kw}


def script_schema():
    char = {"type": "OBJECT", "properties": {
        "name": S(), "gender": S(enum=["male", "female"]), "hair": S(enum=HAIR_STYLES), "hair_color": S(enum=HAIR_COLORS),
        "skin": S(enum=SKINS), "shirt": S(enum=SHIRTS), "accessory": S(enum=ACCESSORIES), "voice": S(enum=VOICES)},
        "required": ["name", "gender", "hair", "hair_color", "skin", "shirt", "accessory", "voice"]}
    scene = {"type": "OBJECT", "properties": {
        "speaker": {"type": "INTEGER"}, "line": S(), "emotion": S(enum=EMOTIONS), "action": S(enum=ACTIONS),
        "bg": S(enum=BGS), "prop": S(enum=PROPS), "label": S(), "listener_emotion": S(enum=EMOTIONS),
        "listener_action": S(enum=ACTIONS), "sfx": S(enum=SFX)},
        "required": ["speaker", "line", "emotion", "action", "bg", "prop", "label", "listener_emotion", "listener_action", "sfx"]}
    return {"type": "OBJECT", "properties": {
        "topic": S(), "title": S(), "description": S(), "tags": {"type": "ARRAY", "items": S()}, "music_mood": S(enum=MOODS),
        "characters": {"type": "ARRAY", "items": char}, "scenes": {"type": "ARRAY", "items": scene}},
        "required": ["topic", "title", "description", "tags", "music_mood", "characters", "scenes"]}


def ideas_schema():
    item = {"type": "OBJECT", "properties": {
        "topic": S(), "hook": S(), "punchline": S(),
        "relatable": {"type": "INTEGER"}, "funny": {"type": "INTEGER"}, "surprise": {"type": "INTEGER"}},
        "required": ["topic", "hook", "punchline", "relatable", "funny", "surprise"]}
    return {"type": "OBJECT", "properties": {"ideas": {"type": "ARRAY", "items": item}}, "required": ["ideas"]}


# ------------------------------------------------------------------ pipeline
def idea_score(p):
    def n(k):
        try:
            return max(0, min(10, int(p.get(k, 0))))
        except Exception:
            return 0
    return 3 * n("relatable") + 2 * n("funny") + n("surprise")


def pick_idea(area, recent):
    prompt = f"""You are the head writer of a viral 2D-cartoon YouTube Shorts channel about RELATABLE everyday moments.
Think of 8 brand-new situations in this area: {area}.
Each must be something millions of teens and young adults instantly recognise ("that's literally me"), with a funny twist at the end.
Rules: specific and visual (not vague), one clear situation, no politics, no religion jokes, no mean-spirited humour, nothing sexual.
Do NOT repeat or resemble these recent topics: {json.dumps(recent[-60:])}
For each give: topic (3-8 words), hook (the first spoken line, max 10 words, makes people stop scrolling), punchline (the last beat),
and honest scores 0-10 for relatable, funny, surprise."""
    d = parse(ask_gemini(prompt, ideas_schema(), max_out=2500, think=512))
    ideas = [i for i in d.get("ideas", []) if i.get("topic")]
    low = [r.lower() for r in recent]
    ideas = [i for i in ideas if i["topic"].strip().lower() not in low] or ideas
    ideas.sort(key=idea_score, reverse=True)
    return ideas[0]


WRITE_RULES = """FORMAT (very important):
- A 2D cartoon skit of 1 or 2 characters, 30-40 seconds when spoken. 9-12 scenes. Each scene = ONE spoken line, max 12 words.
  Total spoken words 80-110. Natural, funny, conversational English a teenager would say. No emojis, no hashtags, no stage directions inside lines.
- Scene 1 is the HOOK: the most relatable or surprising line, spoken immediately (no greeting, no intro).
- Then: setup -> escalation (it gets worse or funnier each scene) -> twist -> punchline.
- LOOP: the LAST line must flow back into the FIRST line so the video feels endless when it replays
  (e.g. repeat the first line with a new meaning, or end on a half-thought the first line completes).
- Two characters work best (e.g. "Me" and "Mom", "Me" and "Brain", "Me" and "Friend"). Speaker is the index (0 or 1) in characters.
  With one character use only speaker 0 (monologue / talking to the audience). Names are short (max 8 letters).
- Characters: pick looks that fit (hijab for a mom is fine, glasses, beard, cap...). Two characters must have DIFFERENT voices
  (m1/m2 male, f1/f2 female) matching gender.
- For every scene choose: emotion + action for the speaker, listener_emotion + listener_action for the other one (react! shock, laugh, facepalm...),
  bg (the place), prop (one big icon that shows the topic, or none), sfx (a sound effect on the beat, or none).
  Change bg only when the place really changes. label = a short caption like "POV: it's 3 AM" or "10 minutes later" (max 5 words) only on 2-3 scenes, else empty string.
- title: max 60 characters, curiosity or relatable, ends with #Shorts. description: 1-2 lines + 5 hashtags. tags: 6-8 words.
"""


def clean_script(d):
    """Gemini ke output ko renderer ke liye safe banata hai. Kharab ho to None."""
    def pick(v, allowed, default):
        v = str(v or "").strip().lower()
        return v if v in allowed else default

    chars = []
    for c in (d.get("characters") or [])[:2]:
        g = pick(c.get("gender"), ("male", "female"), "male")
        v = pick(c.get("voice"), VOICES, "m1" if g == "male" else "f1")
        if (g == "male") != v.startswith("m"):
            v = "m1" if g == "male" else "f1"
        chars.append(dict(
            name=re.sub(r"[^A-Za-z0-9 ]", "", str(c.get("name") or "Me"))[:10] or "Me", gender=g,
            hair=pick(c.get("hair"), HAIR_STYLES, "short"), hair_color=pick(c.get("hair_color"), HAIR_COLORS, "black"),
            skin=pick(c.get("skin"), SKINS, "tan"), shirt=pick(c.get("shirt"), SHIRTS, "blue"),
            accessory=pick(c.get("accessory"), ACCESSORIES, "none"), voice=v))
    if not chars:
        return None
    if len(chars) == 2 and chars[0]["voice"] == chars[1]["voice"]:
        chars[1]["voice"] = {"m1": "m2", "m2": "m1", "f1": "f2", "f2": "f1"}[chars[1]["voice"]]
    scenes = []
    for s in d.get("scenes") or []:
        line = str(s.get("line") or "")
        line = line.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
        line = re.sub(r"[^\x20-\x7E]", "", line).strip()
        if len(line.split()) < 1:
            continue
        try:
            spk = int(s.get("speaker", 0))
        except Exception:
            spk = 0
        label = re.sub(r"[^\x20-\x7E]", "", str(s.get("label") or "")).strip()[:32]
        scenes.append(dict(
            speaker=spk if 0 <= spk < len(chars) else 0, line=line[:140],
            emotion=pick(s.get("emotion"), EMOTIONS, "neutral"), action=pick(s.get("action"), ACTIONS, "talk"),
            bg=pick(s.get("bg"), BGS, "plain"), prop=pick(s.get("prop"), PROPS, "none"), label=label,
            listener_emotion=pick(s.get("listener_emotion"), EMOTIONS, "neutral"),
            listener_action=pick(s.get("listener_action"), ACTIONS, "idle"), sfx=pick(s.get("sfx"), SFX, "none")))
    if len(scenes) < 5:
        return None
    scenes = scenes[:14]
    # speaker ki action "idle" na ho (munh to chal raha hai), listener ki action "talk" na ho
    for s in scenes:
        if s["action"] == "idle":
            s["action"] = "talk"
        if s["listener_action"] == "talk":
            s["listener_action"] = "idle"
        if len(chars) == 1:
            s["listener_action"], s["listener_emotion"] = "idle", "neutral"
    # background: pehle scene ka bg 'plain' na ho to baqi mein "plain" ko pichhle bg se badal do
    prev = scenes[0]["bg"]
    for s in scenes:
        if s["bg"] == "plain" and prev != "plain":
            s["bg"] = prev
        prev = s["bg"]
    title = re.sub(r"[^\x20-\x7E]", "", str(d.get("title") or "")).strip()[:90] or "Relatable moment #Shorts"
    tags = [re.sub(r"[^A-Za-z0-9 ]", "", str(t)).strip() for t in (d.get("tags") or [])][:10]
    return dict(
        topic=str(d.get("topic") or title)[:100], title=title,
        description=str(d.get("description") or "").strip()[:900] or "Relatable. Funny. Daily.\n\n#relatable #funny #shorts",
        tags=[t for t in tags if t] or ["relatable", "funny", "shorts"],
        music_mood=pick(d.get("music_mood"), MOODS, "quirky"), characters=chars, scenes=scenes)


def write_script(idea, area):
    prompt = f"""Write the script for ONE YouTube Short (2D cartoon skit).
Area: {area}
Topic: {idea['topic']}
Hook idea: {idea.get('hook', '')}
Punchline idea: {idea.get('punchline', '')}

{WRITE_RULES}
Return JSON only."""
    return clean_script(parse(ask_gemini(prompt, script_schema(), max_out=5000)))


def polish(d):
    prompt = f"""You are a ruthless comedy script doctor for 30-second cartoon Shorts. Here is a draft (JSON):
{json.dumps(d, ensure_ascii=False)}

Improve it: sharper hook in scene 1 (max 10 words), funnier escalation, a punchline that really lands, and make sure the LAST line flows back into the FIRST line (loop).
Keep it relatable and clean. Keep 9-12 scenes and 80-110 total spoken words, max 12 words per line. Keep the same characters unless a change clearly helps.
Keep every field valid. Return the full improved JSON only."""
    return clean_script(parse(ask_gemini(prompt, script_schema(), max_out=5000)))


def total_words(d):
    return sum(len(s["line"].split()) for s in d["scenes"])


def gen():
    recent = [h.get("topic", "") for h in load_history()[-150:]]
    area = random.choice(AREAS)
    print("Area:", area)
    idea = with_retries("idea", lambda: pick_idea(area, recent))
    if not idea:
        return None
    print("Idea:", idea["topic"], "| score", idea_score(idea))
    d = with_retries("write", lambda: write_script(idea, area))
    if not d:
        return None
    better = with_retries("polish", lambda: polish(d), tries=2)
    if better and 60 <= total_words(better) <= 130 and len(better["scenes"]) >= 7:
        d = better
        print("Polish pass applied")
    d["topic"] = d.get("topic") or idea["topic"]
    return d


def save_history(hist, d):
    key = d["topic"].strip().lower()
    if any(h.get("topic", "").strip().lower() == key for h in hist):
        return
    hist.append({"topic": d["topic"], "title": d["title"], "date": datetime.date.today().isoformat()})
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist[-300:], f, ensure_ascii=False, indent=1)


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    hist = load_history()
    d, fallback = (gen() if API_KEY else None), False
    if not d:
        print("Gemini unavailable -> fallback skit (history mein save nahi hogi)")
        d, fallback = FALLBACK, True
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("SCRIPT:", d["title"], f"({len(d['scenes'])} scenes, {total_words(d)} words)")
    if not fallback:
        save_history(hist, d)


if __name__ == "__main__":
    main()
