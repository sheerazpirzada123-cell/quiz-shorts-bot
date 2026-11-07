"""Gemini se naya script banata hai (story + characters + har scene ki animation directions).

MODE (env):
  both  -> script_long.json (landscape, ~9-10 min) + script_short.json (long ko promote karne wala teaser Short)
  long  -> sirf script_long.json
  short -> sirf script_short.json (standalone Short, loop ending)

Flow (long): 1) research (Google Search grounding, na chale to skip)  2) plan: topic/title/cast/10 chapters
             3) har chapter alag call (taake lambai aur quality dono pakki rahein).
Topic hamesha aisi sachchi kahani jo 99% logon ne nahi suni. history.json se purane topics repeat nahi hote.
"""
import datetime
import json
import os
import random
import re
import sys
import time

import requests

from vocab import ACCESSORIES, ACTIONS, BGS, COLORS, EMOTIONS, GARMENTS, MOODS, PROPS

API_KEY = os.environ.get("GEMINI_API_KEY")
MODE = os.environ.get("MODE", "both").strip().lower()
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"] if m]
HISTORY = "history.json"
LONG_TARGET_WORDS = int(os.environ.get("LONG_TARGET_WORDS", "1500"))  # ~9-10 min (1700 = poore 10 min)
N_CHAPTERS = max(8, min(12, round(LONG_TARGET_WORDS / 150)))

CTA_FALLBACK = {
    "narration": "Want the full story? Watch the full video on my channel. It's linked in the description.",
    "action": "point", "emotion": "excited", "focus": 0, "bg": "white", "props": ["crowd", "exclaim"],
    "label": "FULL VIDEO", "other": None, "other_action": "idle",
}

# Obscure angles: Gemini inme se ek aisi story chunta hai jo bohat kam logon ne suni ho
AREAS = [
    "a forgotten 'first' of everyday life: the first time anyone did something totally ordinary (queued, tipped, shook hands, signed a name) - and a weird, specific origin nobody remembers",
    "a strange but TRUE historical event that sounds fake (animals put on trial, a town that moved, a day deleted from a calendar, a city abandoned overnight)",
    "an everyday object whose invention story is bizarre and little known (a specific inventor, a specific accident, a specific year)",
    "a forgotten person who changed daily life but is almost never mentioned in textbooks",
    "the first workers' strike, first prank, first joke, first complaint or first scam in recorded history and what happened next",
    "a lost ancient technology or skill that humans forgot and how we found out (specific site, specific discovery)",
    "an absurd real law, tax or ritual from history and the logic that made sense at the time",
    "the first time humans did something to or with food that sounds disgusting or crazy today (and who did it)",
    "a real mystery that was finally solved by a tiny clue (a specific case, a specific object)",
    "a forgotten disaster or near-disaster that almost changed history, but hardly anyone knows about",
    "how an ancient culture solved a modern-sounding problem (traffic, garbage, fake news, noisy neighbours, taxes) in a surprising way",
    "the strangest 'first' in sports, games or toys (the first referee, the first cheat, the first board game, the first trophy)",
    "the first times animals were used in ways that surprise people (war pigeons, ant surgeons, dog police, cat mail)",
    "bizarre origins of everyday words, names, numbers or symbols that people use daily without knowing",
    "a real expedition, voyage or escape that sounds like fiction but is documented, with a specific year and names",
    "the first time humans tried to fly, dive, or survive somewhere impossible, with a specific funny or brave attempt",
    "weird real medical history: the strangest first treatments, first doctors, first hospitals and what they really did",
    "a forgotten scientific mistake that everyone believed for centuries and how it was finally fixed",
    "the secret history of a familiar place (a street, a market, a bridge, a library) and the odd event that created it",
    "a real case of a hoax, forgery or impostor that fooled the world for years (documented, with names and dates)",
]

SCENE_RULES = f"""SCENE FIELDS (the animation is drawn by code from these - choose them carefully):
- narration: 1 or 2 spoken sentences (plain text, no emojis/hashtags/stage directions). Write numbers and years as spoken words ("seventeen sixty-three").
- focus: index (0-based) of the character who is the main actor / narrator-surrogate in this scene.
- other: index of a SECOND character shown in this scene, or -1 for none. other_action: that character's action (use "idle" for listening).
- action (what the focus character does): {", ".join(ACTIONS)}. Vary them: NEVER the same action more than twice in a row. Use shock for big reveals, think for questions/mysteries, celebrate for wins, sad for tragedy, run for chases/escapes, walk for journeys, work for building/crafting/digging, dance for fun, hide for danger, point when explaining something, shrug for "nobody knows".
- emotion: {", ".join(EMOTIONS)} (must match the narration's mood).
- bg: one of {", ".join(BGS)}. Use "white" for about a third of the scenes; pick the rest to match place/time (night for dark events, snow for cold, ocean for sea, city for towns, desert, cave, etc).
- props: 0 to 3 items from [{", ".join(PROPS)}] that literally show what the narration talks about (crowd = groups of people, animal = any animal, fire, coin, map, clock, calendar, crown, castle...). Prefer 2 props most of the time.
- label: OPTIONAL big sticker text (max 4 words, e.g. "1,200 YEARS AGO", "ONLY ONE SURVIVED", a key date/number/name). Use it in about one scene out of four, empty string otherwise."""

CAST_RULES = (
    "characters: 1 to 3 stick-man characters who appear in the story. name (one word), gender: male or female (if a woman is "
    "central to the real story, make her female). Female characters automatically get long hair; male characters get hair "
    "\"short\" or \"bald\". garment: " + "/".join(GARMENTS) + " (era-appropriate: loincloth for prehistoric, tunic/robe for ancient, "
    "dress for women, cape for kings). accessory: " + "/".join(ACCESSORIES) + " (crown for rulers, hat/helmet for workers/soldiers, "
    "beard for old men, flower for young women, glasses for scientists). color: " + "/".join(COLORS) + " (clothes color; different for each character)."
)

STORY_STYLE = """STORYTELLING STYLE (this decides whether people keep watching - follow it strictly):
- Tell it like a gripping story told to a friend, NOT a lecture or a list of facts. Specific people, places, objects and numbers, with small human details (what they felt, said, feared, got wrong).
- Conversational, high-energy, teenager-friendly spoken English. Mix very short punchy sentences with longer ones. Ask the viewer questions. Use "you" and "imagine".
- Keep curiosity loops open: promise something ("but that's not even the strangest part") and pay it off LATER, not immediately.
- Add one light joke, funny comparison or absurd detail in every chapter. Add at least one genuine "wait, WHAT?" twist.
- Never use filler or clichés: no "in today's video", "let's dive in", "welcome", "in conclusion", "did you know", "as we all know", no greetings, no channel intro.
- Every sentence must add NEW information or raise the tension. No repeating, no padding."""

ACCURACY = (
    "ACCURACY (non-negotiable): everything must be TRUE and verifiable. Use only facts you are sure about. For uncertain or "
    "prehistoric details say what evidence suggests ('historians believe', 'the oldest known record', 'according to one account'). "
    "NEVER invent exact dates, names, quotes or numbers. If you are not sure about a detail, leave it out or soften it."
)

OBSCURE = (
    "TOPIC RULE: choose a story that fewer than one in a hundred people have ever heard. Do NOT choose famous trivia "
    "(pyramids, Titanic, Cleopatra, dinosaurs, Tutankhamun, Great Wall, Area 51, Roman basics, Einstein, Nikola Tesla, Napoleon). "
    "It must be a specific, real, documented story with names, places and years you are certain about."
)


def sc_schema():
    return {
        "type": "OBJECT",
        "properties": {
            "narration": {"type": "STRING"},
            "focus": {"type": "INTEGER"},
            "other": {"type": "INTEGER"},
            "other_action": {"type": "STRING", "enum": ACTIONS},
            "action": {"type": "STRING", "enum": ACTIONS},
            "emotion": {"type": "STRING", "enum": EMOTIONS},
            "bg": {"type": "STRING", "enum": BGS},
            "props": {"type": "ARRAY", "items": {"type": "STRING", "enum": PROPS}},
            "label": {"type": "STRING"},
        },
        "required": ["narration", "focus", "other", "other_action", "action", "emotion", "bg", "props", "label"],
    }


CAST_SCHEMA = {
    "type": "ARRAY",
    "items": {"type": "OBJECT", "properties": {
        "name": {"type": "STRING"}, "gender": {"type": "STRING", "enum": ["male", "female"]},
        "hair": {"type": "STRING", "enum": ["short", "bald", "long"]},
        "garment": {"type": "STRING", "enum": GARMENTS}, "accessory": {"type": "STRING", "enum": ACCESSORIES},
        "color": {"type": "STRING", "enum": COLORS}},
        "required": ["name", "gender", "hair", "garment", "accessory", "color"]},
}


def short_schema():
    return {"type": "OBJECT", "properties": {
        "topic": {"type": "STRING"}, "title": {"type": "STRING"}, "description": {"type": "STRING"},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}}, "music_mood": {"type": "STRING", "enum": MOODS},
        "characters": CAST_SCHEMA, "scenes": {"type": "ARRAY", "items": sc_schema()}},
        "required": ["topic", "title", "description", "tags", "music_mood", "characters", "scenes"]}


PLAN_SCHEMA = {"type": "OBJECT", "properties": {
    "topic": {"type": "STRING"}, "title": {"type": "STRING"}, "description": {"type": "STRING"},
    "tags": {"type": "ARRAY", "items": {"type": "STRING"}}, "thumb_text": {"type": "STRING"},
    "music_mood": {"type": "STRING", "enum": MOODS}, "characters": CAST_SCHEMA,
    "chapters": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "beat": {"type": "STRING"}, "hook_end": {"type": "STRING"}}, "required": ["beat", "hook_end"]}}},
    "required": ["topic", "title", "description", "tags", "thumb_text", "music_mood", "characters", "chapters"]}

CHAPTER_SCHEMA = {"type": "OBJECT", "properties": {"scenes": {"type": "ARRAY", "items": sc_schema()}}, "required": ["scenes"]}

FALLBACK = {  # Gemini bilkul na chale to ye (offline) Short banta hai
    "topic": "the first clothes", "title": "Why Did Humans Really Start Wearing Clothes? #Shorts",
    "description": "The surprising reason humans first wore clothes. #Shorts #history #facts",
    "tags": ["history", "facts", "first clothes", "ancient humans", "shorts"], "music_mood": "quirky",
    "characters": [dict(name="Una", gender="female", hair="long", garment="dress", accessory="flower", color="pink"),
                   dict(name="Grog", gender="male", hair="bald", garment="loincloth", accessory="none", color="brown")],
    "scenes": [
        dict(narration="Humans did not start wearing clothes because they were cold.", action="shock", emotion="surprised", focus=0, other=None, other_action="idle", bg="grass", props=["sun", "tree"], label="NOT FOR WARMTH?"),
        dict(narration="Scientists studied the DNA of clothing lice to find out when it began.", action="think", emotion="curious", focus=1, other=None, other_action="idle", bg="white", props=["magnifier", "question"], label=""),
        dict(narration="Those lice split from head lice around one hundred seventy thousand years ago.", action="point", emotion="excited", focus=0, other=1, other_action="idle", bg="orange", props=["calendar", "clock"], label="170,000 YEARS AGO"),
        dict(narration="That means people were wearing something long before the ice age cold arrived.", action="walk", emotion="happy", focus=1, other=None, other_action="idle", bg="desert", props=["mountain", "bird"], label=""),
        dict(narration="So why dress up? Maybe for decoration, status, or protection from insects.", action="dance", emotion="excited", focus=0, other=None, other_action="idle", bg="sky", props=["crown", "crowd"], label=""),
        dict(narration="And the oldest needles ever found are about fifty thousand years old.", action="work", emotion="neutral", focus=1, other=None, other_action="idle", bg="cave", props=["fire", "bone"], label=""),
        dict(narration="Warm clothes came later, and they helped humans spread into freezing lands.", action="run", emotion="scared", focus=0, other=None, other_action="idle", bg="snow", props=["snowflake", "animal"], label=""),
        dict(narration="So the real first clothes were never about warmth. Then what were they about?", action="shrug", emotion="curious", focus=1, other=0, other_action="think", bg="night", props=["moon", "question"], label=""),
    ],
}


# ------------------------------------------------------------------ Gemini calls
def load_history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def ask_gemini(prompt, sch=None, max_out=8192, ground=False):
    """sch ho to JSON (schema), ground=True ho to Google Search wala plain text."""
    last = None
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        cfg = {"temperature": 0.95 if sch else 0.8, "maxOutputTokens": max_out}
        if sch:
            cfg["responseMimeType"] = "application/json"
            cfg["responseSchema"] = sch
        if "2.5-flash" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": 0}
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
        if ground:
            body["tools"] = [{"google_search": {}}]
        for _ in range(2):
            try:
                r = requests.post(url, headers={"x-goog-api-key": API_KEY}, json=body, timeout=180)
                if r.status_code == 200:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    return "".join(p.get("text", "") for p in parts)
                last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
                if r.status_code == 429:
                    time.sleep(20)
            except Exception as e:  # noqa: BLE001
                last = f"{model}: {e}"
            time.sleep(4)
    raise RuntimeError(last)


def parse(text):
    return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())


def with_retries(label, fn, tries=3):
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            print(f"{label} attempt {attempt + 1} failed: {e}")
            time.sleep(3)
    return None


def research(area, recent, long=True):
    """Google Search se asli facts ikatthe karo (grounding). Fail ho to '' (script phir bhi chalti hai)."""
    prompt = f"""Use Google Search. Area: {area}.
{OBSCURE}
Do NOT repeat or resemble these earlier topics: {recent}.
Random seed: {random.randint(1, 10**7)}.
Pick ONE story and verify it with search. Reply in plain text with:
TOPIC: (3-8 words)
FACTS: 18-25 short bullet facts (names, places, exact years, numbers, what happened step by step, the twist, what is still uncertain or disputed).
Only include facts confirmed by sources. Mark anything uncertain with (uncertain)."""
    try:
        return ask_gemini(prompt, None, 6000, ground=True).strip()[:9000]
    except Exception as e:  # noqa: BLE001
        print(f"research skipped: {str(e)[:160]}")
        return ""


# ------------------------------------------------------------------ cleaning
def clean_cast(chars):
    out = []
    for c in (chars or [])[:3]:
        g = c.get("gender") if c.get("gender") in ("male", "female") else "male"
        acc = c.get("accessory") if c.get("accessory") in ACCESSORIES else "none"
        if g == "female" and acc in ("beard", "helmet"):
            acc = "none"
        out.append(dict(
            name=str(c.get("name", "Hero"))[:16], gender=g,
            hair="long" if g == "female" else ("bald" if c.get("hair") == "bald" else "short"),
            garment=c.get("garment") if c.get("garment") in GARMENTS else "tunic", accessory=acc,
            color=c.get("color") if c.get("color") in COLORS else random.choice(COLORS)))
    return out or [dict(name="Hero", gender="male", hair="short", garment="tunic", accessory="none", color="blue")]


def clean_scene(s, ncast):
    nar = re.sub(r"\s+", " ", str(s.get("narration", "")).replace("*", "")).strip()
    assert nar, "empty narration"
    try:
        focus = max(0, min(ncast - 1, int(s.get("focus", 0))))
    except Exception:  # noqa: BLE001
        focus = 0
    try:
        other = int(s.get("other", -1))
    except Exception:  # noqa: BLE001
        other = -1
    other = other if (0 <= other < ncast and other != focus) else None
    props = []
    for p in s.get("props", []) or []:
        if p in PROPS and p not in props:
            props.append(p)
    return dict(
        narration=nar, focus=focus, other=other,
        other_action=s.get("other_action") if s.get("other_action") in ACTIONS else "idle",
        action=s.get("action") if s.get("action") in ACTIONS else "talk",
        emotion=s.get("emotion") if s.get("emotion") in EMOTIONS else "neutral",
        bg=s.get("bg") if s.get("bg") in BGS else "white", props=props[:3],
        label=str(s.get("label", "") or "").strip()[:28])


def spice(scenes):
    """Ek hi action teen baar lagatar na ho (stickman ruka hua na lage)."""
    for i in range(2, len(scenes)):
        if scenes[i]["action"] == scenes[i - 1]["action"] == scenes[i - 2]["action"]:
            scenes[i]["action"] = random.choice([a for a in ACTIONS if a not in ("idle", scenes[i]["action"])])
    return scenes


def common_fields(d):
    d["tags"] = [t for t in d.get("tags", []) if isinstance(t, str)][:12]
    d["music_mood"] = d.get("music_mood") if d.get("music_mood") in MOODS else "quirky"
    d["characters"] = clean_cast(d.get("characters"))
    return d


# ------------------------------------------------------------------ LONG
def gen_long(area, recent):
    notes = research(area, recent)
    notes_block = f"\nVERIFIED RESEARCH NOTES (use these facts; do not contradict them):\n{notes}\n" if notes else ""
    per = round(LONG_TARGET_WORDS / N_CHAPTERS)
    plan_prompt = f"""You plan a LONG YouTube explainer (landscape, about 9-10 minutes) in the animated stick-man style of channels like "Ink Explainer" and "Kurzgesagt".
Area: {area}.
{OBSCURE}
Do NOT repeat or resemble these earlier topics: {recent}.
Random seed: {random.randint(1, 10**7)}.
{notes_block}
{ACCURACY}

Produce the PLAN:
- topic: 3-8 words. title: curiosity-driven, max 80 chars, NO hashtags, makes people NEED to click (e.g. "The Town That Vanished For A Day (And Why Nobody Noticed)").
- description: 3 short paragraphs (what the video reveals, without spoiling the twist) + 6-8 hashtags. tags: 10-15 keywords. thumb_text: 2-4 punchy ALL-CAPS words, max 22 chars.
- music_mood: quirky (funny/light), mysterious, epic (dramatic/war/disaster) or chill.
- {CAST_RULES}
- chapters: EXACTLY {N_CHAPTERS} chapters. Each: beat = 2-3 sentences of what happens in this chapter (concrete facts only); hook_end = the cliffhanger / open question / "but then..." line that ends the chapter and makes viewers stay (the last chapter's hook_end = the closing thought + a question for the comments).
Chapter flow: 1 shocking hook & the world before; 2-3 build-up and first clue; middle chapters escalate with twists, myths vs reality and weird details; second-last = the real surprising WHY / payoff of the biggest open loop; last = modern echo, closing thought, comment question, short invitation to subscribe for more untold stories."""

    def plan():
        d = parse(ask_gemini(plan_prompt, PLAN_SCHEMA, 8192))
        assert len(d["chapters"]) >= 6, "too few chapters"
        return d
    plan_d = with_retries("Gemini plan", plan)
    if not plan_d:
        return None
    plan_d = common_fields(plan_d)
    cast = plan_d["characters"]
    cast_txt = "; ".join(f"{i}: {c['name']} ({c['gender']}, {c['garment']}, {c['accessory']})" for i, c in enumerate(cast))
    chapters = plan_d["chapters"][:N_CHAPTERS + 2]
    outline = "\n".join(f"{i + 1}. {c['beat']}  [ends with: {c['hook_end']}]" for i, c in enumerate(chapters))
    scenes, prev = [], ""
    for ci, ch in enumerate(chapters):
        first, last = ci == 0, ci == len(chapters) - 1
        prompt = f"""You are writing chapter {ci + 1} of {len(chapters)} of the narration for the video "{plan_d['title']}" (topic: {plan_d['topic']}).
{notes_block}
FULL OUTLINE:
{outline}

CAST (use focus/other = these indexes): {cast_txt}

THIS CHAPTER: {ch['beat']}
It must END on this hook: {ch['hook_end']}
{"This is the OPENING: scene 1 is the HOOK, max 18 words, a shocking claim or myth-flip. No greeting, no intro." if first else "Last lines of the previous chapter (continue seamlessly, do NOT recap): " + prev}
{"This is the FINAL chapter: payoff everything, then one thought-provoking question for the comments, then one short line inviting viewers to subscribe for more untold stories." if last else ""}

{STORY_STYLE}
{ACCURACY}
LENGTH: about {per} words of narration in total for this chapter, split into 5 to 8 scenes (each scene 15 to 32 words).
{SCENE_RULES}"""

        def chapter():
            d = parse(ask_gemini(prompt, CHAPTER_SCHEMA, 6000))
            sc = [clean_scene(s, len(cast)) for s in d["scenes"]]
            words = sum(len(s["narration"].split()) for s in sc)
            assert 4 <= len(sc) <= 11, f"scene count {len(sc)}"
            assert per * 0.6 <= words <= per * 1.7, f"word count {words} (want ~{per})"
            return sc
        sc = with_retries(f"Gemini chapter {ci + 1}", chapter)
        if not sc:
            print(f"chapter {ci + 1} fail ho gaya")
            return None
        scenes += sc
        prev = " ".join(s["narration"] for s in sc[-2:])
        time.sleep(2)
    words = sum(len(s["narration"].split()) for s in scenes)
    print(f"long script: {len(chapters)} chapters, {len(scenes)} scenes, {words} words")
    assert words >= LONG_TARGET_WORDS * 0.6, "script bohat chhoti"
    d = dict(plan_d)
    d.pop("chapters", None)
    d["scenes"] = spice(scenes)
    d["title"] = re.sub(r"\s*#shorts\s*", " ", d["title"], flags=re.I).strip()[:95]
    d["thumb_text"] = (d.get("thumb_text") or d["topic"]).upper()[:24]
    return d


# ------------------------------------------------------------------ SHORT
def gen_short(area, recent, long=None):
    teaser = long is not None
    if teaser:
        story = "\n".join(f"{i + 1}. {s['narration']}" for i, s in enumerate(long["scenes"][:40]))
        notes_block = ""
        brief = f"""You write the Shorts TEASER that promotes a long video on the same channel.
Long video title: {long['title']}
Topic: {long['topic']}
The long video's story (scene by scene, for reference):
{story}

TEASER RULES:
- Tell only the FIRST part of this story (setup + the single most surprising fact), told gripping and fast, then STOP at the most curious moment. Do NOT reveal the twist or the answer - leave a strong open loop.
- Last scene = call to action, 10-18 words, must contain the words "full video" and mention the description, e.g. "Want the full story? Watch the full video on my channel, it's linked in the description."
- The scene before the CTA is the cliffhanger line (a question or half-reveal).
- Facts must match the long video exactly. Use this exact cast (same people, same indexes): {json.dumps(long['characters'])}. Return them unchanged in "characters"."""
    else:
        notes = research(area, recent, long=False)
        notes_block = f"\nVERIFIED RESEARCH NOTES (use these facts):\n{notes}\n" if notes else ""
        brief = f"""Area for this video: {area}.
{OBSCURE}
Do NOT repeat or resemble these earlier topics: {recent}.
Random seed: {random.randint(1, 10**7)}.
{notes_block}
{ACCURACY}
STANDALONE RULES:
- SEAMLESS LOOP: the very last sentence must flow naturally back into scene 1 when the video restarts (end with a question or half-thought whose answer or continuation is the hook). No "subscribe", no "follow", no goodbye, no outro.
- Create tension: keep one small open loop ("but here's the weird part") and pay it off before the end."""
    prompt = f"""You write viral YouTube Shorts scripts for an animated stick-man explainer channel (style of "Ink Explainer").

{brief}

COMMON RULES:
- Total narration 90-110 words (about 35-42 seconds spoken, NEVER longer: shorter Shorts get watched to the end). 11 to 13 scenes, each scene ONE short punchy sentence (5-11 words).
- Scene 1 is the HOOK, max 12 words: a shocking claim, a myth-flip or a curiosity gap that makes people unable to swipe away in the first 2 seconds. Start with the most surprising fact, not with background. No greetings, no intro.
- RETENTION: by scene 3 promise a payoff ("and the reason is insane"); around the middle re-hook with a twist or "but it gets worse"; reveal the payoff only in the last third. Every sentence must add NEW information, no filler.
- Write like a real person talking: contractions (it's, they'd), occasional "okay", "wait", "honestly", one funny comparison. No dictionary-style sentences.
- Teenager-friendly, conversational, high-energy spoken English. Short sentences, vary rhythm, one funny detail, occasional exclamation or question. No clichés ("did you know", "let's dive in").
- {CAST_RULES}
- {SCENE_RULES}
- title: max 70 characters, curiosity-driven, ends with " #Shorts". description: 2 sentences plus 5-8 hashtags. tags: 8-12 short keywords. topic: 3-8 words. music_mood: quirky / mysterious / epic / chill."""

    def run():
        d = parse(ask_gemini(prompt, short_schema(), 8192))
        d = common_fields(d)
        d["scenes"] = [clean_scene(s, len(d["characters"])) for s in d["scenes"]]
        n = len(d["scenes"])
        words = sum(len(s["narration"].split()) for s in d["scenes"])
        assert (9 if teaser else 8) <= n <= 16, f"scene count {n}"
        assert 70 <= words <= 135, f"word count {words}"
        if teaser:
            d["topic"], d["characters"] = long["topic"], long["characters"]
            d["teaser"] = True
            last = d["scenes"][-1]["narration"].lower()
            if not ("full" in last and ("video" in last or "story" in last)):
                d["scenes"].append(dict(CTA_FALLBACK))
        d["scenes"] = spice(d["scenes"])
        return d
    return with_retries("Gemini short", run)


# ------------------------------------------------------------------ io
def save_history(hist, d, mode):
    hist.append({"topic": d["topic"], "title": d["title"], "date": datetime.date.today().isoformat(), "mode": mode})
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist[-250:], f, ensure_ascii=False, indent=1)


def dump(d, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def main():
    if MODE not in ("both", "long", "short"):
        sys.exit(f"MODE '{MODE}' galat hai (both / long / short)")
    for p in ("script_long.json", "script_short.json"):
        if os.path.exists(p):
            os.remove(p)
    hist = load_history()
    recent = [h.get("topic", "") for h in hist[-120:]]
    area = random.choice(AREAS)
    long = None
    if MODE in ("both", "long"):
        if not API_KEY:
            sys.exit("GEMINI_API_KEY missing - long video ke liye zaroori hai")
        long = gen_long(area, recent)
        if not long:
            sys.exit("Gemini long script fail - kuch post nahi kiya (dobara run karein)")
        dump(long, "script_long.json")
        print("LONG :", long["title"], f"({len(long['scenes'])} scenes)")
    if MODE == "both":
        short = gen_short(area, recent, long=long)
        if short:
            dump(short, "script_short.json")
            print("SHORT:", short["title"])
        else:
            print("WARNING: teaser Short script nahi bana - sirf long video post hogi")
    elif MODE == "short":
        short = gen_short(area, recent) if API_KEY else None
        if not short:
            print("Gemini unavailable -> fallback script")
            short = FALLBACK
        dump(short, "script_short.json")
        print("SHORT:", short["title"])
    main_script = long or short
    save_history(hist, main_script, MODE)
    print("Topic:", main_script["topic"])


if __name__ == "__main__":
    main()
