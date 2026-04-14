"""
db.py — SQLite state management for file and session tracking.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    drive_file_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    drive_created_time TEXT NOT NULL,
    file_size INTEGER,
    first_seen_at TEXT NOT NULL,
    last_size_check INTEGER,
    status TEXT NOT NULL DEFAULT 'new',
    session_id TEXT,
    error_message TEXT,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    session_date TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    mp3_drive_file_id TEXT,
    mp3_filename TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    notebooklm_status TEXT DEFAULT 'not_asked',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
"""


class Database:
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def upsert_file(self, drive_file_id: str, filename: str, created_time: str, size: int) -> None:
        """Insert a new file or update its size for stability tracking."""
        now = datetime.now(timezone.utc).isoformat()
        row = self._conn.execute(
            "SELECT drive_file_id, status FROM files WHERE drive_file_id = ?",
            (drive_file_id,)
        ).fetchone()

        if row is None:
            self._conn.execute(
                "INSERT INTO files (drive_file_id, filename, drive_created_time, file_size, first_seen_at, last_size_check, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'new')",
                (drive_file_id, filename, created_time, size, now, size),
            )
        elif row["status"] in ("new",):
            # Update size check for stability detection
            self._conn.execute(
                "UPDATE files SET last_size_check = ? WHERE drive_file_id = ?",
                (size, drive_file_id),
            )
        self._conn.commit()

    def mark_stable_files(self, stable_minutes: int) -> None:
        """Mark files as stable if their size hasn't changed and they've been seen long enough."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stable_minutes)).isoformat()
        self._conn.execute(
            "UPDATE files SET status = 'stable' "
            "WHERE status = 'new' AND first_seen_at <= ? AND file_size = last_size_check",
            (cutoff,),
        )
        self._conn.commit()

    def get_stable_files(self) -> list[dict]:
        """Return all files with status 'stable' that haven't been assigned to a session."""
        rows = self._conn.execute(
            "SELECT drive_file_id, filename, drive_created_time, file_size "
            "FROM files WHERE status = 'stable' AND session_id IS NULL "
            "ORDER BY drive_created_time"
        ).fetchall()
        return [dict(r) for r in rows]

    def is_session_complete(self, session_files: list[dict], wait_minutes: int) -> bool:
        """Check if the newest file in a session has been stable long enough."""
        if not session_files:
            return False
        # Get the newest file's first_seen_at
        newest_id = session_files[-1]["drive_file_id"]
        row = self._conn.execute(
            "SELECT first_seen_at FROM files WHERE drive_file_id = ?",
            (newest_id,)
        ).fetchone()
        if not row:
            return False
        first_seen = datetime.fromisoformat(row["first_seen_at"])
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=wait_minutes)
        return first_seen <= cutoff

    def create_session(self, session_files: list[dict]) -> str | None:
        """Create a new session and assign files to it. Returns session_id or None if already exists."""
        # Generate session ID from date of first file
        first_time = session_files[0]["drive_created_time"]
        session_date = first_time[:10]  # YYYY-MM-DD
        now = datetime.now(timezone.utc).isoformat()

        # Check if these files are already in a session
        file_ids = [f["drive_file_id"] for f in session_files]
        placeholders = ",".join("?" for _ in file_ids)
        existing = self._conn.execute(
            f"SELECT session_id FROM files WHERE drive_file_id IN ({placeholders}) AND session_id IS NOT NULL",
            file_ids,
        ).fetchone()
        if existing:
            return None

        # Create unique session ID
        count = self._conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE session_date = ?",
            (session_date,)
        ).fetchone()[0]
        session_id = f"{session_date}_{count + 1:02d}"

        self._conn.execute(
            "INSERT INTO sessions (session_id, session_date, file_count, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (session_id, session_date, len(session_files), now),
        )

        # Assign files to session
        for f in session_files:
            self._conn.execute(
                "UPDATE files SET session_id = ? WHERE drive_file_id = ?",
                (session_id, f["drive_file_id"]),
            )

        self._conn.commit()
        return session_id

    def update_session_status(self, session_id: str, status: str, error: str | None = None) -> None:
        if status == "done":
            self._conn.execute(
                "UPDATE sessions SET status = ?, completed_at = ? WHERE session_id = ?",
                (status, datetime.now(timezone.utc).isoformat(), session_id),
            )
        elif error:
            self._conn.execute(
                "UPDATE sessions SET status = ? WHERE session_id = ?",
                (status, session_id),
            )
        else:
            self._conn.execute(
                "UPDATE sessions SET status = ? WHERE session_id = ?",
                (status, session_id),
            )
        self._conn.commit()

    def complete_session(self, session_id: str, mp3_drive_id: str, mp3_filename: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE sessions SET status = 'done', mp3_drive_file_id = ?, mp3_filename = ?, completed_at = ? "
            "WHERE session_id = ?",
            (mp3_drive_id, mp3_filename, now, session_id),
        )
        self._conn.commit()

    def update_files_status(self, file_ids: list[str], status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for fid in file_ids:
            if status == "done":
                self._conn.execute(
                    "UPDATE files SET status = ?, processed_at = ? WHERE drive_file_id = ?",
                    (status, now, fid),
                )
            else:
                self._conn.execute(
                    "UPDATE files SET status = ? WHERE drive_file_id = ?",
                    (status, fid),
                )
        self._conn.commit()

    def update_notebooklm_status(self, session_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET notebooklm_status = ? WHERE session_id = ?",
            (status, session_id),
        )
        self._conn.commit()

    def get_session(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_pending_notebooklm_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE status = 'done' AND notebooklm_status = 'accepted'"
        ).fetchall()
        return [dict(r) for r in rows]

    def recover_from_crash(self) -> None:
        """Reset in-progress states back to stable on startup."""
        self._conn.execute(
            "UPDATE files SET status = 'stable' WHERE status IN ('downloading', 'processing')"
        )
        self._conn.execute(
            "UPDATE sessions SET status = 'pending' WHERE status = 'processing'"
        )
        self._conn.commit()
        logger.info("Crash recovery: reset in-progress states")

    def close(self) -> None:
        self._conn.close()
