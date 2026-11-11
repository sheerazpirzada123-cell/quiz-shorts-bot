# quiz-shorts-bot v5 ("parable explainer" Shorts)

Har run: Gemini ek **bilkul nayi parable-story** likhta hai ("The Difference Between Rich And Poor" jaisi: chhoti si allegory-duniya
jahan 2-4 gol-sar characters kisi money/society/psychology ke idea ko events se samjhate hain) -> narrator voice (Kokoro, free) ->
har location ka khaali **3D-diorama background** (Pollinations, free) -> **animated characters** code se (`rick.py`: chalna, ishare,
expressions, lipsync) -> camera moves + word-by-word captions -> YouTube Short.

Characters code se draw hote hain, isliye har scene mein bilkul **same** dikhte hain (AI images mein ye nahi hota).

Files: `story_gen.py` (story + cast + locations) | `voice.py` (awaaz + word timing + mouth data) | `bgimg.py` (backgrounds + fallback) |
`rick.py` (character engine) | `render_story.py` (actors, camera, captions, mix) | `music.py` (music + sfx) | `main.py` (upload).

Offline test (bina internet / bina API key):
`ALLOW_FALLBACK=1 python story_gen.py && BG_OFFLINE=1 VOICE_ENGINE=fake python render_story.py`

Tweak:
- Topics: `story_gen.py` -> `CONCEPTS`, `WORLDS`, `FORMATS`, `RULES`
- Awaaz: workflow `KOKORO_VOICE`, `VOICE_SPEED`
- Characters: `rick.py` (look) | `story_gen.py` -> `HATS`, `SHIRT_C` (options)
- Shot size / positions: `render_story.py` -> `SHOT_H`, `SHOT_TOP`, `SLOTS`
- Background look: `bgimg.py` -> `STYLE`
- Captions: `render_story.py` -> `word_sprite()` (size, colour, outline), `fonts/Poppins-Bold.ttf`
