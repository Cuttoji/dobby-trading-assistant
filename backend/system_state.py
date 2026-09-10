"""Persistent system state: trading mode, kill switch and pause flag.

These flags are stored in the database so the EA, the API and the dashboard all
observe the same values, and they survive a restart.
"""

from __future__ import annotations

from .config import VALID_TRADING_MODES, settings
from .database import Database, get_database
from .models import SystemState, TradingMode, utcnow

KEY_MODE = "trading_mode"
KEY_KILL_SWITCH = "kill_switch"
KEY_KILL_REASON = "kill_reason"
KEY_PAUSED = "paused"
KEY_PAUSE_REASON = "pause_reason"

TRUTHY = {"1", "true", "yes", "on"}


class SystemStateStore:
    """Reads and writes the trading-control flags held in ``app_state``."""

    def __init__(self, db: Database | None = None) -> None:
        self._db = db or get_database()
        if not self._db.get_state(KEY_MODE):
            self._db.set_state(KEY_MODE, settings.trading_mode)

    # ----------------------------------------------------------- trading mode

    @property
    def mode(self) -> TradingMode:
        raw = self._db.get_state(KEY_MODE, settings.trading_mode)
        try:
            return TradingMode(raw)
        except ValueError:
            return TradingMode.SIGNAL_ONLY

    def set_mode(self, mode: TradingMode | str) -> TradingMode:
        value = mode.value if isinstance(mode, TradingMode) else str(mode).upper()
        if value not in VALID_TRADING_MODES:
            raise ValueError(
                f"Invalid trading mode '{value}'. Expected one of {VALID_TRADING_MODES}."
            )
        self._db.set_state(KEY_MODE, value)
        return TradingMode(value)

    # -------------------------------------------------------------- kill switch

    @property
    def kill_switch(self) -> bool:
        return self._db.get_state(KEY_KILL_SWITCH, "0").lower() in TRUTHY

    @property
    def kill_reason(self) -> str:
        return self._db.get_state(KEY_KILL_REASON, "")

    def engage_kill_switch(self, reason: str = "Manual emergency stop") -> None:
        self._db.set_state(KEY_KILL_SWITCH, "1")
        self._db.set_state(KEY_KILL_REASON, reason)

    def release_kill_switch(self) -> None:
        self._db.set_state(KEY_KILL_SWITCH, "0")
        self._db.set_state(KEY_KILL_REASON, "")

    # ------------------------------------------------------------------ pause

    @property
    def paused(self) -> bool:
        return self._db.get_state(KEY_PAUSED, "0").lower() in TRUTHY

    @property
    def pause_reason(self) -> str:
        return self._db.get_state(KEY_PAUSE_REASON, "")

    def pause(self, reason: str = "Paused by operator") -> None:
        self._db.set_state(KEY_PAUSED, "1")
        self._db.set_state(KEY_PAUSE_REASON, reason)

    def resume(self) -> None:
        self._db.set_state(KEY_PAUSED, "0")
        self._db.set_state(KEY_PAUSE_REASON, "")

    # ---------------------------------------------------------------- snapshot

    def snapshot(self, trading_allowed: bool = False, reason: str = "") -> SystemState:
        return SystemState(
            trading_mode=self.mode,
            kill_switch=self.kill_switch,
            paused=self.paused,
            trading_allowed=trading_allowed,
            reason=reason,
            last_updated=utcnow(),
        )
