"""Background music + sound effects, sab code se.

Default (MUSIC_MODE=synth): music numpy se banta hai -> 100% original, koi copyright claim / Content ID nahi ho sakta,
koi download nahi, kabhi fail nahi hota.
MUSIC_MODE=download : Kevin MacLeod (incompetech, CC-BY 4.0) ka track online utarta hai (credit description mein khud lag jata hai);
                      download fail ho to synth chal jata hai.
"""
import os
import random
import subprocess
import tempfile
import wave

import numpy as np

SR = 44100
MODE = os.environ.get("MUSIC_MODE", "synth").strip().lower()
MUSIC_GAIN = float(os.environ.get("MUSIC_GAIN", "0.20"))   # voice ke muqable music kitna halka ho
SFX_GAIN = float(os.environ.get("SFX_GAIN", "0.30"))


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


# ------------------------------------------------------------------ instruments
def _env_t(n):
    return np.arange(n) / SR


def pluck(f, dur=0.5, bright=1.0):
    n = int(dur * SR)
    t = _env_t(n)
    x = (np.sin(2 * np.pi * f * t) + 0.45 * bright * np.sin(4 * np.pi * f * t) * np.exp(-t * 14)
         + 0.2 * bright * np.sin(6 * np.pi * f * t) * np.exp(-t * 22))
    return x * np.exp(-t * 7.5) * np.minimum(1, t * 400)


def bass(f, dur=0.6):
    n = int(dur * SR)
    t = _env_t(n)
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 3.2) * np.minimum(1, t * 300)


def pad(f, dur=2.2):
    n = int(dur * SR)
    t = _env_t(n)
    x = np.zeros(n)
    for det, a in ((1.0, 1.0), (1.004, 0.7), (0.996, 0.7), (2.0, 0.25)):
        x += a * np.sin(2 * np.pi * f * det * t + det)
    att = np.minimum(1, t / 0.6)
    rel = np.minimum(1, (dur - t) / 0.7)
    return x * att * rel * 0.35


def kick():
    n = int(0.28 * SR)
    t = _env_t(n)
    f = 45 + 110 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)


def hat(rnd, open_=False):
    n = int((0.16 if open_ else 0.05) * SR)
    t = _env_t(n)
    x = np.diff(rnd.randn(n + 1))
    return x * np.exp(-t * (28 if open_ else 90)) * 0.5


def snare(rnd):
    n = int(0.18 * SR)
    t = _env_t(n)
    return (rnd.randn(n) * 0.6 + np.sin(2 * np.pi * 190 * t) * 0.5) * np.exp(-t * 22)


def _add(buf, x, pos, g=1.0):
    pos = int(pos)
    if pos >= len(buf) or pos < 0:
        return
    e = min(len(buf), pos + len(x))
    buf[pos:e] += x[:e - pos] * g


# ------------------------------------------------------------------ synth music
MOOD = {  # bpm, minor?, progressions (scale degrees), kick, arp style
    "quirky": dict(bpm=116, minor=False, progs=[[0, 5, 3, 4], [0, 3, 5, 4], [5, 3, 0, 4]], kick=True, arp="stac", pad=0.5),
    "mysterious": dict(bpm=84, minor=True, progs=[[0, 5, 2, 6], [0, 3, 5, 4], [0, 6, 5, 6]], kick=False, arp="slow", pad=1.0),
    "epic": dict(bpm=100, minor=True, progs=[[0, 5, 2, 6], [0, 2, 6, 4], [5, 6, 0, 0]], kick=True, arp="drive", pad=1.1),
    "chill": dict(bpm=92, minor=False, progs=[[0, 4, 5, 3], [3, 4, 2, 5], [0, 5, 3, 4]], kick=False, arp="soft", pad=0.8),
}
MAJ = [0, 2, 4, 5, 7, 9, 11]
MIN = [0, 2, 3, 5, 7, 8, 10]


def synth_music(total_sec, mood="quirky", seed=1):
    rnd = np.random.RandomState(seed % 100000)
    pr = random.Random(seed)
    p = MOOD.get(mood, MOOD["quirky"])
    scale = MIN if p["minor"] else MAJ
    root = pr.choice([48, 50, 52, 53, 55, 57])  # C3..A3
    beat = 60.0 / p["bpm"]
    bar = beat * 4
    n_bars = int(total_sec / bar) + 3
    buf = np.zeros(int((n_bars * bar + 4) * SR), np.float32)

    def note(deg, octv=0):
        d = deg % 7
        return root + scale[d] + 12 * (deg // 7) + 12 * octv

    section_len = 8
    for b in range(n_bars):
        sec = (b // section_len) % 4
        prog = p["progs"][0 if sec in (0, 2) else (1 if sec == 1 else 2)]
        chord = prog[b % 4]
        t0 = b * bar
        tones = [chord, chord + 2, chord + 4, chord + 7]
        # pad
        for d in tones[:3]:
            _add(buf, pad(mtof(note(d, 1)), bar + 0.9), t0 * SR, 0.20 * p["pad"])
        # bass
        _add(buf, bass(mtof(note(chord, -1)), beat * 1.8), t0 * SR, 0.55)
        _add(buf, bass(mtof(note(chord + 4, -1)), beat * 1.6), (t0 + 2 * beat) * SR, 0.42)
        if p["arp"] in ("stac", "drive", "soft"):
            order = [0, 1, 2, 3, 2, 1, 2, 3] if (b // 2) % 2 == 0 else [0, 2, 1, 3, 0, 2, 3, 1]
            step = beat / 2
            for i in range(8):
                if p["arp"] == "soft" and i % 2 == 1:
                    continue
                d = tones[order[i]]
                _add(buf, pluck(mtof(note(d, 1)), 0.35 if p["arp"] == "stac" else 0.6), (t0 + i * step) * SR,
                     0.26 if p["arp"] != "soft" else 0.22)
            if sec in (1, 3) and p["arp"] != "soft":  # melody-ish top line
                for i, off in enumerate([0, 4, 6]):
                    _add(buf, pluck(mtof(note(tones[(i + b) % 4], 2)), 0.5, 0.6), (t0 + off * step) * SR, 0.17)
        else:  # slow mysterious plucks
            for i, off in enumerate([0, 3, 5]):
                _add(buf, pluck(mtof(note(tones[(i + b) % 4], 2)), 1.1, 0.5), (t0 + off * beat * 0.75) * SR, 0.2)
        # drums
        if p["kick"]:
            for q in (0, 2):
                _add(buf, kick(), (t0 + q * beat) * SR, 0.55)
            if p["arp"] == "drive":
                _add(buf, snare(rnd), (t0 + 3 * beat) * SR, 0.18)
            for i in range(4):
                _add(buf, hat(rnd), (t0 + (i + 0.5) * beat) * SR, 0.20)
        elif p["arp"] == "slow":
            _add(buf, kick(), t0 * SR, 0.30)
            _add(buf, kick(), (t0 + 2.5 * beat) * SR, 0.18)
        else:
            for i in range(8):
                _add(buf, hat(rnd), (t0 + i * beat / 2) * SR, 0.10)
    # chhota reverb/echo
    for d, g in ((0.23, 0.28), (0.41, 0.17), (0.67, 0.10)):
        k = int(d * SR)
        buf[k:] += buf[:-k] * g
    n = int(total_sec * SR)
    out = buf[:n].copy()
    fade = int(2.0 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    out[:int(0.5 * SR)] *= np.linspace(0, 1, int(0.5 * SR))
    out /= max(0.05, float(np.abs(out).max()))
    return out.astype(np.float32)


# ------------------------------------------------------------------ optional download
KM_TRACKS = [  # Kevin MacLeod, incompetech.com, CC-BY 4.0
    "Sneaky Snitch", "Fluffing a Duck", "Carefree", "Monkeys Spinning Monkeys", "Investigations", "Wallpaper",
    "Local Forecast - Elevator", "Pamgaea",
]


def download_music(total_sec, seed):
    import requests
    pr = random.Random(seed)
    names = KM_TRACKS[:]
    pr.shuffle(names)
    for name in names[:3]:
        url = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/" + name.replace(" ", "%20") + ".mp3"
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200 or len(r.content) < 300_000:
                print(f"music download {name}: HTTP {r.status_code}, {len(r.content)} bytes - skip")
                continue
            tmp = tempfile.mkdtemp()
            mp3, wav = os.path.join(tmp, "m.mp3"), os.path.join(tmp, "m.wav")
            with open(mp3, "wb") as f:
                f.write(r.content)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ac", "1", "-ar", str(SR), wav], check=True)
            x = read_wav(wav)
            if len(x) < 20 * SR:
                continue
            reps = int(total_sec * SR / len(x)) + 2
            x = np.tile(x, reps)[: int(total_sec * SR)].copy()
            fade = int(2.0 * SR)
            x[-fade:] *= np.linspace(1, 0, fade)
            x /= max(0.05, float(np.abs(x).max()))
            credit = (f'Music: "{name}" Kevin MacLeod (incompetech.com) Licensed under Creative Commons: By Attribution 4.0 '
                      f"License http://creativecommons.org/licenses/by/4.0/")
            return x.astype(np.float32), credit
        except Exception as e:  # noqa: BLE001
            print(f"music download failed ({name}): {str(e)[:120]}")
    return None, ""


# ------------------------------------------------------------------ sfx
def sfx_bank(seed=3):
    rnd = np.random.RandomState(seed)
    bank = {}
    n = int(0.38 * SR)
    t = _env_t(n)
    spec = np.fft.rfft(rnd.randn(n))
    fr = np.fft.rfftfreq(n, 1 / SR)
    spec *= np.exp(-((fr - 1800) / 1500.0) ** 2)
    w = np.fft.irfft(spec, n)
    w /= np.abs(w).max()
    bank["whoosh"] = w * np.sin(np.pi * np.clip(t / 0.38, 0, 1)) ** 1.5 * 0.9
    n = int(0.16 * SR)
    t = _env_t(n)
    bank["pop"] = np.sin(2 * np.pi * np.cumsum(700 * np.exp(-t * 12) + 220) / SR) * np.exp(-t * 22)
    n = int(0.7 * SR)
    t = _env_t(n)
    bank["ding"] = (np.sin(2 * np.pi * 1318 * t) + 0.5 * np.sin(2 * np.pi * 1975 * t)) * np.exp(-t * 7) * 0.6
    n = int(0.4 * SR)
    t = _env_t(n)
    bank["thud"] = (np.sin(2 * np.pi * 70 * t) * 1.0 + rnd.randn(n) * 0.25 * np.exp(-t * 60)) * np.exp(-t * 9)
    n = int(0.5 * SR)
    t = _env_t(n)
    bank["rise"] = np.sin(2 * np.pi * np.cumsum(300 + 900 * (t / 0.5) ** 2) / SR) * np.sin(np.pi * t / 0.5) * 0.5
    return bank


# ------------------------------------------------------------------ wav io
def read_wav(path):
    with wave.open(path, "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        x = np.frombuffer(raw, np.int32).astype(np.float32) / 2147483648.0
    else:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:  # sirf sanity: ffmpeg se 44100 hi aata hai
        idx = np.linspace(0, len(x) - 1, int(len(x) * SR / sr))
        x = np.interp(idx, np.arange(len(x)), x).astype(np.float32)
    return x


def write_wav(path, x):
    y = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(y.tobytes())


# ------------------------------------------------------------------ final mix
def mix(voice, total_sec, mood, seed, sfx_events):
    """voice: float32 mono (total_sec lambi). sfx_events: [(time_sec, name, gain)]. Returns (mix, credit)."""
    n = int(total_sec * SR)
    voice = np.pad(voice, (0, max(0, n - len(voice))))[:n]
    music, credit = (None, "")
    if MODE == "download":
        music, credit = download_music(total_sec, seed)
    if music is None:
        music = synth_music(total_sec, mood, seed)
    # music ko awaaz ke neeche dabao (ducking)
    hop = int(0.02 * SR)
    frames = np.abs(voice[: (n // hop) * hop]).reshape(-1, hop).max(axis=1)
    act = np.clip(frames / 0.05, 0, 1)
    k = 12
    sm = np.convolve(act, np.ones(k) / k, mode="same")
    duck = 1.0 - 0.62 * np.clip(sm * 1.4, 0, 1)
    duck_s = np.interp(np.arange(n), (np.arange(len(duck)) + 0.5) * hop, duck)
    music = np.pad(music, (0, max(0, n - len(music))))[:n]
    out = voice + music * duck_s * MUSIC_GAIN * 1.6
    bank = sfx_bank(seed)
    for tsec, name, g in sfx_events:
        if name in bank:
            _add(out, bank[name].astype(np.float32), tsec * SR, g * SFX_GAIN)
    peak = float(np.abs(out).max())
    if peak > 0.97:
        out = out * (0.97 / peak)
    return out.astype(np.float32), credit
