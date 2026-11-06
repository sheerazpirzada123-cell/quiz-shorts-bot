"""Kokoro (male, engaging) voice; fail ho to edge-tts backup."""
import asyncio
import os


VOICE = os.environ.get("KOKORO_VOICE", "am_michael")  # am_michael / am_fenrir / am_puck / am_adam
SPEED = float(os.environ.get("KOKORO_SPEED", "1.08"))
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


def synth(text, path):
    try:
        _kokoro(text, path)
    except Exception as e:  # noqa: BLE001
        print(f"Kokoro failed ({e}); using edge-tts backup")
        _edge(text, path)  # mp3 data; ffprobe/ffmpeg content se pehchan lete hain
