"""Shared service singletons used by the API routers.

Each accessor is memoised so the whole process shares one database connection,
one risk manager and so on. Tests can call ``clear_service_cache()`` to rebuild
them against a fresh database.
"""

from __future__ import annotations

from functools import lru_cache

from ..ai_analyst import AIAnalyst
from ..database import get_database
from ..notifications import Notifier
from ..risk_manager import RiskManager
from ..system_state import SystemStateStore
from ..trading_service import TradingService


@lru_cache(maxsize=1)
def get_state_store() -> SystemStateStore:
    return SystemStateStore()


@lru_cache(maxsize=1)
def get_risk_manager() -> RiskManager:
    return RiskManager(state_store=get_state_store())


@lru_cache(maxsize=1)
def get_notifier() -> Notifier:
    return Notifier()


@lru_cache(maxsize=1)
def get_analyst() -> AIAnalyst:
    return AIAnalyst()


@lru_cache(maxsize=1)
def get_trading_service() -> TradingService:
    return TradingService(
        db=get_database(),
        risk_manager=get_risk_manager(),
        notifier=get_notifier(),
    )


def clear_service_cache() -> None:
    """Drop the memoised services (used by tests)."""
    for factory in (
        get_trading_service,
        get_analyst,
        get_notifier,
        get_risk_manager,
        get_state_store,
    ):
        factory.cache_clear()
