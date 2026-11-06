"""Gemini se ek random quiz question generate karta hai aur quiz.json mein save karta hai."""
import json
import os
import random
import re
import time

import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"] if m]

TOPICS = [
    "world geography", "space and astronomy", "human body", "animals", "famous inventions",
    "world history", "science", "movies and music", "sports", "food and drinks",
    "technology", "famous landmarks", "famous people", "nature and weather", "language and words",
    "general knowledge", "Islamic history", "Pakistan general knowledge", "math and logic",
]
DIFFICULTY = ["easy", "medium", "medium", "hard"]

# Agar Gemini fail ho jaye to video phir bhi ban jaye
FALLBACK = [
    {"question": "Which planet is known as the Red Planet?", "options": ["Venus", "Mars", "Jupiter", "Mercury"],
     "correct": 1, "explanation": "Mars looks red because of iron oxide on its surface.", "topic": "space"},
    {"question": "What is the largest ocean on Earth?", "options": ["Atlantic", "Indian", "Pacific", "Arctic"],
     "correct": 2, "explanation": "The Pacific Ocean covers about one third of the planet.", "topic": "geography"},
    {"question": "How many bones does an adult human body have?", "options": ["186", "206", "226", "256"],
     "correct": 1, "explanation": "Babies are born with more, but many fuse together as we grow.", "topic": "human body"},
]


def _ask_gemini(prompt):
    last_err = None
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.1, "responseMimeType": "application/json"},
        }
        for attempt in range(2):
            try:
                r = requests.post(url, headers={"x-goog-api-key": API_KEY}, json=body, timeout=60)
                if r.status_code == 200:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return text
                last_err = f"{model}: HTTP {r.status_code} {r.text[:200]}"
            except Exception as e:  # noqa: BLE001
                last_err = f"{model}: {e}"
            time.sleep(3)
    raise RuntimeError(last_err)


def _validate(q):
    opts = q["options"]
    assert isinstance(opts, list) and len(opts) == 4, "need exactly 4 options"
    assert len({o.strip().lower() for o in opts}) == 4, "options must be different"
    q["correct"] = int(q["correct"])
    assert 0 <= q["correct"] <= 3, "correct index out of range"
    assert len(q["question"]) <= 140, "question too long"
    assert all(len(o) <= 40 for o in opts), "option too long"
    return q


def generate():
    if not API_KEY:
        print("GEMINI_API_KEY missing, using fallback question")
        return random.choice(FALLBACK)
    topic = random.choice(TOPICS)
    diff = random.choice(DIFFICULTY)
    prompt = (
        f"Create ONE multiple-choice trivia question for a YouTube Short. Topic: {topic}. Difficulty: {diff}. "
        "Random seed: " + str(random.randint(1, 10**6)) + ". "
        "Rules: question max 120 characters, exactly 4 short options (max 35 characters each), one clearly correct answer, "
        "factually accurate, put the correct answer at a random position. "
        'Reply ONLY with JSON: {"question": str, "options": [str,str,str,str], '
        '"correct": 0-3 index of right option, "explanation": one short sentence (max 120 chars), "topic": short topic name}'
    )
    for attempt in range(3):
        try:
            text = _ask_gemini(prompt)
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            return _validate(json.loads(text))
        except Exception as e:  # noqa: BLE001
            print(f"Gemini attempt {attempt + 1} failed: {e}")
    print("Using fallback question")
    return random.choice(FALLBACK)


if __name__ == "__main__":
    q = generate()
    with open("quiz.json", "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    print("Quiz saved:", q["question"])
