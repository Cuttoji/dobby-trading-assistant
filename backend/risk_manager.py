"""Risk policy enforcement.

Every check here is deterministic and code-owned: the AI layer may *explain*
these rules but can never relax them. The manager answers two questions:

* may we open a new position right now? (:meth:`can_trade`)
* how large may that position be? (:meth:`evaluate`)
"""

from __future__ import annotations

from .config import settings
from .database import Database, get_database
from .models import Action, RiskDecision, SystemState, TradeSignal, TradingMode, utcnow
from .position_sizing import position_size
from .system_state import SystemStateStore


class RiskManager:
    """Applies the configured risk limits before any order is allowed."""

    def __init__(
        self, db: Database | None = None, state_store: SystemStateStore | None = None
    ) -> None:
        self._db = db or get_database()
        self._state = state_store or SystemStateStore(self._db)

    @property
    def state_store(self) -> SystemStateStore:
        return self._state

    # ------------------------------------------------------------------ inputs

    def daily_loss_percent(self, balance: float) -> float:
        """Today's realised loss as a percentage of ``balance`` (>= 0)."""
        if balance <= 0:
            return 0.0
        today = utcnow().date()
        net = sum(
            trade.profit
            for trade in self._db.get_closed_trades()
            if trade.closed_at is not None and trade.closed_at.date() == today
        )
        return max(0.0, -net) / balance * 100.0

    def trades_today(self) -> int:
        today = utcnow().date()
        return sum(
            1 for trade in self._db.get_trades(limit=1000)
            if trade.opened_at.date() == today
        )

    def consecutive_losses(self) -> int:
        streak = 0
        for trade in reversed(self._db.get_closed_trades()):
            if trade.profit < 0:
                streak += 1
            else:
                break
        return streak

    # ------------------------------------------------------------------ checks

    def can_trade(self, balance: float, open_orders: int) -> RiskDecision:
        """Gate that must pass before any new position may be opened."""
        if self._state.kill_switch:
            return RiskDecision(
                allowed=False,
                reason=f"Kill switch engaged ({self._state.kill_reason or 'no reason given'})",
            )
        if self._state.paused:
            return RiskDecision(
                allowed=False,
                reason=f"System paused ({self._state.pause_reason or 'no reason given'})",
            )
        if self._state.mode is TradingMode.SIGNAL_ONLY:
            return RiskDecision(
                allowed=False, reason="SIGNAL_ONLY mode: order execution is disabled"
            )
        if open_orders >= settings.max_open_orders:
            return RiskDecision(
                allowed=False,
                reason=f"Max open orders reached ({settings.max_open_orders})",
            )
        if self.trades_today() >= settings.max_daily_trades:
            return RiskDecision(
                allowed=False,
                reason=f"Daily trade limit reached ({settings.max_daily_trades})",
            )

        loss_percent = self.daily_loss_percent(balance)
        if loss_percent >= settings.max_daily_loss_percent:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Daily loss limit reached ({loss_percent:.2f}% >= "
                    f"{settings.max_daily_loss_percent}%)"
                ),
            )

        streak = self.consecutive_losses()
        if streak >= settings.max_consecutive_losses:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Consecutive loss limit reached ({streak} >= "
                    f"{settings.max_consecutive_losses})"
                ),
            )

        return RiskDecision(allowed=True, reason="All risk checks passed")

    def evaluate(
        self, signal: TradeSignal, balance: float, open_orders: int
    ) -> RiskDecision:
        """Full authorisation for a concrete signal, including position size."""
        if signal.action is Action.WAIT:
            return RiskDecision(allowed=False, reason=signal.reason or "No setup")

        if signal.risk_reward < settings.min_risk_reward:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Risk/reward {signal.risk_reward:.2f} is below the minimum "
                    f"{settings.min_risk_reward:.2f}"
                ),
            )

        gate = self.can_trade(balance, open_orders)
        if not gate.allowed:
            return gate

        return position_size(
            balance=balance,
            risk_percent=settings.effective_risk_percent,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
        )

    def state(self, balance: float, open_orders: int) -> SystemState:
        """Current system state including whether trading is permitted."""
        decision = self.can_trade(balance, open_orders)
        return self._state.snapshot(decision.allowed, decision.reason)
