"""Narration voice (free): Kokoro (offline) -> fallback edge-tts. Har scene ka alag wav + word timings + mouth envelope."""
import asyncio
import os
import re
import subprocess
import unicodedata
import wave

import numpy as np

SR = 24000
VOICE = os.environ.get("KOKORO_VOICE", "am_adam")
SPEED = float(os.environ.get("VOICE_SPEED", "1.03"))          # 1.08 par lafz dab jaate the -> thoda dheema = saaf
EDGE_VOICE = os.environ.get("EDGE_VOICE", "en-US-AndrewNeural")
_pipe = None

# Kokoro (misaki) ke liye saaf talaffuz: [lafz](/phonemes/). Default American "water" mein 't' flap ('d' jaisa) ho jata hai.
# Naye lafz yahan add kar sakte hain.
PRON = {
    "water": "wˈɔtɚ",
    "waters": "wˈɔtɚz",
    "watery": "wˈɔtɚɹi",
}
_PRON_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, PRON), key=len, reverse=True)) + r")\b", re.I)


def _kokoro_markup(text):
    return _PRON_RE.sub(lambda m: f"[{m.group(0)}](/{PRON[m.group(0).lower()]}/)", text)


def clean_text(text):
    """TTS ko ulta-seedha karne wali cheezein hataata hai: emoji, markdown, '...', '—', '!!', adhoori punctuation."""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = re.sub(r"[\u2013\u2014]+", ", ", t)
    t = re.sub(r"\s-\s", ", ", t)
    t = t.replace("&", " and ").replace("%", " percent").replace("/", " ")
    t = re.sub(r"[^\w\s.,!?;:'\"()\-$]", " ", t)                 # emoji / markdown / ajeeb symbols
    lines = []
    for ln in t.split("\n"):
        ln = re.sub(r"\s*\.{2,}\s*", ", ", ln)                    # "..." -> chhota saaf pause
        ln = re.sub(r"([!?.,;:])\1+", r"\1", ln)
        ln = re.sub(r"([!?])[.!?]+", r"\1", ln)
        ln = re.sub(r"\s+([.,!?;:])", r"\1", ln)
        ln = re.sub(r"\s+", " ", ln).strip(" ,;:-")
        if not ln:
            continue
        tail = ln.rstrip("\"')")
        if not tail or tail[-1] not in ".!?":                     # jumla poora ho -> awaaz beech mein nahi atakti
            ln += "."
        lines.append(ln)
    return "\n".join(lines) or text.strip()


def _fade(x, sr, ms_in=6, ms_out=25):
    """Shuru/aakhir mein chhota fade -> click/pop khatam."""
    x = np.array(x, dtype=np.float32, copy=True)
    a = min(len(x) // 2, int(sr * ms_in / 1000))
    b = min(len(x) // 2, int(sr * ms_out / 1000))
    if a > 1:
        x[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    if b > 1:
        x[-b:] *= np.linspace(1, 0, b, dtype=np.float32)
    return x


def _kokoro(text, path):
    global _pipe
    from kokoro import KPipeline
    import soundfile as sf
    if _pipe is None:
        _pipe = KPipeline(lang_code="a")
    gap = np.zeros(int(0.08 * SR), np.float32)

    def run(t):
        parts = []
        for _, _, audio in _pipe(t, voice=VOICE, speed=SPEED, split_pattern=r"\n+"):
            a = audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio
            a = np.asarray(a, dtype=np.float32).reshape(-1)
            if len(a) == 0:
                continue
            if parts:
                parts.append(gap)
            parts.append(_fade(a, SR, 4, 12))
        return parts

    try:
        parts = run(_kokoro_markup(text))
    except Exception:                                             # purana kokoro/misaki markup na samjhe to seedha text
        parts = run(text)
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


ENGINES = {"kokoro": _kokoro, "edge": _edge, "fake": _fake}


def engines():
    forced = os.environ.get("VOICE_ENGINE", "").lower()
    return [forced] if forced in ENGINES else ["kokoro", "edge"]


def synth(text, path, engine):
    """Ek hi engine (ek hi awaaz). Do baar koshish, phir error (build() poori video agle engine se dobara banata hai)."""
    text = clean_text(text)
    err = None
    for _ in range(2):
        try:
            ENGINES[engine](text, path)
            return engine
        except Exception as e:
            err = e
    raise RuntimeError(f"{engine}: {str(err)[:120]}")


def read(path):
    with wave.open(path, "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16 if sw == 2 else np.int32).astype(np.float32)
    x /= 32768.0 if sw == 2 else 2147483648.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def trim(x, sr, thr=0.006):
    """Threshold kam: 'w', 'th', 'f' jaisi halki shuruaati awaazein (jaise 'water' ka 'w') kat'ti nahi. DC hata kar fade lagata hai."""
    if len(x) == 0:
        return x, 0.0, 0.0
    x = x - float(np.mean(x))
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x, 0.0, len(x) / sr
    a, b = max(0, idx[0] - int(0.04 * sr)), min(len(x), idx[-1] + int(0.06 * sr))
    x = _fade(x[a:b], sr, 8, 30)
    return x, 0.0, len(x) / sr


def squeeze_silences(x, sr, thr=0.004, max_pause=0.22, win=0.01):
    """Jumlon ke beech lambe pause (kokoro/edge aksar 0.4s+ chhorte hain) ko max_pause tak chhota karta hai."""
    hop = int(sr * win)
    n = len(x) // hop
    if n < 3:
        return x
    rms = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    quiet = rms < thr
    keep = np.ones(n, bool)
    maxf = int(max_pause / win)
    i = 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            run = j - i
            if run > maxf:
                s = i + maxf // 2
                keep[s:s + (run - maxf)] = False
            i = j
        else:
            i += 1
    mask = np.repeat(keep, hop)
    return np.concatenate([x[: n * hop][mask], x[n * hop:]])


def _syl(w):
    return max(1, len(re.findall(r"[aeiouy]+", re.sub(r"[^a-z]", "", w.lower()))))


def word_times(text, dur, env=None, fps=30):
    """Words ke start/end. env (audio energy) mile to words ko asli bolne wale hisson par rakhta hai
    (pause/chup mein nahi), warna lambai se andaza."""
    words = text.split()
    if not words:
        return []
    wts = [0.45 * len(re.sub(r"\W", "", w)) + _syl(w) + 0.3 for w in words]
    tot = sum(wts)
    fr = np.concatenate([[0.0], np.cumsum(wts)]) / tot
    if env is not None and len(env) > 4:
        e = np.asarray(env, np.float32)
        cum = np.concatenate([[0.0], np.cumsum(0.04 + np.clip(e, 0, 1))])
        cum /= cum[-1]
        tg = np.arange(len(cum)) / fps
        bounds = np.interp(fr, cum, tg) * (dur / tg[-1])
    else:
        bounds = fr * dur
    return [(w, float(bounds[i]), float(bounds[i + 1])) for i, w in enumerate(words)]


def analyze(x, sr, fps):
    """Audio -> (env 0..1 smooth, vis int): 0 band, 1 'oh'(low formant), 2 'ah', 3 'ee'/'s'(high). Har video frame ke liye ek."""
    hop = int(sr / fps)
    n = len(x) // hop
    if n == 0:
        return np.zeros(1, np.float32), np.zeros(1, np.int8)
    fr = x[: n * hop].reshape(n, hop)
    rms = np.sqrt((fr ** 2).mean(axis=1))
    e = np.clip(rms / (np.percentile(rms, 92) + 1e-6), 0, 1.2)
    sm = np.zeros(n, np.float32)
    for i in range(n):                      # tez khulna, thoda dheere band hona
        prev = sm[i - 1] if i else 0.0
        sm[i] = prev + (0.65 if e[i] > prev else 0.35) * (e[i] - prev)
    env = np.clip(sm, 0, 1) ** 0.85
    pad = np.concatenate([x[: n * hop], np.zeros(hop, np.float32)])
    win = np.hanning(2 * hop).astype(np.float32)
    fq = np.fft.rfftfreq(2 * hop, 1.0 / sr)
    vis = np.zeros(n, np.int8)
    for i in range(n):
        if env[i] < 0.10:
            continue
        sp = np.abs(np.fft.rfft(pad[i * hop:i * hop + 2 * hop] * win))
        if sp.sum() < 1e-3:                 # sannata (sirf smoothing ki dum) -> pichla shape rakho
            vis[i] = vis[i - 1] if i else 0
            continue
        c = float((sp * fq).sum() / sp.sum())
        vis[i] = 1 if c < 1000 else (2 if c < 2000 else 3)
    if n > 2:                               # flicker hataane ke liye median(3)
        m = vis.copy()
        for i in range(1, n - 1):
            if vis[i] and (vis[i - 1] or vis[i + 1]):
                m[i] = int(np.median([vis[i - 1] or vis[i], vis[i], vis[i + 1] or vis[i]]))
        vis = m
    return env.astype(np.float32), vis


def envelope(x, sr, fps):
    return analyze(x, sr, fps)[0]


def build(scenes, tmp, fps=30, **kw):
    """Poori video ek hi narrator awaaz mein: engine beech mein nahi badalta. Kokoro beech mein fail ho to
    saari scenes edge-tts (male) se dobara banti hain, taake awaaz kabhi mix na ho."""
    errs = []
    for eng in engines():
        try:
            return _build(eng, scenes, tmp, fps, **kw)
        except Exception as e:
            errs.append(str(e)[:160])
            print(f"[voice] {eng} failed -> next engine for the WHOLE video ({errs[-1]})", flush=True)
    raise RuntimeError("voice fail: " + " | ".join(errs))


def _build(eng, scenes, tmp, fps=30, gap=0.10, lead=0.25, tail=0.40):
    """Har scene: wav banata hai, scene ki 'hold' = voice length + gap. Returns (voice_mix_array@SR, per-scene info)."""
    chunks, info, t = [], [], 0.0
    for i, sc in enumerate(scenes):
        p = os.path.join(tmp, f"v{i}.wav")
        synth(sc["text"], p, eng)
        x, sr = read(p)
        if sr != SR:
            x = np.interp(np.linspace(0, len(x), int(len(x) * SR / sr), endpoint=False), np.arange(len(x)), x).astype(np.float32)
        x, _, _ = trim(x, SR)
        x = squeeze_silences(x, SR)
        d = len(x) / SR
        pre = lead if i == 0 else 0.0
        post = tail if i == len(scenes) - 1 else gap
        hold = pre + d + post
        env, vis = analyze(x, SR, fps)
        wt = [(w, pre + a, pre + b) for w, a, b in word_times(sc["text"], d, env, fps)]
        info.append(dict(start=t, hold=hold, words=wt, env=env, vis=vis, env_off=pre, voice_off=pre))
        chunks.append((t + pre, x))
        t += hold
    out = np.zeros(int(t * SR) + SR, np.float32)
    for st, x in chunks:
        a = int(st * SR)
        out[a:a + len(x)] += x
    print(f"[voice] engine={eng}, total {t:.1f}s")
    return out[: int(t * SR)], info, t
