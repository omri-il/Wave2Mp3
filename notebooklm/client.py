"""
notebooklm/client.py — HTTP client for the NotebookLM API bridge on Home PC.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from config import settings

logger = logging.getLogger(__name__)


class NotebookLMClient:
    def __init__(self):
        self._base_url = settings.notebooklm_api_url.rstrip("/")
        self._api_key = settings.notebooklm_api_key

    @property
    def enabled(self) -> bool:
        return bool(self._base_url)

    def health_check(self) -> bool:
        """Check if the NotebookLM bridge is reachable."""
        if not self.enabled:
            return False
        try:
            resp = httpx.get(f"{self._base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            logger.debug("NotebookLM bridge unreachable")
            return False

    def list_notebooks(self) -> list[dict]:
        """Get list of available notebooks."""
        resp = httpx.get(
            f"{self._base_url}/notebooks",
            timeout=10,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def upload_audio(self, mp3_path: Path, notebook_id: str | None = None) -> dict:
        """Upload an MP3 file to NotebookLM as a source."""
        with mp3_path.open("rb") as f:
            files = {"file": (mp3_path.name, f, "audio/mpeg")}
            data = {}
            if notebook_id:
                data["notebook_id"] = notebook_id
            resp = httpx.post(
                f"{self._base_url}/upload",
                files=files,
                data=data,
                headers=self._headers(),
                timeout=120,
            )
        resp.raise_for_status()
        result = resp.json()
        logger.info("Uploaded %s to NotebookLM: %s", mp3_path.name, result)
        return result

    def _headers(self) -> dict:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
