"""
drive/auth.py — Google OAuth2 authentication for Drive API.
"""
from __future__ import annotations

import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)


def get_google_creds() -> Credentials:
    creds: Credentials | None = None

    if settings.google_token_file.exists():
        creds = Credentials.from_authorized_user_file(
            str(settings.google_token_file), settings.google_scopes
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(settings.google_credentials_file), settings.google_scopes
            )
            flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
            auth_url, _ = flow.authorization_url(prompt="consent")
            print("\n*** Open this URL in your browser and paste the code below ***")
            print(f"\n{auth_url}\n")
            code = input("Enter the authorization code: ").strip()
            flow.fetch_token(code=code)
            creds = flow.credentials
        with settings.google_token_file.open("w") as f:
            f.write(creds.to_json())

    return creds


def build_drive_service(creds: Credentials):
    return build("drive", "v3", credentials=creds)
