"""Fair Value Gap (FVG) detection.

An FVG is a three-candle imbalance: the middle candle moves so fast that it
leaves a price range untouched by the candles on either side of it.

* Bullish FVG  -> third candle's low is above the first candle's high.
* Bearish FVG  -> third candle's high is below the first candle's low.
"""

from __future__ import annotations

from ..config import settings
from ..models import Candle, Zone, ZoneKind


def _is_fully_filled(candles: list[Candle], zone: Zone) -> bool:
    """True once later price action completely retraces the gap."""
    for candle in candles[zone.formed_index + 1 :]:
        if zone.bullish and candle.low <= zone.bottom:
            return True
        if not zone.bullish and candle.high >= zone.top:
            return True
    return False


def _build_zone(
    candles: list[Candle], index: int, bullish: bool, top: float, bottom: float
) -> Zone:
    zone = Zone(
        kind=ZoneKind.FVG,
        bullish=bullish,
        top=round(top, 6),
        bottom=round(bottom, 6),
        formed_index=index,
        formed_at=candles[index].timestamp,
    )
    zone.mitigated = _is_fully_filled(candles, zone)
    return zone


def detect_fvgs(
    candles: list[Candle],
    lookback: int | None = None,
    min_gap: float = 0.0,
    include_mitigated: bool = False,
) -> list[Zone]:
    """Return FVGs found in the last ``lookback`` candles (oldest first)."""
    lookback = lookback or settings.fvg_lookback
    zones: list[Zone] = []
    start = max(2, len(candles) - lookback)

    for index in range(start, len(candles)):
        first = candles[index - 2]
        third = candles[index]

        if third.low > first.high:
            top, bottom = third.low, first.high
            if top - bottom > min_gap:
                zones.append(_build_zone(candles, index, True, top, bottom))
        elif third.high < first.low:
            top, bottom = first.low, third.high
            if top - bottom > min_gap:
                zones.append(_build_zone(candles, index, False, top, bottom))

    if include_mitigated:
        return zones
    return [zone for zone in zones if not zone.mitigated]


def latest_zone(zones: list[Zone], bullish: bool | None = None) -> Zone | None:
    """Most recently formed zone, optionally filtered by direction."""
    candidates = [
        zone for zone in zones if bullish is None or zone.bullish is bullish
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda zone: zone.formed_index)
