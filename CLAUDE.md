# Wave2MP3

WAV session merger and converter. Polls Google Drive for .wav recordings from a portable mic, groups them into sessions by time gap, merges + converts to MP3, uploads to Drive, and optionally pushes to NotebookLM.

## Architecture

Two components:
1. **VPS Agent** (`main.py`) — Polls Drive, groups sessions, merges via FFmpeg, uploads MP3, archives originals, sends Telegram notifications
2. **USB Transfer** (`usb_transfer/`) — Laptop script that detects USB mic, uploads .wav to Drive, asks via Telegram whether to delete from mic

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
notifier/telegram_bot.py     — Telegram notifications + inline keyboard
notebooklm/client.py        — HTTP client for NotebookLM bridge
usb_transfer/detector.py    — USB drive detection (psutil)
usb_transfer/transfer.py    — Copy .wav from mic → Drive + delete prompt
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

## NotebookLM Integration

Optional. Requires the notebooklm-api bridge running on Home PC (`http://100.111.186.101:5111`).
Set `NOTEBOOKLM_API_URL` in `.env` to enable. If bridge is unreachable, notifications are sent via Telegram — non-fatal.

## GitHub

https://github.com/omri-il/Wave2Mp3
