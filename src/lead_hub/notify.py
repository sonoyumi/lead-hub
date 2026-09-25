"""Telegram notifications. Without a bot token everything is only written to the log."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)
API_URL = "https://api.telegram.org"


class NotifyError(RuntimeError):
    pass


class Notifier(Protocol):
    def send_message(self, chat_id: str, text: str) -> None: ...
    def send_document(self, chat_id: str, path: Path, caption: str = "") -> None: ...


class LogNotifier:
    """Used when BOT_TOKEN is empty: keeps the service working and shows what would be sent."""

    def send_message(self, chat_id: str, text: str) -> None:
        logger.info("[notify → %s] %s", chat_id, text)

    def send_document(self, chat_id: str, path: Path, caption: str = "") -> None:
        logger.info("[notify → %s] file %s: %s", chat_id, path.name, caption)


class TelegramNotifier:
    def __init__(self, token: str, client: httpx.Client | None = None) -> None:
        self._token = token
        self._client = client or httpx.Client(timeout=30)

    def _call(self, method: str, **kwargs) -> None:
        try:
            response = self._client.post(f"{API_URL}/bot{self._token}/{method}", **kwargs)
        except httpx.HTTPError as exc:
            raise NotifyError(f"Telegram: network error {type(exc).__name__}") from None
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != 200 or not payload.get("ok"):
            # The token is part of the URL, so it is never put into the error text.
            raise NotifyError(f"Telegram rejected {method}: {payload.get('description', response.status_code)}")

    def send_message(self, chat_id: str, text: str) -> None:
        self._call(
            "sendMessage",
            data={"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML", "disable_web_page_preview": "true"},
        )

    def send_document(self, chat_id: str, path: Path, caption: str = "") -> None:
        with path.open("rb") as file:
            self._call(
                "sendDocument",
                data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
                files={"document": (path.name, file)},
            )
