"""
notifier/telegram_bot.py — Telegram notifications + NotebookLM inline keyboard.
"""
from __future__ import annotations

import logging
import json
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self._token = bot_token
        self._chat_id = chat_id
        self._app: Application | None = None
        self._callback_handler = None  # set externally for NotebookLM callbacks

    def send_message(self, text: str) -> None:
        """Send a simple HTML message."""
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

    def send_session_complete(self, session_id: str, mp3_filename: str, file_count: int) -> None:
        """Send session complete notification with NotebookLM inline keyboard."""
        text = (
            f"✅ <b>Session processed</b>\n"
            f"📁 {mp3_filename}\n"
            f"🎵 {file_count} file(s) merged\n"
            f"🆔 {session_id}"
        )

        if not self._token:
            logger.debug("Telegram not configured, skipping notification")
            return

        try:
            import asyncio
            asyncio.run(self._async_send_with_keyboard(text, session_id))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            t = threading.Thread(target=lambda: loop.run_until_complete(
                self._async_send_with_keyboard(text, session_id)
            ))
            t.start()
            t.join(timeout=10)

    async def _async_send_with_keyboard(self, text: str, session_id: str) -> None:
        from telegram import Bot
        bot = Bot(token=self._token)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Upload to NotebookLM", callback_data=json.dumps({"action": "nlm_yes", "sid": session_id})),
                InlineKeyboardButton("❌ Skip", callback_data=json.dumps({"action": "nlm_no", "sid": session_id})),
            ]
        ])
        await bot.send_message(
            chat_id=self._chat_id, text=text, parse_mode="HTML", reply_markup=keyboard
        )

    def start_polling(self, callback_handler) -> None:
        """Start the Telegram bot polling in a background thread for handling callbacks."""
        if not self._token:
            return

        self._app = Application.builder().token(self._token).build()

        async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            query = update.callback_query
            await query.answer()
            data = json.loads(query.data)
            callback_handler(data)
            action_text = "Uploading to NotebookLM..." if data["action"] == "nlm_yes" else "Skipped NotebookLM"
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(action_text)

        async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            callback_handler({"action": "status"})

        self._app.add_handler(CallbackQueryHandler(handle_callback))
        self._app.add_handler(CommandHandler("status", status_command))

        def run_bot():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._app.run_polling(drop_pending_updates=True))

        thread = threading.Thread(target=run_bot, daemon=True)
        thread.start()
        logger.info("Telegram bot polling started")
