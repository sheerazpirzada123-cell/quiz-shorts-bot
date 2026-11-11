
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
    recent = [h.get("topic", "") for h in hist]
    d, fb = None, False
    rejected = []
    last_validation_error = ""
    if API_KEY:
        for attempt in range(4):
            seeds = (f"Inspiration (twist it into something fresh, do not copy literally): setting = {random.choice(SETTINGS)}; "
                     f"hero = {random.choice(HEROES)}; twist type = {random.choice(TWISTS)}.")
            prompt = (f"{RULES}\n\n{seeds}\nDo NOT repeat or closely resemble any of these past stories: {recent[-60:] + rejected}\n"
                      f"STRICT REMINDER: 18-22 scenes, exactly 5-7 spoken words per scene, and 115-155 words total. "
                      f"The local validator rejects anything outside 16-28 scenes and 105-175 words. "
                      f"{('Your previous response failed: ' + last_validation_error + '. Correct the length now; do not repeat that mistake. ') if last_validation_error else ''}"
                      "Return JSON only.")
            try:
                cand = clean(ask(prompt, schema()))
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
        import copy
        d, fb = finalize(copy.deepcopy(FALLBACK)), True
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    write_plan(d)
    print("SCRIPT:", d["title"], f"({len(d['scenes'])} scenes, {sum(len(s['text'].split()) for s in d['scenes'])} words)")
    if not fb and not any(h.get("topic", "").lower() == d["topic"].lower() for h in hist):
        hist.append({"topic": d["topic"], "title": d["title"], "date": datetime.date.today().isoformat()})
        json.dump(hist[-1000:], open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
