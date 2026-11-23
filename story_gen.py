"""Gemini se har run NAYI "engineering & science suspense" story (jaise "Why Perfect Railroads Don't Work"):
asli engineering failures, physics paradoxes, historical design mysteries; 2-4 fixed characters, 4-8 locations, har scene ka cast.
Har run par topic RANDOM: category + starting idea + twist-type + protagonist + hook-style (aur purane used topics repeat nahi hote).
Output: script.json (video ke liye) + story_plan.md (padhne wala plan)."""
import copy
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
HISTORY, OUT, PLAN = "history.json", "script.json", "story_plan.md"

# ---- har run mein random ingredients: category -> starting idea (asli, documented cases) + twist-type + protagonist + hook-style + title-format
# Naya topic jodna ho to bas SEEDS ki kisi category mein ek line add karo. Seeds sirf "shuruaati idea" hain: Gemini unhe badal/behtar bana sakta hai.
SEEDS = {
    "engineering failures": [
        "the Tacoma Narrows Bridge twisting itself apart in 1940",
        "the London Millennium Bridge that wobbled on opening day",
        "the Hyatt Regency skywalk collapse caused by one changed rod detail",
        "the de Havilland Comet airliners and their square windows",
        "the Liberty ships that cracked in half in cold water",
        "the warship Vasa that sank minutes after launch in 1628",
        "the Citicorp Center skyscraper and the secret fix on its bolts",
        "the Quebec Bridge that fell twice while being built",
        "the Boston Hancock Tower whose windows kept falling out",
        "the Mars Climate Orbiter lost to a units mix-up",
        "the Leaning Tower of Pisa and the surprising way it was straightened",
        "the Sydney Opera House roof that nobody knew how to build",
    ],
    "physics paradoxes & counter-intuitive science": [
        "Braess's paradox: adding a road makes every traffic jam worse",
        "why train wheels are cone-shaped, not flat, and how that steers the train",
        "why a hole in a parachute makes it more stable",
        "why the tiny hole in an airplane window is essential",
        "why the Eiffel Tower is taller in summer than in winter",
        "why long steel rails suddenly buckle on a hot day",
        "why skyscrapers hide a giant swinging weight at the top",
        "why dams are curved and not straight",
        "why the Hoover Dam had cooling pipes inside its concrete",
        "why a suspension bridge cable hangs in a precise curve",
        "why ships made of steel float but a small steel ball sinks",
    ],
    "historical design mysteries": [
        "how Egyptians dragged giant pyramid stones across desert sand",
        "how Brunelleschi built the Florence dome without a wooden frame",
        "why Roman concrete harbours are still standing after 2000 years",
        "the Antikythera mechanism, an ancient gear computer",
        "how Roman aqueducts pushed water uphill with siphons",
        "the Inca rope bridge that is rebuilt from grass every year",
        "why Gothic cathedrals needed flying buttresses",
        "the first Hagia Sophia dome that fell and how the second one survived",
        "how the Panama Canal beat the sea with locks instead of digging level",
        "how Dutch engineers keep a country below sea level dry",
        "the Great Pyramid's nearly perfect alignment to north",
        "how builders raised the Bell Rock Lighthouse on a reef covered by every tide",
    ],
    "rival approaches & technical showdowns": [
        "Brunel's wide-gauge railway against the narrow standard gauge",
        "Edison's direct current against Westinghouse and Tesla's alternating current",
        "Langley's government-funded Aerodrome against the Wright brothers' bicycle shop",
        "how the Gotthard tunnel crews digging from both ends met almost perfectly in the middle",
        "the elevator brake that Otis tested by cutting his own rope",
        "why Concorde grew longer in flight because of heat",
        "the lighthouse builders who copied an oak tree's shape to survive storms",
        "Frank Whittle's jet engine that the establishment ignored for years",
        "why the Hindenburg was filled with hydrogen instead of helium",
        "Davy's miners' safety lamp against George Stephenson's rival lamp",
        "why early skyscrapers in Chicago sank into the mud",
        "the race to build a tunnel under the English Channel from two sides",
    ],
    "everyday tech with a hidden secret": [
        "why railway tracks sit on sharp gravel and not smooth stone",
        "why manhole covers are round",
        "why tall chimneys are tapered and wrapped with spiral fins",
        "why power lines sag and why they are never pulled tight",
        "why bridge expansion joints look like giant metal teeth",
        "why airplane wings flex up and survive turbulence",
        "why elevators in tall towers have giant counterweights",
        "why a ship's anchor chain is much heavier than the anchor needs",
        "why tunnels are rarely built with square roofs",
        "why a building survives an earthquake by swaying instead of resisting",
        "why a bicycle stays upright and a standing bicycle falls",
    ],
}
TWISTS = [
    "the obvious fix makes the problem worse", "a hidden physical law nobody respected decides everything",
    "the cheaper or older-looking approach quietly wins", "one tiny overlooked detail (a bolt, a window shape, a rope) flips the result",
    "the experts were measuring the wrong thing", "the problem only appears at scale or after time passes",
    "the rival approach that looked foolish turns out to be correct", "the failure creates a rule every engineer follows today",
]
PROTAGONISTS = [
    "a lone engineer nobody listens to", "a young apprentice who spots the flaw", "a stubborn foreman against the head office",
    "a night-shift inspector who notices something odd", "two rival designers with opposite ideas", "a veteran builder everyone calls old-fashioned",
    "a small team racing a brutal deadline", "a curious worker who asks one uncomfortable question",
]
HOOKS = [
    "a mind-breaking puzzle question", "a high-stakes moment seconds before disaster", "a counter-intuitive fact stated flatly",
    "an impossible-sounding comparison or number", "a bold claim that sounds wrong but is true",
]
FORMATS = [
    "Title like 'Why Perfect X Don't Work'", "Title like 'The Hidden Law Behind X'", "Title like 'X Should Have Worked. It Didn't.'",
    "Title like 'What Really Happened To X'", "Title like 'The Engineer Who Was Right'", "Title like 'The Tiny Detail That Broke X'",
]
ANIMS = ["zoom_in", "zoom_out", "slow_zoom_out", "push_in", "pan_left", "pan_right", "shake", "drift"]
TRANS = ["cut", "flash", "fade", "glitch"]
SECTIONS = ["HOOK", "BODY", "TWIST"]
SFX = ["none", "whoosh", "thud", "rise", "gasp", "knock", "sparkle", "alarm", "buzz", "scratch", "gulp"]
MOODS = ["quirky", "chill", "mysterious", "epic"]
# ---- characters (rick.py ke options)
ACTIONS = ["talk", "idle", "smile", "listen", "point", "shock", "scream", "celebrate", "shrug", "think", "facepalm", "laugh", "angry",
           "hold", "wave", "walk", "run", "sad", "sleep"]
EMOS = ["neutral", "happy", "smug", "angry", "surprised", "scared", "sad", "laughing", "sleepy", "confused", "excited", "evil", "worried", "proud", "cry"]
SHIRT_C = ["yellow", "red", "blue", "green", "orange", "purple", "teal", "pink", "gray", "black", "white", "brown", "navy"]
HAIR_C = ["black", "brown", "blonde", "red", "gray", "orange"]
HATS = ["none", "cap", "hardhat", "beanie", "slick", "hair", "messy"]
STYLES = ["tee", "polo", "stripe", "hoodie"]
SHOTS = ["wide", "medium", "close"]
POS = ["left", "center", "right"]
# ---- flat-vector props (props.py) - naya prop jodo to yahan naam likho (purane chicken/barrel/eggs/moneybag props.py mein hain, bas ab prompt mein nahi)
PROP_TYPES = ["gear", "train", "rails", "bridge", "tower", "chalkboard", "sign", "graph", "hand", "house", "tree", "coins"]
PROP_ACTIONS = ["idle", "walk", "run", "peck", "flap", "pop", "fall", "rise", "spin", "shake", "occupied", "hold", "drop"]
PLACES = ["left", "center", "right", "front", "back"]
WORDS_MIN, WORDS_MAX = 140, 160           # script ke total words (strict)
SCENES_MIN, SCENES_MAX = 18, 26         # model thoda upar-neeche ho to bhi chalega, words ka rule hi asli hai
REACT_ACTIONS = {"shock", "scream", "laugh", "sad", "facepalm", "angry", "celebrate", "think"}

RULES = """You are an autonomous viral YouTube Shorts creator. Write ONE original 'engineering & science suspense story' in the style of the
hit 2D animation 'Why Perfect Railroads Don't Work': a tense, TRUE story about engineering, real-world science, a historical design
mystery or a technical failure, told with a few round-headed cartoon characters (engineers, workers, inventors). A hidden physical,
scientific or historical law flips the outcome dramatically at the end. English only, very simple spoken words, short punchy sentences,
one deep calm male narrator. Never preachy: the lesson must come from what HAPPENS.
ACCURACY: the story must be a real, well-documented case or a real scientific principle. Use only facts you are sure about; when you are
not sure of an exact number say 'about' or leave it out. Never invent statistics, quotes or named people: refer to people by role
('the chief engineer', 'the young apprentice') unless the real name is famous and certain. Never present myths as facts.

LENGTH (strict): 20-24 scenes, 6-8 spoken words per scene, 140-160 words TOTAL (about 60 seconds). Count the words before answering.
Word budget: HOOK ~16 words, CONFLICT ~34, RISING ACTION ~52, CLIMAX & TWIST ~48.
STRUCTURE (use these exact section labels in the JSON: HOOK, BODY, TWIST):
HOOK (section HOOK, scenes 1-2, first ~5 seconds): open with a mind-breaking puzzle, a high-stakes moment or a counter-intuitive
engineering fact. It must create a question the viewer needs answered. No greeting, no 'today we will learn'.
CONFLICT (section BODY, the next 4-5 scenes): introduce the protagonist (engineer / worker / inventor) who faces a choice that goes AGAINST
conventional wisdom (the boss, the crowd or the rival says one thing, the protagonist or rival believes another). Make the stakes concrete
(a bridge, a train, a city, a deadline, a budget).
RISING ACTION (section BODY, the next 7-9 scenes): the initial assumptions or the rival approach seem to WORK. Success builds, confidence
grows, tiny warning signs appear. One clear visual action per scene; use concrete numbers and objects ('two bridges', 'ten trains', 'one bolt').
CLIMAX & TWIST (section TWIST, the last 5-6 scenes): the surprise lands, then reveal the hidden physical / scientific / historical law in one
plain sentence, show how it flips the outcome, and end with ONE memorable closing line that echoes the hook so the video loops.

CHARACTERS (code draws them, so design them with the given options only): create 2-4 characters (id, name, role) that look clearly
different from each other: big round beige head, tiny dot eyes, potato-shaped body, thin legs (different shirt colour + hat + hair).
Engineers wear a hardhat or cap; use glasses, mustache, tie, overalls as signature props (e.g. chief engineer = white shirt + tie + glasses,
foreman = orange shirt + hardhat + mustache, apprentice = blue overalls + cap). Keep the same characters for the whole film. Ids are short lowercase words.
LOCATIONS: create 4-6 locations of the SAME real-world setting (e.g. a railway cutting, a bridge construction site, a drafting office, a
workshop, a shipyard, a canyon). Each has an id and an image prompt (35-60 words) describing ONLY the empty environment: stylized
3D-rendered cartoon diorama look, warm daylight, rich detail, a large flat open ground area filling the lower 45% of the picture where
characters can stand, camera at eye level, vertical 9:16. NO people, NO characters, no text. All locations must feel like one consistent place and era.
PER-SCENE: text (narration), section, loc (a location id), shot (wide | medium | close), cast (1-3 characters visible in the
scene; each has id, action, emo, pos left|center|right, facing left|right: characters should face each other or the action),
speaker (id of the character whose mouth moves because they are talking in this line, else empty string; use sparingly),
anim (camera move), transition (mostly cut: hard cuts like a real animation), emph (1-2 key words from text, empty for HOOK), sfx, props.
PROPS (flat-vector objects drawn by code, 0-3 per scene, MOST scenes should have at least one so the world feels alive):
type = gear (action spin | shake(jammed) | idle; text = tiny label) | train (action idle | walk | run; text 'red' or 'blue') | rails (text 'gap',
'bend' or 'crack' shows a track problem, empty = healthy track) | bridge (action idle | shake = swaying deck | fall = collapsing; text 'collapse' also
collapses) | tower (a tall building; action idle | shake; text 'lean' = tilted) | chalkboard (text = what is written, e.g. '2 trains|1 track';
'|' = new line; icons (up) (down) (coin)) | sign (text = short warning like 'DANGER!', max 14 chars) | graph (text 'up' or 'down' + optional label
like '+300%') | hand (a BIG hand dropping or holding an item from above, text = gear | coin | bag; action hold or drop; use for 2-3 dramatic
close-ups) | house | tree | coins (text = count). place = left | center | right | front | back. Props must illustrate what the narration says
(narration says 'the bridge began to sway' -> bridge with action shake; 'the track bent' -> rails text 'bend'; 'a tiny gear' -> hand holding gear).
Vary shots: mostly medium and wide, 3-5 CLOSE-UP reaction shots (one character, big emotion) right after a surprising event. Let characters REACT.
Use walk/run only when someone really moves. Show the same characters repeatedly so the viewer follows their story.
WORLD: one sentence naming the art direction of the environment (palette, materials, era, mood) used for every location.
TITLE: 35-70 characters, curiosity-driven (e.g. 'Why Perfect Railroads Don't Work'). DESCRIPTION: one hook sentence + 3-5 hashtags (#engineering #science #history ...).
TAGS: 6-10 short tags. TOPIC: one short, specific premise used for repeat avoidance. music_mood: mysterious or epic (or quirky/chill if it truly fits).
Return JSON only."""


def schema(strict=True):
    # strict=False: enums hata deta hai (Gemini kabhi 'schema too complex' 400 deta hai); finalize() phir bhi sab theek karta hai
    S = lambda **k: {"type": "STRING", **{a: b for a, b in k.items() if strict or a != "enum"}}
    B = {"type": "BOOLEAN"}
    char = {"type": "OBJECT", "properties": {
        "id": S(), "name": S(), "role": S(), "shirt": S(enum=SHIRT_C), "pants": S(enum=SHIRT_C), "hair_color": S(enum=HAIR_C), "hat": S(enum=HATS),
        "hat_color": S(enum=SHIRT_C), "style": S(enum=STYLES), "glasses": B, "mustache": B, "tie": B, "overalls": B, "monocle": B},
        "required": ["id", "name", "role", "shirt", "pants", "hair_color", "hat", "hat_color", "style", "glasses", "mustache", "tie", "overalls", "monocle"]}
    loc = {"type": "OBJECT", "properties": {"id": S(), "prompt": S()}, "required": ["id", "prompt"]}
    actor = {"type": "OBJECT", "properties": {"id": S(), "action": S(enum=ACTIONS), "emo": S(enum=EMOS), "pos": S(enum=POS), "facing": S(enum=["left", "right"])},
             "required": ["id", "action", "emo", "pos", "facing"]}
    prop_ = {"type": "OBJECT", "properties": {"type": S(enum=PROP_TYPES), "place": S(enum=PLACES), "action": S(enum=PROP_ACTIONS), "text": S()},
             "required": ["type", "place", "action", "text"]}
    sc = {"type": "OBJECT", "properties": {"text": S(), "section": S(enum=SECTIONS), "loc": S(), "shot": S(enum=SHOTS), "cast": {"type": "ARRAY", "items": actor},
          "speaker": S(), "anim": S(enum=ANIMS), "transition": S(enum=TRANS), "emph": S(), "sfx": S(enum=SFX), "props": {"type": "ARRAY", "items": prop_}},
          "required": ["text", "section", "loc", "shot", "cast", "speaker", "anim", "transition", "emph", "sfx", "props"]}
    return {"type": "OBJECT", "properties": {"topic": S(), "title": S(), "description": S(), "tags": {"type": "ARRAY", "items": S()},
            "music_mood": S(enum=MOODS), "world": S(), "characters": {"type": "ARRAY", "items": char}, "locations": {"type": "ARRAY", "items": loc},
            "scenes": {"type": "ARRAY", "items": sc}},
            "required": ["topic", "title", "description", "tags", "music_mood", "world", "characters", "locations", "scenes"]}


def ask(prompt, sch, max_out=12000, think=1024):
    last = None
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        cfg = {"temperature": 1.0, "maxOutputTokens": max_out, "responseMimeType": "application/json", "responseSchema": sch}
        if "2.5-flash" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": think}
            cfg["maxOutputTokens"] = max_out + think
        for attempt in range(3):
            try:
                r = requests.post(url, headers={"x-goog-api-key": API_KEY}, json={"contents": [{"parts": [{"text": prompt}]}],
                                  "generationConfig": cfg}, timeout=240)
                if r.status_code == 200:
                    cands = r.json().get("candidates") or []
                    parts = (cands[0].get("content") or {}).get("parts") or [] if cands else []
                    txt = "".join(p.get("text", "") for p in parts).strip()
                    if not txt:
                        last = f"{model}: empty answer (blocked or cut off)"
                        continue
                    return json.loads(re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip())
                last = f"{model}: HTTP {r.status_code} {r.text[:160]}"
                if r.status_code in (400, 401, 403, 404):    # retry se theek nahi hoga -> seedha agla model
                    break
                time.sleep(20 if r.status_code == 429 else 5 * (attempt + 1))
            except Exception as e:
                last = f"{model}: {e}"
                time.sleep(4)
    raise RuntimeError(last)


def _words(s):
    return {re.sub(r"(ed|s)$", "", w) for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 3}


def too_similar(topic, past, thr=0.4):
    """Same story ko naye alfaaz mein dobara na banaye (sirf exact match nahi, overlap bhi dekhta hai)."""
    a = _words(topic)
    if not a:
        return False
    for p in past:
        b = _words(p)
        if b and len(a & b) / len(a | b) >= thr:
            return True
    return False


def load_history():
    try:
        return json.load(open(HISTORY, encoding="utf-8"))
    except Exception:
        return []


def _tok(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def _id(x):
    return re.sub(r"[^a-z0-9_]", "", str(x or "").lower().replace(" ", "_"))[:20]


def _pick(v, allowed, default):
    return v if v in allowed else default


def finalize(d):
    """Model ki galtiyan theek karta hai: characters/locations/cast ke ids, enums, positions, section ki tarteeb, fixed camera cues."""
    chars = []
    for c in d.get("characters") or []:
        cid = _id(c.get("id") or c.get("name"))
        if not cid or any(x["id"] == cid for x in chars):
            continue
        chars.append(dict(id=cid, name=str(c.get("name") or cid)[:24], role=str(c.get("role") or "")[:60],
                          shirt=_pick(c.get("shirt"), SHIRT_C, "blue"), pants=_pick(c.get("pants"), SHIRT_C, "navy"),
                          hair_color=_pick(c.get("hair_color"), HAIR_C, "brown"), hat=_pick(c.get("hat"), HATS, "none"),
                          hat_color=_pick(c.get("hat_color"), SHIRT_C, "red"), style=_pick(c.get("style"), STYLES, "tee"),
                          glasses=bool(c.get("glasses")), mustache=bool(c.get("mustache")), tie=bool(c.get("tie")), overalls=bool(c.get("overalls")),
                          monocle=bool(c.get("monocle"))))
    chars = chars[:4]
    d["characters"] = chars
    locs = []
    for l in d.get("locations") or []:
        lid = _id(l.get("id"))
        if lid and l.get("prompt") and not any(x["id"] == lid for x in locs):
            locs.append(dict(id=lid, prompt=re.sub(r"\s+", " ", str(l["prompt"])).strip()))
    d["locations"] = locs[:8]
    ids, lids = [c["id"] for c in chars], [l["id"] for l in d["locations"]]
    sc = d["scenes"]
    order = [SECTIONS.index(s["section"]) if s.get("section") in SECTIONS else -1 for s in sc]
    ok = (min(order) >= 0 and order == sorted(order) and order.count(0) >= 1 and order.count(2) >= 2)
    if not ok:                                              # model ki tarteeb galat -> position se: pehle 2 HOOK, aakhri 5 TWIST
        n = len(sc)
        for k, s in enumerate(sc):
            s["section"] = "HOOK" if k < 2 else ("TWIST" if k >= n - 5 else "BODY")
    body_cycle = ["push_in", "pan_left", "zoom_in", "drift", "pan_right", "push_in"]
    prev_loc = lids[0]
    for k, s in enumerate(sc):
        s["anim"] = _pick(s.get("anim"), ANIMS, "zoom_in" if s["section"] == "HOOK" else body_cycle[k % len(body_cycle)])
        s["transition"] = _pick(s.get("transition"), TRANS, "cut")
        s["sfx"] = _pick(s.get("sfx"), SFX, "none")
        s["shot"] = _pick(s.get("shot"), SHOTS, "medium")
        lid = _id(s.get("loc"))
        s["loc"] = lid if lid in lids else prev_loc
        prev_loc = s["loc"]
        cast, used = [], set()
        for a in s.get("cast") or []:
            cid = _id(a.get("id"))
            if cid in ids and cid not in used and len(cast) < 3:
                used.add(cid)
                cast.append(dict(id=cid, action=_pick(a.get("action"), ACTIONS, "idle"), emo=_pick(a.get("emo"), EMOS, "neutral"),
                                 pos=_pick(a.get("pos"), POS, "center"), facing=_pick(a.get("facing"), ["left", "right"], "right")))
        if not cast:                                        # model ne cast nahi diya -> pehla character
            cast = [dict(id=ids[0], action="idle", emo="neutral", pos="center", facing="right")]
        if len(cast) > 1 and len({a["pos"] for a in cast}) < len(cast):    # do actors ek jagah par na aayen
            for j, a in enumerate(cast):
                a["pos"] = POS[j % 3] if len(cast) == 3 else ("left", "right")[j]
        s["cast"] = cast
        sp = _id(s.get("speaker"))
        s["speaker"] = sp if sp in used else ""
        s["props"] = clean_props(s.get("props"), ids)
        toks = {_tok(w) for w in s["text"].split()}
        em = [w for w in re.findall(r"[A-Za-z0-9']+", s.get("emph") or "") if _tok(w) in toks][:2]
        s["emph"] = "" if s["section"] == "HOOK" else " ".join(em)
    for k, s in enumerate(sc):                              # reference jaisa: zyada tar HARD CUT (fade hata do, glitch sirf impact sfx par)
        if k and (s["transition"] == "fade" or (s["transition"] == "glitch" and s["sfx"] not in ("buzz", "alarm", "scratch"))):
            s["transition"] = "cut"
    last_close = -9                                          # reaction close-ups: single character + bada emotion => 'close' (kam se kam 3 gap)
    for k, s in enumerate(sc):
        if (len(s["cast"]) == 1 and s["cast"][0]["action"] in REACT_ACTIONS and not any(p["type"] == "hand" for p in s["props"])
                and k - last_close >= 4 and 1 < k < len(sc) - 1 and s["shot"] != "close"):
            s["shot"], last_close = "close", k
        elif s["shot"] == "close":
            last_close = k
    sc[0]["anim"], sc[0]["transition"] = "zoom_in", "flash"
    first_twist = next(k for k, s in enumerate(sc) if s["section"] == "TWIST")
    sc[first_twist]["transition"] = "flash"
    sc[-1]["anim"] = "slow_zoom_out"
    d["world"] = re.sub(r"\s+", " ", d.get("world") or "").strip() or "stylized 3D cartoon diorama of a real engineering site, warm daylight, saturated colours, soft shadows"
    d["music_mood"] = _pick(d.get("music_mood"), MOODS, "mysterious")
    return d


def clean(d):
    for s in d["scenes"]:
        s["text"] = re.sub(r"\s+", " ", str(s.get("text", ""))).strip()
    d["scenes"] = [s for s in d["scenes"] if s["text"]]
    words = sum(len(s["text"].split()) for s in d["scenes"])
    if words > WORDS_MAX:
        raise ValueError(f"script has {words} words: TOO LONG, cut at least {words - WORDS_MAX} words (need {WORDS_MIN}-{WORDS_MAX} words, {len(d['scenes'])} scenes now)")
    if words < WORDS_MIN:
        raise ValueError(f"script has {words} words: TOO SHORT, add at least {WORDS_MIN - words} words (need {WORDS_MIN}-{WORDS_MAX} words, {len(d['scenes'])} scenes now)")
    if not (SCENES_MIN <= len(d["scenes"]) <= SCENES_MAX):
        raise ValueError(f"bad size: {len(d['scenes'])} scenes (need {SCENES_MIN}-{SCENES_MAX} scenes, 6-8 words each)")
    if not (2 <= len(d.get("characters") or []) <= 6) or not (3 <= len(d.get("locations") or []) <= 10):
        raise ValueError("need 2-4 characters and 4-6 locations")
    t = re.sub(r"\s*#\w+", "", d["title"]).strip()           # title mein hashtag main.py lagata hai
    if len(t) > 80:
        t = t[:80].rsplit(" ", 1)[0]
    d["title"] = t
    tags = []
    for x in d.get("tags") or []:                            # YouTube: tags kul 500 chars se kam
        x = re.sub(r"[^\w ]", "", str(x)).strip()
        if x and x.lower() not in [y.lower() for y in tags] and sum(len(y) + 1 for y in tags) + len(x) < 400:
            tags.append(x)
    d["tags"] = tags[:10] or ["engineering", "science", "history", "mystery"]
    return finalize(d)


def clean_props(raw, ids):
    """Gemini ke props ko saaf karta hai: valid type/place/action, max 3, hand max 1, text chhota."""
    out = []
    for p in raw or []:
        if not isinstance(p, dict):
            continue
        t = str(p.get("type", "")).lower().strip()
        if t not in PROP_TYPES or len(out) >= 3 or (t == "hand" and any(o["type"] == "hand" for o in out)):
            continue
        txt = re.sub(r"\s+", " ", str(p.get("text", "") or "")).strip()[:28]
        act = _pick(str(p.get("action", "idle")).lower(), PROP_ACTIONS, "idle")
        if t == "barrel":
            act = "occupied" if (act == "occupied" or _id(txt) in ids) else "idle"
            txt = _id(txt) if act == "occupied" else ""
        if t == "hand":
            act = act if act in ("hold", "drop") else "hold"
            txt = txt.lower() if txt.lower() in ("gear", "coin", "bag") else "gear"
        out.append(dict(type=t, place=_pick(str(p.get("place", "right")).lower(), PLACES, "right"), action=act, text=txt))
    return out


def _P(t, place="right", action="idle", text=""):
    return dict(type=t, place=place, action=action, text=text)


def _A(i, action="idle", emo="neutral", pos="center", facing="right"):
    return dict(id=i, action=action, emo=emo, pos=pos, facing=facing)


def _S(text, sec, loc, shot, cast, anim="push_in", trans="cut", sfx="none", emph="", speaker="", props=None):
    return dict(text=text, section=sec, loc=loc, shot=shot, cast=cast, speaker=speaker, anim=anim, transition=trans, sfx=sfx, emph=emph, props=props or [])


# offline test / emergency fallback (ALLOW_FALLBACK=1): Tacoma Narrows Bridge (140-160 words)
FALLBACK = {
    "topic": "the Tacoma Narrows Bridge twisting itself apart in 1940", "title": "Why This Bridge Tore Itself Apart",
    "description": "A slim, elegant bridge fell in ordinary wind. The reason is a law engineers once ignored.\n\n#engineering #science #history #mystery #shorts",
    "tags": ["engineering", "science", "history", "bridge", "mystery", "physics"], "music_mood": "mysterious",
    "world": "stylized 3D cartoon diorama of a 1940 suspension bridge site over a misty strait, warm daylight, steel blues and rust reds",
    "characters": [
        dict(id="chief", name="Chief Designer", role="bridge designer", shirt="white", pants="navy", hair_color="gray", hat="none", hat_color="red", style="polo", glasses=True, mustache=False, tie=True, overalls=False, monocle=False),
        dict(id="foreman", name="Foreman", role="site foreman", shirt="orange", pants="brown", hair_color="black", hat="hardhat", hat_color="yellow", style="tee", glasses=False, mustache=True, tie=False, overalls=False, monocle=False),
        dict(id="kid", name="Apprentice", role="young apprentice", shirt="blue", pants="navy", hair_color="red", hat="cap", hat_color="gray", style="tee", glasses=False, mustache=False, tie=False, overalls=True, monocle=False),
    ],
    "locations": [
        dict(id="strait", prompt="empty windy strait shore with a tall steel bridge tower rising from grey water in the distance, misty hills, stylized 3D cartoon diorama, warm daylight, large flat open gravel ground in lower half"),
        dict(id="office", prompt="empty 1940s drafting office with big blueprint tables, hanging lamps, wooden floor, rolled plans in the corner, stylized 3D cartoon diorama, warm light, large flat open floor in lower half"),
        dict(id="deck", prompt="empty bridge roadway deck seen from the side with steel railings, cables rising to a tower, grey water far below, stylized 3D cartoon diorama, daylight, large flat open road surface in lower half"),
        dict(id="shore", prompt="empty rocky shore beside a bridge tower foundation, construction cranes, wooden crates, cloudy sky, stylized 3D cartoon diorama, warm daylight, large flat open ground in lower half"),
    ],
    "scenes": [
        _S("A giant bridge collapsed in ordinary wind.", "HOOK", "strait", "wide", [_A("foreman", "shock", "scared", "center")], "zoom_in", "flash", "rise", props=[_P("bridge", "back", "fall", "collapse")]),
        _S("Its engineers had trusted every single calculation.", "HOOK", "office", "medium", [_A("chief", "think", "confused", "center")], "push_in", props=[_P("chalkboard", "right", "idle", "all math|correct")]),
        _S("Nineteen-forty. The state needed a cheap bridge.", "BODY", "office", "medium", [_A("chief", "talk", "neutral", "left"), _A("foreman", "listen", "neutral", "right", "left")], "pan_right", props=[_P("coins", "front", "pop", "3")]),
        _S("A deeper, sturdier design cost too much.", "BODY", "office", "close", [_A("chief", "shrug", "smug", "center")], "zoom_in", "cut", "thud", "cost", props=[_P("chalkboard", "left", "idle", "deep = (coin)(coin)(coin)")]),
        _S("So the designer chose a slimmer, elegant deck.", "BODY", "strait", "wide", [_A("chief", "point", "proud", "left")], "pan_left", props=[_P("bridge", "right", "idle", "")]),
        _S("The foreman frowned. Slim felt dangerous.", "BODY", "deck", "medium", [_A("foreman", "think", "worried", "center", "left")], "push_in", "cut", "gulp", "dangerous", props=[_P("sign", "right", "shake", "TOO THIN?")]),
        _S("Opening day: cars crossed, and crowds cheered.", "BODY", "deck", "wide", [_A("kid", "celebrate", "excited", "center")], "zoom_out", "cut", "sparkle", "cheered", props=[_P("train", "left", "walk", "red"), _P("tree", "back", "idle", "")]),
        _S("Soon workers noticed the deck gently rolling.", "BODY", "deck", "medium", [_A("kid", "point", "surprised", "left"), _A("foreman", "listen", "confused", "right", "left")], "drift", props=[_P("bridge", "back", "shake", "")]),
        _S("They nicknamed it Galloping Gertie. Drivers loved it.", "BODY", "shore", "medium", [_A("kid", "laugh", "happy", "center")], "pan_right", "cut", "sparkle", "Gertie", props=[_P("graph", "right", "idle", "up +visitors")]),
        _S("Engineers believed the wobble was harmless.", "BODY", "office", "medium", [_A("chief", "talk", "smug", "left"), _A("kid", "listen", "worried", "right", "left")], "push_in", props=[_P("chalkboard", "right", "idle", "wobble = fine")]),
        _S("They added cables to calm the motion.", "BODY", "deck", "medium", [_A("foreman", "hold", "neutral", "center")], "pan_left", props=[_P("gear", "right", "spin", "")]),
        _S("Nothing helped. The waves kept coming back.", "BODY", "deck", "wide", [_A("foreman", "facepalm", "worried", "center")], "shake", "cut", "buzz", "Nothing", props=[_P("bridge", "back", "shake", "")]),
        _S("Four months later, the wind grew stronger.", "BODY", "strait", "wide", [_A("kid", "shock", "scared", "center")], "zoom_out", "cut", "rise", "stronger", props=[_P("tower", "left", "shake", "")]),
        _S("Suddenly the deck began twisting like ribbon.", "TWIST", "deck", "wide", [_A("foreman", "scream", "scared", "center", "left")], "shake", "flash", "alarm", "twisting", props=[_P("bridge", "back", "shake", "")]),
        _S("Each gust pushed in perfect rhythm.", "TWIST", "strait", "medium", [_A("kid", "point", "surprised", "center")], "push_in", "cut", "none", "rhythm", props=[_P("graph", "right", "rise", "up")]),
        _S("Engineers call this hidden law aeroelastic flutter.", "TWIST", "office", "close", [_A("chief", "think", "surprised", "center", "left")], "zoom_in", "cut", "thud", "flutter", props=[_P("chalkboard", "left", "idle", "wind + rhythm|= flutter")]),
        _S("The solid slim deck could not shed wind.", "TWIST", "deck", "medium", [_A("chief", "sad", "sad", "center")], "drift", props=[_P("hand", "center", "hold", "gear")]),
        _S("Steel tore apart, and the bridge fell.", "TWIST", "shore", "wide", [_A("foreman", "shock", "scared", "left"), _A("kid", "shock", "scared", "right", "left")], "shake", "cut", "thud", "fell", props=[_P("bridge", "back", "fall", "collapse")]),
        _S("Now every big bridge meets a wind tunnel.", "TWIST", "office", "medium", [_A("chief", "talk", "proud", "left"), _A("kid", "smile", "happy", "right", "left")], "push_in", "cut", "sparkle", "wind tunnel", props=[_P("gear", "center", "spin", "TEST")]),
        _S("Strong bridges let the wind slip through.", "TWIST", "strait", "wide", [_A("chief", "smile", "proud", "left"), _A("foreman", "smile", "happy", "right", "left")], "slow_zoom_out", "cut", "sparkle", "slip through", props=[_P("bridge", "back", "idle", "")]),
    ],
}

ANIM_TXT = {"zoom_in": "Quick zoom-in", "zoom_out": "Zoom-out", "slow_zoom_out": "Slow zoom-out + vignette", "push_in": "Slow push-in",
            "pan_left": "Pan left", "pan_right": "Pan right", "shake": "Camera shake", "drift": "Floating drift"}
TRANS_TXT = {"cut": "hard cut", "flash": "flash transition", "fade": "fade from black", "glitch": "glitch transition"}


def write_plan(d):
    """story_plan.md: padhne ke liye plan (HOOK / BODY / TWIST), video isi data se banti hai."""
    heads = [("HOOK", "1. [HOOK - first 5 seconds]"), ("BODY", "2. [BODY]"), ("TWIST", "3. [TWIST & OUTRO]")]
    out = [f"# {d['title']}", "", f"World: {d['world']}", "", "## Characters"]
    for c in d["characters"]:
        out.append(f"- **{c['name']}** ({c['id']}): {c['role']} | shirt {c['shirt']}, hat {c['hat']}, hair {c['hair_color']}")
    out += ["", "## Locations"] + [f"- {l['id']}: {l['prompt']}" for l in d["locations"]] + [""]
    for key, head in heads:
        out.append(head)
        for n, s in enumerate(d["scenes"], 1):
            if s["section"] != key:
                continue
            cue = [ANIM_TXT.get(s["anim"], s["anim"]), TRANS_TXT.get(s["transition"], s["transition"]), f"{s['shot']} shot"]
            if s["sfx"] != "none":
                cue.append(f"sfx: {s['sfx']}")
            who = ", ".join(f"{a['id']} ({a['action']}/{a['emo']})" for a in s["cast"])
            if s.get("props"):
                who += " | Props: " + ", ".join(f"{p['type']}({p['action']}{':' + p['text'] if p['text'] else ''})" for p in s["props"])
            out += [f"   - Scene {n} | {s['text']}", f"       Camera: {', '.join(cue)}", f"       Location: {s['loc']} | Cast: {who}"]
        out.append("")
    open(PLAN, "w", encoding="utf-8").write("\n".join(out))


def pick_ingredients(used_seeds):
    """Har call par bilkul naya random combo: category + starting idea (aaj tak use na hua) + twist + protagonist + hook + title-format.
    20% runs 'wildcard' hote hain: koi seed nahi, Gemini us category ka koi kam-jaana asli case khud chunta hai (isse topics predictable nahi rehte)."""
    rnd = random.SystemRandom()
    cat = rnd.choice(list(SEEDS))
    pool = [x for x in SEEDS[cat] if x not in used_seeds] or SEEDS[cat]
    wild = rnd.random() < 0.20
    if wild:
        idea = (f"Starting idea: NONE. Pick a real, lesser-known, well-documented case from this area yourself: {cat}. "
                "Avoid the famous textbook examples (Tacoma Narrows, Titanic, Eiffel Tower, Leaning Tower of Pisa).")
        seed = f"wildcard:{cat}"
    else:
        seed = rnd.choice(pool)
        idea = (f"Starting idea (you may sharpen it or swap it for a different, lesser-known real case of the same kind): {seed}.")
    spec = (f"TODAY'S RANDOM INGREDIENTS. Area: {cat}. {idea} Climax type: {rnd.choice(TWISTS)}. Protagonist: {rnd.choice(PROTAGONISTS)}. "
            f"Hook style: {rnd.choice(HOOKS)}. {rnd.choice(FORMATS)}.")
    return cat, seed, spec


def main():
    for p in (OUT, PLAN):
        if os.path.exists(p):
            os.remove(p)
    hist = load_history()
    recent = [h.get("topic", "") for h in hist]
    used_seeds = {h.get("seed") for h in hist if h.get("seed")}
    d, fb, seed_used = None, False, ""
    rejected = []
    last_validation_error = ""
    if API_KEY:
        for attempt in range(5):
            cat, seed_txt, spec = pick_ingredients(used_seeds)
            prompt = (f"{RULES}\n\n{spec}\nDo NOT repeat or closely resemble any of these past stories: {recent[-60:] + rejected}\n\n"
                      f"STRICT REMINDER: {WORDS_MIN}-{WORDS_MAX} words TOTAL (count them!), 20-24 scenes of 6-8 words, 2-4 characters, 4-6 locations. "
                      f"Structure: HOOK (2 scenes) -> CONFLICT -> RISING ACTION -> CLIMAX & TWIST with the hidden law. True facts only. "
                      f"{('Your previous response failed: ' + last_validation_error + '. Fix it now. ') if last_validation_error else ''}"
                      "Return JSON only.")
            try:
                cand = clean(ask(prompt, schema(strict="HTTP 400" not in last_validation_error)))
                if too_similar(cand["topic"] + " " + cand["title"], recent):
                    rejected.append(cand["topic"])
                    print(f"story attempt {attempt + 1}: too similar to history ({cand['topic']}) -> retry")
                    continue
                d, seed_used = cand, seed_txt
                break
            except Exception as e:
                last_validation_error = str(e)
                print(f"story attempt {attempt + 1} failed: {e}")
                time.sleep(3)
    if not d:
        if not os.environ.get("ALLOW_FALLBACK"):
            # Fallback par har baar wahi video upload hoti thi. Ab run fail hota hai, kuch upload nahi hota.
            sys.exit("ERROR: no fresh Gemini story (check GEMINI_API_KEY / quota). Stopping so no duplicate video is uploaded.")
        print("ALLOW_FALLBACK set -> offline fallback story (history mein save nahi hogi)")
        d, fb = finalize(copy.deepcopy(FALLBACK)), True
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    write_plan(d)
    print("SCRIPT:", d["title"], f"({len(d['scenes'])} scenes, {sum(len(s['text'].split()) for s in d['scenes'])} words)")
    if not fb and not any(h.get("topic", "").lower() == d["topic"].lower() for h in hist):
        hist.append({"topic": d["topic"], "title": d["title"], "seed": seed_used, "date": datetime.date.today().isoformat()})
        json.dump(hist[-1000:], open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
