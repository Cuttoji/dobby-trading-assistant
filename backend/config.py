"""Central application configuration.

All tunables live here and are loaded from environment variables / the ``.env``
file. Risk-management values are deliberately *not* writable at runtime by the
AI layer - they can only be changed by editing the environment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "trades.db"

# Hard ceiling the AI/strategy layer can never exceed for a single trade.
ABSOLUTE_MAX_RISK_PERCENT = 1.0
VALID_TRADING_MODES = ("SIGNAL_ONLY", "DEMO", "LIVE")


class Settings(BaseSettings):
    """Runtime settings loaded from ``.env`` (see ``.env.example``)."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # --- Storage ---
    database_path: str = str(DEFAULT_DB_PATH)
    export_dir: str = str(PROJECT_ROOT / "exports")

    # --- Trading mode: SIGNAL_ONLY | DEMO | LIVE ---
    trading_mode: str = "SIGNAL_ONLY"

    # Fallback account balance used for dashboard percentages before the EA has
    # reported a live equity snapshot.
    initial_balance: float = 1000.0

    # --- Risk management (AI can never raise these at runtime) ---
    risk_per_trade_percent: float = 0.5
    max_risk_per_trade_percent: float = 1.0
    max_open_orders: int = 1
    max_daily_loss_percent: float = 2.0
    max_consecutive_losses: int = 3
    max_daily_trades: int = 10
    min_risk_reward: float = 2.0

    # --- Strategy ---
    trend_fast_ema: int = 21
    trend_slow_ema: int = 50
    swing_lookback: int = 3
    fvg_lookback: int = 50
    order_block_lookback: int = 50
    min_candles_required: int = 60
    contract_size: float = 100_000.0

    # --- Notifications ---
    notify_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    line_notify_token: str = ""

    # --- AI assistant (explanations only, never risk changes) ---
    ai_enabled: bool = False
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: float = 30.0

    @property
    def effective_risk_percent(self) -> float:
        """Risk per trade, clamped to the configured hard maximum."""
        return min(
            max(self.risk_per_trade_percent, 0.0),
            self.max_risk_per_trade_percent,
            ABSOLUTE_MAX_RISK_PERCENT,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
