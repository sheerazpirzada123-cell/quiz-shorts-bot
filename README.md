# quiz-shorts-bot v4 (RicksClips-style story Shorts)

Har run: Gemini ek **asli origin story** likhta hai ("This Shape Saved Roller Coasters" jaisi) -> voice-over (Kokoro, free) ->
har scene ka 3D-render background (Pollinations, free) -> stick-man actors (code se, `rick.py`) -> word-by-word captions -> YouTube Short.

Files: `story_gen.py` (script) | `voice.py` (awaaz + word timing) | `bgimg.py` (backgrounds + fallback) | `rick.py` (character) |
`render_story.py` (camera, light, bloom, captions, mix) | `music.py` (music + sfx) | `main.py` (upload).

Offline test (bina internet): `BG_OFFLINE=1 VOICE_ENGINE=fake python story_gen.py && BG_OFFLINE=1 VOICE_ENGINE=fake python render_story.py`

Tweak: `story_gen.py` -> `AREAS`, `RULES` | `voice.py` -> `KOKORO_VOICE` (am_adam, am_michael, bm_george...), `VOICE_SPEED` |
`rick.py` -> character look | `render_story.py` -> `SHOT`, `LIGHT`, caption sizes | `bgimg.py` -> `STYLE` (background look).
