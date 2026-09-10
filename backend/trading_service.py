"""Application service for the signal-only trading workflow."""

from __future__ import annotations

from .ai_analyst import AIAnalyst
from .database import Database
from .models import AnalysisResponse, MarketRequest
from .notifications import Notifier, format_signal_message
from .risk_manager import RiskManager
from .strategy import analyze_market


class TradingService:
    """Coordinate strategy, risk checks, persistence and advisory output."""

    def __init__(
        self,
        db: Database,
        risk_manager: RiskManager,
        notifier: Notifier,
        analyst: AIAnalyst | None = None,
    ) -> None:
        self._db = db
        self._risk = risk_manager
        self._notifier = notifier
        self._analyst = analyst or AIAnalyst()

    def analyze(self, request: MarketRequest) -> AnalysisResponse:
        result = analyze_market(request)
        signal = result.signal
        risk = self._risk.evaluate(
            signal,
            balance=request.account_balance,
            open_orders=request.open_orders,
        )

        self._db.record_signal(
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            action=signal.action.value,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            risk_reward=signal.risk_reward,
            reason=signal.reason,
            accepted=risk.allowed,
            block_reason="" if risk.allowed else risk.reason,
        )

        explanation = self._analyst.explain_signal(
            signal, trend=result.trend, conditions=result.conditions
        )
        self._db.log_ai(explanation.kind, explanation.text)

        notifications: list[str] = []
        if signal.action.value != "WAIT":
            notifications = self._notifier.send(format_signal_message(signal))

        return AnalysisResponse(
            signal=signal,
            trend=result.trend,
            zones=result.zones,
            risk=risk,
            trading_allowed=risk.allowed,
            blocked_reason="" if risk.allowed else risk.reason,
            notifications=notifications,
        )