"""Gemini se naya script banata hai (story + characters + har scene ki animation directions).

MODE (env):
  both  -> script_long.json (landscape, ~9-10 min) + script_short.json (long ko promote karne wala teaser Short)
  long  -> sirf script_long.json
  short -> sirf script_short.json (standalone Short, loop ending)

Flow:
  1) PITCH   : Gemini 10 story pitches banata hai (hook + twist + scores); code best-scoring, sabse pakki sachchi pitch chunta hai.
  2) VERIFY  : Google Search se us pitch ki fact-check + research notes (jhooti nikli to agli pitch).
  3) PLAN    : title / thumbnail text / cast / chapters (long).
  4) WRITE   : har chapter alag, ek hi NARRATOR ki awaaz mein.
  5) POLISH  : "script doctor" pass - hook aur jokes tez karta hai.

LIPSYNC RULE: screen par sirf NARRATOR boy ka munh chalta hai. Female / animal / object / actor male sirf act karte hain.
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
LONG_TARGET_WORDS = int(os.environ.get("LONG_TARGET_WORDS", "1500"))
N_CHAPTERS = max(8, min(12, round(LONG_TARGET_WORDS / 150)))
THINK = int(os.environ.get("GEMINI_THINK", "1024"))

CTA_FALLBACK = {
    "narration": "Want the full story? Watch the full video on my channel. It's linked in the description.",
    "action": "point", "emotion": "excited", "focus": 0, "bg": "white", "props": ["crowd", "exclaim"],
    "label": "FULL VIDEO", "other": None, "other_action": "idle",
}

AREAS = [
    "a true story where one tiny mistake (a typo, a wrong turn, a lost key, a missed message) caused something enormous",
    "a real heist, scam, con or impostor so audacious it sounds scripted (documented, with names and dates)",
    "a real survival story where someone should have died but didn't, and the bizarre reason why",
    "an ordinary everyday thing (a food, a habit, a rule, a word, a button) with a shockingly weird origin story",
    "a real law, punishment, tradition or trial from history that sounds like a joke but was completely serious",
    "animals in real history or science doing things that sound impossible but are documented",
    "a forgotten person who did something wild, brave or ridiculous and got zero credit",
    "a historical 'first' with a funny or dark twist",
    "a real mystery that was solved by one tiny, almost silly clue",
    "a disaster or near-miss that almost changed the world, saved by pure luck or one stubborn person",
    "a human body, brain or space fact that feels fake but is proven, told through one real experiment",
    "an absurd engineering, building or inventing attempt that failed hilariously or worked against all odds",
    "a time a whole town, country or crowd lost its mind over something silly - documented",
    "weird money stories: fake money, giant coins, a bank that did something insane, a day a currency became worthless",
    "extreme places and the real, almost sci-fi things that happened there",
    "the origin story of a technology, a video game, a gadget or an internet thing everyone uses without knowing how it started",
    "food and drink origin stories: accidents, bets, banned foods, the first person who tried something gross",
    "a cheating or rule-breaking scandal in sports, games or exams that was ingenious or ridiculous (documented)",
    "how an ancient or medieval culture solved a modern-sounding problem in a surprising way",
    "a lost skill or technology humans forgot, and the specific site or discovery that proved it existed",
    "the dumbest real war, battle, feud or dispute in history, started over something tiny",
    "verified unbelievable coincidences from real history",
    "a famous everyday product or brand that almost never existed",
    "a forgotten scientific mistake everyone believed for centuries and the moment it finally cracked",
]

NARRATOR = """NARRATOR (this is critical): the ENTIRE video is told by ONE single narrator - a witty, curious, slightly dramatic young guy telling his best friend the wildest thing he just learned. Same voice, same personality from the first word to the last. His mouth is the ONLY mouth that moves on screen (he appears as a small sprite in the corner).
- The on-screen story characters NEVER speak in their own voice. The narrator describes what they do, say or think. If a character's words matter, the narrator quotes them in the same voice.
- FEMALE characters, ANIMALS and OBJECTS never move their mouths. They act but they are silent. Always have the narrator report what she said.
- EXPLAINING STYLE: ONE idea per line, a concrete everyday comparison for anything abstract, and he names the feeling out loud. His own emotion shifts with the story: amazed, dry, scared, outraged, sad, smug.
- The narrator may use "I" for his own reactions and "you" for the viewer. He never changes speaker, gender or persona."""

TTS_RULES = """WRITE FOR THE EAR (a text-to-speech voice reads this): plain spoken words and contractions, commas and full stops to control pacing, a question mark for questions, an exclamation mark only now and then. NO parentheses, dashes, colons, semicolons, slashes, abbreviations, digits or symbols in the narration: spell every number and year as spoken words. Avoid hard-to-pronounce foreign names unless essential. DELIVERY: put the strongest word at the END of each sentence, use tiny fragments for punches, build tension with two or three short lines and then ONE longer line for the reveal, and ask a short question right before a reveal."""

SCENE_RULES = f"""SCENE FIELDS (the animation is drawn by code from these - choose them carefully):
- narration: 1 or 2 spoken sentences in the narrator's voice (plain text, no emojis/hashtags/stage directions).
- focus: index (0-based) of the character who is the main ACTOR in this scene. This character NEVER moves its mouth.
- other: index of a SECOND character shown in this scene, or -1 for none. other_action: that character's action ("idle" for listening).
- action (what the focus character does): {", ".join(ACTIONS)}. Vary them: NEVER the same action more than twice in a row.
- emotion: {", ".join(EMOTIONS)} (must match the narration's mood).
- bg: one of {", ".join(BGS)}. Use "white" for about a third of the scenes; pick the rest to match place/time.
- props: 0 to 2 items from [{", ".join(PROPS)}] that literally show what the narration talks about. Keep it SIMPLE: ONE clear prop per scene. The picture should make the line clearer or funnier.
- EMOTION ARC (very important): the emotion drives the WHOLE body, camera and lighting, so use it deliberately. Change it at least every two scenes, never the same emotion three scenes in a row, and avoid "neutral" unless it is a calm explanation. Typical beats: curious (setup) -> scared or angry (stakes) -> surprised (twist) -> sad or excited (result) -> happy or curious (punchline). It must match what the narrator feels in that exact line.
- label: OPTIONAL big sticker text (max 4 words). Use it in about one scene out of four, empty string otherwise."""

CAST_RULES = (
    "characters: 1 to 3 stick-man characters who appear in the story as ACTORS on screen (the narrator does all the talking; "
    "these characters never move their mouths, they only act). "
    "name (one word), gender: male or female (if a woman is central to the real story, make her female). Female characters automatically get long hair; male characters get hair "
    "\"short\" or \"bald\". garment: " + "/".join(GARMENTS) + " (era-appropriate: loincloth for prehistoric, tunic/robe for ancient, "
    "dress for women, cape for kings). accessory: " + "/".join(ACCESSORIES) + " (crown for rulers, hat/helmet for workers/soldiers, "
    "beard for old men, flower for young women, glasses for scientists). color: " + "/".join(COLORS) + " (clothes color; different for each character)."
)

STORY_STYLE = """STORYTELLING STYLE (this decides whether people keep watching - follow it strictly):
- Voice: high-energy, a little sarcastic, genuinely amazed. NOT a teacher, NOT a documentary, NOT a list of facts. Tell it like gossip about the most unbelievable thing that really happened.
- Every scene must do at least ONE of: reveal something new, raise the stakes, flip an expectation, or land a joke. If a line does none of these, cut it.
- Be specific and human: exact names, objects, numbers, what people felt, feared, said and got hilariously wrong. Put the viewer INSIDE the moment.
- Stakes first: make clear what could be lost, who could die, how much money or pride is on the line, and why anyone should care.
- Humor comes from the real facts: a dry modern comparison or absurd detail every few scenes. Never fake-cringe, never explain the joke.
- Rhythm for the ear: mix tiny punches with longer flowing lines. Talk to the viewer: "you", "picture this", rhetorical questions, and now and then "okay, so", "honestly", "I'm not joking".
- Curiosity loops: tease something early, delay it, then pay it off BIGGER than promised. Re-hook every ten seconds or so.
- Land the ending with a punchline, a chilling thought or a callback to the hook. Never a summary.
- BANNED phrases: "in today's video", "let's dive in", "welcome", "in conclusion", "did you know", "as we all know", "buckle up", "get ready", "you won't believe", "mind-blowing", "game changer", "fascinating", "incredible", "little did they know", "fast forward", "in a world where", "imagine a world", "tapestry", "testament", "delve", "journey", "but wait". No greetings, no channel intro, no emojis.
- HOOK (first line of any video, Short or chapter): open INSIDE the most extreme moment or with a contradiction, never with background. Max 12 words, one clear picture the viewer can SEE, a question in the brain that only the end can answer."""

ACCURACY = (
    "ACCURACY (non-negotiable): everything must be TRUE and verifiable. Use only facts you are sure about. For uncertain or "
    "prehistoric details say what evidence suggests ('historians believe', 'the oldest known record', 'according to one account'). "
    "NEVER invent exact dates, names, quotes or numbers. If you are not sure about a detail, leave it out or soften it. "
    "Funny is welcome, but the facts under the jokes must be real."
)

TOPIC_RULE = (
    "TOPIC RULE: pick a story that makes a stranger stop scrolling: surprising, emotional or funny, easy to SEE as drawings, with a clear twist "
    "and one concrete 'wait, WHAT?' moment. Most viewers should not have heard this exact story. Skip the most overused topics "
    "(pyramids, Titanic, Cleopatra, dinosaurs, Tutankhamun, Great Wall, Area 51, Roman basics, Einstein, Nikola Tesla, Napoleon, Tulip mania) "
    "unless you have a genuinely new angle. It must be a specific, real, documented story with names, places and years you are certain about."
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

PITCH_SCHEMA = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "topic": {"type": "STRING"}, "hook": {"type": "STRING"}, "twist": {"type": "STRING"}, "visual": {"type": "STRING"},
    "curiosity": {"type": "INTEGER"}, "shock": {"type": "INTEGER"}, "relatable": {"type": "INTEGER"},
    "certainty": {"type": "INTEGER"}, "hook_power": {"type": "INTEGER"}},
    "required": ["topic", "hook", "twist", "visual", "curiosity", "shock", "relatable", "certainty", "hook_power"]}}

POLISH_SCHEMA = {"type": "OBJECT", "properties": {"narrations": {"type": "ARRAY", "items": {"type": "STRING"}}},
                 "required": ["narrations"]}

FALLBACK = {
    "topic": "the first clothes", "title": "Humans Did NOT Invent Clothes To Stay Warm #Shorts",
    "description": "The real reason humans first got dressed, and the tiny bugs that gave it away. #Shorts #history #facts",
    "tags": ["history", "facts", "first clothes", "ancient humans", "shorts"], "music_mood": "quirky",
    "characters": [dict(name="Una", gender="female", hair="long", garment="dress", accessory="flower", color="pink"),
                   dict(name="Grog", gender="male", hair="bald", garment="loincloth", accessory="none", color="brown")],
    "scenes": [
        dict(narration="Humans did not invent clothes to stay warm.", action="shock", emotion="surprised", focus=0, other=None, other_action="idle", bg="grass", props=["sun", "tree"], label="NOT FOR WARMTH?"),
        dict(narration="And the proof comes from lice. Tiny, disgusting, clothes-loving lice.", action="think", emotion="curious", focus=1, other=None, other_action="idle", bg="white", props=["magnifier", "question"], label=""),
        dict(narration="Body lice can only live in clothing. So when did they appear?", action="point", emotion="curious", focus=0, other=1, other_action="idle", bg="orange", props=["magnifier", "calendar"], label=""),
        dict(narration="Scientists checked their DNA. One study says around one hundred seventy thousand years ago.", action="work", emotion="excited", focus=1, other=None, other_action="idle", bg="white", props=["chart", "clock"], label="170,000 YEARS AGO"),
        dict(narration="That is way before the last ice age. These people were dressed, and nobody was cold yet.", action="shock", emotion="surprised", focus=0, other=None, other_action="idle", bg="snow", props=["snowflake", "crowd"], label=""),
        dict(narration="So why get dressed? Honestly, nobody knows for sure.", action="shrug", emotion="curious", focus=1, other=0, other_action="think", bg="white", props=["question"], label=""),
        dict(narration="Maybe decoration. Maybe status. Maybe keeping bugs off their skin.", action="dance", emotion="excited", focus=0, other=None, other_action="idle", bg="sky", props=["crown", "bird"], label=""),
        dict(narration="The oldest needles ever found are about fifty thousand years old.", action="work", emotion="neutral", focus=1, other=None, other_action="idle", bg="cave", props=["fire", "bone"], label="50,000 YEARS OLD"),
        dict(narration="Warm clothes came later, and they let humans walk into freezing lands.", action="run", emotion="scared", focus=0, other=None, other_action="idle", bg="snow", props=["snowflake", "animal"], label=""),
        dict(narration="So the very first outfit was basically a flex. And the cold? It just got lucky.", action="celebrate", emotion="happy", focus=1, other=0, other_action="idle", bg="orange", props=["crown", "heart"], label=""),
        dict(narration="Which makes sense, because it was never about staying warm.", action="talk", emotion="neutral", focus=0, other=None, other_action="idle", bg="night", props=["moon", "stars"], label=""),
    ],
}


def load_history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def ask_gemini(prompt, sch=None, max_out=8192, ground=False, think=None):
    last = None
    budget = THINK if think is None else think
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        cfg = {"temperature": 0.95 if sch else 0.8, "maxOutputTokens": max_out}
        if sch:
            cfg["responseMimeType"] = "application/json"
            cfg["responseSchema"] = sch
        if "2.5-flash" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": budget}
            cfg["maxOutputTokens"] = max_out + budget
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
        if ground:
            body["tools"] = [{"google_search": {}}]
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


def pitch_score(p):
    def n(k):
        try:
            return max(0, min(10, int(p.get(k, 0))))
        except Exception:
            return 0
    return n("curiosity") + n("shock") + n("relatable") + 2 * n("certainty") + 2 * n("hook_power")


def pitch_topics(area, recent):
    prompt = f"""You are the head of content at a viral YouTube channel with millions of subscribers.
Brainstorm 10 DIFFERENT story pitches for this angle: {area}.
{TOPIC_RULE}
Do NOT repeat or resemble these earlier topics: {recent}.
Random seed: {random.randint(1, 10**7)}.
For each pitch give:
- topic: 3-8 words.
- hook: the single most shocking TRUE sentence of the story, max 15 words.
- twist: the surprising turn or payoff, one sentence.
- visual: what could be shown as funny stick-man drawings, one sentence.
- hook_power: honest 1-10.
- curiosity, shock, relatable, certainty: honest integer scores 1-10.
Only pitch stories you are certain are real. Prefer stories with ONE human at the centre, a clear thing at stake, an emotional turn and an object or place that is easy to draw. The audience is English-speaking viewers aged 15-35 worldwide. Be a harsh judge: most pitches should NOT score 9 or 10."""
    d = parse(ask_gemini(prompt, PITCH_SCHEMA, 6000))
    seen = {t.lower() for t in recent}
    ok = [p for p in d if isinstance(p, dict) and p.get("topic") and p["topic"].lower() not in seen and pitch_score(p) > 0]
    good = [p for p in ok if int(p.get("certainty", 0)) >= 7] or ok
    assert good, "no usable pitch"
    good.sort(key=pitch_score, reverse=True)
    return good[:3]


def verify_topic(p):
    prompt = f"""Use Google Search to fact-check this story pitch and collect the real facts.
TOPIC: {p['topic']}
CLAIMED HOOK: {p['hook']}
CLAIMED TWIST: {p['twist']}
Reply in plain text. The FIRST line must be exactly "VERIFIED: YES" or "VERIFIED: NO" (then one line why and stop).
If YES, continue with:
FACTS: 18-25 short bullet facts. Only facts confirmed by sources. Mark anything uncertain with (uncertain).
If the sources word the hook or twist differently from the claim, add a line "CORRECTION:" with the accurate version."""
    try:
        txt = ask_gemini(prompt, None, 6000, ground=True, think=0).strip()
    except Exception as e:
        print(f"verify skipped: {str(e)[:160]}")
        return "skip", ""
    if re.match(r"\W*VERIFIED:\s*NO", txt, re.I):
        return "no", txt[:300]
    return "ok", txt[:9000]


def choose_topic(area, recent):
    pitches = with_retries("Gemini pitch", lambda: pitch_topics(area, recent), tries=2) or []
    pick, notes = None, ""
    for p in pitches:
        print(f"pitch [{pitch_score(p)}]: {p['topic']} - {p['hook']}")
        status, txt = verify_topic(p)
        print(f"  verify: {status}")
        if status == "no":
            continue
        pick, notes = p, (txt if status == "ok" else "")
        break
    if pick is None and pitches:
        pick = pitches[0]
    if pick is None:
        return (f"Area: {area}.\n{TOPIC_RULE}\nDo NOT repeat or resemble these earlier topics: {recent}.\n"
                f"Random seed: {random.randint(1, 10**7)}.", "")
    block = (f"CHOSEN STORY (already picked, do not change it): {pick['topic']}\n"
             f"Hook (the most shocking true line): {pick['hook']}\nTwist / payoff: {pick['twist']}\n"
             f"What can be drawn: {pick['visual']}")
    notes_block = f"\nVERIFIED RESEARCH NOTES (use these facts; do not contradict them):\n{notes}\n" if notes else ""
    return block, notes_block


def punch_up(scenes, kind, title, max_words, extra=""):
    n = len(scenes)
    lines = "\n".join(f"{i + 1}. {s['narration']}" for i, s in enumerate(scenes))
    prompt = f"""You are a ruthless script doctor for viral YouTube {kind}s. Video title: "{title}".
Below is the current narration, one numbered line per scene (each scene is a drawing, so every line must keep its scene's meaning):
{lines}

YOUR JOB: rewrite EVERY line so it is funnier, punchier, more vivid and more gripping, in the voice of ONE witty young male narrator. Silently brainstorm several versions of the opening line and use the strongest. Cut every boring, generic or filler word. Make the stakes clearer, make numbers concrete, make transitions feel like a story, and add a dry joke or sharp comparison where the facts allow.
HARD RULES:
- Return EXACTLY {n} lines, same order, one per scene. Each line keeps the FACTS and the meaning of its scene.
- Each line at most {max_words} words. Total length stays within 20 percent of the original.
- FEMALE characters / animals / objects never speak aloud. If a line needs to quote a woman, write it as the narrator reporting it.
- {extra}
{NARRATOR}
{STORY_STYLE}
{TTS_RULES}"""

    def run():
        d = parse(ask_gemini(prompt, POLISH_SCHEMA, 6000, think=2048))
        out = [re.sub(r"\s+", " ", str(x).replace("*", "")).strip() for x in d["narrations"]]
        assert len(out) == n, f"polish line count {len(out)} != {n}"
        assert all(out), "polish gave an empty line"
        wo = sum(len(s["narration"].split()) for s in scenes)
        wn = sum(len(x.split()) for x in out)
        assert 0.75 * wo <= wn <= 1.3 * wo, f"polish word count {wn} vs {wo}"
        return out
    res = with_retries(f"Gemini polish ({kind})", run, tries=2)
    if not res:
        return scenes
    for s, new in zip(scenes, res):
        s["narration"] = new
    return scenes


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
    except Exception:
        focus = 0
    try:
        other = int(s.get("other", -1))
    except Exception:
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
        bg=s.get("bg") if s.get("bg") in BGS else "white", props=props[:2],
        label=str(s.get("label", "") or "").strip()[:28])


SYNC_MAP = {
    "run": ["run", "ran", "running", "chase", "chased", "escape", "escaped", "fled", "flee", "dash", "rushed", "sprinted"],
    "walk": ["walk", "walked", "walking", "marched", "journey", "trek", "wandered"],
    "jump": ["jump", "jumped", "leap", "leapt", "vaulted", "hopped"],
    "hide": ["hide", "hid", "hiding", "snuck", "sneak", "crept", "in hiding"],
    "celebrate": ["celebrate", "celebrated", "won", "winning", "victory", "cheered", "party", "triumph"],
    "shock": ["shock", "shocked", "stunned", "could not believe", "jaw dropped", "froze", "frozen", "appalled"],
    "sad": ["sad", "cried", "crying", "grief", "mourned", "died", "death", "tears", "wept"],
    "think": ["think", "thought", "wondered", "puzzled", "realized", "realised", "scientists", "researchers"],
    "work": ["work", "worked", "built", "building", "dug", "digging", "wrote", "writing", "crafted", "cooked", "forged"],
    "dance": ["dance", "danced", "dancing", "partied"],
    "point": ["pointed", "pointing", "showed", "explained", "declared", "announced"],
    "shrug": ["shrugged", "no one knows", "nobody knows", "unclear", "mystery", "mysterious"],
}

EMO_KEYS = {
    "sad": ["died", "death", "dead", "killed", "lost everything", "cried", "tears", "funeral", "never saw", "alone"],
    "angry": ["stole", "stolen", "lied", "cheated", "scam", "betrayed", "furious", "outraged", "banned", "punished", "refused"],
    "scared": ["danger", "deadly", "panic", "terrified", "trapped", "chased", "silence", "dark", "fear", "ticking"],
    "surprised": ["turns out", "suddenly", "twist", "impossible", "shocking", "except", "wait", "actually"],
    "excited": ["won", "jackpot", "finally", "worked", "success", "record", "saved", "discovered", "genius"],
}


def sync_emotion(sc):
    if sc.get("emotion") != "neutral":
        return sc
    nar = sc["narration"].lower()
    for emo, keys in EMO_KEYS.items():
        if any(k in nar for k in keys):
            sc["emotion"] = emo
            return sc
    if nar.rstrip().endswith("?"):
        sc["emotion"] = "curious"
    return sc


def sync_action(sc):
    nar = sc["narration"].lower()
    generic = sc["action"] in ("talk", "idle", "walk", "work", "think", "point", "shrug")
    if not generic:
        return sc
    for act, keys in SYNC_MAP.items():
        if any(k in nar for k in keys):
            sc["action"] = act
            break
    return sc


def spice(scenes):
    for i in range(2, len(scenes)):
        if scenes[i]["action"] == scenes[i - 1]["action"] == scenes[i - 2]["action"]:
            scenes[i]["action"] = random.choice([a for a in ACTIONS if a not in ("idle", scenes[i]["action"])])
    for i in range(2, len(scenes)):
        if scenes[i]["emotion"] == scenes[i - 1]["emotion"] == scenes[i - 2]["emotion"]:
            scenes[i]["emotion"] = {"neutral": "curious", "happy": "excited", "curious": "surprised", "excited": "happy",
                                    "surprised": "curious", "sad": "neutral", "angry": "scared", "scared": "angry"}.get(scenes[i]["emotion"], "curious")
    return scenes


def common_fields(d):
    d["tags"] = [t for t in d.get("tags", []) if isinstance(t, str)][:12]
    d["music_mood"] = d.get("music_mood") if d.get("music_mood") in MOODS else "quirky"
    d["characters"] = clean_cast(d.get("characters"))
    return d


def gen_long(area, recent):
    topic_block, notes_block = choose_topic(area, recent)
    per = round(LONG_TARGET_WORDS / N_CHAPTERS)
    plan_prompt = f"""You plan a LONG YouTube explainer (landscape, about 9-10 minutes) in the animated stick-man style.
{topic_block}
{notes_block}
{ACCURACY}

Produce the PLAN:
- topic: 3-8 words. title: curiosity-driven, max 80 chars, NO hashtags. description: 3 short paragraphs + 6-8 hashtags. tags: 10-15 keywords. thumb_text: 2-4 punchy ALL-CAPS words, max 22 chars.
- music_mood: quirky (funny/light), mysterious, epic (dramatic/war/disaster) or chill.
- {CAST_RULES}
- chapters: EXACTLY {N_CHAPTERS} chapters. Each: beat = 2-3 sentences of what happens in this chapter; hook_end = the cliffhanger line that ends the chapter.
Chapter flow: 1 cold-open hook, 2-3 build-up and first clue; middle chapters escalate with twists; second-last = the real payoff; last = modern echo, punchline, comment question, one short line inviting viewers to subscribe."""

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
{"This is the OPENING: scene 1 is the HOOK, max 18 words. No greeting, no intro, no 'today'." if first else "Last lines of the previous chapter (continue seamlessly, do NOT recap): " + prev}
{"This is the FINAL chapter: payoff everything, land one killer punchline, then one question for the comments, then one short line inviting viewers to subscribe." if last else ""}

{NARRATOR}
{STORY_STYLE}
{TTS_RULES}
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
        if first:
            sc = punch_up(sc, "long video", plan_d["title"], 34,
                          "Scene 1 is the opening hook: max 18 words, an unscrollable shocking claim, no greeting. The chapter must still end on the same cliffhanger.")
        scenes += sc
        prev = " ".join(s["narration"] for s in sc[-2:])
        time.sleep(2)
    words = sum(len(s["narration"].split()) for s in scenes)
    print(f"long script: {len(chapters)} chapters, {len(scenes)} scenes, {words} words")
    assert words >= LONG_TARGET_WORDS * 0.6, "script bohat chhoti"
    d = dict(plan_d)
    d.pop("chapters", None)
    d["scenes"] = [sync_emotion(sync_action(s)) for s in scenes]
    d["scenes"] = spice(d["scenes"])
    d["title"] = re.sub(r"\s*#shorts\s*", " ", d["title"], flags=re.I).strip()[:95]
    d["thumb_text"] = (d.get("thumb_text") or d["topic"]).upper()[:24]
    return d


def gen_short(area, recent, long=None):
    teaser = long is not None
    if teaser:
        story = "\n".join(f"{i + 1}. {s['narration']}" for i, s in enumerate(long["scenes"][:40]))
        brief = f"""You write the Shorts TEASER that promotes a long video on the same channel.
Long video title: {long['title']}
Topic: {long['topic']}
The long video's story (scene by scene, for reference):
{story}

TEASER RULES:
- Tell only the FIRST part of this story (setup + the single most surprising fact), told gripping and fast, then STOP at the most curious moment. Do NOT reveal the twist.
- Last scene = call to action, 10-18 words, must contain the words "full video" and mention the description.
- The scene before the CTA is the cliffhanger line.
- Facts must match the long video exactly. Use this exact cast (same people, same indexes): {json.dumps(long['characters'])}. Return them unchanged in "characters"."""
    else:
        topic_block, notes_block = choose_topic(area, recent)
        brief = f"""{topic_block}
{notes_block}
{ACCURACY}
STANDALONE RULES:
- SEAMLESS LOOP: the very last sentence must flow naturally back into scene 1 when the video restarts. No "subscribe", no "follow", no goodbye, no outro.
- Create tension: keep one small open loop and pay it off before the end."""
    prompt = f"""You write viral YouTube Shorts scripts for an animated stick-man explainer channel.

{brief}

COMMON RULES:
- Total narration 95-115 words (about 35-42 seconds spoken, NEVER longer). 12 to 14 scenes, each scene ONE short punchy sentence (5-11 words).
- Scene 1 is the HOOK, max 12 words. No greetings, no intro.
- RETENTION: by scene 3 promise a payoff; around the middle re-hook with a twist. Every sentence must add NEW information, raise the stakes or land a joke. No filler.
- Include exactly one genuinely funny line and one "wait, WHAT?" moment.
- title: max 70 characters, ends with " #Shorts". description: 2 sentences plus 5-8 hashtags. tags: 8-12 short keywords. topic: 3-8 words. music_mood: quirky / mysterious / epic / chill.
{NARRATOR}
{STORY_STYLE}
{TTS_RULES}
- {CAST_RULES}
- {SCENE_RULES}"""

    def run():
        d = parse(ask_gemini(prompt, short_schema(), 8192))
        d = common_fields(d)
        d["scenes"] = [sync_emotion(sync_action(clean_scene(s, len(d["characters"])))) for s in d["scenes"]]
        n = len(d["scenes"])
        words = sum(len(s["narration"].split()) for s in d["scenes"])
        assert (9 if teaser else 8) <= n <= 16, f"scene count {n}"
        assert 70 <= words <= 135, f"word count {words}"
        return d
    d = with_retries("Gemini short", run)
    if not d:
        return None
    if teaser:
        d["topic"], d["characters"] = long["topic"], long["characters"]
        d["teaser"] = True
        body = d["scenes"][:-1]
        punch_up(body, "YouTube Short", d["title"], 14,
                 "This is a teaser: keep the open loop, do NOT reveal the twist. The last line you get is the cliffhanger.")
    else:
        punch_up(d["scenes"], "YouTube Short", d["title"], 14,
                 "Scene 1 is the hook: max 12 words. The last line must loop back into scene 1 with a punchline or half-thought. Total stays under 120 words.")
    if teaser:
        last = d["scenes"][-1]["narration"].lower()
        if not ("full" in last and ("video" in last or "story" in last)):
            d["scenes"].append(dict(CTA_FALLBACK))
    d["scenes"] = spice(d["scenes"])
    return d


def save_history(hist, d, mode):
    key = d["topic"].strip().lower()
    if any(h.get("topic", "").strip().lower() == key for h in hist):
        return
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
    print("Angle:", area)
    long = None
    used_fallback = False
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
            print("Gemini unavailable -> fallback script (history mein save nahi hogi)")
            short, used_fallback = FALLBACK, True
        dump(short, "script_short.json")
        print("SHORT:", short["title"])
    main_script = long or short
    if not used_fallback:
        save_history(hist, main_script, MODE)
    print("Topic:", main_script["topic"])


if __name__ == "__main__":
    main()
