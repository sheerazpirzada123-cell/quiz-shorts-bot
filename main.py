"""output.mp4 ko YouTube par upload karta hai (GitHub secrets se refresh token use karta hai)."""
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
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
    creds.refresh(Request())  # access token fresh banata hai
    return build("youtube", "v3", credentials=creds)


def upload_video(video_path, title, description, tags):
    youtube = get_youtube_client()
    body = {
        "snippet": {"title": title[:100], "description": description, "tags": tags, "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=-1, resumable=True)
    print(f"Uploading: {title}")
    response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    print(f"Upload done! https://youtube.com/shorts/{response['id']}")
    return response["id"]


if __name__ == "__main__":
    with open("script.json", encoding="utf-8") as f:
        d = json.load(f)
    title = d.get("title", "You won't believe this #Shorts")
    if "#shorts" not in title.lower():
        title = f"{title[:90]} #Shorts"
    description = d.get("description", "")
    if "#shorts" not in description.lower():
        description += "\n\n#Shorts"
    upload_video("output.mp4", title, description, d.get("tags", ["facts", "shorts"]))
