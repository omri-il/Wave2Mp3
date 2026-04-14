"""
main.py — entry point for the Wave2MP3 agent.

Usage:
    python main.py              # Run the polling agent
    python main.py --dry-run    # List Drive files and show grouping, then exit
    python main.py --auth-only  # Run Google OAuth flow and save token, then exit
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from config import settings
from drive.auth import get_google_creds, build_drive_service
from drive.monitor import DriveMonitor
from db import Database
from processor.session_grouper import group_into_sessions
from processor.audio_merger import merge_session
from drive.uploader import upload_mp3
from drive.archiver import archive_files
from notifier.telegram_bot import TelegramNotifier

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _check_disk_space() -> bool:
    """Return True if there's at least 500MB free in temp_dir."""
    import shutil
    free = shutil.disk_usage(settings.temp_dir).free
    if free < 500 * 1024 * 1024:
        logger.warning("Low disk space: %d MB free", free // (1024 * 1024))
        return False
    return True


def _poll_cycle(monitor: DriveMonitor, db: Database, drive_service, notifier: TelegramNotifier) -> None:
    """One complete poll → group → process → upload → archive cycle."""

    # 1. List .wav files on Drive
    wav_files = monitor.list_wav_files()
    if not wav_files:
        return

    # 2. Track new files in DB, update sizes for stability check
    for f in wav_files:
        db.upsert_file(f.file_id, f.name, f.created_time, f.size)

    # 3. Mark stable files (size unchanged for FILE_STABLE_MINUTES)
    db.mark_stable_files(settings.file_stable_minutes)

    # 4. Group stable files into sessions
    stable_files = db.get_stable_files()
    if not stable_files:
        return

    sessions = group_into_sessions(stable_files, settings.session_gap_minutes)

    # 5. Process complete sessions
    for session_files in sessions:
        # Check if session is complete (newest file stable for SESSION_COMPLETE_WAIT_MINUTES)
        if not db.is_session_complete(session_files, settings.session_complete_wait_minutes):
            continue

        session_id = db.create_session(session_files)
        if not session_id:
            continue  # session already processed

        logger.info("Processing session %s (%d files)", session_id, len(session_files))

        if not _check_disk_space():
            notifier.send_message("⚠️ Low disk space — skipping processing")
            db.update_session_status(session_id, "error", "Low disk space")
            continue

        try:
            # Mark files as downloading
            db.update_files_status([f["drive_file_id"] for f in session_files], "downloading")

            # Download all files
            downloaded_paths = []
            for f in session_files:
                from drive.monitor import DriveWavFile
                wav = DriveWavFile(
                    file_id=f["drive_file_id"],
                    name=f["filename"],
                    created_time=f["drive_created_time"],
                    size=f["file_size"],
                )
                path = monitor.download(wav)
                downloaded_paths.append(path)

            # Mark files as processing
            db.update_files_status([f["drive_file_id"] for f in session_files], "processing")
            db.update_session_status(session_id, "processing")

            # Merge and convert to MP3
            mp3_path = merge_session(downloaded_paths, session_id, settings.mp3_bitrate)

            # Upload MP3 to processed folder
            mp3_drive_id, mp3_filename = upload_mp3(drive_service, mp3_path, settings.drive_processed_folder_id)

            # Archive originals on Drive
            archive_files(drive_service, [f["drive_file_id"] for f in session_files], settings.drive_archive_folder_id)

            # Update DB
            db.complete_session(session_id, mp3_drive_id, mp3_filename)
            db.update_files_status([f["drive_file_id"] for f in session_files], "done")

            # Notify via Telegram
            notifier.send_session_complete(session_id, mp3_filename, len(session_files))

            logger.info("Session %s complete: %s", session_id, mp3_filename)

        except Exception as exc:
            logger.exception("Error processing session %s", session_id)
            db.update_session_status(session_id, "error", str(exc))
            db.update_files_status([f["drive_file_id"] for f in session_files], "stable")
            notifier.send_message(f"❌ Error processing session {session_id}: {exc}")

        finally:
            # Clean up temp files
            for p in downloaded_paths:
                p.unlink(missing_ok=True)
            if 'mp3_path' in locals():
                mp3_path.unlink(missing_ok=True)


def _dry_run(monitor: DriveMonitor, db: Database) -> None:
    """Print what would be processed without actually doing anything."""
    wav_files = monitor.list_wav_files()
    if not wav_files:
        logger.info("[dry-run] No .wav files found in source folder")
        return

    logger.info("[dry-run] Found %d .wav file(s):", len(wav_files))
    for f in wav_files:
        logger.info("  %s  (%s, %d bytes)", f.name, f.created_time, f.size)

    # Show grouping preview
    file_dicts = [
        {"drive_created_time": f.created_time, "filename": f.name, "drive_file_id": f.file_id}
        for f in wav_files
    ]
    sessions = group_into_sessions(file_dicts, settings.session_gap_minutes)
    logger.info("[dry-run] Would create %d session(s):", len(sessions))
    for i, session in enumerate(sessions, 1):
        logger.info("  Session %d: %d file(s)", i, len(session))
        for f in session:
            logger.info("    - %s", f["filename"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Wave2MP3 — WAV session merger and converter")
    parser.add_argument("--dry-run", action="store_true", help="List files and show grouping, then exit")
    parser.add_argument("--auth-only", action="store_true", help="Run Google OAuth flow and exit")
    args = parser.parse_args()

    if args.auth_only:
        # Auth-only doesn't need full config validation
        creds = get_google_creds()
        logger.info("OAuth token saved to %s. Copy it to your VPS.", settings.google_token_file)
        sys.exit(0)

    settings.validate()
    creds = get_google_creds()
    drive_service = build_drive_service(creds)
    monitor = DriveMonitor(drive_service)
    db = Database(settings.db_path)
    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)

    if args.dry_run:
        _dry_run(monitor, db)
        sys.exit(0)

    # Crash recovery: reset in-progress states
    db.recover_from_crash()

    logger.info(
        "Wave2MP3 agent started. Polling every %ds. Session gap: %d min.",
        settings.poll_interval_seconds,
        settings.session_gap_minutes,
    )

    while True:
        try:
            _poll_cycle(monitor, db, drive_service, notifier)
        except Exception:
            logger.exception("Unexpected error in poll cycle — will retry next interval")
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
