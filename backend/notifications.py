"""Best-effort outbound notifications to Telegram, Discord and LINE.

Sending must never break trading, so every channel is wrapped and failures are
logged rather than raised. :meth:`Notifier.send` returns the list of channels
that accepted the message.
"""

from __future__ import annotations

import logging

import httpx

from .config import Settings, settings

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 10.0


class Notifier:
    """Fan-out notifier driven entirely by configuration."""

    def __init__(self, config: Settings | None = None) -> None:
        self._cfg = config or settings

    def channels(self) -> list[str]:
        """Names of the channels that are configured and enabled."""
        if not self._cfg.notify_enabled:
            return []
        available: list[str] = []
        if self._cfg.telegram_bot_token and self._cfg.telegram_chat_id:
            available.append("telegram")
        if self._cfg.discord_webhook_url:
            available.append("discord")
        if self._cfg.line_notify_token:
            available.append("line")
        return available

    def send(self, message: str) -> list[str]:
        """Send ``message`` to every configured channel; return the successes."""
        delivered: list[str] = []
        for channel in self.channels():
            try:
                if channel == "telegram":
                    self._send_telegram(message)
                elif channel == "discord":
                    self._send_discord(message)
                elif channel == "line":
                    self._send_line(message)
                delivered.append(channel)
            except Exception as exc:  # noqa: BLE001 - notifications are best-effort
                logger.warning("Notification via %s failed: %s", channel, exc)
        return delivered

    def _send_telegram(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self._cfg.telegram_bot_token}/sendMessage"
        payload = {"chat_id": self._cfg.telegram_chat_id, "text": message}
        response = httpx.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()

    def _send_discord(self, message: str) -> None:
        response = httpx.post(
            self._cfg.discord_webhook_url,
            json={"content": message},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    def _send_line(self, message: str) -> None:
        headers = {"Authorization": f"Bearer {self._cfg.line_notify_token}"}
        response = httpx.post(
            "https://notify-api.line.me/api/notify",
            headers=headers,
            data={"message": message},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()


def format_signal_message(signal) -> str:
    """Human-readable one-liner for a trade signal."""
    if signal.action.value == "WAIT":
        return f"[{signal.symbol} {signal.timeframe}] WAIT - {signal.reason}"
    return (
        f"[{signal.symbol} {signal.timeframe}] {signal.action.value} "
        f"entry={signal.entry} sl={signal.stop_loss} tp={signal.take_profit} "
        f"RR={signal.risk_reward} risk={signal.risk_percent}%"
    )
