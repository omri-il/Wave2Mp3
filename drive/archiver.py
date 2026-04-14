"""
drive/archiver.py — Move processed .wav files to the archive folder on Drive.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def archive_files(service, file_ids: list[str], archive_folder_id: str) -> None:
    """Move files from source folder to archive folder on Drive."""
    for file_id in file_ids:
        try:
            # Get current parents
            f = service.files().get(fileId=file_id, fields="parents").execute()
            current_parents = ",".join(f.get("parents", []))

            # Move to archive folder
            service.files().update(
                fileId=file_id,
                addParents=archive_folder_id,
                removeParents=current_parents,
                fields="id, parents",
            ).execute()
            logger.info("Archived file %s to folder %s", file_id, archive_folder_id)
        except Exception:
            logger.exception("Failed to archive file %s", file_id)
