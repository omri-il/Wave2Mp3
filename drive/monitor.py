"""
drive/monitor.py — Poll Google Drive for new .wav files and download them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class DriveWavFile:
    file_id: str
    name: str
    created_time: str
    size: int


class DriveMonitor:
    def __init__(self, service):
        self._service = service

    def list_wav_files(self) -> list[DriveWavFile]:
        """List all .wav files in the source folder, sorted by createdTime."""
        query = (
            f"'{settings.drive_source_folder_id}' in parents "
            f"and (mimeType='audio/wav' or mimeType='audio/x-wav' "
            f"or name contains '.wav' or name contains '.WAV') "
            f"and trashed=false"
        )
        files: list[DriveWavFile] = []
        page_token = None

        while True:
            resp = self._service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, createdTime, size)",
                orderBy="createdTime",
                pageSize=100,
                pageToken=page_token,
            ).execute()

            for f in resp.get("files", []):
                files.append(DriveWavFile(
                    file_id=f["id"],
                    name=f["name"],
                    created_time=f["createdTime"],
                    size=int(f.get("size", 0)),
                ))

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        logger.info("Found %d .wav file(s) in source folder", len(files))
        return files

    def download(self, file: DriveWavFile) -> Path:
        """Download a .wav file from Drive to the temp directory."""
        dest = settings.temp_dir / file.name
        request = self._service.files().get_media(fileId=file.file_id)
        with dest.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug("Download %s: %d%%", file.name, int(status.progress() * 100))
        logger.info("Downloaded '%s' (%d bytes) to %s", file.name, file.size, dest)
        return dest
