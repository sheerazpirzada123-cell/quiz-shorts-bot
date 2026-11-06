import os
import random
import asyncio
import requests
import tempfile
from moviepy.editor import (
    VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip
)
import edge_tts

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PEXELS_API = "https://api.pexels.com/videos/search"

async def generate_tts(text, output_path):
    """edge-tts free voiceover, no API key needed"""
    communicate = edge_tts.Communicate(text, voice="en-US-GuyNeural", rate="+10%")
    await communicate.save(output_path)

def fetch_background(query="abstract background", output_dir="."):
    """Pexels free background video"""
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": 5, "orientation": "portrait"}
    resp = requests.get(PEXELS_API, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        raise Exception("No background video found")
    video = random.choice(videos)
    # Find a suitable mp4 file
    for vf in video.get("video_files", []):
        if vf.get("file_type") == "video/mp4":
            url = vf.get("link")
            path = os.path.join(output_dir, "bg.mp4")
            r = requests.get(url, timeout=30)
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    raise Exception("No mp4 file in Pexels result")

def create_short(question_row, output_path="output.mp4"):
    """Create one quiz short from a CSV row dict"""
    question = question_row["question"]
    options = [
        f"A) {question_row['option_a']}",
        f"B) {question_row['option_b']}",
        f"C) {question_row['option_c']}",
        f"D) {question_row['option_d']}",
    ]
    correct = question_row["correct"].strip().upper()

    # Full narration text
    narration = f"{question}. " + ". ".join(options) + f". The answer is {correct}."
    
    tmpdir = tempfile.mkdtemp()
    tts_path = os.path.join(tmpdir, "voice.mp3")
    asyncio.run(generate_tts(narration, tts_path))

    bg_path = fetch_background(output_dir=tmpdir)
    
    bg = VideoFileClip(bg_path).subclip(0, 15).resize((1080, 1920))
    audio = AudioFileClip(tts_path)
    
    # Text clips
    title_clip = TextClip(
        question, fontsize=70, color="white", font="DejaVu-Sans-Bold",
        size=(900, None), method="caption", align="center"
    ).set_position(("center", 300)).set_duration(15)
    
    option_clips = []
    y_start = 700
    for i, opt in enumerate(options):
        clip = TextClip(
            opt, fontsize=60, color="white", font="DejaVu-Sans",
            size=(850, None), method="caption", align="left"
        ).set_position((100, y_start + i * 120)).set_duration(15)
        option_clips.append(clip)
    
    answer_clip = TextClip(
        f"Answer: {correct}", fontsize=80, color="yellow", font="DejaVu-Sans-Bold",
        size=(900, None), method="caption", align="center"
    ).set_position(("center", 1500)).set_duration(3).set_start(12)
    
    final = CompositeVideoClip([bg, title_clip] + option_clips + [answer_clip])
    final = final.set_audio(audio)
    final.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
    
    bg.close()
    audio.close()
    final.close()

if __name__ == "__main__":
    import csv
    with open("questions.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    row = random.choice(rows)
    create_short(row, "output.mp4")
    print("Video created: output.mp4")
