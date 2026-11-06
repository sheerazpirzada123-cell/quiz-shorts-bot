"""quiz.json se 1080x1920 Short banata hai (Pillow + edge-tts + ffmpeg, moviepy/ImageMagick ki zaroorat nahi)."""
import asyncio
import json
import os
import random
import subprocess
import tempfile

import edge_tts
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
LETTERS = "ABCD"
VOICES = ["en-US-GuyNeural", "en-US-AriaNeural", "en-US-JennyNeural", "en-GB-RyanNeural"]
FONT_BOLD = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]
FONT_REG = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"]

PALETTES = [
    ((30, 20, 80), (120, 40, 160)),
    ((10, 60, 90), (20, 160, 160)),
    ((90, 20, 40), (220, 90, 60)),
    ((20, 40, 30), (40, 150, 90)),
    ((25, 25, 45), (70, 90, 200)),
]


def font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def gradient(c1, c2):
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return img


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=fnt) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def centered(draw, text, fnt, y, fill, max_w=920, line_gap=14):
    for line in wrap(draw, text, fnt, max_w):
        w = draw.textlength(line, font=fnt)
        draw.text(((W - w) / 2, y), line, font=fnt, fill=fill)
        y += fnt.size + line_gap
    return y


def frame(q, palette, highlight=None, countdown=None):
    img = gradient(*palette)
    d = ImageDraw.Draw(img)
    centered(d, "QUIZ TIME", font(FONT_BOLD, 64), 130, (255, 215, 0))
    if q.get("topic"):
        centered(d, q["topic"].upper(), font(FONT_REG, 38), 220, (230, 230, 230))
    d.rounded_rectangle((70, 320, W - 70, 800), radius=45, fill=(255, 255, 255, 255))
    qf = font(FONT_BOLD, 62)
    lines = wrap(d, q["question"], qf, 860)
    while len(lines) > 5 and qf.size > 40:
        qf = font(FONT_BOLD, qf.size - 4)
        lines = wrap(d, q["question"], qf, 860)
    total_h = len(lines) * (qf.size + 14)
    y = 320 + (480 - total_h) / 2
    for line in lines:
        w = d.textlength(line, font=qf)
        d.text(((W - w) / 2, y), line, font=qf, fill=(25, 25, 50))
        y += qf.size + 14

    of = font(FONT_BOLD, 50)
    for i, opt in enumerate(q["options"]):
        top = 860 + i * 190
        if highlight is None:
            fill, txt = (255, 255, 255), (25, 25, 50)
        elif i == highlight:
            fill, txt = (40, 190, 90), (255, 255, 255)
        else:
            fill, txt = (110, 110, 130), (200, 200, 210)
        d.rounded_rectangle((90, top, W - 90, top + 150), radius=40, fill=fill)
        d.text((130, top + 42), f"{LETTERS[i]}.", font=of, fill=txt)
        text = opt
        while d.textlength(text, font=of) > 760 and len(text) > 5:
            text = text[:-2]
        if text != opt:
            text = text.rstrip() + "…"
        d.text((220, top + 42), text, font=of, fill=txt)

    if countdown is not None:
        cf = font(FONT_BOLD, 200)
        s = str(countdown)
        w = d.textlength(s, font=cf)
        d.ellipse((W / 2 - 150, 1640, W / 2 + 150, 1900), fill=(255, 215, 0))
        d.text(((W - w) / 2, 1655), s, font=cf, fill=(25, 25, 50))
    elif highlight is None:
        centered(d, "Think fast! Comment your answer", font(FONT_BOLD, 46), 1680, (255, 255, 255))
    else:
        centered(d, "Follow for a daily quiz!", font(FONT_BOLD, 46), 1700, (255, 255, 255))
    return img


async def tts(text, path, voice):
    last = None
    for _ in range(3):
        try:
            await edge_tts.Communicate(text, voice=voice, rate="+5%").save(path)
            if os.path.getsize(path) > 1000:
                return
        except Exception as e:  # noqa: BLE001
            last = e
            await asyncio.sleep(2)
    raise RuntimeError(f"edge-tts failed: {last}")


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def segment(img_path, audio, dur, out):
    """Ek image + (audio ya silence) ko dur seconds ki mp4 mein badalta hai."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", img_path]
    if audio:
        cmd += ["-i", audio]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += [
        "-filter_complex", "[1:a]apad,aformat=sample_rates=44100:channel_layouts=stereo[a]",
        "-map", "0:v", "-map", "[a]", "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", out,
    ]
    subprocess.run(cmd, check=True)


def create_short(q, output_path="output.mp4"):
    tmp = tempfile.mkdtemp()
    voice = random.choice(VOICES)
    palette = random.choice(PALETTES)
    c = q["correct"]

    ask = q["question"].rstrip("?.! ") + "? " + " ".join(f"{LETTERS[i]}. {o}." for i, o in enumerate(q["options"]))
    ans = f"The answer is {LETTERS[c]}, {q['options'][c]}. {q.get('explanation', '')}"
    a1, a2 = os.path.join(tmp, "a1.mp3"), os.path.join(tmp, "a2.mp3")
    asyncio.run(tts(ask, a1, voice))
    asyncio.run(tts(ans, a2, voice))

    segs = []

    def add(name, img, audio, dur):
        p = os.path.join(tmp, name + ".png")
        img.save(p)
        o = os.path.join(tmp, name + ".mp4")
        segment(p, audio, dur, o)
        segs.append(o)

    add("q", frame(q, palette), a1, duration(a1) + 0.6)
    for n in (3, 2, 1):
        add(f"c{n}", frame(q, palette, countdown=n), None, 1.0)
    add("a", frame(q, palette, highlight=c), a2, duration(a2) + 1.2)

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", "-movflags", "+faststart", output_path], check=True)
    total = duration(output_path)
    print(f"Video created: {output_path} ({total:.1f}s)")
    if total > 59:
        print("WARNING: video is longer than 59s, YouTube may not treat it as a Short")


if __name__ == "__main__":
    with open("quiz.json", encoding="utf-8") as f:
        create_short(json.load(f), "output.mp4")
