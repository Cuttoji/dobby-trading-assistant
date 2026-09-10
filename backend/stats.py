"""Derived performance statistics computed from stored trades."""

from __future__ import annotations

from .models import TradeRecord, TradeStats, utcnow


def _drawdown_percent(closed: list[TradeRecord], initial_balance: float) -> float:
    """Maximum peak-to-trough drop of the equity curve, in percent."""
    if initial_balance <= 0:
        return 0.0
    equity = initial_balance
    peak = initial_balance
    max_dd = 0.0
    for trade in closed:
        equity += trade.profit
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return round(max_dd, 4)


def _consecutive_losses(closed: list[TradeRecord]) -> int:
    """Number of losing trades at the tail of the closed-trade history."""
    streak = 0
    for trade in reversed(closed):
        if trade.profit < 0:
            streak += 1
        else:
            break
    return streak


def compute_stats(
    closed_trades: list[TradeRecord],
    open_orders: int,
    initial_balance: float,
) -> TradeStats:
    """Aggregate win rate, profit, drawdown and streaks for the dashboard."""
    closed_count = len(closed_trades)
    wins = sum(1 for trade in closed_trades if trade.profit > 0)
    total_profit = sum(trade.profit for trade in closed_trades)

    today = utcnow().date()
    today_profit = sum(
        trade.profit
        for trade in closed_trades
        if trade.closed_at is not None and trade.closed_at.date() == today
    )

    return TradeStats(
        total_trades=closed_count + open_orders,
        closed_trades=closed_count,
        win_rate=round(wins / closed_count * 100.0, 2) if closed_count else 0.0,
        total_profit=round(total_profit, 2),
        today_profit=round(today_profit, 2),
        today_percent=(
            round(today_profit / initial_balance * 100.0, 4)
            if initial_balance > 0
            else 0.0
        ),
        max_drawdown_percent=_drawdown_percent(closed_trades, initial_balance),
        consecutive_losses=_consecutive_losses(closed_trades),
        open_orders=open_orders,
    )
