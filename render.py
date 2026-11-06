"""script.json -> 1080x1920 Short: Pollinations images + Kokoro voice + zoom/pan + captions + seamless loop."""
import json
import os
import random
import subprocess
import sys
import tempfile
import time

from PIL import Image, ImageDraw

import images
import voice

W, H, FPS = 1080, 1920, 30
GAP = 0.06  # scenes ke beech chhota saans (last scene mein nahi, taake loop seamless ho)
FONT = "DejaVu Sans"


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def fallback_card(path, prev=None):
    """Image na bane to pichli image dobara use hoti hai, warna simple gradient."""
    if prev and os.path.exists(prev):
        Image.open(prev).save(path)
        return
    img = Image.new("RGB", (720, 1280))
    d = ImageDraw.Draw(img)
    for y in range(1280):
        t = y / 1280
        d.line([(0, y), (720, y)], fill=(int(40 + 60 * t), int(30 + 40 * t), int(70 + 90 * t)))
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


def make_segment(img, audio, seg_dur, idx, out):
    n = max(2, int(seg_dur * FPS))
    z, x, y = zoom_expr(idx, n)
    vf = (
        f"[0:v]scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS},format=yuv420p[v];"
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
    """Chhote chunks (max 3 lafz / ~17 characters) taake caption screen ke andar rahe."""
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or len(" ".join(cur + [w])) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(scene_info, path):
    """Har lafz par highlight hone wale captions (active word yellow)."""
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Cap,{FONT},80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,9,2,2,60,60,430,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = []
    for start, speech, text in scene_info:
        words = [w for w in text.replace("\n", " ").split() if w]
        weights = [len(w) + (4 if w[-1] in ".,!?;:" else 0) for w in words]
        total = sum(weights) or 1
        t = start
        starts = []
        for w_i, wt in enumerate(weights):
            starts.append(t)
            t += speech * wt / total
        ends = starts[1:] + [start + speech]
        idx = 0
        for chunk in chunk_words(words, 3):
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


def create_short(data, output_path="output.mp4"):
    tmp = tempfile.mkdtemp()
    scenes = data["scenes"]
    segs, info = [], []
    ok_images, prev, t0 = 0, None, 0.0

    for i, sc in enumerate(scenes):
        print(f"Scene {i + 1}/{len(scenes)}: {sc['narration']}")
        audio = os.path.join(tmp, f"a{i}.wav")
        voice.synth(sc["narration"], audio)
        speech = duration(audio)

        img = os.path.join(tmp, f"i{i}.png")
        if images.fetch_image(sc["image_prompt"], img):
            ok_images += 1
            prev = img
        else:
            print("  image failed, reusing fallback")
            fallback_card(img, prev)
        time.sleep(2)  # Pollinations ko saans lene do

        last = i == len(scenes) - 1
        seg_dur = speech + (0.04 if last else GAP)
        out = os.path.join(tmp, f"s{i}.mp4")
        make_segment(img, audio, seg_dur, i, out)
        segs.append(out)
        info.append((t0, speech, sc["narration"]))
        t0 += seg_dur

    if ok_images == 0 and os.environ.get("ALLOW_NO_IMAGES") != "1":
        sys.exit("ERROR: Pollinations se koi image nahi bani, video post nahi ki ja rahi.")

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    joined = os.path.join(tmp, "joined.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])

    build_ass(info, os.path.join(tmp, "cap.ass"))
    abs_out = os.path.abspath(output_path)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", "joined.mp4", "-vf", "subtitles=cap.ass",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", abs_out], check=True, cwd=tmp)
    total = duration(abs_out)
    print(f"Video created: {output_path} ({total:.1f}s, {ok_images}/{len(scenes)} AI images)")
    if total > 59:
        print("WARNING: 59s se lamba hai; Gemini ko chhota script dene ke liye prompt mein word limit kam karein")


if __name__ == "__main__":
    with open("script.json", encoding="utf-8") as f:
        create_short(json.load(f), "output.mp4")
