"""Gemini se naya script banata hai.

MODE (env):
  both  -> script_long.json (landscape long video) + script_short.json (long ko promote karne wala teaser Short)
  long  -> sirf script_long.json
  short -> sirf script_short.json (standalone Short, loop ending)
Topic hamesha "duniya mein pehli baar kuch hua" type ka hota hai. history.json se purane topics repeat nahi hote.
"""
import datetime
import json
import os
import random
import re
import sys
import time

import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
MODE = os.environ.get("MODE", "both").strip().lower()
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"] if m]
HISTORY = "history.json"
CTA_FALLBACK = {
    "narration": "Want the full story? Watch the full video on my channel. It's linked in the description.",
    "image_prompt": "the stick man pointing excitedly at a giant glowing play button on a big screen, a crowd of tiny curious "
                    "stick men looking up at it, popcorn, a clapperboard and a magnifying glass floating around",
    "background": "clean plain white paper background",
}

# "Pehli baar" wale topic areas - Gemini inme se ek specific, sachcha "first" chunta hai
AREAS = [
    "the first time humans ever wore clothes, and the strange reasons why (not just warmth)",
    "the first time anyone cooked food, and how fire changed the human body",
    "the first time humans wore shoes, and what people walked on before",
    "the first haircut, shave, razor or hairstyle in history",
    "the first time humans brushed their teeth or did dentistry",
    "the first soap, bath, toilet or sewer in the world",
    "the first time anyone slept in a bed, used a pillow or built a house",
    "the first money, coin, bank or shop - how trade began",
    "the first time humans tamed an animal (dogs, cats, horses, chickens, cows)",
    "the first farmers: how and why humans first planted seeds",
    "the first time anyone drank tea, coffee, milk, beer or juice",
    "the first bread, pizza, sweets, ice cream or fast food",
    "the first mirror, jewelry, perfume or makeup in history",
    "the first glasses, umbrella, watch, clock or calendar",
    "the first time humans made music, danced or told a joke",
    "the first writing, alphabet, paper, book, letter or school",
    "the first doctor, surgery, medicine or hospital in history",
    "the first wheel, boat, road, bridge or map",
    "the first city, king, law, police or prison",
    "the first war, army, weapon or flag",
    "the first wedding, birthday, name, holiday or festival",
    "the first sport, game, toy or playground in history",
    "the first time humans painted, drew or made art (cave paintings, first statues)",
    "the first language, first word, first counting and first numbers",
    "what the very first ancient humans actually did all day, ate, and how they lived",
    "the first time humans crossed oceans, climbed mountains or reached the poles",
    "the first invention of everyday tools: needle, knife, rope, basket, pot",
    "the first time humans used a key, lock, door, window or stairs",
]

FOOTER_STYLE = (
    "VISUAL STYLE (very important): the video is a \"Mack and Explain in Paint\" style stick-man explainer. ONE recurring "
    "stick man (big plain white round head, simple dot eyes, expressive eyebrows, thin black line body) acts out the story. "
    "Because the same character appears in every scene, first write \"character\": ONE short phrase for his outfit/look for "
    "this video's era (e.g. \"wearing a rough animal-hide loincloth\", \"wearing a Roman toga and laurel wreath\")."
)
IMG_RULES = (
    "image_prompt for each scene (45-70 words): a DETAILED, concrete description of the picture for that exact narration: the "
    "stick man's pose, facial expression and action; 3 to 6 specific, richly detailed objects/props/buildings/animals around "
    "him that belong to the topic and narration (rack of clothes, bubbling pot, burning city, crowd of small stick men, map with "
    "route, thought bubble containing icons, lightbulb above head, etc). Show things, do not describe abstractions. Thought "
    "bubbles may contain pictures but NEVER words. NO text, letters or numbers in the image. "
    "background for each scene: 5-12 words, one of: \"clean plain white paper background\", \"flat warm orange wall with a grey "
    "floor strip\", \"green grass field with pale sky\", \"pale blue sky with ground\", \"dark night sky with stars and ground\" "
    "- choose what fits, using plain white for about half of the scenes."
)
ACCURACY = (
    "ACCURACY: everything must be true. For prehistoric or uncertain 'firsts' say what the evidence suggests "
    "(\"archaeologists think\", \"the oldest known\", \"genetic studies of lice suggest\") - never invent exact dates or names. "
    "Include real names, places, numbers and years only when you are sure."
)

SCENE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "narration": {"type": "STRING"},
        "image_prompt": {"type": "STRING"},
        "background": {"type": "STRING"},
    },
    "required": ["narration", "image_prompt", "background"],
}


def schema(extra=None):
    props = {
        "topic": {"type": "STRING"},
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "character": {"type": "STRING"},
        "scenes": {"type": "ARRAY", "items": SCENE_SCHEMA},
    }
    req = ["topic", "title", "description", "tags", "character", "scenes"]
    if extra:
        props.update(extra)
        req += list(extra)
    return {"type": "OBJECT", "properties": props, "required": req}


LONG_SCHEMA = schema({"thumb_text": {"type": "STRING"}})
SHORT_SCHEMA = schema()

FALLBACK = {
    "topic": "the first clothes",
    "title": "Why Did Humans Really Start Wearing Clothes? #Shorts",
    "description": "The surprising reason humans first wore clothes. #Shorts #history #facts",
    "tags": ["history", "facts", "first clothes", "ancient humans", "shorts"],
    "character": "wearing a simple animal-hide cloak",
    "scenes": [
        {"narration": "Humans did not start wearing clothes because they were cold.",
         "image_prompt": "a shivering-free stick man in a warm sunny savanna holding a folded animal hide, puzzled eyebrows, thought bubble with a question mark icon, acacia tree and a grazing zebra behind him",
         "background": "clean plain white paper background"},
        {"narration": "Scientists studied the DNA of clothing lice to find out when it began.",
         "image_prompt": "a stick man scientist with a magnifying glass inspecting a giant cartoon louse on a leaf, DNA helix floating above, a microscope and a notebook beside him",
         "background": "clean plain white paper background"},
        {"narration": "Those lice split from head lice around one hundred seventy thousand years ago.",
         "image_prompt": "a big family tree drawn with two louse branches splitting apart, a stick man pointing at the split with a stick, a stone-age sun and moon above, small bones and tools around",
         "background": "flat warm orange wall with a grey floor strip"},
        {"narration": "That means people were wearing something long before the ice age cold arrived.",
         "image_prompt": "a stick man in a rough hide wrap walking confidently across a warm grassland, small footprints behind him, a sun high above and a far-away snowy mountain in a thought bubble",
         "background": "green grass field with pale sky"},
        {"narration": "So why dress up? Maybe for decoration, status, or protection from insects.",
         "image_prompt": "three small stick men in a row: one with a feather necklace, one with a bone belt, one swatting flies, a proud main stick man in the middle with a flower crown, butterflies around",
         "background": "pale blue sky with ground"},
        {"narration": "And the oldest needles ever found are about fifty thousand years old.",
         "image_prompt": "a stick man holding a huge bone needle up to the sun with a thread of sinew, a pile of sewn hides, a tiny cave behind him and a smiling face",
         "background": "clean plain white paper background"},
        {"narration": "Warm clothes came later, and they helped humans spread into freezing lands.",
         "image_prompt": "a stick man in a thick fur coat and boots trudging through snow, a line of small stick men following, snowflakes and a mammoth silhouette far behind, smoke from a campfire",
         "background": "pale blue sky with ground"},
        {"narration": "So the real first clothes were never about warmth. Then what were they about?",
         "image_prompt": "the stick man with a big question mark above his head, holding up a fur cloak in one hand and a feather in the other, a crowd of tiny curious stick men and a glowing lightbulb around",
         "background": "clean plain white paper background"},
    ],
}


def load_history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def ask_gemini(prompt, sch, max_out=8192):
    last = None
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        cfg = {
            "temperature": 1.0,
            "maxOutputTokens": max_out if "2.0" not in model else 8192,
            "responseMimeType": "application/json",
            "responseSchema": sch,
        }
        if "2.5-flash" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": 0}  # thinking tokens lambi script ko kaat dete hain
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
        for _ in range(2):
            try:
                r = requests.post(url, headers={"x-goog-api-key": API_KEY}, json=body, timeout=180)
                if r.status_code == 200:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
            except Exception as e:  # noqa: BLE001
                last = f"{model}: {e}"
            time.sleep(4)
    raise RuntimeError(last)


def parse(text):
    return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())


def clean_common(d):
    for s in d["scenes"]:
        assert s["narration"].strip() and s["image_prompt"].strip()
        s.setdefault("background", "clean plain white paper background")
    d["tags"] = [t for t in d["tags"] if isinstance(t, str)][:12]
    return d


def validate_long(d):
    n = len(d["scenes"])
    words = sum(len(s["narration"].split()) for s in d["scenes"])
    assert 22 <= n <= 46, f"scene count {n}"
    assert 520 <= words <= 1150, f"word count {words}"
    d["title"] = re.sub(r"\s*#shorts\s*", " ", d["title"], flags=re.I).strip()[:95]
    d["thumb_text"] = (d.get("thumb_text") or d["topic"]).upper()[:24]
    return clean_common(d)


def validate_short(d, teaser):
    n = len(d["scenes"])
    words = sum(len(s["narration"].split()) for s in d["scenes"])
    assert (9 if teaser else 8) <= n <= 17, f"scene count {n}"
    assert 70 <= words <= 165, f"word count {words}"
    return clean_common(d)


def with_retries(label, fn):
    for attempt in range(3):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            print(f"{label} attempt {attempt + 1} failed: {e}")
    return None


def gen_long(area, recent):
    target = os.environ.get("LONG_TARGET_WORDS", "760")
    prompt = f"""You write scripts for LONG YouTube explainer videos (landscape, 4 to 6 minutes) in the style of the animated stick-man channel "Ink Explainer"
(example video: "What Did Ancient Humans Actually Do All Day?" - a surprising truth that flips what people believe, told like a story).

Area: {area}. Pick ONE specific "first time ever" story inside it - the first time humans/anyone did this thing. Do NOT repeat or closely resemble any of these earlier topics: {recent}.
Random seed: {random.randint(1, 10**7)}.

{ACCURACY}

STRUCTURE (flow like one continuous story, no headings spoken):
1. HOOK (first scene, max 20 words): a shocking claim or myth-flip. No greetings, no "did you know", no channel intro.
2. The world BEFORE this first: what life was like without it.
3. The first known moment/evidence: who, where, when, how we know.
4. The surprising WHY (the real reason is not what people assume).
5. Myths vs reality: at least one popular belief that is wrong.
6. How it spread and changed daily life; weird or funny consequences and small details.
7. A modern echo: how this still shows up in our life today.
8. Payoff of every open loop, then one closing thought-provoking question for the comments, then one short line inviting viewers to subscribe for more first-ever stories.

RULES:
- About {target} words of narration in total (about 5 minutes). 30 to 38 scenes. Each scene = 1 or 2 spoken sentences, 18 to 30 words, and gets its OWN picture that shows exactly what that narration says.
- Teenager-friendly, conversational, high-energy spoken English like an excited storyteller. Vary rhythm, use questions, small suspense ("but here's the weird part"), keep open loops and pay them off.
- Narration is plain spoken text only: no emojis, no hashtags, no stage directions, no scene numbers.
- {FOOTER_STYLE}
- {IMG_RULES}
- title: curiosity-driven, max 80 characters, NO hashtags, e.g. "The First Time Humans Wore Clothes (It Wasn't For Warmth)". description: 3 short paragraphs (what the video reveals without spoiling the twist), then 6-8 hashtags. tags: 10-15 short keywords.
- thumb_text: 2 to 4 punchy words in capital letters for the thumbnail (e.g. "THE FIRST CLOTHES?"), max 22 characters.
- topic: 3-8 words naming the specific topic."""
    return with_retries("Gemini long", lambda: validate_long(parse(ask_gemini(prompt, LONG_SCHEMA, 24000))))


def gen_short(area, recent, long=None):
    teaser = long is not None
    if teaser:
        story = "\n".join(f"{i + 1}. {s['narration']}" for i, s in enumerate(long["scenes"]))
        brief = f"""You write the Shorts TEASER that promotes a long video on the same channel.
Long video title: {long['title']}
Topic: {long['topic']}
The long video's full story (for your reference, scene by scene):
{story}

TEASER RULES:
- Tell only the FIRST part of this story (setup + the single most surprising fact), told gripping and fast, then STOP at the most curious moment. Do NOT reveal the twist or the answer - leave a strong open loop.
- Last scene = call to action, 10-18 words, must contain the words "full video" and mention the description, e.g. "Want the full story? Watch the full video on my channel, it's linked in the description."
- The scene before the CTA should be the cliffhanger line (a question or half-reveal).
- Everything told must match the long video's facts exactly. Use the same character look: {long['character']}.
- NO seamless loop requirement here (this one ends with the CTA)."""
    else:
        brief = f"""Area for this video: {area}. Pick ONE specific, surprising, TRUE "first time ever" topic inside it. Do NOT repeat or closely resemble any of these earlier topics: {recent}.
Random seed: {random.randint(1, 10**7)}.
{ACCURACY}
STANDALONE RULES:
- SEAMLESS LOOP: the very last sentence must flow naturally back into scene 1 when the video restarts (end with a question or half-thought whose answer or continuation is the hook). No "subscribe", no "follow", no goodbye, no outro.
- Create tension: keep a small open loop ("but here's the weird part") and pay it off before the end."""
    prompt = f"""You write viral YouTube Shorts scripts in the style of the animated explainer channel "Ink Explainer"
(example video: "What Did Ancient Humans Actually Do All Day?" - a surprising truth that flips what people believe, explained like a story).

{brief}

COMMON RULES:
- Total narration 100-125 words (about 40-45 seconds spoken). 11 to 14 scenes, each scene ONE short punchy sentence (6-13 words). Every sentence gets its OWN picture that shows exactly what that sentence says.
- Scene 1 is the HOOK, max 14 words: a shocking claim, a myth-flip or a curiosity gap that makes people unable to swipe away. No greetings, no "did you know", no intro.
- Teenager-friendly, conversational, high-energy spoken English like an excited storyteller. Short sentences, vary rhythm, occasional exclamation or question.
- Narration is plain spoken text only: no emojis, no hashtags, no stage directions.
- {FOOTER_STYLE}
- {IMG_RULES}
- title: max 70 characters, curiosity-driven, ends with " #Shorts". description: 2 sentences plus 5-8 hashtags. tags: 8-12 short keywords.
- topic: 3-8 words naming the specific topic."""

    def run():
        d = validate_short(parse(ask_gemini(prompt, SHORT_SCHEMA, 8192)), teaser)
        if teaser:
            d["topic"], d["character"] = long["topic"], long["character"]
            last = d["scenes"][-1]["narration"].lower()
            if not ("full" in last and ("video" in last or "story" in last)):
                d["scenes"].append(dict(CTA_FALLBACK))  # CTA pakka karne ke liye
        return d
    return with_retries("Gemini short", run)


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
            sys.exit("Gemini long script 3 baar fail - kuch post nahi kiya (dobara run karein)")
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
