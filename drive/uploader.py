"""
drive/uploader.py — Upload MP3 files to Google Drive.
"""
from __future__ import annotations

import logging
from pathlib import Path

from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)


def upload_mp3(service, mp3_path: Path, folder_id: str) -> tuple[str, str]:
    """
    Upload an MP3 file to the specified Drive folder.

    Returns (drive_file_id, filename).
    """
    file_metadata = {
        "name": mp3_path.name,
        "parents": [folder_id],
    }
    media = MediaFileUpload(str(mp3_path), mimetype="audio/mpeg", resumable=True)
    uploaded = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, name")
        .execute()
    )
    logger.info("Uploaded '%s' to folder %s (file ID: %s)", mp3_path.name, folder_id, uploaded["id"])
    return uploaded["id"], uploaded["name"]
