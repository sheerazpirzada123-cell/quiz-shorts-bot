"""Videos YouTube par upload karta hai (GitHub secrets se refresh token).

MODE: both  -> pehle long video, phir uski link ke saath promote karne wala Short
      long  -> sirf long video
      short -> sirf standalone Short
"""
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
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags, "categoryId": "27"},
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


def set_thumbnail(youtube, video_id, path="thumbnail.jpg"):
    if not os.path.exists(path):
        return
    try:
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(path, mimetype="image/jpeg")).execute()
        print("Thumbnail set")
    except Exception as e:
        print(f"Thumbnail skipped: {str(e)[:160]}")


def post_link_comment(youtube, video_id, text):
    try:
        youtube.commentThreads().insert(part="snippet", body={"snippet": {
            "videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()
        print("Link comment posted")
    except Exception as e:
        print(f"Link comment skipped: {str(e)[:120]}")


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
    mode = os.environ.get("MODE", "both").strip().lower()
    youtube = get_youtube_client()
    long_id = None
    out = ["### Uploaded"]

    if mode in ("both", "long") and os.path.exists("output_long.mp4"):
        d = load("script_long.json")
        long_id = upload_video(youtube, "output_long.mp4", d["title"], d.get("description", ""), d.get("tags", ["facts"]))
        print(f"Long upload done! https://youtu.be/{long_id}")
        set_thumbnail(youtube, long_id)
        out.append(f"- Long video: https://youtu.be/{long_id}")

    if mode in ("both", "short") and os.path.exists("output_short.mp4"):
        d = load("script_short.json")
        title = d.get("title", "You won't believe this #Shorts")
        if "#shorts" not in title.lower():
            title = f"{title[:90]} #Shorts"
        desc = d.get("description", "")
        if long_id:
            desc = f"Watch the full story: https://youtu.be/{long_id}\n\n{desc}"
        short_id = upload_video(youtube, "output_short.mp4", title, with_tag(desc), d.get("tags", ["facts", "shorts"]))
        print(f"Short upload done! https://youtube.com/shorts/{short_id}")
        out.append(f"- Short: https://youtube.com/shorts/{short_id}")
        if long_id:
            post_link_comment(youtube, short_id, f"Full story here: https://youtu.be/{long_id}")
            out.append("- Tip: YouTube API se 'Related video' set nahi hota. Chahein to Studio > Short > Edit > Related video "
                       "mein long video chun lein (10 second).")

    summary(out)
    if len(out) == 1:
        sys.exit("Kuch upload nahi hua (output files nahi mili)")


if __name__ == "__main__":
    main()
