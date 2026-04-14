"""
processor/session_grouper.py — Group .wav files into recording sessions by time gap.
"""
from __future__ import annotations

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _parse_sequence_number(filename: str) -> int:
    """
    Extract sequence number from filename.
    Handles patterns like:
      DJI_15_20260413_135841.WAV → 15
      REC_001.wav → 1
    """
    # Try DJI pattern: letters_NUMBER_date_time
    m = re.match(r"[A-Za-z]+_(\d+)_", filename)
    if m:
        return int(m.group(1))
    # Fallback: first number found
    m = re.search(r"(\d+)", filename)
    return int(m.group(1)) if m else 0


def group_into_sessions(files: list[dict], gap_minutes: int) -> list[list[dict]]:
    """
    Group files into sessions based on time gaps.

    Args:
        files: List of dicts with 'drive_created_time' and 'filename' keys,
               sorted by drive_created_time.
        gap_minutes: A gap larger than this between consecutive files starts a new session.

    Returns:
        List of sessions, each a list of file dicts sorted by sequence number.
    """
    if not files:
        return []

    # Sort by created time first
    sorted_files = sorted(files, key=lambda f: f["drive_created_time"])

    sessions: list[list[dict]] = []
    current_session: list[dict] = [sorted_files[0]]

    for prev, curr in zip(sorted_files, sorted_files[1:]):
        prev_time = datetime.fromisoformat(prev["drive_created_time"].replace("Z", "+00:00"))
        curr_time = datetime.fromisoformat(curr["drive_created_time"].replace("Z", "+00:00"))
        gap = (curr_time - prev_time).total_seconds() / 60

        if gap > gap_minutes:
            # New session
            sessions.append(current_session)
            current_session = [curr]
        else:
            current_session.append(curr)

    sessions.append(current_session)

    # Sort files within each session by sequence number
    for session in sessions:
        session.sort(key=lambda f: _parse_sequence_number(f["filename"]))

    logger.info("Grouped %d files into %d session(s)", len(files), len(sessions))
    return sessions
