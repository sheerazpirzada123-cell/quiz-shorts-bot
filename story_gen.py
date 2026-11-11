"""Gemini se NAYI dark-fantasy / mystery story (twist ke saath): HOOK -> BODY -> TWIST & OUTRO.
Har scene ke saath: narration, animation cue (camera/transition/highlight word/sfx) aur image prompt.
Output: script.json (video ke liye) + story_plan.md (padhne wala plan, tumhare format mein)."""
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

# Har run mein random ingredients -> har baar alag setup (Gemini inhe twist karke use karta hai, copy nahi)
SETTINGS = [
    "a lighthouse on a cliff", "a library that rearranges itself at night", "a drowned city under a black lake", "a monastery in endless snow",
    "a mirror-maze at an abandoned fair", "a forest where the trees whisper names", "a clockmaker's tower where time runs backwards",
    "a desert caravan following a falling star", "a castle with one door that never opens", "an island that appears only at low tide",
    "a village where nobody casts a shadow", "a train that stops at stations that don't exist", "a witch's market sold only at midnight",
    "a cave of glowing crystals that hum", "a ship sailing through a sea of fog", "a graveyard with one fresh unnamed grave",
    "a bell tower that rings thirteen times", "a painter's studio where portraits blink", "a frozen lake with something moving beneath",
    "an old well that answers questions", "a labyrinth beneath a royal palace", "a lantern festival in a dying kingdom",
]
HEROES = [
    "a young cartographer", "a retired knight", "a lonely lighthouse keeper", "a thief with a stolen map", "an orphan apprentice",
    "a night watchman", "a travelling storyteller", "a blind bell-ringer", "a curious librarian", "a runaway princess",
    "a grave-digger's daughter", "a disgraced alchemist", "a ferryman", "a monster hunter who has never seen a monster",
]
TWISTS = [
    "the hero was the monster all along", "the hero has been dead since the first scene", "the villain is the hero's future self",
    "the monster was protecting everyone from something worse", "the prize everyone wants IS the curse", "the story is a loop and the hero is on lap 1000",
    "the narrator is the one who is trapped", "the helper character is the real villain", "the place is not a place - it is a living creature",
    "the hero's rescue mission is what caused the disaster", "the warning sign was written by the hero himself", "everything the hero feared was a lie told to keep him in place",
    "the thing being hunted is actually lost and scared", "the hero finds his own name already carved in the final room",
]
ANIMS = ["zoom_in", "zoom_out", "slow_zoom_out", "push_in", "pan_left", "pan_right", "shake", "drift"]
TRANS = ["cut", "flash", "fade", "glitch"]
SECTIONS = ["HOOK", "BODY", "TWIST"]
SFX = ["none", "whoosh", "thud", "rise", "gasp", "knock", "sparkle", "alarm", "buzz", "scratch", "gulp"]
MOODS = ["mysterious", "epic"]

RULES = """You are an autonomous viral video creator for YouTube Shorts and Reels. You write ONE completely unique, highly engaging
ORIGINAL fictional story with a twist (cinematic dark fantasy / mystery), plus exact animation, voice-over and image cues for each scene.
Never repeat a past story setup. English only, dramatic, fast, mysterious, atmospheric. It is narrated by ONE deep male narrator.

TOTAL: 125-150 spoken words (about 55 seconds). 20-24 scenes. Every scene = ONE short narration line of 5-9 words (scene changes every 2-3 seconds).
Short punchy sentences, simple spoken words, zero fluff, no filler, no lectures, no moral. Present or past tense - stay consistent.
BANNED phrases: "Did you know", "Imagine", "In this video", "Let's dive in", "Hey guys", "Once upon a time", "Little did he know".

STRUCTURE (set `section` on every scene, in this order):
1. HOOK (1-2 scenes, <=5 seconds, <=10 words total in the first scene): an EXTREME curiosity hook - a bold, specific, impossible-sounding claim or question
   that the viewer must see resolved. e.g. "Every night, the lighthouse never guided a single ship."
2. BODY (about 15-17 scenes): fast-paced storytelling that BUILDS TENSION. Rule of three escalation. One open loop around the middle ("But the door was already open.").
   One concrete detail every scene (an object, a sound, a number, a rule). A hero with a clear want, an obstacle that escalates, a creeping wrong feeling.
3. TWIST (3-4 scenes, the last ~12 seconds): the unexpected resolution viewers did not see coming - it must RE-EXPLAIN something from the hook or body.
   The LAST line is a strong, quotable closing line that can loop back to the hook.

PER-SCENE CUES (all required):
 - text: the narration line (exactly what is spoken, and shown as word-by-word subtitles).
 - section: HOOK | BODY | TWIST.
 - visual: a DETAILED image-generation prompt for THIS frame only (35-60 words): subject, action, camera angle (low angle, wide, close-up, over-the-shoulder...), setting, light (moonlight, torch, volumetric fog, rim light), mood.
   Vertical 9:16 cinematic dark fantasy / mystery. Characters are fictional (hooded figures, silhouettes, creatures are great). NO text, NO letters, NO logos, NO real people or celebrities, NO gore.
 - anim (screen animation cue): zoom_in (quick punch-in, great for reveals) | zoom_out | slow_zoom_out | push_in | pan_left | pan_right | shake (jolt/danger) | drift. Vary them; use shake only 2-3 times.
 - transition (how this scene starts): cut | flash (white flash, big reveal) | fade (from black, calm/eerie) | glitch (something is wrong). Mostly cut; flash <=4 times, glitch <=3 times.
 - emph: 1-2 KEY words from the text that pop up as big kinetic yellow text (empty for HOOK scenes).
 - sfx: one sound at the key moment (none | whoosh | thud | rise | gasp | knock | sparkle | alarm | buzz | scratch | gulp). Use it on about half the scenes.
STYLE ANCHOR (style_anchor): ONE sentence (max 35 words) describing the fixed look of the whole film - colour palette, lighting and the main character's recurring appearance
(clothes, face marks, props). It is appended to every image prompt so the frames look like the same movie.
TITLE: 35-65 characters, curiosity-driven, no hashtags. DESCRIPTION: one hook sentence + 3-5 hashtags. TAGS: 6-10 short tags.
TOPIC: one short line describing the story setup (used to avoid repeats). music_mood: mysterious (default) or epic.
Return JSON only."""


def schema():
    S = lambda **k: {"type": "STRING", **k}
    sc = {"type": "OBJECT", "properties": {"text": S(), "section": S(enum=SECTIONS), "visual": S(), "anim": S(enum=ANIMS),
          "transition": S(enum=TRANS), "emph": S(), "sfx": S(enum=SFX)},
          "required": ["text", "section", "visual", "anim", "transition", "emph", "sfx"]}
    return {"type": "OBJECT", "properties": {"topic": S(), "title": S(), "description": S(), "tags": {"type": "ARRAY", "items": S()},
            "music_mood": S(enum=MOODS), "style_anchor": S(), "scenes": {"type": "ARRAY", "items": sc}},
            "required": ["topic", "title", "description", "tags", "music_mood", "style_anchor", "scenes"]}


def ask(prompt, sch, max_out=8000, think=1024):
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


def finalize(d):
    """Sections ki tarteeb, default cues, aur fixed cues: pehla scene zoom-in+flash, twist flash se shuru, aakhri scene slow zoom-out."""
    sc = d["scenes"]
    order = [SECTIONS.index(s["section"]) if s.get("section") in SECTIONS else -1 for s in sc]
    ok = (min(order) >= 0 and order == sorted(order) and order.count(0) >= 1 and order.count(2) >= 2)
    if not ok:                                              # model ki tarteeb galat -> position se: pehle 2 HOOK, aakhri 4 TWIST
        n = len(sc)
        for k, s in enumerate(sc):
            s["section"] = "HOOK" if k < 2 else ("TWIST" if k >= n - 4 else "BODY")
    body_cycle = ["push_in", "pan_left", "zoom_in", "drift", "pan_right", "push_in"]
    for k, s in enumerate(sc):
        if s.get("anim") not in ANIMS:
            s["anim"] = "zoom_in" if s["section"] == "HOOK" else body_cycle[k % len(body_cycle)]
        if s.get("transition") not in TRANS:
            s["transition"] = "cut"
        if s.get("sfx") not in SFX:
            s["sfx"] = "none"
        s["visual"] = re.sub(r"\s+", " ", s.get("visual") or "").strip() or f"dark fantasy cinematic scene, {s['text']}"
        toks = {_tok(w) for w in s["text"].split()}
        em = [w for w in re.findall(r"[A-Za-z0-9']+", s.get("emph") or "") if _tok(w) in toks][:2]
        s["emph"] = "" if s["section"] == "HOOK" else " ".join(em)
    sc[0]["anim"], sc[0]["transition"] = "zoom_in", "flash"
    first_twist = next(k for k, s in enumerate(sc) if s["section"] == "TWIST")
    sc[first_twist]["transition"] = "flash"
    sc[-1]["anim"] = "slow_zoom_out"
    d["style_anchor"] = re.sub(r"\s+", " ", d.get("style_anchor") or "").strip() or "cinematic dark fantasy, teal and amber palette, volumetric fog, lone hooded traveller"
    if d.get("music_mood") not in MOODS:
        d["music_mood"] = "mysterious"
    return d


def clean(d):
    for s in d["scenes"]:
        s["text"] = re.sub(r"\s+", " ", str(s.get("text", ""))).strip()
    d["scenes"] = [s for s in d["scenes"] if s["text"]]
    words = sum(len(s["text"].split()) for s in d["scenes"])
    if not (16 <= len(d["scenes"]) <= 28 and 105 <= words <= 175):
        raise ValueError(f"bad size: {len(d['scenes'])} scenes / {words} words")
    t = re.sub(r"\s*#\w+", "", d["title"]).strip()           # title mein hashtag main.py lagata hai
    if len(t) > 80:
        t = t[:80].rsplit(" ", 1)[0]
    d["title"] = t
    tags = []
    for x in d.get("tags") or []:                            # YouTube: tags kul 500 chars se kam
        x = re.sub(r"[^\w ]", "", str(x)).strip()
        if x and x.lower() not in [y.lower() for y in tags] and sum(len(y) + 1 for y in tags) + len(x) < 400:
            tags.append(x)
    d["tags"] = tags[:10] or ["darkfantasy", "mystery", "storytime", "twist"]
    return finalize(d)


def _S(text, sec, visual, anim="push_in", trans="cut", sfx="none", emph=""):
    return dict(text=text, section=sec, visual=visual, anim=anim, transition=trans, sfx=sfx, emph=emph)


FALLBACK = {
    "topic": "a lighthouse keeper discovers the light is a lullaby for drowned keepers", "title": "The Lighthouse Never Guided Ships",
    "description": "Every night, the light was calling something else.\n\n#darkfantasy #mystery #storytime #twist #shorts",
    "tags": ["darkfantasy", "mystery", "storytime", "twist", "shorts"], "music_mood": "mysterious",
    "style_anchor": "cinematic dark fantasy, teal storm and amber lantern light, lone keeper in a yellow oilskin coat with a grey beard",
    "scenes": [
        _S("Every night, this lighthouse never guided a single ship.", "HOOK", "low angle of a towering black lighthouse on a cliff, beam cutting through storm clouds, huge waves below, moonlight"),
        _S("It was calling something else.", "HOOK", "close-up of a giant glowing lamp lens, amber light, swirling fog, eerie reflection of a pale face"),
        _S("Elias became keeper after the last man vanished.", "BODY", "old keeper in a yellow oilskin coat climbing a spiral staircase, lantern in hand, long shadows"),
        _S("Rule one in the logbook: never watch the sea at midnight.", "BODY", "open leather logbook on a wooden desk, candle flame, handwritten warning, dust in the air", "push_in", "cut", "knock", "midnight"),
        _S("For years, he obeyed.", "BODY", "wide shot of the lighthouse at dawn over calm teal water, seagulls, soft mist"),
        _S("Then one stormy night, the lamp went dark.", "BODY", "lighthouse lamp room going black, lightning flash outside the windows, keeper silhouette", "shake", "glitch", "buzz", "dark"),
        _S("Below, the waves pulled back like a curtain.", "BODY", "dark ocean water drawing back from the rocks, exposed seabed, glowing foam, ominous sky", "pan_left"),
        _S("Hundreds of pale hands rose from the water.", "BODY", "hundreds of pale ghostly hands rising from black sea water under moonlight, volumetric fog", "zoom_in", "flash", "gasp", "hands"),
        _S("They weren't drowning. They were waiting.", "BODY", "close-up of one pale hand open towards the lighthouse beam, water dripping, teal glow", "drift", "cut", "none", "waiting"),
        _S("Elias relit the lamp with shaking fingers.", "BODY", "keeper's trembling hands striking a match beside a huge lens, sparks, amber glow", "push_in", "cut", "rise"),
        _S("The hands sank back, calm. He had kept them asleep.", "TWIST", "pale hands slowly sinking into calm glowing water, lighthouse beam sweeping, peaceful eerie mood", "zoom_out", "flash", "thud", "asleep"),
        _S("The logbook's last page was in his handwriting.", "TWIST", "close-up of a logbook page with scratchy handwriting, candlelight, trembling finger", "push_in", "fade", "none", "handwriting"),
        _S("Every keeper before him wrote the same warning.", "TWIST", "shelf of identical old logbooks with a dozen yellow coats hanging on hooks, dim lantern", "pan_right"),
        _S("The light was never for ships.", "TWIST", "wide cinematic shot of the lighthouse beam over the sea, shadowy figures below the surface", "drift", "cut", "whoosh"),
        _S("It was a lullaby for the drowned keepers.", "TWIST", "lantern glowing over a sea of sleeping pale faces beneath the waves, teal and amber, ethereal", "zoom_out", "cut", "sparkle", "lullaby"),
        _S("And tonight, the sea whispered his name.", "TWIST", "keeper alone on the balcony at night, huge dark waves, moon behind clouds, wind in his coat", "slow_zoom_out", "cut", "none", "whispered"),
    ],
}

ANIM_TXT = {"zoom_in": "Quick zoom-in", "zoom_out": "Zoom-out", "slow_zoom_out": "Slow zoom-out + dramatic vignette", "push_in": "Slow push-in",
            "pan_left": "Pan left", "pan_right": "Pan right", "shake": "Camera shake", "drift": "Floating drift"}
TRANS_TXT = {"cut": "hard cut", "flash": "flash transition", "fade": "fade from black", "glitch": "glitch transition"}


def write_plan(d):
    """story_plan.md: tumhare format mein (1. HOOK / 2. BODY / 3. TWIST & OUTRO) - padhne ke liye, video isi se banti hai."""
    heads = [("HOOK", "1. [HOOK - 0 to 5 seconds]"), ("BODY", "2. [BODY - 5 to 45 seconds]"), ("TWIST", "3. [TWIST & OUTRO - 45 to 60 seconds]")]
    out = [f"# {d['title']}", "", f"Style: {d['style_anchor']}", "Subtitles: word-by-word highlighted (yellow/white on dark box)", ""]
    last = len(d["scenes"])
    for key, head in heads:
        out.append(head)
        for n, s in enumerate(d["scenes"], 1):
            if s["section"] != key:
                continue
            cue = [ANIM_TXT.get(s["anim"], s["anim"]), TRANS_TXT.get(s["transition"], s["transition"])]
            if s["emph"]:
                cue.append(f"kinetic text: {s['emph'].upper()}")
            if key == "HOOK":
                cue.append("shaking bold text")
            if s["sfx"] != "none":
                cue.append(f"sfx: {s['sfx']}")
            if n == last:
                cue.append("pop-up subscribe/follow cue")
            out += [f"   - Scene {n} | Text/Script: {s['text']}", f"       Screen Animation Cue: {', '.join(cue)}",
                    f"       Visual Scene Description: {s['visual']}"]
        out.append("")
    open(PLAN, "w", encoding="utf-8").write("\n".join(out))


def main():
    for p in (OUT, PLAN):
        if os.path.exists(p):
            os.remove(p)
    hist = load_history()
    recent = [h.get("topic", "") for h in hist[-150:]]
    d, fb = None, False
    rejected = []
    if API_KEY:
        for attempt in range(4):
            seeds = (f"Inspiration (twist it into something fresh, do not copy literally): setting = {random.choice(SETTINGS)}; "
                     f"hero = {random.choice(HEROES)}; twist type = {random.choice(TWISTS)}.")
            prompt = (f"{RULES}\n\n{seeds}\nDo NOT repeat or closely resemble any of these past stories: {recent[-60:] + rejected}\nJSON only.")
            try:
                cand = clean(ask(prompt, schema()))
                if too_similar(cand["topic"] + " " + cand["title"], recent):
                    rejected.append(cand["topic"])
                    print(f"story attempt {attempt + 1}: too similar to history ({cand['topic']}) -> retry")
                    continue
                d = cand
                break
            except Exception as e:
                print(f"story attempt {attempt + 1} failed: {e}")
                time.sleep(3)
    if not d:
        if not os.environ.get("ALLOW_FALLBACK"):
            # Fallback par har baar wahi video upload hoti thi. Ab run fail hota hai, kuch upload nahi hota.
            sys.exit("ERROR: no fresh Gemini story (check GEMINI_API_KEY / quota). Stopping so no duplicate video is uploaded.")
        print("ALLOW_FALLBACK set -> offline fallback story (history mein save nahi hogi)")
        import copy
        d, fb = finalize(copy.deepcopy(FALLBACK)), True
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    write_plan(d)
    print("SCRIPT:", d["title"], f"({len(d['scenes'])} scenes, {sum(len(s['text'].split()) for s in d['scenes'])} words)")
    if not fb and not any(h.get("topic", "").lower() == d["topic"].lower() for h in hist):
        hist.append({"topic": d["topic"], "title": d["title"], "date": datetime.date.today().isoformat()})
        json.dump(hist[-300:], open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
