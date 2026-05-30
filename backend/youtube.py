"""YouTube Shorts auto-upload.

OAuth lives in client_secret.json (the Desktop app credentials from Google Cloud).
On first call we open a browser for the user to consent; the refresh token is then
cached in data/youtube_token.json so subsequent uploads are silent.

Quota note: each upload is 1,600 units of the 10,000/day free YouTube Data API quota.
That caps autonomous use at ~6 uploads/day unless you request a quota increase."""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent.parent
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN_PATH = ROOT / "data" / "youtube_token.json"

# upload: insert videos. readonly: read back view/like/comment stats for the
# performance feedback loop. Adding readonly changes the scope set, so existing
# users must delete data/youtube_token.json and re-run `python -m backend.youtube`
# to re-consent — otherwise stats calls 403.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def fetch_stats(video_ids: list[str]) -> dict[str, dict]:
    """Return {video_id: {views, likes, comments}} for up to 50 videos per call.
    Reads statistics via the Data API. Quota cost is trivial (1 unit per call) vs.
    the 1600/upload, so this is cheap to run every cycle."""
    if not video_ids:
        return {}
    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    out: dict[str, dict] = {}
    # API caps at 50 ids per request.
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = youtube.videos().list(part="statistics", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            s = item.get("statistics", {})
            out[item["id"]] = {
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
            }
    return out


def _credentials() -> Credentials:
    """Load cached creds, refresh if expired, or run the consent flow if absent."""
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not CLIENT_SECRET.exists():
        raise RuntimeError(
            f"{CLIENT_SECRET} is missing. Download OAuth Desktop credentials from "
            "Google Cloud Console and save them as client_secret.json in the project root."
        )

    # Opens a browser tab and spins up a localhost listener for the redirect.
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload(
    video_path: Path,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy: str = "private",
) -> str:
    """Upload one mp4 as a YouTube Short. Returns the new video ID.

    privacy: one of 'public', 'unlisted', 'private'. Default private for safety —
    main.py reads YOUTUBE_PRIVACY from .env to override.
    """
    # YouTube enforces 100-char title cap. Hard-truncate so we never 400.
    title = (title or "Untitled clip")[:100]
    # #Shorts in the description is what makes YouTube classify a vertical video
    # under 60s as a Short rather than a regular upload. Belt-and-suspenders since
    # the 9:16 aspect ratio also signals it, but missing this tag has bitten people.
    description = (description + "\n\n#Shorts").strip()

    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22",  # "People & Blogs" — safest default for talking-head content
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # Resumable upload — loop until done. Could surface progress to the job record
    # but uploads are fast (<10s for a 30s short) so we just block.
    response = None
    while response is None:
        _, response = request.next_chunk()

    return response["id"]


def authorize() -> None:
    """One-shot CLI helper: `python -m backend.youtube` runs the consent flow without
    requiring a full job. Useful for confirming auth works before kicking off a pipeline."""
    creds = _credentials()
    print(f"Authorized. Token cached at {TOKEN_PATH}")
    print(f"Scopes: {creds.scopes}")


if __name__ == "__main__":
    authorize()
