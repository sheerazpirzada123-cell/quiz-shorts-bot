"""Narration voice (free): Kokoro (offline) -> fallback edge-tts. Har scene ka alag wav + word timings + mouth envelope."""
import asyncio
import os
import re
import subprocess
import wave

import numpy as np

SR = 24000
VOICE = os.environ.get("KOKORO_VOICE", "am_adam")
SPEED = float(os.environ.get("VOICE_SPEED", "1.08"))
EDGE_VOICE = os.environ.get("EDGE_VOICE", "en-US-AndrewNeural")
_pipe = None


def _kokoro(text, path):
    global _pipe
    from kokoro import KPipeline
    import soundfile as sf
    if _pipe is None:
        _pipe = KPipeline(lang_code="a")
    parts = []
    for _, _, audio in _pipe(text, voice=VOICE, speed=SPEED, split_pattern=r"\n+"):
        parts.append(np.asarray(audio, dtype=np.float32))
    if not parts:
        raise RuntimeError("kokoro: no audio")
    sf.write(path, np.concatenate(parts), SR)


def _edge(text, path):
    import edge_tts
    mp3 = path + ".mp3"
    rate = f"{int((SPEED - 1) * 100):+d}%"
    asyncio.run(edge_tts.Communicate(text, EDGE_VOICE, rate=rate).save(mp3))
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", str(SR), "-ac", "1", path])


def _fake(text, path):
    """Sirf offline test ke liye (VOICE_ENGINE=fake): bolne jaisi awaaz."""
    n = int(len(text) * 0.065 * SR)
    t = np.arange(n) / SR
    env = np.clip(np.sin(t * 2 * np.pi * 4.2) * 0.8 + 0.3, 0, 1) ** 1.5
    x = (np.sin(2 * np.pi * 140 * t) + 0.5 * np.sin(2 * np.pi * 280 * t)) * env * 0.3
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def synth(text, path):
    if os.environ.get("VOICE_ENGINE", "").lower() == "fake":
        _fake(text, path)
        return "fake"
    errs = []
    for name, fn in (("kokoro", _kokoro), ("edge", _edge)):
        if os.environ.get("VOICE_ENGINE", "").lower() not in ("", name):
            continue
        try:
            fn(text, path)
            return name
        except Exception as e:
            errs.append(f"{name}: {str(e)[:120]}")
    raise RuntimeError("voice fail: " + " | ".join(errs))


def read(path):
    with wave.open(path, "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16 if sw == 2 else np.int32).astype(np.float32)
    x /= 32768.0 if sw == 2 else 2147483648.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def trim(x, sr, thr=0.012):
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x, 0.0, len(x) / sr
    a, b = max(0, idx[0] - int(0.03 * sr)), min(len(x), idx[-1] + int(0.08 * sr))
    return x[a:b], 0.0, (b - a) / sr


def word_times(text, dur):
    """Words ke start/end: lambai + punctuation pause ke hisaab se estimate."""
    words = text.split()
    wts = []
    for w in words:
        base = max(2.0, len(re.sub(r"\W", "", w)) + 1.5)
        if w.endswith((",", ";", ":")):
            base += 2.5
        if w.endswith((".", "!", "?")):
            base += 4.5
        wts.append(base)
    tot = sum(wts)
    out, t = [], 0.0
    for w, k in zip(words, wts):
        d = dur * k / tot
        out.append((w, t, t + d))
        t += d
    return out


def envelope(x, sr, fps):
    hop = int(sr / fps)
    n = len(x) // hop
    if n == 0:
        return np.zeros(1, np.float32)
    e = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    e = e / (np.percentile(e, 95) + 1e-6)
    return np.clip(e, 0, 1).astype(np.float32)


def build(scenes, tmp, fps=30, gap=0.14, lead=0.35, tail=0.5):
    """Har scene: wav banata hai, scene ki 'hold' = voice length + gap. Returns (voice_mix_array@SR, per-scene info)."""
    chunks, info, t = [], [], 0.0
    eng = None
    for i, sc in enumerate(scenes):
        p = os.path.join(tmp, f"v{i}.wav")
        eng = synth(sc["text"], p)
        x, sr = read(p)
        if sr != SR:
            x = np.interp(np.linspace(0, len(x), int(len(x) * SR / sr), endpoint=False), np.arange(len(x)), x).astype(np.float32)
        x, _, d = trim(x, SR)
        pre = lead if i == 0 else 0.0
        post = tail if i == len(scenes) - 1 else gap
        hold = pre + d + post
        wt = [(w, pre + a, pre + b) for w, a, b in word_times(sc["text"], d)]
        info.append(dict(start=t, hold=hold, words=wt, env=envelope(x, SR, fps), env_off=pre, voice_off=pre))
        chunks.append((t + pre, x))
        t += hold
    out = np.zeros(int(t * SR) + SR, np.float32)
    for st, x in chunks:
        a = int(st * SR)
        out[a:a + len(x)] += x
    print(f"[voice] engine={eng}, total {t:.1f}s")
    return out[: int(t * SR)], info, t
