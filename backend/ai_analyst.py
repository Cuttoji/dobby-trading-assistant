"""AI analyst: explains signals and summarises performance.

Strictly advisory. The system prompt forbids the model from proposing changes
to risk limits, and nothing in this module can mutate trading configuration.
When AI is disabled - or the request fails - a deterministic summary is returned
so the caller always gets useful text.
"""

from __future__ import annotations

import logging

import httpx

from .config import Settings, settings
from .models import AIExplanation, TradeSignal, TradeStats, TrendInfo

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a conservative forex trading analyst assistant for a demo/backtest "
    "system. Explain setups and results in plain language. Never suggest raising "
    "risk per trade, removing stop losses, or overriding the system's risk "
    "limits. Always state that Fair Value Gap and Order Block strategies are not "
    "guaranteed to be profitable. Keep replies under 150 words."
)


def _fallback_signal(
    signal: TradeSignal, trend: TrendInfo | None, conditions: list[str] | None
) -> str:
    lines = [
        f"Signal: {signal.action.value} on {signal.symbol} {signal.timeframe}.",
        f"Reason: {signal.reason or 'no setup'}.",
    ]
    if signal.action.value != "WAIT":
        lines.append(
            f"Entry {signal.entry}, stop {signal.stop_loss}, "
            f"target {signal.take_profit}, R/R {signal.risk_reward}."
        )
    if trend is not None:
        lines.append(f"Trend: {trend.detail}.")
    if conditions:
        lines.append("Checks: " + " | ".join(conditions) + ".")
    lines.append(
        "Note: FVG and Order Block setups are not guaranteed to be profitable."
    )
    return " ".join(lines)


def _fallback_summary(stats: TradeStats) -> str:
    return (
        f"Closed trades: {stats.closed_trades}, win rate {stats.win_rate}%, "
        f"total profit {stats.total_profit}, today {stats.today_profit} "
        f"({stats.today_percent}%). Max drawdown {stats.max_drawdown_percent}%, "
        f"consecutive losses {stats.consecutive_losses}. "
        "Past performance does not guarantee future results."
    )


class AIAnalyst:
    """Thin OpenAI-compatible client used only for explanations."""

    def __init__(self, config: Settings | None = None) -> None:
        self._cfg = config or settings

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.ai_enabled and self._cfg.ai_api_key)

    # ------------------------------------------------------------------ public

    def explain_signal(
        self,
        signal: TradeSignal,
        trend: TrendInfo | None = None,
        conditions: list[str] | None = None,
    ) -> AIExplanation:
        if not self.enabled:
            return AIExplanation(
                enabled=False,
                kind="signal",
                text=_fallback_signal(signal, trend, conditions),
            )

        user_prompt = (
            f"Explain this trade decision briefly.\n"
            f"Symbol: {signal.symbol} {signal.timeframe}\n"
            f"Action: {signal.action.value}\n"
            f"Entry: {signal.entry}, Stop: {signal.stop_loss}, "
            f"Target: {signal.take_profit}, R/R: {signal.risk_reward}\n"
            f"Trend: {trend.detail if trend else 'unknown'}\n"
            f"Reason: {signal.reason}\n"
            f"Checks: {'; '.join(conditions or [])}"
        )
        return AIExplanation(
            enabled=True,
            kind="signal",
            text=self._safe_chat(user_prompt, _fallback_signal(signal, trend, conditions)),
        )

    def summarize_session(self, stats: TradeStats) -> AIExplanation:
        if not self.enabled:
            return AIExplanation(
                enabled=False, kind="session", text=_fallback_summary(stats)
            )

        user_prompt = (
            "Summarise this trading session and suggest one improvement focused on "
            "discipline (never raise risk).\n"
            f"Closed trades: {stats.closed_trades}\n"
            f"Win rate: {stats.win_rate}%\n"
            f"Total profit: {stats.total_profit}\n"
            f"Today: {stats.today_profit} ({stats.today_percent}%)\n"
            f"Max drawdown: {stats.max_drawdown_percent}%\n"
            f"Consecutive losses: {stats.consecutive_losses}"
        )
        return AIExplanation(
            enabled=True,
            kind="session",
            text=self._safe_chat(user_prompt, _fallback_summary(stats)),
        )

    # ----------------------------------------------------------------- private

    def _safe_chat(self, user_prompt: str, fallback: str) -> str:
        try:
            return self._chat(user_prompt)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("AI request failed, using fallback: %s", exc)
            return fallback

    def _chat(self, user_prompt: str) -> str:
        url = f"{self._cfg.ai_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._cfg.ai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 400,
        }
        headers = {"Authorization": f"Bearer {self._cfg.ai_api_key}"}
        response = httpx.post(
            url, json=payload, headers=headers, timeout=self._cfg.ai_timeout_seconds
        )
        response.raise_for_status()
        body = response.json()
        return body["choices"][0]["message"]["content"].strip()
