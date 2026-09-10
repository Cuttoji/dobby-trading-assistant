"""Pydantic models shared across the backend and the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"


class TrendDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    RANGE = "RANGE"


class ZoneKind(str, Enum):
    FVG = "FVG"
    ORDER_BLOCK = "ORDER_BLOCK"


class TradingMode(str, Enum):
    SIGNAL_ONLY = "SIGNAL_ONLY"
    DEMO = "DEMO"
    LIVE = "LIVE"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Candle(BaseModel):
    """A single OHLC(V) bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @field_validator("high")
    @classmethod
    def _high_not_below_low(cls, high: float, info) -> float:
        low = info.data.get("low")
        if low is not None and high < low:
            raise ValueError("high must be >= low")
        return high

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def candle_range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)


class Zone(BaseModel):
    """A price zone (Fair Value Gap or Order Block)."""

    kind: ZoneKind
    bullish: bool
    top: float
    bottom: float
    formed_index: int = Field(description="Index in the candle list where the zone formed")
    formed_at: datetime | None = None
    mitigated: bool = False

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2.0

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top

    def overlaps(self, low: float, high: float) -> bool:
        return self.bottom <= high and self.top >= low


class TrendInfo(BaseModel):
    direction: TrendDirection
    strength: float = Field(ge=0.0, le=1.0)
    ema_fast: float
    ema_slow: float
    detail: str


class MarketRequest(BaseModel):
    """Payload sent by the MT5 EA with recent candles + account state."""

    symbol: str
    timeframe: str = "M15"
    candles: list[Candle] = Field(default_factory=list)
    account_balance: float = 1000.0
    account_equity: float = 1000.0
    open_orders: int = 0
    point: float = 0.0001
    digits: int = 5

    @field_validator("candles")
    @classmethod
    def _sorted_candles(cls, candles: list[Candle]) -> list[Candle]:
        return sorted(candles, key=lambda c: c.timestamp)


class RiskDecision(BaseModel):
    allowed: bool
    reason: str
    lots: float = 0.0
    risk_amount: float = 0.0
    risk_percent: float = 0.0


class TradeSignal(BaseModel):
    action: Action
    symbol: str
    timeframe: str
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 0.0
    risk_percent: float = 0.0
    lots: float = 0.0
    reason: str = ""
    trend: TrendDirection | None = None
    zones: list[Zone] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class AnalysisResponse(BaseModel):
    signal: TradeSignal
    trend: TrendInfo | None = None
    zones: list[Zone] = Field(default_factory=list)
    risk: RiskDecision | None = None
    trading_allowed: bool = False
    blocked_reason: str = ""
    notifications: list[str] = Field(default_factory=list)


class TradeRecord(BaseModel):
    id: int | None = None
    ticket: int | None = None
    symbol: str
    action: Action
    entry: float
    stop_loss: float
    take_profit: float
    lots: float
    risk_percent: float = 0.0
    profit: float = 0.0
    status: TradeStatus = TradeStatus.OPEN
    reason: str = ""
    source: str = "EA"
    opened_at: datetime = Field(default_factory=utcnow)
    closed_at: datetime | None = None


class TradeStats(BaseModel):
    total_trades: int = 0
    closed_trades: int = 0
    win_rate: float = 0.0
    total_profit: float = 0.0
    today_profit: float = 0.0
    today_percent: float = 0.0
    max_drawdown_percent: float = 0.0
    consecutive_losses: int = 0
    open_orders: int = 0


class SystemState(BaseModel):
    trading_mode: TradingMode = TradingMode.SIGNAL_ONLY
    kill_switch: bool = False
    paused: bool = False
    trading_allowed: bool = False
    reason: str = ""
    last_updated: datetime = Field(default_factory=utcnow)


class AIExplanation(BaseModel):
    enabled: bool
    kind: str
    text: str
    created_at: datetime = Field(default_factory=utcnow)


class OpenTradeRequest(BaseModel):
    """Payload sent by the EA when it has opened a live/demo position."""

    ticket: int | None = None
    symbol: str
    action: Action
    entry: float
    stop_loss: float
    take_profit: float
    lots: float
    risk_percent: float = 0.0
    reason: str = ""
    source: str = "EA"


class CloseTradeRequest(BaseModel):
    """Payload sent by the EA when a position has been closed."""

    trade_id: int | None = None
    ticket: int | None = None
    profit: float


class ModeRequest(BaseModel):
    mode: TradingMode


class ReasonRequest(BaseModel):
    reason: str = ""


class MessageResponse(BaseModel):
    ok: bool = True
    message: str = ""
    detail: str = ""
