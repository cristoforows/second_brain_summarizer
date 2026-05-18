from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger()


class TelegramService:
    def __init__(self, outbound_url: str, secret: str) -> None:
        self._url = outbound_url
        self._headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        }

    def send_message(self, chat_id: str, text: str) -> dict:
        """POST {chat_id, text} to the bot endpoint and return the parsed JSON response."""
        response = httpx.post(
            self._url,
            json={"chat_id": chat_id, "text": text},
            headers=self._headers,
            timeout=10,
        )
        response.raise_for_status()
        log.info("telegram_message_sent", chat_id=chat_id)
        return response.json()
