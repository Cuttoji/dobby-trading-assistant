"""Pure-python technical indicators used by the analysis layer.

Kept dependency-free (no pandas/numpy) so the strategy code stays fast and
trivially testable. All series functions return lists aligned 1:1 with the
input so an index always refers to the same candle.
"""

from __future__ import annotations

from .models import Candle


def sma(values: list[float], period: int) -> list[float | None]:
    """Simple moving average aligned with ``values`` (None during warmup)."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema_series(values: list[float], period: int) -> list[float | None]:
    """Exponential moving average aligned with ``values`` (None during warmup)."""
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(values)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    multiplier = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    for i in range(period, n):
        previous = out[i - 1]
        assert previous is not None
        out[i] = values[i] * multiplier + previous * (1.0 - multiplier)
    return out


def true_ranges(candles: list[Candle]) -> list[float]:
    ranges: list[float] = []
    for i, candle in enumerate(candles):
        if i == 0:
            ranges.append(candle.high - candle.low)
            continue
        previous_close = candles[i - 1].close
        ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    return ranges


def atr(candles: list[Candle], period: int) -> float | None:
    """Average true range over the most recent ``period`` candles."""
    if period <= 0 or len(candles) < period:
        return None
    ranges = true_ranges(candles[-period:])
    return sum(ranges) / period


def body_ratio(candle: Candle) -> float:
    """Body size relative to the full candle range (0..1)."""
    if candle.candle_range <= 0:
        return 0.0
    return candle.body / candle.candle_range


def find_swing_highs(candles: list[Candle], lookback: int) -> list[int]:
    """Indices whose high is the local maximum within +/- ``lookback``."""
    highs: list[int] = []
    for i in range(lookback, len(candles) - lookback):
        center = candles[i].high
        window = candles[i - lookback : i + lookback + 1]
        if center >= max(c.high for c in window):
            highs.append(i)
    return highs


def find_swing_lows(candles: list[Candle], lookback: int) -> list[int]:
    """Indices whose low is the local minimum within +/- ``lookback``."""
    lows: list[int] = []
    for i in range(lookback, len(candles) - lookback):
        center = candles[i].low
        window = candles[i - lookback : i + lookback + 1]
        if center <= min(c.low for c in window):
            lows.append(i)
    return lows


def highest_high(candles: list[Candle], start: int, end: int) -> float:
    return max(c.high for c in candles[start:end])


def lowest_low(candles: list[Candle], start: int, end: int) -> float:
    return min(c.low for c in candles[start:end])
