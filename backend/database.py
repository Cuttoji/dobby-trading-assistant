"""SQLite persistence for trades, signals, AI logs and system state.

A single connection guarded by a lock is plenty for this workload (one EA and
one dashboard) and keeps the code simple and dependency-free.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .config import settings
from .models import Action, TradeRecord, TradeStatus, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    lots REAL NOT NULL,
    risk_percent REAL NOT NULL DEFAULT 0,
    profit REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'OPEN',
    reason TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'EA',
    opened_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    action TEXT NOT NULL,
    entry REAL NOT NULL DEFAULT 0,
    stop_loss REAL NOT NULL DEFAULT 0,
    take_profit REAL NOT NULL DEFAULT 0,
    risk_reward REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    accepted INTEGER NOT NULL DEFAULT 0,
    block_reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ai_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    balance REAL NOT NULL,
    equity REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_closed_at ON trades(closed_at);
"""


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Database:
    """Thin wrapper around a SQLite file with the tables used by the app."""

    def __init__(self, path: str | None = None) -> None:
        self.path = str(path or settings.database_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---------------------------------------------------------------- trades

    def insert_trade(self, record: TradeRecord) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO trades (ticket, symbol, action, entry, stop_loss,
                    take_profit, lots, risk_percent, profit, status, reason,
                    source, opened_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.ticket,
                    record.symbol,
                    record.action.value,
                    record.entry,
                    record.stop_loss,
                    record.take_profit,
                    record.lots,
                    record.risk_percent,
                    record.profit,
                    record.status.value,
                    record.reason,
                    record.source,
                    _to_iso(record.opened_at),
                    _to_iso(record.closed_at),
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def close_trade(
        self, trade_id: int | None, ticket: int | None, profit: float
    ) -> bool:
        """Close a trade by id (preferred) or broker ticket. Returns success."""
        with self._lock:
            if trade_id is not None:
                cursor = self._conn.execute(
                    "UPDATE trades SET profit = ?, status = ?, closed_at = ? WHERE id = ?",
                    (profit, TradeStatus.CLOSED.value, _to_iso(utcnow()), trade_id),
                )
            elif ticket is not None:
                cursor = self._conn.execute(
                    "UPDATE trades SET profit = ?, status = ?, closed_at = ? "
                    "WHERE ticket = ? AND status = ?",
                    (profit, TradeStatus.CLOSED.value, _to_iso(utcnow()), ticket, TradeStatus.OPEN.value),
                )
            else:
                return False
            self._conn.commit()
            return cursor.rowcount > 0

    def get_open_trades(self) -> list[TradeRecord]:
        return self._fetch_trades("WHERE status = ?", (TradeStatus.OPEN.value,))

    def get_open_trade_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM trades WHERE status = ?",
                (TradeStatus.OPEN.value,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def get_closed_trades(self) -> list[TradeRecord]:
        return self._fetch_trades(
            "WHERE status = ? ORDER BY closed_at ASC", (TradeStatus.CLOSED.value,)
        )

    def get_trades(self, limit: int = 200) -> list[TradeRecord]:
        return self._fetch_trades("ORDER BY id DESC LIMIT ?", (limit,))

    def _fetch_trades(self, clause: str, params: tuple) -> list[TradeRecord]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM trades {clause}", params
            ).fetchall()
        return [self._row_to_trade(row) for row in rows]

    @staticmethod
    def _row_to_trade(row: sqlite3.Row) -> TradeRecord:
        return TradeRecord(
            id=row["id"],
            ticket=row["ticket"],
            symbol=row["symbol"],
            action=Action(row["action"]),
            entry=row["entry"],
            stop_loss=row["stop_loss"],
            take_profit=row["take_profit"],
            lots=row["lots"],
            risk_percent=row["risk_percent"],
            profit=row["profit"],
            status=TradeStatus(row["status"]),
            reason=row["reason"],
            source=row["source"],
            opened_at=_from_iso(row["opened_at"]) or utcnow(),
            closed_at=_from_iso(row["closed_at"]),
        )

    # --------------------------------------------------------------- signals

    def record_signal(
        self,
        symbol: str,
        timeframe: str,
        action: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        risk_reward: float,
        reason: str,
        accepted: bool,
        block_reason: str = "",
    ) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO signals (created_at, symbol, timeframe, action, entry,
                    stop_loss, take_profit, risk_reward, reason, accepted, block_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _to_iso(utcnow()), symbol, timeframe, action, entry, stop_loss,
                    take_profit, risk_reward, reason, 1 if accepted else 0, block_reason,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def get_signals(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------- ai logs

    def log_ai(self, kind: str, text: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO ai_logs (created_at, kind, text) VALUES (?, ?, ?)",
                (_to_iso(utcnow()), kind, text),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def get_ai_logs(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ai_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # -------------------------------------------------------------- state

    def get_state(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM app_state WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_state(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO app_state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def dump_state(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM app_state").fetchall()
        return {row["key"]: row["value"] for row in rows}

    # ------------------------------------------------------------- equity

    def record_equity(self, balance: float, equity: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO equity_snapshots (created_at, balance, equity) VALUES (?, ?, ?)",
                (_to_iso(utcnow()), balance, equity),
            )
            self._conn.commit()

    def get_equity_curve(self, limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_database: Database | None = None
_database_lock = threading.Lock()


def get_database() -> Database:
    """Process-wide singleton database."""
    global _database
    if _database is None:
        with _database_lock:
            if _database is None:
                _database = Database()
    return _database


def reset_database(path: str | None = None) -> Database:
    """Replace the singleton (used by tests and by the CLI)."""
    global _database
    with _database_lock:
        if _database is not None:
            _database.close()
        _database = Database(path)
    return _database
