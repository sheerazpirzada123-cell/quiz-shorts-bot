"""script_*.json -> video. Short: 1080x1920 (9:16). Long: 1920x1080 (16:9).

Poora visual code se banta hai (anim.py): koi image API / internet nahi chahiye, is liye video hamesha ban jati hai.
Awaaz: Kokoro (voice.py). Music + sound effects: music.py (code se, copyright-free).
MODE (env): both | long | short.  Output: output_short.mp4, output_long.mp4, thumbnail.jpg (long ke liye)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import zlib

import faulthandler

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import anim
import music
import voice

cv2.setNumThreads(1)  # torch (Kokoro) ke saath OpenMP/thread ulajhne se bachne ke liye
FPS = 30
FONT = "DejaVu Sans"
PROFILES = {
    "short": dict(W=720, H=1280, OW=1080, OH=1920, portrait=True, gap=0.10,
                  cap=dict(size=80, margin_v=330, margin_h=60, outline=9, words=3, chars=17)),
    "long": dict(W=1280, H=720, OW=1920, OH=1080, portrait=False, gap=0.28,
                 cap=dict(size=58, margin_v=60, margin_h=140, outline=6, words=6, chars=34)),
}
DEFAULT_CAST = [dict(name="Hero", gender="male", hair="short", garment="tunic", accessory="none", color="blue")]


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True)
    return float(out.strip())


# ------------------------------------------------------------------ captions
def ass_time(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def chunk_words(words, max_words=3, max_chars=17):
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
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {p['OW']}\nPlayResY: {p['OH']}\nWrapStyle: 0\n\n"
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
                lines.append(f"Dialogue: 0,{ass_time(starts[g])},{ass_time(ends[g])},Cap,,0,0,0,,{shown}")
            idx += len(chunk)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")


def make_thumbnail(frame_bgr, text, out="thumbnail.jpg"):
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).resize((1280, 720), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    size = 120
    font = None
    while size > 60:
        try:
            font = ImageFont.truetype(fp, size)
        except OSError:
            return
        words, lines, cur = text.split(), [], ""
        for w in words:
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
    y = 40
    for line in lines:
        w = d.textlength(line, font=font)
        d.text(((1280 - w) / 2, y), line, font=font, fill=(255, 235, 0), stroke_width=max(8, size // 12), stroke_fill=(0, 0, 0))
        y += int(size * 1.15)
    img.save(out, quality=90)


# ------------------------------------------------------------------ audio helpers
def mouth_envelope(x, n_frames):
    """Awaaz ki zor se har frame ka munh khulne ka andaza (0..1) - lip sync."""
    hop = music.SR / FPS
    env = np.zeros(n_frames, np.float32)
    for f in range(n_frames):
        a, b = int(f * hop), int((f + 1) * hop)
        seg = x[a:b]
        env[f] = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
    ref = float(np.percentile(env[env > 0.002], 85)) if (env > 0.002).any() else 1.0
    m = np.clip(env / max(ref, 1e-4), 0, 1.0) ** 0.8
    sm = np.convolve(m, [0.25, 0.5, 0.25], mode="same")
    return sm


def sfx_for_scene(sc, t0):
    ev = []
    if t0 > 0:
        ev.append((t0, "whoosh", 0.7))
    for n, name in enumerate(sc.get("props", [])[:3]):
        ev.append((t0 + 0.2 + 0.2 * n, "pop", 0.8))
    if (sc.get("label") or "").strip():
        ev.append((t0 + 0.35, "ding", 0.7))
    if sc.get("action") == "shock":
        ev.append((t0 + 0.05, "thud", 0.9))
    if sc.get("action") == "celebrate":
        ev.append((t0 + 0.15, "ding", 0.6))
    return ev


# ------------------------------------------------------------------ main builder
def create_video(kind, data, output_path):
    p = PROFILES[kind]
    st = anim.Stage(p["W"], p["H"], p["portrait"])
    tmp = tempfile.mkdtemp()
    scenes = data["scenes"]
    cast = data.get("characters") or DEFAULT_CAST
    speed = float(os.environ.get("LONG_SPEED", "1.12")) if kind == "long" else None
    seed = zlib.crc32(data.get("topic", "x").encode()) % 100000
    teaser = bool(data.get("teaser"))
    t_start = time.time()

    # 1) awaaz (har scene ki alag)
    audio, speech_dur, wavs = [], [], []
    for i, sc in enumerate(scenes):
        print(f"[{kind}] voice {i + 1}/{len(scenes)}: {sc['narration']}", flush=True)
        wp = os.path.join(tmp, f"a{i}.wav")
        # Poori video mein NARRATOR ek hi hai (male boy). Character (larki ho ya larka) apni awaaz mein nahi bolta.
        voice.synth(sc["narration"], wp, speed, "male")
        x = music.read_wav(wp)
        wavs.append(x)
        speech_dur.append(len(x) / music.SR)

    # 2) timeline
    starts, durs, t0 = [], [], 0.0
    for i, sd in enumerate(speech_dur):
        last = i == len(scenes) - 1
        end_pad = 0.04 if (last and kind == "short" and not teaser) else (0.7 if last else p["gap"])
        d = sd + end_pad
        starts.append(t0)
        durs.append(d)
        t0 += d
    total = t0
    n_frames = int(round(total * FPS))

    # 3) audio: awaaz + music + sfx
    voice_track = np.zeros(int(total * music.SR) + music.SR, np.float32)
    sfx = []
    for i, sc in enumerate(scenes):
        a = int(starts[i] * music.SR)
        voice_track[a:a + len(wavs[i])] += wavs[i]
        sfx += sfx_for_scene(sc, starts[i])
    mood = data.get("music_mood", "quirky")
    mixed, credit = music.mix(voice_track[: int(total * music.SR)], total, mood, seed, sfx)
    audio_path = os.path.join(tmp, "mix.wav")
    music.write_wav(audio_path, mixed)
    print(f"[{kind}] audio ready ({total:.1f}s, mood={mood})", flush=True)

    # 4) captions
    info = [(starts[i], speech_dur[i], sc["narration"]) for i, sc in enumerate(scenes)]
    build_ass(p, info, os.path.join(tmp, "cap.ass"))

    # 5) frames -> ffmpeg (pipe)
    abs_out = os.path.abspath(output_path)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{p['W']}x{p['H']}",
           "-r", str(FPS), "-i", "-", "-i", audio_path,
           "-vf", f"scale={p['OW']}:{p['OH']}:flags=lanczos,subtitles=cap.ass:fontsdir=/usr/share/fonts/truetype/dejavu",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20" if kind == "short" else "21", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", abs_out]
    try:  # Kokoro model ka bojh/threads hata do, ab sirf frames banane hain
        voice._pipe = None
        import gc
        gc.collect()
    except Exception:  # noqa: BLE001
        pass
    faulthandler.dump_traceback_later(120, repeat=True)  # kahin atke to log mein dikhe kahan
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=tmp)
    renderer, cur_i, envs = None, -1, {}
    thumb_done = kind != "long"
    try:
        for f in range(n_frames):
            tg = f / FPS
            i = cur_i
            while i + 1 < len(scenes) and tg >= starts[i + 1] - 1e-9:
                i += 1
            i = max(i, 0)
            if i != cur_i:
                cur_i = i
                sc = scenes[i]
                renderer = anim.SceneRenderer(st, sc.get("bg", "white"), seed + i * 7)
                nfr = int(round(durs[i] * FPS)) + 2
                envs[i] = mouth_envelope(wavs[i], nfr)
            lt = tg - starts[i]
            env = envs[i]
            fi = min(int(lt * FPS), len(env) - 1)
            mouth = float(env[fi]) if lt < speech_dur[i] else 0.0
            frame = renderer.frame(scenes[i], cast, i, lt, mouth, durs[i])
            if not thumb_done and i == 0 and lt >= 0.9:
                try:
                    make_thumbnail(frame, data.get("thumb_text") or data["topic"].upper())
                except Exception as e:  # noqa: BLE001
                    print(f"  thumbnail skipped: {e}")
                thumb_done = True
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                break
            if f % 90 == 0:
                print(f"[{kind}] frame {f}/{n_frames} ({time.time() - t_start:.0f}s elapsed)", flush=True)
        proc.stdin.close()
    finally:
        rc = proc.wait()
        faulthandler.cancel_dump_traceback_later()
    if rc != 0:
        sys.exit(f"ERROR: ffmpeg fail hua (code {rc})")
    out_total = duration(abs_out)
    print(f"Video created: {output_path} ({out_total:.1f}s, {len(scenes)} scenes, {time.time() - t_start:.0f}s lagay)")
    if kind == "short" and out_total > 59:
        print("WARNING: 59s se lamba hai; Short shayad Short na rahe")
    return out_total, credit


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
            data = json.load(f)
        _, credit = create_video(kind, data, out)
        if credit:  # CC-BY music ho to credit description mein khud lag jaye
            data["description"] = (data.get("description", "") + "\n\n" + credit).strip()
            with open(sj, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
