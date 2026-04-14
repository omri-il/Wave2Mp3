"""
usb_transfer/detector.py — Detect new removable USB drives (mic plugged in).
"""
from __future__ import annotations

import logging
import time

import psutil

logger = logging.getLogger(__name__)


def get_removable_drives() -> set[str]:
    """Return mount points of all currently connected removable drives."""
    drives = set()
    for part in psutil.disk_partitions():
        if "removable" in part.opts.lower():
            drives.add(part.mountpoint)
    return drives


def wait_for_new_drive(poll_seconds: int = 5) -> str:
    """Block until a new removable drive appears. Returns its mount point."""
    known = get_removable_drives()
    logger.info("Watching for new USB drives... (known: %s)", known or "none")

    while True:
        time.sleep(poll_seconds)
        current = get_removable_drives()
        new_drives = current - known
        if new_drives:
            drive = new_drives.pop()
            logger.info("New removable drive detected: %s", drive)
            return drive
        known = current
