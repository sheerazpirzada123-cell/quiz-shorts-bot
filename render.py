"""script_*.json -> video. Short: 1080x1920 (9:16). Long: 1920x1080 (16:9). AI images + Kokoro voice + zoom/pan + captions.

MODE (env): both | long | short.  Output: output_short.mp4, output_long.mp4, thumbnail.jpg (long ke liye)
"""
import json
import os
import random
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

import images
import voice

FPS = 30
FONT = "DejaVu Sans"
MIN_IMAGE_RATIO = float(os.environ.get("MIN_IMAGE_RATIO", "0.7"))  # itni % scenes ki asli AI image na bani to post nahi

PROFILES = {
    "short": dict(W=1080, H=1920, orient="portrait", up=(1620, 2880), gap=0.06, loop=True,
                  cap=dict(size=80, margin_v=430, margin_h=60, outline=9, words=3, chars=17)),
    "long": dict(W=1920, H=1080, orient="landscape", up=(2400, 1350), gap=0.18, loop=False,
                 cap=dict(size=60, margin_v=70, margin_h=140, outline=6, words=6, chars=34)),
}


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def fallback_card(path, size, prev=None):
    """Image na bane to pichli image dobara use hoti hai, warna simple gradient."""
    if prev and os.path.exists(prev):
        Image.open(prev).save(path)
        return
    w, h = size
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(40 + 60 * t), int(30 + 40 * t), int(70 + 90 * t)))
    img.save(path)


def zoom_expr(i, n):
    """Har scene ka alag camera move (zoom in/out/pan)."""
    k = i % 4
    if k == 0:
        return f"1+0.20*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if k == 1:
        return f"1.20-0.20*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if k == 2:
        return "1.18", f"(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"
    return "1.18", f"(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)"


def make_segment(p, img, audio, seg_dur, idx, out):
    n = max(2, int(seg_dur * FPS))
    z, x, y = zoom_expr(idx, n)
    uw, uh = p["up"]
    vf = (
        f"[0:v]scale={uw}:{uh}:force_original_aspect_ratio=increase,crop={uw}:{uh},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={p['W']}x{p['H']}:fps={FPS},format=yuv420p[v];"
        f"[1:a]apad,aformat=sample_rates=44100:channel_layouts=stereo[a]"
    )
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", img, "-i", audio, "-filter_complex", vf,
         "-map", "[v]", "-map", "[a]", "-t", f"{seg_dur:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", out])


def ass_time(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def chunk_words(words, max_words=3, max_chars=17):
    """Chhote chunks taake caption screen ke andar rahe."""
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or len(" ".join(cur + [w])) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(p, scene_info, path):
    """Har lafz par highlight hone wale captions (active word yellow)."""
    c = p["cap"]
    head = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {p['W']}\nPlayResY: {p['H']}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Cap,{FONT},{c['size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{c['outline']},2,2,"
        f"{c['margin_h']},{c['margin_h']},{c['margin_v']},1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = []
    for start, speech, text in scene_info:
        words = [w for w in text.replace("\n", " ").split() if w]
        if not words:
            continue
        weights = [len(w) + (4 if w[-1] in ".,!?;:" else 0) for w in words]
        total = sum(weights) or 1
        t = start
        starts = []
        for wt in weights:
            starts.append(t)
            t += speech * wt / total
        ends = starts[1:] + [start + speech]
        idx = 0
        for chunk in chunk_words(words, c["words"], c["chars"]):
            for j, _ in enumerate(chunk):
                g = idx + j
                shown = " ".join(
                    ("{\\c&H00FFFF&}" + w.upper() + "{\\c&HFFFFFF&}") if k == j else w.upper()
                    for k, w in enumerate(chunk)
                )
                shown = shown.replace("\n", " ")
                lines.append(f"Dialogue: 0,{ass_time(starts[g])},{ass_time(ends[g])},Cap,,0,0,0,,{shown}")
            idx += len(chunk)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")


def make_thumbnail(src, text, out="thumbnail.jpg"):
    """Long video ke liye 1280x720 thumbnail: hook scene ki image + bada outline wala text."""
    img = Image.open(src).convert("RGB").resize((1280, 720), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    size = 110
    while size > 60:
        try:
            font = ImageFont.truetype(fp, size)
        except OSError:
            return
        words, lines, cur = text.split(), [], ""
        for w in words:  # max 2 lines
            trial = (cur + " " + w).strip()
            if d.textlength(trial, font=font) <= 1180 or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) <= 2 and max(d.textlength(l, font=font) for l in lines) <= 1180:
            break
        size -= 8
    y = 720 - 40 - len(lines) * int(size * 1.15)
    for line in lines:
        w = d.textlength(line, font=font)
        d.text(((1280 - w) / 2, y), line, font=font, fill=(255, 235, 0), stroke_width=max(8, size // 12),
               stroke_fill=(0, 0, 0))
        y += int(size * 1.15)
    img.save(out, quality=90)


def create_video(kind, data, output_path):
    p = PROFILES[kind]
    tmp = tempfile.mkdtemp()
    scenes = data["scenes"]
    segs, info = [], []
    ok_images, prev, t0 = 0, None, 0.0
    video_seed = random.randint(1, 10**7)  # saari images par ek hi seed -> character ek jaisa
    speed = float(os.environ.get("LONG_SPEED", "1.12")) if kind == "long" else None

    for i, sc in enumerate(scenes):
        print(f"[{kind}] Scene {i + 1}/{len(scenes)}: {sc['narration']}", flush=True)
        audio = os.path.join(tmp, f"a{i}.wav")
        voice.synth(sc["narration"], audio, speed)
        speech = duration(audio)

        img = os.path.join(tmp, f"i{i}.png")
        if images.fetch_image(sc["image_prompt"], img, character=data.get("character", ""),
                              background=sc.get("background", ""), seed=video_seed, orient=p["orient"]):
            ok_images += 1
            prev = img
        else:
            print("  image failed, reusing fallback")
            fallback_card(img, (p["W"], p["H"]), prev)
        if kind == "long" and i == 0:
            try:
                make_thumbnail(img, data.get("thumb_text") or data["topic"].upper())
            except Exception as e:  # noqa: BLE001
                print(f"  thumbnail skipped: {e}")

        last = i == len(scenes) - 1
        seg_dur = speech + (0.04 if (last and p["loop"]) else (0.5 if last else p["gap"]))
        out = os.path.join(tmp, f"s{i}.mp4")
        make_segment(p, img, audio, seg_dur, i, out)
        segs.append(out)
        info.append((t0, speech, sc["narration"]))
        t0 += seg_dur

    ratio = ok_images / len(scenes)
    if ok_images == 0 and os.environ.get("ALLOW_NO_IMAGES") == "1":
        pass
    elif ratio < MIN_IMAGE_RATIO:
        sys.exit(f"ERROR: sirf {ok_images}/{len(scenes)} scenes ki AI image bani (minimum {MIN_IMAGE_RATIO:.0%}); "
                 f"video post nahi ki ja rahi. Baad mein dobara run karein.")

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    joined = os.path.join(tmp, "joined.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])

    build_ass(p, info, os.path.join(tmp, "cap.ass"))
    abs_out = os.path.abspath(output_path)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", "joined.mp4", "-vf", "subtitles=cap.ass",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21" if kind == "long" else "20", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", abs_out], check=True, cwd=tmp)
    total = duration(abs_out)
    print(f"Video created: {output_path} ({total:.1f}s, {ok_images}/{len(scenes)} AI images)")
    if kind == "short" and total > 59:
        print("WARNING: 59s se lamba hai; Short shayad Short na rahe")
    return total


def main():
    mode = os.environ.get("MODE", "both").strip().lower()
    jobs = []
    if mode in ("both", "long"):
        jobs.append(("long", "script_long.json", "output_long.mp4"))
    if mode in ("both", "short"):
        jobs.append(("short", "script_short.json", "output_short.mp4"))
    for kind, sj, out in jobs:
        if not os.path.exists(sj):
            print(f"{sj} nahi mila, {kind} skip")
            continue
        with open(sj, encoding="utf-8") as f:
            create_video(kind, json.load(f), out)


if __name__ == "__main__":
    main()
