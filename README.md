# quiz-shorts-bot (stick-man explainer: long video + promo Short)

Har run par Gemini ek **aisi sachchi kahani** chunta hai jo 99% logon ne nahi suni, phir code khud stick-man animation banata hai
aur YouTube par upload karta hai. **Koi image API / koi extra key nahi** - sab kuch code se banta hai, isliye video kabhi
"images fail" ki wajah se rukti nahi.

## Kya naya hai
- **Animation (anim.py)**: stick-man ab chalta, daudta, kudta, sochta, shock hota, nachta hai. Munh awaaz ke saath hilta hai (lip-sync).
  Female characters ke **lambe baal**, male ke **chhote baal ya ganje**. Har scene mein background, props (pop-in animation),
  label sticker (jaise "170,000 YEARS AGO"), camera zoom/pan/shake.
- **Music + sound effects (music.py)**: bg music code se banta hai (4 moods: quirky / mysterious / epic / chill), awaaz ke neeche
  khud dab jata hai. Whoosh/pop/ding/thud effects har scene par. 100% original => copyright claim ka masla hi nahi.
  `MUSIC_MODE=download` karein to Kevin MacLeod (CC-BY) ka track online utarta hai aur credit description mein khud laga deta hai.
- **Story (script_gen.py)**: pehle Google Search se research, phir plan (topic, title, cast, 10 chapters), phir har chapter alag
  likha jata hai -> lambi video (~9-10 min) aur har chapter ke end par cliffhanger. Obscure topics, hook, suspense, mazah.
- Long video default ~9 min (`LONG_TARGET_WORDS` = 1500). Poore 10 min ke liye 1700 kar dein (workflow ke `env:` mein).

## Modes
- `both` (cron yehi karta hai): long video (thumbnail ke saath) + usko promote karne wala Short (description mein long ka link).
- `short`: sirf ek standalone Short (sabse tez, test ke liye). `long`: sirf long video.

Manual run: Actions > Daily Explainer Short > Run workflow > `mode` chunein. `upload` band karein to sirf test hoga
(video "videos" artifact mein milegi, topic history save nahi hogi).

## Secrets
Zaroori: GEMINI_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
(Cloudflare / Pollinations / Horde ki keys ab **zaroorat nahi**, hata sakte hain.)

## Free limit / credits
Ek `both` run mein Gemini ki ~13 calls lagti hain (1 research + 1 plan + 10 chapters + 1 teaser); `short` mein 2. Baqi sab (voice, animation,
music) local CPU par chalta hai, koi paid API nahi.

## Local test (bina Gemini/Kokoro ke)
`FAKE_VOICE=1 MODE=short python script_gen.py && FAKE_VOICE=1 MODE=short python render.py` (Gemini key na ho to fallback script banti hai;
FAKE_VOICE sirf test ke liye nakli awaaz deta hai).

## Tweak
voice `KOKORO_VOICE` (am_michael, am_fenrir, am_puck, am_adam), speed `KOKORO_SPEED` / `LONG_SPEED`, music `MUSIC_GAIN` (default 0.20),
`SFX_GAIN`, `MUSIC_MODE` (synth/download), `LONG_TARGET_WORDS`, random wait `MAX_DELAY_MIN` (workflow).
