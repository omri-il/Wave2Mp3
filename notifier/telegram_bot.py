"""
notifier/telegram_bot.py — Telegram messages for problems only.

A finished session is good news and goes to the 08:00 business-hq digest
(notifier/hq_receipt.py), not here (Omri, 2026-10-19). Until 2026-10-20 it was
a Telegram message with "✅ Upload to NotebookLM" / "❌ Skip" buttons that
nothing answered: start_polling() was never called, and the token is the
shared bot, whose updates belong to other services. Both are gone.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self._token = bot_token
        self._chat_id = chat_id

    def send_message(self, text: str) -> None:
        """Send a simple HTML message (it rings: use it for problems only)."""
        if not self._token:
            logger.debug("Telegram not configured, skipping notification")
            return
        try:
            import asyncio
            asyncio.run(self._async_send(text))
        except RuntimeError:
            # Already in an event loop — use thread
            loop = asyncio.new_event_loop()
            t = threading.Thread(target=lambda: loop.run_until_complete(self._async_send(text)))
            t.start()
            t.join(timeout=10)

    async def _async_send(self, text: str) -> None:
        from telegram import Bot
        bot = Bot(token=self._token)
        await bot.send_message(chat_id=self._chat_id, text=text, parse_mode="HTML")
