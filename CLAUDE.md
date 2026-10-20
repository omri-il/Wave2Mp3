# Wave2MP3

WAV session merger and converter. Polls Google Drive for .wav recordings from a portable mic, groups them into sessions by time gap, merges + converts to MP3, uploads to Drive, and optionally pushes to NotebookLM.

## Architecture

Two components:
1. **VPS Agent** (`main.py`) — Polls Drive, groups sessions, merges via FFmpeg, uploads MP3, archives originals, counts the session in the 08:00 business-hq digest (Telegram only for problems)
2. **USB Transfer** (`usb_transfer/`) — Laptop script that detects USB mic, checks which files are already on Drive, uploads new ones, offers to delete confirmed-on-Drive files via Telegram

## Project Structure

```
config.py              — Settings dataclass (.env)
main.py                — Entry point: polling loop, CLI flags
db.py                  — SQLite state management (files + sessions tables)
drive/auth.py          — Google OAuth2
drive/monitor.py       — Poll Drive for .wav files, download
drive/uploader.py      — Upload MP3 to Drive
drive/archiver.py      — Move .wav to archive folder on Drive
processor/session_grouper.py — Group files by time gap into sessions
processor/audio_merger.py    — FFmpeg concat + WAV→MP3
notifier/telegram_bot.py     — Telegram messages, problems only (low disk, a failed session)
notifier/hq_receipt.py       — good news → business-hq's receipts box (the 08:00 digest)
notebooklm/client.py        — HTTP client for NotebookLM bridge
usb_transfer/detector.py    — USB drive detection (psutil)
usb_transfer/transfer.py    — Copy .wav from mic → Drive, skip already-uploaded, Telegram delete prompt
deploy/wave2mp3.service      — systemd unit
```

## Commands

```bash
# Auth (run locally, copy token.json to VPS)
python main.py --auth-only

# Dry run (list files and session grouping)
python main.py --dry-run

# Run agent
python main.py

# USB transfer (laptop)
python -m usb_transfer.transfer        # Watch mode
python -m usb_transfer.transfer --once # One-shot
```

## Configuration

All settings via `.env` file. See `.env.example` for all options.

Key settings:
- `DRIVE_SOURCE_FOLDER_ID` — Where .wav files land
- `DRIVE_PROCESSED_FOLDER_ID` — Where MP3s go
- `DRIVE_ARCHIVE_FOLDER_ID` — Where originals are moved
- `SESSION_GAP_MINUTES=45` — Gap that defines a new session
- `MP3_BITRATE=128k` — MP3 encoding quality

## Dependencies

- Python 3.11+
- FFmpeg (system package on VPS)
- Google Drive API credentials (`credentials.json`)

## Deployment (VPS)

```bash
cd /root/Projects/Wave2Mp3
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with folder IDs and tokens
sudo cp deploy/wave2mp3.service /etc/systemd/system/
sudo systemctl enable --now wave2mp3
```

## Service

- **systemd:** `wave2mp3.service`
- **Logs:** `journalctl -u wave2mp3 -f`
- **Restart:** `systemctl restart wave2mp3`
- ⚠️ **Keep `httpx`/`httpcore` at WARNING** (right after `basicConfig` in `main.py` and `usb_transfer/transfer.py`). python-telegram-bot sends through httpx, which logs every request URL at INFO — and a Telegram URL contains the bot token. This bot is shared with ~10 other services, so a leak here would expose all of them.

## Notifications: problems ring, good news goes to the digest (2026-10-20)

Omri's rule (2026-10-19): a receipt lives only as a line in the 08:00 business-hq digest.
A finished session is one count there: `hq_receipt.receipt(...)` → `POST HQ_RECEIPT_URL`
`{"group":"wave2mp3","key":"merged","n":1,"label":"{n} הקלטות מהמיקרופון הומרו ל-MP3"}`
(VPS `.env`: `HQ_RECEIPT_URL=http://127.0.0.1:5051/api/receipt`, `HQ_RECEIPT_TOKEN` = business-hq's
`RECEIPT_TOKEN`; unset → skipped; a down HQ is logged and dropped). Low disk space and a failed
session still go to Telegram and ring. The laptop's USB "delete from the mic?" prompt is unchanged.

Removed the same day: the "✅ Upload to NotebookLM" / "❌ Skip" buttons under the old
"Session processed" message. Nothing ever answered them (`start_polling()` was never called), and
a `getUpdates` reader on the shared bot would have stolen other services' taps. The
`notebooklm/client.py` module is still here, unused.

## NotebookLM Integration

Optional. Requires the notebooklm-api bridge running on Home PC (`http://100.111.186.101:5111`).
Set `NOTEBOOKLM_API_URL` in `.env` to enable. ⚠️ Nothing in `main.py` calls it today (see Notifications above).

## NotebookLM Bridge

The bridge (repo `notebooklm-api`) runs on the **home PC** (`desktop-7hqm8go`) at `C:\Users\omrii\Projects\notebooklm-api\`.
- Start: the scheduled task **"NotebookLM API Server"** runs `start_bridge_hidden.vbs`, which runs `py -3.10 -m uvicorn server:app --host 0.0.0.0 --port 5111`. The task **"NotebookLM Bridge Watchdog"** restarts it if it dies.
- Google login state: `%USERPROFILE%\.notebooklm\profiles\` on the home PC (details in notebooklm-api's CLAUDE.md)
- API key: in the home PC's `notebooklm-api/.env` as `API_KEY`, and in the VPS `/root/Projects/Wave2Mp3/.env` as `NOTEBOOKLM_API_KEY`. Never write the value in this file: this repo is public.
- VPS reaches it via Tailscale: `http://100.111.186.101:5111` (`NOTEBOOKLM_API_URL` in the VPS `.env`)
- **Must be running on the home PC** for NotebookLM upload to work — non-fatal if offline

## File Naming

Mic produces files like: `DJI_15_20260413_135841.WAV`
- Session grouper extracts sequence number from position 2 (`DJI_[SEQ]_date_time`)
- Drive query matches both `.wav` and `.WAV` (uppercase)

## GitHub

https://github.com/omri-il/Wave2Mp3
