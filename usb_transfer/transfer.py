"""
usb_transfer/transfer.py — Copy .wav files from USB mic to Google Drive + Telegram prompt.

Usage:
    python -m usb_transfer.transfer          # Watch for USB drives and transfer
    python -m usb_transfer.transfer --once   # Transfer from currently connected drives and exit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import asyncio
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from drive.auth import get_google_creds, build_drive_service
from drive.monitor import DriveMonitor
from googleapiclient.http import MediaFileUpload
from usb_transfer.detector import get_removable_drives, wait_for_new_drive

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Track transferred files to avoid re-uploading
TRANSFER_LOG = Path(__file__).parent.parent / "state" / "transferred.json"


def _load_transferred() -> set[str]:
    if TRANSFER_LOG.exists():
        with TRANSFER_LOG.open() as f:
            return set(json.load(f))
    return set()


def _save_transferred(transferred: set[str]) -> None:
    TRANSFER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with TRANSFER_LOG.open("w") as f:
        json.dump(sorted(transferred), f, indent=2)


def _find_wav_files(drive_path: str) -> list[Path]:
    """Scan removable drive for .wav files in root and common subdirectories."""
    root = Path(drive_path)
    wav_files = []

    # Search root and one level of subdirectories
    for pattern in ["*.wav", "*.WAV", "*/*.wav", "*/*.WAV"]:
        wav_files.extend(root.glob(pattern))

    # Deduplicate and sort
    wav_files = sorted(set(wav_files))
    return wav_files


def _get_drive_filenames(drive_service) -> set[str]:
    """Return the set of filenames currently in the Drive source folder."""
    try:
        monitor = DriveMonitor(drive_service)
        return {f.name for f in monitor.list_wav_files()}
    except Exception:
        logger.exception("Could not query Drive for existing files — assuming none")
        return set()


def _upload_to_drive(service, local_path: Path, folder_id: str) -> str:
    """Upload a file to Google Drive. Returns the Drive file ID."""
    file_metadata = {
        "name": local_path.name,
        "parents": [folder_id],
    }
    media = MediaFileUpload(str(local_path), mimetype="audio/wav", resumable=True)
    uploaded = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    return uploaded["id"]


async def _telegram_delete_prompt(
    bot_token: str,
    chat_id: str,
    already_on_drive: list[Path],
    newly_uploaded: list[Path],
) -> bool:
    """Send Telegram message asking whether to delete confirmed-on-Drive files from mic. Returns True if user says yes."""
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    total = len(already_on_drive) + len(newly_uploaded)
    lines = [f"📱 <b>{total} file(s)</b> on mic are on Google Drive:"]
    if newly_uploaded:
        lines.append(f"\n⬆️ Just uploaded: <b>{len(newly_uploaded)}</b>")
        for f in newly_uploaded:
            lines.append(f"  • {f.name}")
    if already_on_drive:
        lines.append(f"\n✅ Already on Drive: <b>{len(already_on_drive)}</b>")
        for f in already_on_drive:
            lines.append(f"  • {f.name}")
    lines.append("\nDelete all from mic?")

    bot = Bot(token=bot_token)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Yes, delete from mic", callback_data="usb_delete_yes"),
            InlineKeyboardButton("❌ No, keep files", callback_data="usb_delete_no"),
        ]
    ])
    msg = await bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # Poll for callback response (timeout 5 minutes)
    from telegram.ext import Application
    app = Application.builder().token(bot_token).build()
    await app.initialize()

    result = None
    deadline = asyncio.get_event_loop().time() + 300  # 5 min timeout

    while asyncio.get_event_loop().time() < deadline:
        updates = await bot.get_updates(offset=-1, timeout=10)
        for update in updates:
            if update.callback_query and update.callback_query.message.message_id == msg.message_id:
                await update.callback_query.answer()
                result = update.callback_query.data == "usb_delete_yes"
                action_text = "🗑️ Deleting files from mic..." if result else "📁 Files kept on mic"
                await update.callback_query.edit_message_reply_markup(reply_markup=None)
                await bot.send_message(chat_id=chat_id, text=action_text)
                return result
        await asyncio.sleep(2)

    # Timeout — don't delete
    await bot.send_message(chat_id=chat_id, text="⏰ No response — keeping files on mic")
    return False


def transfer_from_drive(drive_path: str, drive_service, folder_id: str, bot_token: str, chat_id: str) -> int:
    """Transfer .wav files from USB mic to Google Drive, skipping files already there. Returns upload count."""
    transferred = _load_transferred()
    wav_files = _find_wav_files(drive_path)

    if not wav_files:
        logger.info("No .wav files found on %s", drive_path)
        return 0

    # Check which files are already on Drive
    drive_filenames = _get_drive_filenames(drive_service)
    already_on_drive = [f for f in wav_files if f.name in drive_filenames]
    new_files = [f for f in wav_files if f.name not in drive_filenames and str(f) not in transferred]

    logger.info(
        "%s: %d file(s) total — %d already on Drive, %d new to upload",
        drive_path, len(wav_files), len(already_on_drive), len(new_files),
    )

    # Upload files not yet on Drive
    newly_uploaded: list[Path] = []
    for wav in new_files:
        try:
            size_mb = wav.stat().st_size / (1024 * 1024)
            logger.info("Uploading %s (%.1f MB)...", wav.name, size_mb)
            _upload_to_drive(drive_service, wav, folder_id)
            transferred.add(str(wav))
            _save_transferred(transferred)
            newly_uploaded.append(wav)
            logger.info("Uploaded %s (%d/%d)", wav.name, len(newly_uploaded), len(new_files))
        except Exception:
            logger.exception("Failed to upload %s", wav.name)

    # Offer to delete all files confirmed to be on Drive
    deletable = already_on_drive + newly_uploaded
    if deletable and bot_token and chat_id:
        should_delete = asyncio.run(
            _telegram_delete_prompt(bot_token, chat_id, already_on_drive, newly_uploaded)
        )
        if should_delete:
            for wav in deletable:
                try:
                    wav.unlink()
                    logger.info("Deleted %s from mic", wav.name)
                except Exception:
                    logger.exception("Failed to delete %s", wav.name)
    elif not deletable:
        logger.info("No files to delete from mic — nothing is on Drive yet")

    return len(newly_uploaded)


def main() -> None:
    parser = argparse.ArgumentParser(description="USB Transfer — copy .wav files from mic to Google Drive")
    parser.add_argument("--once", action="store_true", help="Transfer from connected drives and exit")
    args = parser.parse_args()

    folder_id = os.getenv("DRIVE_SOURCE_FOLDER_ID")
    if not folder_id:
        logger.error("DRIVE_SOURCE_FOLDER_ID not set in .env")
        sys.exit(1)

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    creds = get_google_creds()
    drive_service = build_drive_service(creds)

    if args.once:
        for drive_path in get_removable_drives():
            transfer_from_drive(drive_path, drive_service, folder_id, bot_token, chat_id)
        return

    # Continuous watch mode
    logger.info("USB Transfer watcher started")
    while True:
        drive_path = wait_for_new_drive()
        transfer_from_drive(drive_path, drive_service, folder_id, bot_token, chat_id)


if __name__ == "__main__":
    main()
