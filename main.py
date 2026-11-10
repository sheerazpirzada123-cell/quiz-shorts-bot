"""output.mp4 ko YouTube Short ki tarah upload karta hai (GitHub secrets se refresh token)."""
import json
import os
import sys
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

TOKEN_URI = "https://oauth2.googleapis.com/token"


def get_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"].strip(),
        client_id=os.environ["YOUTUBE_CLIENT_ID"].strip(),
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"].strip(),
        token_uri=TOKEN_URI,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, video_path, title, description, tags):
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags, "categoryId": "24"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=16 * 1024 * 1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    print(f"Uploading: {title}")
    response, retries = None, 0
    while response is None:
        try:
            status, response = req.next_chunk()
            if status:
                print(f"  {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retries < 6:
                retries += 1
                time.sleep(5 * retries)
                continue
            raise
    return response["id"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def with_tag(text, tag="#Shorts"):
    return text if tag.lower() in text.lower() else f"{text}\n\n{tag}"


def summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def main():
    youtube = get_youtube_client()
    d = load("script.json")
    title = d.get("title", "Relatable moment #Shorts")
    if "#shorts" not in title.lower():
        title = f"{title[:90]} #Shorts"
    short_id = upload_video(youtube, "output.mp4", title, with_tag(d.get("description", "")), d.get("tags", ["relatable", "funny"]))
    url = f"https://youtube.com/shorts/{short_id}"
    print(f"Short upload done! {url}")
    summary(["### Uploaded", f"- Short: {url}"])


if __name__ == "__main__":
    main()
