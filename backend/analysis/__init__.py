"""Market-structure analysis: trend, Fair Value Gaps, Order Blocks."""

from .fvg import detect_fvgs, latest_zone
from .order_block import detect_order_blocks
from .trend import detect_trend

__all__ = ["detect_trend", "detect_fvgs", "detect_order_blocks", "latest_zone"]
