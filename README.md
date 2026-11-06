# quiz-shorts-bot (Explainer bot: long video + promo Short)

Har run par Gemini ek "duniya mein pehli baar" topic chunta hai (pehle kapde, pehla haircut, pehla paisa...),
stick-man explainer banta hai (free AI images + Kokoro male voice + zoom/pan + captions) aur YouTube par jata hai.

- `both` (cron yehi karta hai): landscape long video (~5 min, thumbnail ke saath) + usko promote karne wala Short.
  Short kahani ka shuru batata hai, curiosity jagata hai, phir bolta hai "full video dekho". Short ki description mein
  long video ka link hota hai.
- `short`: sirf ek standalone Short (sabse tez, test ke liye).
- `long`: sirf long video.

Manual run: Actions > Daily Explainer Short > Run workflow > `mode` chunein. `upload` band karein to sirf test hoga
(video "videos" artifact mein milegi, topic history save nahi hogi).

## Secrets
Zaroori: GEMINI_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

Image providers (sab optional; chain: Cloudflare -> Pollinations -> AI Horde). Koi band/quota-out ho to agla chalta hai:
- CF_ACCOUNT_ID + CF_API_TOKEN: Cloudflare Workers AI (FLUX.1-schnell), free daily quota, card nahi chahiye. Sabse behtar quality.
- POLLINATIONS_API_KEY: enter.pollinations.ai se free key (anonymous mein ~1 image / 15 sec throttle hai).
- HORDE_API_KEY: aihorde.net ki free key (na ho to anonymous chalta hai). Unlimited lekin slow.

## Tweak
voice `KOKORO_VOICE` (am_michael, am_fenrir, am_puck, am_adam), speed `KOKORO_SPEED` / `LONG_SPEED`, image style `IMAGE_STYLE_HEAD` /
`IMAGE_STYLE_TAIL`, provider order `IMAGE_PROVIDERS`, long video length `LONG_TARGET_WORDS` (default 760 = ~5 min),
kam se kam asli AI images `MIN_IMAGE_RATIO` (default 0.7), random wait `MAX_DELAY_MIN` (workflow).
