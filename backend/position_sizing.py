"""Position sizing from account risk budget and stop distance.

Assumes a standard forex contract where ``contract_size`` units of the quote
currency are moved per 1.0 price unit, so the loss for one lot equals
``stop_distance * contract_size`` expressed in the account currency. This is
correct for USD-quoted pairs (EURUSD, GBPUSD, ...) and is a deliberate,
documented simplification for others.
"""

from __future__ import annotations

from .config import settings
from .models import RiskDecision

MIN_LOT = 0.01
LOT_STEP = 0.01
MAX_LOT = 100.0


def round_lots(lots: float) -> float:
    """Snap lots to the broker step (0.01) and clamp to sane bounds."""
    stepped = round(round(lots / LOT_STEP) * LOT_STEP, 2)
    return max(MIN_LOT, min(stepped, MAX_LOT))


def position_size(
    balance: float,
    risk_percent: float,
    entry: float,
    stop_loss: float,
    contract_size: float | None = None,
) -> RiskDecision:
    """Return the lot size that risks ``risk_percent`` of ``balance``.

    A blocked decision (``allowed=False``) is returned when the inputs are
    invalid or when even the minimum lot would breach the risk ceiling.
    """
    contract_size = contract_size or settings.contract_size
    risk_amount = balance * risk_percent / 100.0
    distance = abs(entry - stop_loss)

    if balance <= 0 or risk_amount <= 0 or distance <= 0:
        return RiskDecision(
            allowed=False,
            reason="Invalid balance, risk amount or stop distance",
            risk_percent=risk_percent,
        )

    loss_per_lot = distance * contract_size
    lots = round_lots(risk_amount / loss_per_lot)
    actual_risk_amount = lots * loss_per_lot
    actual_percent = actual_risk_amount / balance * 100.0

    if actual_percent > settings.max_risk_per_trade_percent:
        return RiskDecision(
            allowed=False,
            reason=(
                f"Minimum lot risk {actual_percent:.2f}% exceeds the "
                f"{settings.max_risk_per_trade_percent:.2f}% ceiling"
            ),
            lots=lots,
            risk_amount=round(actual_risk_amount, 2),
            risk_percent=round(actual_percent, 4),
        )

    return RiskDecision(
        allowed=True,
        reason="Position size within risk budget",
        lots=lots,
        risk_amount=round(actual_risk_amount, 2),
        risk_percent=round(actual_percent, 4),
    )
