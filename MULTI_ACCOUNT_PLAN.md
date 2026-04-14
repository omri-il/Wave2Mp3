# Wave2MP3 — Multi-Account Implementation Plan

## Goal
Support multiple Google Drive accounts with separate recording pipelines, each with its own source/processed/archive folders, credentials, and state.

## Approach
Run multiple instances of the same agent — one per account. No code changes needed. Each instance gets its own folder, credentials, .env, and systemd service.

---

## Prompt for Next Session

```
I want to add a second Google Drive account to Wave2MP3.

The project is at /root/Projects/Wave2Mp3 on the VPS (also c:\Users\omrii\projects\Wave2Mp3 on laptop).
It's already running as systemd service `wave2mp3` for account 1.

The plan is to run a second instance for a different Google account:

1. Copy the project folder on the VPS:
   cp -r /root/Projects/Wave2Mp3 /root/Projects/Wave2Mp3-account2

2. The second account needs its own:
   - credentials.json (from Google Cloud Console on the second account)
   - token.json (run --auth-only on laptop, copy to VPS)
   - .env file with the second account's Drive folder IDs
   - systemd service: wave2mp3-account2.service

3. The systemd service file needs to point to the new folder:
   WorkingDirectory=/root/Projects/Wave2Mp3-account2
   ExecStart=/root/Projects/Wave2Mp3-account2/venv/bin/python main.py

4. Steps to do:
   a. On laptop: create second credentials.json and run --auth-only to get token.json
   b. Copy both files to VPS: /root/Projects/Wave2Mp3-account2/
   c. Create /root/Projects/Wave2Mp3-account2/.env with new folder IDs
   d. Create and enable wave2mp3-account2.service
   e. Test with --dry-run from the account2 folder

The existing wave2mp3 instance (account 1) must keep running untouched.
```
