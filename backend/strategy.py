"""Strategy engine: turns candles into a directional trade signal.

Buy setup (sell is the mirror image):

1. The dominant trend is UP.
2. Price has retraced into a fresh bullish Order Block.
3. A bullish Fair Value Gap is present (ideally overlapping the Order Block).
4. The latest candle confirms the reversal with a strong bullish body.
5. The structural target yields at least the configured risk/reward.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analysis import detect_fvgs, detect_order_blocks, detect_trend
from .config import settings
from .indicators import atr
from .models import (
    Action,
    Candle,
    MarketRequest,
    TradeSignal,
    TrendDirection,
    TrendInfo,
    Zone,
)
from .strategy_conditions import (
    candle_touched_zone,
    has_directional_fvg,
    is_confirmation_candle,
    latest_zone_of,
    structural_target,
)

ATR_PERIOD = 14
STOP_BUFFER_ATR = 0.25
DEFAULT_RR = 2.0
FALLBACK_RANGE_FRACTION = 0.0005


@dataclass
class AnalysisResult:
    """Everything the API needs from one analysis pass."""

    signal: TradeSignal
    trend: TrendInfo | None = None
    zones: list[Zone] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)


def _wait(
    request: MarketRequest,
    reason: str,
    trend: TrendInfo | None = None,
    zones: list[Zone] | None = None,
) -> TradeSignal:
    return TradeSignal(
        action=Action.WAIT,
        symbol=request.symbol,
        timeframe=request.timeframe,
        reason=reason,
        trend=trend.direction if trend else None,
        zones=zones or [],
    )


def _round(request: MarketRequest, value: float) -> float:
    digits = max(0, min(request.digits, 8))
    return round(value, digits)


def _evaluate_direction(
    request: MarketRequest,
    trend: TrendInfo,
    zones: list[Zone],
    blocks: list[Zone],
    fvgs: list[Zone],
    last: Candle,
    buffer: float,
    bullish: bool,
) -> tuple[TradeSignal, list[str]]:
    label = "bullish" if bullish else "bearish"
    conditions = [f"Trend {trend.direction.value.lower()} (strength {trend.strength:.2f})"]

    block = latest_zone_of(blocks, bullish)
    if block is None:
        conditions.append(f"No unmitigated {label} Order Block")
        return _wait(request, f"No {label} Order Block found", trend, zones), conditions

    if not candle_touched_zone(last, block):
        conditions.append(f"Price has not retraced into the {label} Order Block")
        return _wait(request, f"Waiting for a pullback into the {label} Order Block", trend, zones), conditions

    conditions.append(
        f"Price retraced into {label} Order Block {block.bottom:.5f}-{block.top:.5f}"
    )

    if not has_directional_fvg(fvgs, bullish, overlap=block):
        conditions.append(f"No {label} Fair Value Gap overlapping the Order Block")
        return _wait(request, f"No {label} Fair Value Gap confirms the zone", trend, zones), conditions

    conditions.append(f"{label.capitalize()} Fair Value Gap present in the zone")

    if not is_confirmation_candle(last, bullish):
        conditions.append("No confirmation candle yet")
        return _wait(request, "Waiting for a confirmation candle", trend, zones), conditions

    conditions.append("Confirmation candle closed strong")

    entry = last.close
    if bullish:
        stop = min(block.bottom, last.low) - buffer
    else:
        stop = max(block.top, last.high) + buffer

    risk = abs(entry - stop)
    if risk <= 0:
        conditions.append("Invalid stop distance")
        return _wait(request, "Could not derive a valid stop distance", trend, zones), conditions

    target = structural_target(zones, entry, bullish)
    if target is None:
        target = entry + risk * DEFAULT_RR if bullish else entry - risk * DEFAULT_RR

    reward = abs(target - entry)
    risk_reward = reward / risk
    if risk_reward < settings.min_risk_reward:
        conditions.append(
            f"Risk/reward {risk_reward:.2f} below minimum {settings.min_risk_reward:.2f}"
        )
        return _wait(request, "Structural target gives insufficient risk/reward", trend, zones), conditions

    conditions.append(f"Risk/reward {risk_reward:.2f} meets the minimum")

    signal = TradeSignal(
        action=Action.BUY if bullish else Action.SELL,
        symbol=request.symbol,
        timeframe=request.timeframe,
        entry=_round(request, entry),
        stop_loss=_round(request, stop),
        take_profit=_round(request, target),
        risk_reward=round(risk_reward, 2),
        risk_percent=settings.effective_risk_percent,
        reason="; ".join(conditions),
        trend=trend.direction,
        zones=[block],
    )
    return signal, conditions


def analyze_market(request: MarketRequest) -> AnalysisResult:
    """Run the full analysis pipeline for one EA payload."""
    candles = request.candles
    if len(candles) < settings.min_candles_required:
        reason = (
            f"Not enough candles ({len(candles)} of {settings.min_candles_required} required)"
        )
        return AnalysisResult(
            signal=_wait(request, reason), conditions=[reason]
        )

    trend = detect_trend(candles)
    fvgs = detect_fvgs(candles)
    blocks = detect_order_blocks(candles)
    zones = blocks + fvgs

    last = candles[-1]
    atr_value = atr(candles, ATR_PERIOD) or last.candle_range or last.close * FALLBACK_RANGE_FRACTION
    buffer = atr_value * STOP_BUFFER_ATR

    if trend.direction is TrendDirection.UP:
        signal, conditions = _evaluate_direction(
            request, trend, zones, blocks, fvgs, last, buffer, bullish=True
        )
    elif trend.direction is TrendDirection.DOWN:
        signal, conditions = _evaluate_direction(
            request, trend, zones, blocks, fvgs, last, buffer, bullish=False
        )
    else:
        reason = "No clear trend - market is ranging"
        signal = _wait(request, reason, trend, zones)
        conditions = [reason]

    return AnalysisResult(signal=signal, trend=trend, zones=zones, conditions=conditions)
