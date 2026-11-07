"""Kokoro (male, engaging) voice; fail ho to edge-tts backup."""
import asyncio
import os
import subprocess


VOICE = os.environ.get("KOKORO_VOICE", "am_fenrir")  # am_fenrir / am_michael / am_puck / am_adam
SPEED = float(os.environ.get("KOKORO_SPEED", "1.22"))
_pipe = None


def _kokoro(text, path, speed):
    global _pipe
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    if _pipe is None:
        _pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    parts = []
    for _, _, audio in _pipe(text, voice=VOICE, speed=speed, split_pattern=r"\n+"):
        if audio is not None:
            parts.append(audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio))
    if not parts:
        raise RuntimeError("kokoro returned no audio")
    sf.write(path, np.concatenate(parts), 24000, format="WAV", subtype="PCM_16")


def _edge(text, path):
    import edge_tts

    voice = os.environ.get("EDGE_VOICE", "en-US-AndrewMultilingualNeural")
    try:
        asyncio.run(edge_tts.Communicate(text, voice=voice, rate="+8%", pitch="+0Hz").save(path))
    except Exception:  # noqa: BLE001  (multilingual voice na mile to purani wali)
        asyncio.run(edge_tts.Communicate(text, voice="en-US-AndrewNeural", rate="+8%").save(path))


def _tighten(src, dst):
    """Shuru/beech/aakhir ki lambi khamoshi kaat do, awaaz thodi tez aur zordar karo."""
    af = (
        "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.02:"
        "stop_periods=-1:stop_duration=0.12:stop_threshold=-42dB:stop_silence=0.05,"
        "areverse,silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.03,areverse,"
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=60,loudnorm=I=-14:TP=-1.5:LRA=7"
    )
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", af, "-ar", "44100", dst], check=True)


def _fake(text, path):
    """Sirf local test ke liye (FAKE_VOICE=1): awaaz jaisi shor wali dhun, taake lip-sync/timing test ho sake."""
    import numpy as np
    import wave

    n_words = max(1, len(text.split()))
    dur = n_words / 2.9
    sr = 44100
    t = np.arange(int(dur * sr)) / sr
    syl = np.clip(np.sin(2 * np.pi * 4.2 * t) * 0.6 + 0.5, 0, 1)
    x = (np.sin(2 * np.pi * 140 * t) + 0.5 * np.sin(2 * np.pi * 280 * t)) * syl * 0.25
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def synth(text, path, speed=None):
    if os.environ.get("FAKE_VOICE") == "1":
        return _fake(text, path)
    raw_wav, raw_mp3 = path + ".k.wav", path + ".e.mp3"
    src = None
    for attempt in (1, 2):
        try:
            _kokoro(text, raw_wav, speed or SPEED)
            src = raw_wav
            break
        except Exception as e:  # noqa: BLE001
            print(f"Kokoro failed (attempt {attempt}): {e}")
    if src is None:
        print("Using edge-tts backup")
        _edge(text, raw_mp3)
        src = raw_mp3
    _tighten(src, path)
    for f in (raw_wav, raw_mp3):
        if os.path.exists(f):
            os.remove(f)
