"""Reusable market-condition checks used by the strategy engine.

Kept separate from :mod:`strategy` so each rule is small, pure and unit-testable.
"""

from __future__ import annotations

from .indicators import body_ratio
from .models import Candle, Zone

# A confirmation candle must close with a body covering this share of its range.
CONFIRMATION_BODY_RATIO = 0.5


def is_confirmation_candle(candle: Candle, bullish: bool) -> bool:
    """Strong directional candle closing near its extreme."""
    if bullish:
        return candle.is_bullish and body_ratio(candle) >= CONFIRMATION_BODY_RATIO
    return candle.is_bearish and body_ratio(candle) >= CONFIRMATION_BODY_RATIO


def candle_touched_zone(candle: Candle, zone: Zone) -> bool:
    """True when the candle's range intersects the zone."""
    return candle.low <= zone.top and candle.high >= zone.bottom


def latest_zone_of(zones: list[Zone], bullish: bool) -> Zone | None:
    """Most recently formed zone in the requested direction."""
    matching = [zone for zone in zones if zone.bullish is bullish]
    if not matching:
        return None
    return max(matching, key=lambda zone: zone.formed_index)


def has_directional_fvg(zones: list[Zone], bullish: bool, overlap: Zone | None = None) -> bool:
    """Whether an FVG exists in the direction, optionally overlapping a zone."""
    for zone in zones:
        if zone.bullish is not bullish:
            continue
        if overlap is None or zone.overlaps(overlap.bottom, overlap.top):
            return True
    return False


def structural_target(zones: list[Zone], entry: float, bullish: bool) -> float | None:
    """Nearest opposing zone boundary to use as a take-profit target."""
    if bullish:
        candidates = [zone.bottom for zone in zones if not zone.bullish and zone.bottom > entry]
        return min(candidates) if candidates else None
    candidates = [zone.top for zone in zones if zone.bullish and zone.top < entry]
    return max(candidates) if candidates else None
