"""
config.py — loads .env and exposes a typed Settings singleton.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set. Check your .env file.")
    return value


@dataclass
class Settings:
    # Google OAuth2
    google_credentials_file: Path = field(
        default_factory=lambda: Path(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))
    )
    google_token_file: Path = field(
        default_factory=lambda: Path(os.getenv("GOOGLE_TOKEN_FILE", "token.json"))
    )
    google_scopes: list[str] = field(default_factory=lambda: [
        "https://www.googleapis.com/auth/drive",
    ])

    # Google Drive folder IDs
    drive_source_folder_id: str = field(default_factory=lambda: _require("DRIVE_SOURCE_FOLDER_ID"))
    drive_processed_folder_id: str = field(default_factory=lambda: _require("DRIVE_PROCESSED_FOLDER_ID"))
    drive_archive_folder_id: str = field(default_factory=lambda: _require("DRIVE_ARCHIVE_FOLDER_ID"))

    # Processing
    poll_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("POLL_INTERVAL_SECONDS", "120"))
    )
    session_gap_minutes: int = field(
        default_factory=lambda: int(os.getenv("SESSION_GAP_MINUTES", "45"))
    )
    session_complete_wait_minutes: int = field(
        default_factory=lambda: int(os.getenv("SESSION_COMPLETE_WAIT_MINUTES", "15"))
    )
    file_stable_minutes: int = field(
        default_factory=lambda: int(os.getenv("FILE_STABLE_MINUTES", "5"))
    )
    mp3_bitrate: str = field(
        default_factory=lambda: os.getenv("MP3_BITRATE", "128k")
    )

    # Telegram
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    # NotebookLM bridge (optional)
    notebooklm_api_url: str = field(default_factory=lambda: os.getenv("NOTEBOOKLM_API_URL", ""))
    notebooklm_api_key: str = field(default_factory=lambda: os.getenv("NOTEBOOKLM_API_KEY", ""))

    # Paths
    db_path: Path = field(
        default_factory=lambda: Path(os.getenv("DB_PATH", "state/wave2mp3.db"))
    )
    temp_dir: Path = field(
        default_factory=lambda: Path(os.getenv("TEMP_DIR", "/tmp/wave2mp3"))
    )

    def validate(self) -> None:
        if not self.google_credentials_file.exists():
            raise FileNotFoundError(
                f"Google credentials file not found: {self.google_credentials_file}. "
                "Download it from Google Cloud Console."
            )
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
