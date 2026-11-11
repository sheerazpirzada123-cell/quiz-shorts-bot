"""Gemini se har run NAYI "parable explainer" story (jaise "The Difference Between Rich And Poor"):
chhoti si allegory-duniya, 2-4 fixed characters, 3-8 locations, aur har scene ka cast (kaun, kya action, kya expression, kahan).
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

# ---- har run mein random ingredients: concept (kis cheez ko samjhana hai) + world (kahani kis duniya mein hai) + format
CONCEPTS = [
    "the difference between rich and poor", "why the rich get richer", "employee vs business owner mindset", "how inflation quietly steals your money",
    "how debt traps people", "saving vs investing", "assets vs liabilities", "how compound interest works", "why taxes exist and who pays them",
    "how a monopoly squeezes everyone", "supply and demand", "why banks need your trust", "what a stock market really is", "how a recession starts",
    "why status symbols keep people poor", "time vs money: what is worth more", "why cheap things end up costing more", "how a bubble forms and bursts",
    "why the middle class feels squeezed", "how credit scores control your life", "the difference between price and value", "why people copy the crowd and lose",
    "how one small habit beats talent", "how a good reputation becomes real money", "why free things are never free", "how competition lowers prices",
    "why hard workers are not always the richest", "how opportunity compounds for those who already have it", "scarcity: why rare things cost more",
    "why saving a little every day beats a big lucky win", "the difference between being busy and being productive", "how trust builds a whole economy",
]
WORLDS = [
    "a tiny village where everyone lives inside wooden barrels", "an island that uses coconuts as money", "a medieval market town with cobblestone streets",
    "a desert oasis where water is the only wealth", "a farm village where chickens lay golden eggs", "a snowy mountain town of bakers and woodcutters",
    "a floating city of hot-air balloons", "a pirate harbour with a treasure bank", "a tiny space colony on a red planet", "a toy-block city made of colourful bricks",
    "a jungle village that trades fruit", "a fishing port where boats are the only job", "a mini railway town with one big train station",
    "a lemonade-stand street where every kid runs a shop", "a bee-hive kingdom of workers and a queen", "a candy-factory town",
]
FORMATS = [
    "Title like 'The Difference Between X And Y'", "Title like 'Why X Always Happens'", "Title like 'How X Really Works'",
    "Title like 'The Truth About X'", "Title like 'What Nobody Tells You About X'",
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
# ---- flat-vector props (props.py) - naya prop jodo to yahan naam likho
PROP_TYPES = ["chicken", "barrel", "chalkboard", "coins", "eggs", "house", "tree", "sign", "moneybag", "graph", "hand"]
PROP_ACTIONS = ["idle", "walk", "run", "peck", "flap", "pop", "fall", "rise", "spin", "shake", "occupied", "hold", "drop"]
PLACES = ["left", "center", "right", "front", "back"]
REACT_ACTIONS = {"shock", "scream", "laugh", "sad", "facepalm", "angry", "celebrate", "think"}

RULES = """You are an autonomous viral YouTube Shorts creator. Write ONE original 'parable explainer' in the style of the
hit 2D animation 'The Difference Between Rich And Poor': a tiny allegory WORLD with a few round-headed cartoon characters that
explains, through simple cause-and-effect events, how money / society / economics / psychology really works.
Every run must use a genuinely new concept, world and plot. English only, very simple spoken words, short punchy sentences,
one deep calm male narrator who tells the story ('In a village, every person lives in a barrel...'). Never preachy; the lesson
must come from what HAPPENS in the story, ending in a clever insight.

LENGTH (strict): 24-30 scenes, 6-9 spoken words per scene, 170-215 words TOTAL. Count before answering.
HOOK (2 scenes): shows the strange world or asks the big question immediately.
BODY (18-22 scenes): step-by-step events; each scene = ONE clear visual action; stakes escalate; rules of the world get tested;
use concrete numbers and objects (e.g. 'two eggs', 'ten days') so the viewer can follow.
TWIST (4 scenes): surprising turn that reveals the real lesson, then one memorable closing line.

CHARACTERS (code draws them, so design them with the given options only): create 2-4 characters (id, name, role) that look clearly
different from each other: big round beige head, tiny dot eyes, potato-shaped body, thin legs (different shirt colour + hat + hair;
cap / slick hair / beanie, glasses, MONOCLE, mustache, tie, overalls are fun signature props: e.g. poor man = brown shirt + flat cap,
rich man = green waistcoat + monocle + tie).
Keep the same characters for the whole film. Character ids are short lowercase words.
LOCATIONS: create 4-8 locations. Each has an id and an image prompt (35-60 words) describing ONLY the empty environment of the
SAME world: stylized 3D-rendered cartoon diorama look, warm daylight, rich detail, a large flat open ground area filling the
lower 45% of the picture where characters can stand, camera at eye level, vertical 9:16. NO people, NO characters, no text.
Props, buildings, barrels, animals in the distance are allowed. All locations must feel like one consistent world.
PER-SCENE: text (narration), section, loc (a location id), shot (wide | medium | close), cast (1-3 characters visible in the
scene; each has id, action, emo, pos left|center|right, facing left|right: characters should face each other or the action),
speaker (id of the character whose mouth moves because they are talking in this line, else empty string; use sparingly),
anim (camera move), transition (mostly cut: hard cuts like a real animation), emph (1-2 key words from text, empty for HOOK), sfx, props.
PROPS (flat-vector explainer objects drawn by code, 0-3 per scene, MOST scenes should have at least one so the world feels alive):
type = chicken (action walk/peck/flap/idle) | barrel (action occupied, text = id of the character standing inside it) | chalkboard
(text = what is written, e.g. '2 = (egg)' or '1 egg|per day'; icons (egg) (coin) (up) (down); '|' = new line) | coins (text = count e.g. '3')
| eggs (text = count, add the word gold for golden eggs) | house | tree | sign (text = short protest slogan like 'UNFAIR!', max 14 chars)
| moneybag | graph (text 'up' or 'down' + optional label like '+300%') | hand (a BIG hand dropping or holding an item from above, text = coin | egg | bag;
action hold or drop; use it for 2-4 dramatic close-up scenes). place = left | center | right | front | back. Props must illustrate what the
narration says (narration says 'two eggs' -> eggs prop with text '2'; 'every house' -> house; 'a protest' -> sign).
Vary shots: mostly medium and wide, 3-5 CLOSE-UP reaction shots (one character, big emotion) right after a surprising event. Let characters REACT (shock, laugh, sad, proud, facepalm, shrug).
Use walk/run only when someone really moves. Show the same characters repeatedly so the viewer follows their story.
WORLD: one sentence naming the art direction of the environment (palette, materials, mood) used for every location.
TITLE: 35-70 characters, curiosity-driven. DESCRIPTION: one hook sentence + 3-5 hashtags. TAGS: 6-10 short tags.
TOPIC: one short, specific premise used for repeat avoidance. music_mood: quirky or chill (or epic/mysterious if it truly fits).
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
    if not ok:                                              # model ki tarteeb galat -> position se: pehle 2 HOOK, aakhri 4 TWIST
        n = len(sc)
        for k, s in enumerate(sc):
            s["section"] = "HOOK" if k < 2 else ("TWIST" if k >= n - 4 else "BODY")
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
    d["world"] = re.sub(r"\s+", " ", d.get("world") or "").strip() or "stylized 3D cartoon diorama, warm daylight, saturated colours, soft shadows"
    d["music_mood"] = _pick(d.get("music_mood"), MOODS, "quirky")
    return d


def clean(d):
    for s in d["scenes"]:
        s["text"] = re.sub(r"\s+", " ", str(s.get("text", ""))).strip()
    d["scenes"] = [s for s in d["scenes"] if s["text"]]
    words = sum(len(s["text"].split()) for s in d["scenes"])
    if not (20 <= len(d["scenes"]) <= 34 and 150 <= words <= 240):
        raise ValueError(f"bad size: {len(d['scenes'])} scenes / {words} words (need 24-30 scenes, 170-215 words)")
    if not (2 <= len(d.get("characters") or []) <= 6) or not (3 <= len(d.get("locations") or []) <= 10):
        raise ValueError("need 2-4 characters and 4-8 locations")
    t = re.sub(r"\s*#\w+", "", d["title"]).strip()           # title mein hashtag main.py lagata hai
    if len(t) > 80:
        t = t[:80].rsplit(" ", 1)[0]
    d["title"] = t
    tags = []
    for x in d.get("tags") or []:                            # YouTube: tags kul 500 chars se kam
        x = re.sub(r"[^\w ]", "", str(x)).strip()
        if x and x.lower() not in [y.lower() for y in tags] and sum(len(y) + 1 for y in tags) + len(x) < 400:
            tags.append(x)
    d["tags"] = tags[:10] or ["storytime", "animation", "lifelessons", "money"]
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
            txt = txt.lower() if txt.lower() in ("coin", "egg", "bag") else "coin"
        out.append(dict(type=t, place=_pick(str(p.get("place", "right")).lower(), PLACES, "right"), action=act, text=txt))
    return out


def _P(t, place="right", action="idle", text=""):
    return dict(type=t, place=place, action=action, text=text)


def _A(i, action="idle", emo="neutral", pos="center", facing="right"):
    return dict(id=i, action=action, emo=emo, pos=pos, facing=facing)


def _S(text, sec, loc, shot, cast, anim="push_in", trans="cut", sfx="none", emph="", speaker="", props=None):
    return dict(text=text, section=sec, loc=loc, shot=shot, cast=cast, speaker=speaker, anim=anim, transition=trans, sfx=sfx, emph=emph, props=props or [])


# offline test / emergency fallback (ALLOW_FALLBACK=1): original barrel-village parable
FALLBACK = {
    "topic": "the barrel village and the golden egg hens: why the rich get richer", "title": "Why The Rich Keep Getting Richer",
    "description": "Two neighbours, one hen each, and a lesson about money.\n\n#money #animation #storytime #lifelessons #shorts",
    "tags": ["money", "animation", "storytime", "lifelessons", "rich", "poor"], "music_mood": "quirky",
    "world": "stylized 3D cartoon diorama of a sunny barrel village, warm daylight, saturated colours, soft shadows",
    "characters": [
        dict(id="sam", name="Sam", role="poor farmer", shirt="brown", pants="navy", hair_color="black", hat="cap", hat_color="gray", style="tee", glasses=False, mustache=False, tie=False, overalls=True),
        dict(id="lord", name="Lord Bram", role="rich landlord", shirt="green", pants="black", hair_color="gray", hat="slick", hat_color="black", style="polo", glasses=False, mustache=False, tie=True, overalls=False, monocle=True),
        dict(id="mia", name="Mia", role="baker", shirt="red", pants="navy", hair_color="red", hat="beanie", hat_color="yellow", style="stripe", glasses=False, mustache=False, tie=False, overalls=False),
    ],
    "locations": [
        dict(id="square", prompt="empty cobblestone village square with wooden barrel houses, a big yellow mansion in the background, blue sky with clouds, stylized 3D cartoon diorama, large flat open ground in lower half"),
        dict(id="farm", prompt="empty sunny farmyard with a small wooden hen house, fence, haystacks, green hills, stylized 3D cartoon diorama, large flat open ground in lower half"),
        dict(id="mansion", prompt="empty front yard of a big yellow mansion with red shutters, flower boxes, paved path, stylized 3D cartoon diorama, large flat open ground in lower half"),
        dict(id="market", prompt="empty market street with wooden stalls and colourful awnings, cobblestones, warm afternoon light, stylized 3D cartoon diorama, large flat open ground in lower half"),
    ],
    "scenes": [
        _S("In this village, everyone starts with one hen.", "HOOK", "square", "wide", [_A("sam", "talk", "neutral", "left"), _A("lord", "talk", "smug", "right", "left")], "zoom_in", "flash", props=[_P("barrel","left","occupied","sam"),_P("chicken","center","idle"),_P("house","back")]),
        _S("Yet some people end up owning thousands of eggs.", "HOOK", "mansion", "medium", [_A("lord", "celebrate", "proud", "center")], "push_in", props=[_P("hand","center","hold","egg"),_P("eggs","front","pop","gold 5")]),
        _S("Sam works hard and sells his eggs every morning.", "BODY", "farm", "medium", [_A("sam", "walk", "happy", "center")], "pan_right", props=[_P("chicken","right","walk"),_P("eggs","left","pop","2")]),
        _S("Every coin he earns, he spends on dinner.", "BODY", "market", "medium", [_A("sam", "talk", "happy", "left"), _A("mia", "smile", "happy", "right", "left")], "push_in", "cut", "sparkle", props=[_P("coins","front","pop","3")]),
        _S("Lord Bram sells just one egg per day.", "BODY", "mansion", "medium", [_A("lord", "idle", "smug", "center")], "drift", "cut", "none", "one", props=[_P("chalkboard","left","idle","1 (egg)|per day"),_P("chicken","right","peck")]),
        _S("The rest he saves, and buys another hen.", "BODY", "farm", "medium", [_A("lord", "point", "evil", "left"), _A("sam", "listen", "confused", "right", "left")], "pan_left", "cut", "rise", "another", props=[_P("moneybag","left","shake"),_P("chicken","right","flap")]),
        _S("Now two hens lay eggs while he sleeps.", "BODY", "mansion", "close", [_A("lord", "sleep", "sleepy", "center")], "zoom_in", "cut", "none", "sleeps", props=[_P("eggs","front","pop","gold 4")]),
        _S("Sam notices and feels the unfairness burn.", "BODY", "square", "medium", [_A("sam", "angry", "angry", "center", "left")], "shake", "glitch", "buzz", "unfairness", props=[_P("sign","right","shake","UNFAIR!"),_P("barrel","left","occupied","sam")]),
        _S("But Sam's hen gets tired, and he cannot rest.", "BODY", "farm", "medium", [_A("sam", "sad", "worried", "center")], "push_in", props=[_P("chicken","right","idle"),_P("graph","left","fall","down")]),
        _S("Within a year, Bram owns twenty hens.", "BODY", "mansion", "wide", [_A("lord", "celebrate", "excited", "center")], "zoom_out", "cut", "thud", "twenty", props=[_P("chicken","left","walk"),_P("chicken","right","peck"),_P("house","back")]),
        _S("Sam asks him for help, and Bram says yes.", "BODY", "mansion", "medium", [_A("sam", "wave", "worried", "left"), _A("lord", "talk", "smug", "right", "left")], "pan_right", "cut", "knock", "", "lord", props=[_P("hand","center","drop","coin")]),
        _S("But Sam must work for him, for tiny pay.", "BODY", "farm", "medium", [_A("sam", "walk", "sad", "center")], "drift", props=[_P("coins","front","pop","1"),_P("tree","back")]),
        _S("The rich did not work harder than Sam.", "TWIST", "square", "close", [_A("lord", "shrug", "smug", "center", "left")], "zoom_in", "flash", "thud", "harder", props=[_P("chalkboard","right","idle","same work|different pay")]),
        _S("They just let their money work instead.", "TWIST", "market", "medium", [_A("lord", "talk", "proud", "left"), _A("mia", "think", "confused", "right", "left")], "push_in", "cut", "sparkle", "money", props=[_P("graph","right","grow","up +300%"),_P("moneybag","left","shake")]),
        _S("And that first extra hen changes everything.", "TWIST", "farm", "wide", [_A("sam", "think", "worried", "left"), _A("lord", "celebrate", "excited", "right", "left")], "pan_left", "cut", "rise", "first", props=[_P("chicken","center","flap"),_P("eggs","front","pop","gold 3")]),
        _S("Remember: save first, and spend what remains.", "TWIST", "square", "wide", [_A("sam", "smile", "proud", "left"), _A("mia", "smile", "happy", "center"), _A("lord", "smile", "happy", "right", "left")], "slow_zoom_out", "cut", "sparkle", "save", props=[_P("coins","front","pop","6"),_P("house","back")]),
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


def main():
    for p in (OUT, PLAN):
        if os.path.exists(p):
            os.remove(p)
    hist = load_history()
    recent = [h.get("topic", "") for h in hist]
    d, fb = None, False
    rejected = []
    last_validation_error = ""
    if API_KEY:
        for attempt in range(4):
            seeds = (f"Inspiration (twist it into something fresh, do not copy literally): concept = {random.choice(CONCEPTS)}; "
                     f"world = {random.choice(WORLDS)}; {random.choice(FORMATS)}.")
            prompt = (f"{RULES}\n\n{seeds}\nDo NOT repeat or closely resemble any of these past stories: {recent[-60:] + rejected}\n"
                      f"STRICT REMINDER: 24-30 scenes, 6-9 spoken words per scene, 170-215 words total; 2-4 characters; 4-8 locations. "
                      f"{('Your previous response failed: ' + last_validation_error + '. Fix it now. ') if last_validation_error else ''}"
                      "Return JSON only.")
            try:
                cand = clean(ask(prompt, schema(strict="HTTP 400" not in last_validation_error)))
                if too_similar(cand["topic"] + " " + cand["title"], recent):
                    rejected.append(cand["topic"])
                    print(f"story attempt {attempt + 1}: too similar to history ({cand['topic']}) -> retry")
                    continue
                d = cand
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
        hist.append({"topic": d["topic"], "title": d["title"], "date": datetime.date.today().isoformat()})
        json.dump(hist[-1000:], open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
