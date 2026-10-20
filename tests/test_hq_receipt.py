"""A finished session is one count in the 08:00 business-hq digest, never a
Telegram message (Omri, 2026-10-19). Run: python -m pytest tests"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx  # noqa: E402

from notifier import hq_receipt, telegram_bot  # noqa: E402

URL = "http://127.0.0.1:5051/api/receipt"


class _Resp:
    def raise_for_status(self):
        pass


def test_posts_the_contract_body_with_the_token(monkeypatch):
    calls = []
    monkeypatch.setattr(hq_receipt.httpx, "post",
                        lambda url, json, headers, timeout: calls.append((url, json, headers)) or _Resp())
    hq_receipt.receipt(URL, "box-token", "wave2mp3", "merged", n=1, label="{n} הקלטות")
    assert calls == [(URL, {"group": "wave2mp3", "key": "merged", "n": 1, "label": "{n} הקלטות"},
                      {"X-Api-Key": "box-token"})]


def test_skipped_when_not_configured(monkeypatch):
    calls = []
    monkeypatch.setattr(hq_receipt.httpx, "post", lambda *a, **k: calls.append(a))
    hq_receipt.receipt(URL, "", "wave2mp3", "merged", n=1, label="x")
    hq_receipt.receipt("", "box-token", "wave2mp3", "merged", n=1, label="x")
    assert calls == []


def test_a_down_hq_never_breaks_the_session(monkeypatch):
    def down(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(hq_receipt.httpx, "post", down)
    hq_receipt.receipt(URL, "box-token", "wave2mp3", "merged", n=1, label="x")  # no raise


def test_the_dead_notebooklm_buttons_are_gone():
    # Nothing ever answered "Upload to NotebookLM" / "Skip" (start_polling was never
    # called), and a getUpdates reader on the shared bot would steal other services' taps.
    notifier = telegram_bot.TelegramNotifier("t", "c")
    assert not hasattr(notifier, "send_session_complete")
    assert not hasattr(notifier, "start_polling")
