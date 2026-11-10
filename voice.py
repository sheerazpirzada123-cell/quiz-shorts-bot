"""Kokoro voices (male / female, 2-2 alag awaazein). Kokoro fail ho to edge-tts backup."""
import asyncio
import os
import re
import subprocess

VOICE_MAP = {
    "m1": os.environ.get("KOKORO_VOICE_M1", "am_michael"),
    "m2": os.environ.get("KOKORO_VOICE_M2", "am_puck"),
    "f1": os.environ.get("KOKORO_VOICE_F1", "af_heart"),
    "f2": os.environ.get("KOKORO_VOICE_F2", "af_bella"),
}
EDGE_MAP = {
    "m1": "en-US-AndrewMultilingualNeural", "m2": "en-US-GuyNeural",
    "f1": "en-US-AvaMultilingualNeural", "f2": "en-US-JennyNeural",
}
SPEED = float(os.environ.get("KOKORO_SPEED", "1.12"))
_pipe = None


def _kokoro(text, path, speed, voice):
    global _pipe
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    if _pipe is None:
        _pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    parts = []
    sents = [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]
    for si, sent in enumerate(sents or [text]):
        for _, _, audio in _pipe(sent, voice=voice, speed=speed, split_pattern=r"\n+"):
            if audio is not None:
                parts.append(audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio))
        if si < len(sents) - 1:
            parts.append(np.zeros(int(24000 * 0.12), dtype=np.float32))
    if not parts:
        raise RuntimeError("kokoro returned no audio")
    sf.write(path, np.concatenate(parts), 24000, format="WAV", subtype="PCM_16")


def _edge(text, path, vid):
    import edge_tts

    voice = EDGE_MAP.get(vid, EDGE_MAP["m1"])
    try:
        asyncio.run(edge_tts.Communicate(text, voice=voice, rate="+8%").save(path))
    except Exception:
        fb = "en-US-AriaNeural" if vid.startswith("f") else "en-US-AndrewNeural"
        asyncio.run(edge_tts.Communicate(text, voice=fb, rate="+8%").save(path))


def _tighten(src, dst):
    af = (
        "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.02:"
        "stop_periods=-1:stop_duration=0.24:stop_threshold=-42dB:stop_silence=0.11,"
        "areverse,silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.03,areverse,"
        "highpass=f=75,equalizer=f=170:t=q:w=1.0:g=1.5,equalizer=f=3200:t=q:w=1.2:g=2.5,"
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=60,loudnorm=I=-14:TP=-1.5:LRA=7"
    )
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", af, "-ar", "44100", dst], check=True)


def _fake(text, path, vid="m1"):
    import numpy as np
    import wave

    n_words = max(1, len(text.split()))
    dur = n_words / 2.9
    sr = 44100
    t = np.arange(int(dur * sr)) / sr
    syl = np.clip(np.sin(2 * np.pi * 4.2 * t) * 0.6 + 0.5, 0, 1)
    f0 = {"m1": 130, "m2": 175, "f1": 230, "f2": 270}.get(vid, 140)
    x = (np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2 * f0 * t)) * syl * 0.25
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def synth(text, path, speed=None, vid="m1"):
    """text -> path (wav). vid: m1 / m2 (male), f1 / f2 (female)."""
    vid = vid if vid in VOICE_MAP else "m1"
    if os.environ.get("FAKE_VOICE") == "1":
        return _fake(text, path, vid)
    raw_wav, raw_mp3 = path + ".k.wav", path + ".e.mp3"
    src = None
    for attempt in (1, 2):
        try:
            _kokoro(text, raw_wav, speed or SPEED, VOICE_MAP[vid])
            src = raw_wav
            break
        except Exception as e:
            print(f"Kokoro failed (attempt {attempt}): {e}")
    if src is None:
        print("Using edge-tts backup")
        _edge(text, raw_mp3, vid)
        src = raw_mp3
    _tighten(src, path)
    for f in (raw_wav, raw_mp3):
        if os.path.exists(f):
            os.remove(f)
