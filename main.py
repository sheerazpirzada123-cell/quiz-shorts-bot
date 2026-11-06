import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Scope: Sirf upload ki ijazat
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_youtube_client():
    """Yeh function client_secret.json aur token.json ko load karta hai"""
    creds = None
    
    # 1. Agar token.json mojood hai, toh usse credentials load karein
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # 2. Agar token nahi hai ya expire ho gaya hai, toh naya banayein
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh token se automatic renew (Yeh automatic hota hai, user ko pata nahi chalta)
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            # Yeh sirf pehli baar chalega agar token.json mojood nahi
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Naya token save karein taake agli baar kaam aaye
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    
    # 3. YouTube service banayein
    return build("youtube", "v3", credentials=creds)

def upload_video(video_path, title, description, tags):
    """Yeh function video ko upload karta hai"""
    youtube = get_youtube_client()
    
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "27",  # 27 = Education (Quiz ke liye)
        },
        "status": {
            "privacyStatus": "public",  # public, private, ya unlisted
            "selfDeclaredMadeForKids": False,
        },
    }
    
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    
    print(f"Uploading: {title}...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )
    response = request.execute()
    
    print(f"✅ Upload ho gaya! Video ID: {response['id']}")
    print(f"🔗 Link: https://youtube.com/shorts/{response['id']}")
    return response["id"]

# --- Istemaal ka tareeqa ---
if __name__ == "__main__":
    upload_video(
        video_path="output.mp4",  # Aapki render ki hui video
        title="Guess the Answer! #Shorts",
        description="Daily quiz short. #Shorts #Quiz",
        tags=["quiz", "trivia", "shorts"]
    )
