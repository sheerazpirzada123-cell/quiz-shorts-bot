"""script.json -> output.mp4 (Short, 1080x1920, 9:16). Sab kuch code se: animation (cartoon.py), awaaz (voice.py), music + sfx (music.py)."""
import faulthandler
import json
import os
import subprocess
import sys
import tempfile
import time
import zlib

import cv2
import numpy as np

import cartoon
import music
import voice

cv2.setNumThreads(1)
FPS = 30
FONT = "DejaVu Sans"
OW, OH = 1080, 1920
CAP = dict(size=76, margin_v=285, margin_h=60, outline=9, words=3, chars=17)
EMO_SPEED = dict(excited=1.08, angry=1.05, surprised=1.0, scared=1.0, sad=0.9, tired=0.9, laughing=1.04,
                 smug=0.97, confused=0.97, embarrassed=0.96, love=0.98, happy=1.03, neutral=1.0)


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True)
    return float(out.strip())


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


def build_ass(scene_info, path):
    c = CAP
    head = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {OW}\nPlayResY: {OH}\nWrapStyle: 0\n\n"
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
                    ("{\\c&H00FFFF&\\fscx112\\fscy112}" + w.upper() + "{\\c&HFFFFFF&\\fscx100\\fscy100}") if k == j else w.upper()
                    for k, w in enumerate(chunk))
                lines.append(f"Dialogue: 0,{ass_time(starts[g])},{ass_time(ends[g])},Cap,,0,0,0,,{shown}")
            idx += len(chunk)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")


def mouth_envelope(x, n_frames):
    hop = music.SR / FPS
    env = np.zeros(n_frames, np.float32)
    for f in range(n_frames):
        a, b = int(f * hop), int((f + 1) * hop)
        seg = x[a:b]
        env[f] = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
    ref = float(np.percentile(env[env > 0.002], 85)) if (env > 0.002).any() else 1.0
    m = np.clip(env / max(ref, 1e-4), 0, 1.0) ** 0.8
    return np.convolve(m, [0.25, 0.5, 0.25], mode="same")


def sfx_events(sc, prev, t0, pre):
    ev = []
    if prev is not None and sc["bg"] != prev["bg"]:
        ev.append((t0, "whoosh", 0.7))
    elif prev is not None:
        ev.append((t0, "pop", 0.35))
    if sc["prop"] != "none" and (prev is None or prev["prop"] != sc["prop"]):
        ev.append((t0 + 0.14, "pop", 0.8))
    if sc.get("label") and (prev is None or prev.get("label") != sc["label"]):
        ev.append((t0 + 0.3, "ding", 0.6))
    name = sc.get("sfx", "none")
    if name != "none":
        ev.append((t0 + pre + 0.04, name, 0.9))
    elif sc["action"] == "shock":
        ev.append((t0 + 0.04, "thud", 0.8))
    if prev is None:
        ev.append((0.03, "pop", 0.8))
    return ev


def create_video(data, output_path):
    cast = data["characters"]
    scenes = data["scenes"]
    tmp = tempfile.mkdtemp()
    seed = zlib.crc32(data.get("topic", "x").encode()) % 100000
    t_start = time.time()

    speech_dur, wavs = [], []
    for i, sc in enumerate(scenes):
        ch = cast[min(sc["speaker"], len(cast) - 1)]
        print(f"[short] voice {i + 1}/{len(scenes)} ({ch['name']}): {sc['line']}", flush=True)
        wp = os.path.join(tmp, f"a{i}.wav")
        sp = max(0.85, min(1.45, voice.SPEED * EMO_SPEED.get(sc["emotion"], 1.0)))
        voice.synth(sc["line"], wp, sp, ch.get("voice", "m1"))
        x = music.read_wav(wp)
        wavs.append(x)
        speech_dur.append(len(x) / music.SR)

    starts, durs, pres, t0 = [], [], [], 0.0
    for i, sd in enumerate(speech_dur):
        sc = scenes[i]
        pre = 0.0 if i == 0 else (0.16 if (sc["action"] == "shock" or sc["emotion"] == "surprised") else 0.07)
        last = i == len(scenes) - 1
        d = pre + sd + (0.05 if last else 0.12)
        pres.append(pre)
        starts.append(t0)
        durs.append(d)
        t0 += d
    total = t0
    n_frames = int(round(total * FPS))

    voice_track = np.zeros(int(total * music.SR) + music.SR, np.float32)
    sfx = []
    for i, sc in enumerate(scenes):
        a = int((starts[i] + pres[i]) * music.SR)
        voice_track[a:a + len(wavs[i])] += wavs[i]
        sfx += sfx_events(sc, scenes[i - 1] if i else None, starts[i], pres[i])
    mood = data.get("music_mood", "quirky")
    mixed, credit = music.mix(voice_track[: int(total * music.SR)], total, mood, seed, sfx)
    audio_path = os.path.join(tmp, "mix.wav")
    music.write_wav(audio_path, mixed)
    print(f"[short] audio ready ({total:.1f}s, mood={mood})", flush=True)

    info = [(starts[i] + pres[i], speech_dur[i], sc["line"]) for i, sc in enumerate(scenes)]
    build_ass(info, os.path.join(tmp, "cap.ass"))

    abs_out = os.path.abspath(output_path)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{cartoon.W}x{cartoon.H}",
           "-r", str(FPS), "-i", "-", "-i", audio_path,
           "-vf", f"scale={OW}:{OH}:flags=lanczos,subtitles=cap.ass:fontsdir=/usr/share/fonts/truetype/dejavu",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", abs_out]
    voice._pipe = None
    import gc
    gc.collect()
    faulthandler.dump_traceback_later(120, repeat=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=tmp)
    renderer, cur_i, envs = None, -1, {}
    try:
        for f in range(n_frames):
            tg = f / FPS
            i = cur_i
            while i + 1 < len(scenes) and tg >= starts[i + 1] - 1e-9:
                i += 1
            i = max(i, 0)
            if i != cur_i:
                cur_i = i
                renderer = cartoon.SceneRenderer(scenes[i]["bg"], seed + i * 7, intro=(i == 0))
                envs[i] = mouth_envelope(wavs[i], int(round(durs[i] * FPS)) + 2)
            lt = tg - starts[i]
            env = envs[i]
            lt_v = lt - pres[i]
            fi = min(max(int(lt_v * FPS), 0), len(env) - 1)
            mouth = float(env[fi]) if 0.0 <= lt_v < speech_dur[i] else 0.0
            frame = renderer.frame(scenes[i], cast, lt, mouth, durs[i])
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                break
            if f % 90 == 0:
                print(f"[short] frame {f}/{n_frames} ({time.time() - t_start:.0f}s elapsed)", flush=True)
        proc.stdin.close()
    finally:
        rc = proc.wait()
        faulthandler.cancel_dump_traceback_later()
    if rc != 0:
        sys.exit(f"ERROR: ffmpeg fail hua (code {rc})")
    out_total = duration(abs_out)
    print(f"Video created: {output_path} ({out_total:.1f}s, {len(scenes)} scenes, {time.time() - t_start:.0f}s lagay)")
    if out_total > 59:
        print("WARNING: 59s se lamba hai; Short shayad Short na rahe")
    return out_total, credit


def main():
    if not os.path.exists("script.json"):
        sys.exit("script.json nahi mila (pehle script_gen.py chalayein)")
    with open("script.json", encoding="utf-8") as f:
        data = json.load(f)
    _, credit = create_video(data, "output.mp4")
    if credit:
        data["description"] = (data.get("description", "") + "\n\n" + credit).strip()
        with open("script.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
