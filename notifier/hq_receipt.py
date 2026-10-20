"""
notifier/hq_receipt.py — reports good news to business-hq's receipts box.

Omri, 2026-10-19: a receipt (a message that only says something happened)
lives ONLY as a line in the 08:00 business-hq digest ("🗂 מה קרה מאז אתמול"),
never as a Telegram message. Failures still go to Telegram (telegram_bot.py)
and ring. The contract lives in business-hq's receipts.py.

Fire and forget: unset HQ_RECEIPT_URL / HQ_RECEIPT_TOKEN → skipped; any error
is logged without the token and dropped. It never falls back to Telegram.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def receipt(url: str, token: str, group: str, key: str, *, n: int | None = None,
            label: str | None = None, text: str | None = None) -> None:
    if not url or not token:
        logger.debug("HQ receipt skipped — HQ_RECEIPT_URL/HQ_RECEIPT_TOKEN not set")
        return
    body: dict = {"group": group, "key": key}
    if text is not None:
        body["text"] = text
    else:
        body["n"] = n
        body["label"] = label
    try:
        httpx.post(url, json=body, headers={"X-Api-Key": token}, timeout=10).raise_for_status()
        logger.info("HQ receipt sent (%s/%s)", group, key)
    except Exception as exc:  # noqa: BLE001 — a receipt must never break a session
        logger.warning("HQ receipt not sent (%s/%s): %s", group, key, type(exc).__name__)
