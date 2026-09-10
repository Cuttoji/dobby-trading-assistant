"""Order Block (OB) detection.

An Order Block is the last opposite-direction candle before an impulsive,
displacement move that breaks away from it. Institutional-flow traders treat
that candle's range as an area where resting orders may still sit.

* Bullish OB -> last bearish candle before a strong bullish displacement.
* Bearish OB -> last bullish candle before a strong bearish displacement.
"""

from __future__ import annotations

from ..config import settings
from ..models import Candle, Zone, ZoneKind

# Displacement must be at least this multiple of the average candle body.
DEFAULT_IMPULSE_MULTIPLIER = 1.5


def _average_body(candles: list[Candle]) -> float:
    bodies = [candle.body for candle in candles if candle.body > 0]
    if not bodies:
        return 0.0
    return sum(bodies) / len(bodies)


def _is_mitigated(candles: list[Candle], zone: Zone) -> bool:
    """True once price has traded back into the zone after it formed."""
    for candle in candles[zone.formed_index + 1 :]:
        if zone.bullish and candle.low <= zone.top:
            return True
        if not zone.bullish and candle.high >= zone.bottom:
            return True
    return False


def _build_zone(candles: list[Candle], index: int, bullish: bool) -> Zone:
    candle = candles[index]
    zone = Zone(
        kind=ZoneKind.ORDER_BLOCK,
        bullish=bullish,
        top=round(candle.high, 6),
        bottom=round(candle.low, 6),
        formed_index=index,
        formed_at=candle.timestamp,
    )
    zone.mitigated = _is_mitigated(candles, zone)
    return zone


def detect_order_blocks(
    candles: list[Candle],
    lookback: int | None = None,
    impulse_multiplier: float = DEFAULT_IMPULSE_MULTIPLIER,
    include_mitigated: bool = False,
) -> list[Zone]:
    """Return Order Blocks found in the last ``lookback`` candles (oldest first)."""
    lookback = lookback or settings.order_block_lookback
    reference = _average_body(candles)
    threshold = reference * impulse_multiplier

    zones: list[Zone] = []
    start = max(1, len(candles) - lookback)

    for index in range(start, len(candles) - 1):
        candle = candles[index]
        impulse = candles[index + 1]

        # Bullish OB: down candle followed by a bullish displacement.
        if candle.is_bearish and impulse.is_bullish and impulse.close > candle.high:
            if impulse.body >= threshold and impulse.body > 0:
                zones.append(_build_zone(candles, index, True))

        # Bearish OB: up candle followed by a bearish displacement.
        elif candle.is_bullish and impulse.is_bearish and impulse.close < candle.low:
            if impulse.body >= threshold and impulse.body > 0:
                zones.append(_build_zone(candles, index, False))

    if include_mitigated:
        return zones
    return [zone for zone in zones if not zone.mitigated]
