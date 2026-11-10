# quiz-shorts-bot (relatable 2D cartoon Shorts)

Har run par Gemini ek **nayi relatable situation** chunta hai ("ye to mere saath hota hai" wali), uski 30-40 second ki
chhoti baat-cheet likhta hai, aur code khud **2D cartoon animation** banakar YouTube **Short** upload kar deta hai.
Long video ab nahi banti - sirf Shorts. Koi image API nahi, sab kuch code se banta hai.

## Kya banta hai
- **Characters (cartoon.py)**: 1-2 rang-birange cartoon characters (Me + Mom / Brain / Friend...), alag baal / skin / kapde / hijab / cap /
  glasses / beard. 13 emotions (gussa, sharmana, shock, pyaar, thaka hua...), 14 actions (phone, facepalm, laugh, sleep...),
  munh awaaz ke saath hilta hai, palkein jhapakti hain, aankhein doosre character ko dekhti hain.
- **Backgrounds**: bedroom, kitchen, living, school, office, street, park, night, cafe. **Props**: phone, alarm, pizza, exam paper, wifi...
- **Awaaz**: Kokoro ki 4 awaazein (m1, m2 male, f1, f2 female); har character ki apni awaaz. Kokoro fail ho to edge-tts.
- **Music + sound effects (music.py)**: code se, copyright-free. Boing / fail / tada / pop / whoosh waghera beat par.
- **Story**: hook (pehli line) -> escalation -> twist -> punchline, aur **last line pehli line mein loop** hoti hai (repeat views).
- **Repeat nahi**: purane topics `history.json` mein save hote hain.

## Chalana
Actions > Daily Relatable Short > Run workflow. `upload` band karein to sirf test hoga (video "video" artifact mein).
Cron din mein 2 baar chalta hai, har baar random waqt par (`MAX_DELAY_MIN`).

## Secrets
GEMINI_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

## Local test (bina Gemini / Kokoro ke)
`FAKE_VOICE=1 python script_gen.py && FAKE_VOICE=1 python render.py` -> output.mp4
(Gemini key na ho to fallback skit banti hai.)

## Tweak
`script_gen.py`: `AREAS` (topics ke areas), `WRITE_RULES` (style / length). `render.py`: caption size `CAP`.
Awaaz: `KOKORO_VOICE_M1/M2/F1/F2`, speed `KOKORO_SPEED` (default 1.12). Music: `MUSIC_GAIN`, `SFX_GAIN`.
