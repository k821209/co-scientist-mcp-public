"""Compile-time defaults for the hosted co-scientist service.

These can be overridden via env vars for self-hosted forks of the repo.
The `web_api_key` is **public** (per Firebase docs) — it identifies the
project to client SDKs but is not a credential.
"""

DEFAULT_FIREBASE_PROJECT_ID = "co-scientist-5af1a"
DEFAULT_FIREBASE_STORAGE_BUCKET = "co-scientist-5af1a.firebasestorage.app"
DEFAULT_FIREBASE_WEB_API_KEY = "AIzaSyCap5WxY6br-vo-D0l6mIS7uohPxuROz4E"
DEFAULT_EXCHANGE_URL_TEMPLATE = (
    "https://us-central1-{project_id}.cloudfunctions.net/exchange_key"
)
DEFAULT_GENERATE_IMAGE_URL_TEMPLATE = (
    "https://us-central1-{project_id}.cloudfunctions.net/generate_image"
)
