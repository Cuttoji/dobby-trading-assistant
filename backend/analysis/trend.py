"""Trend detection using EMA alignment confirmed by swing structure."""

from __future__ import annotations

from ..config import settings
from ..indicators import ema_series, find_swing_highs, find_swing_lows
from ..models import Candle, TrendDirection, TrendInfo

# EMA separation (as a fraction of the slow EMA) that counts as a full-strength
# trend. Below this the market is treated as a range.
FULL_STRENGTH_SEPARATION = 0.0025


def _structure_direction(candles: list[Candle], lookback: int) -> TrendDirection:
    """Higher-highs/higher-lows = UP, lower-highs/lower-lows = DOWN."""
    highs = find_swing_highs(candles, lookback)
    lows = find_swing_lows(candles, lookback)
    if len(highs) < 2 or len(lows) < 2:
        return TrendDirection.RANGE

    last_high, prev_high = candles[highs[-1]].high, candles[highs[-2]].high
    last_low, prev_low = candles[lows[-1]].low, candles[lows[-2]].low

    if last_high > prev_high and last_low > prev_low:
        return TrendDirection.UP
    if last_high < prev_high and last_low < prev_low:
        return TrendDirection.DOWN
    return TrendDirection.RANGE


def detect_trend(
    candles: list[Candle],
    fast_period: int | None = None,
    slow_period: int | None = None,
    swing_lookback: int | None = None,
) -> TrendInfo:
    """Return the prevailing trend for the supplied candles.

    The direction is driven by the fast/slow EMA relationship and only kept if
    the swing structure agrees; otherwise it degrades to RANGE.
    """
    fast_period = fast_period or settings.trend_fast_ema
    slow_period = slow_period or settings.trend_slow_ema
    swing_lookback = swing_lookback or settings.swing_lookback

    closes = [c.close for c in candles]
    if len(closes) < slow_period + 1:
        last_close = closes[-1] if closes else 0.0
        return TrendInfo(
            direction=TrendDirection.RANGE,
            strength=0.0,
            ema_fast=last_close,
            ema_slow=last_close,
            detail=f"Not enough candles for EMA{slow_period} ({len(closes)} available)",
        )

    fast_series = ema_series(closes, fast_period)
    slow_series = ema_series(closes, slow_period)
    ema_fast = fast_series[-1]
    ema_slow = slow_series[-1]
    assert ema_fast is not None and ema_slow is not None

    separation = (ema_fast - ema_slow) / ema_slow if ema_slow else 0.0
    strength = min(abs(separation) / FULL_STRENGTH_SEPARATION, 1.0)

    if separation > 0:
        ema_direction = TrendDirection.UP
    elif separation < 0:
        ema_direction = TrendDirection.DOWN
    else:
        ema_direction = TrendDirection.RANGE

    structure = _structure_direction(candles, swing_lookback)

    if ema_direction is TrendDirection.RANGE:
        direction = TrendDirection.RANGE
    elif structure in (TrendDirection.RANGE, ema_direction):
        # EMA agrees with structure, or structure is unresolved - trust the EMA.
        direction = ema_direction
    else:
        direction = TrendDirection.RANGE

    detail = (
        f"EMA{fast_period} {ema_fast:.5f} vs EMA{slow_period} {ema_slow:.5f} "
        f"(sep {separation * 100:.3f}%), structure {structure.value.lower()}"
    )
    return TrendInfo(
        direction=direction,
        strength=round(strength, 4),
        ema_fast=round(ema_fast, 6),
        ema_slow=round(ema_slow, 6),
        detail=detail,
    )
