"""Kokoro (male, engaging) voice; fail ho to edge-tts backup."""
import asyncio
import os
import subprocess


VOICE = os.environ.get("KOKORO_VOICE", "am_fenrir")  # am_fenrir / am_michael / am_puck / am_adam
SPEED = float(os.environ.get("KOKORO_SPEED", "1.22"))
_pipe = None


def _kokoro(text, path):
    global _pipe
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    if _pipe is None:
        _pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    parts = []
    for _, _, audio in _pipe(text, voice=VOICE, speed=SPEED, split_pattern=r"\n+"):
        if audio is not None:
            parts.append(audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio))
    if not parts:
        raise RuntimeError("kokoro returned no audio")
    sf.write(path, np.concatenate(parts), 24000)


def _edge(text, path):
    import edge_tts

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


def synth(text, path):
    raw = path + ".raw"
    try:
        _kokoro(text, raw)
    except Exception as e:  # noqa: BLE001
        print(f"Kokoro failed ({e}); using edge-tts backup")
        _edge(text, raw)
    _tighten(raw, path)
    os.remove(raw)
