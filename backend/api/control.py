"""Trading-control endpoints: state, mode, pause and the kill switch."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..database import Database, get_database
from ..models import MessageResponse, ModeRequest, ReasonRequest, SystemState
from ..risk_manager import RiskManager
from ..system_state import SystemStateStore
from .deps import get_risk_manager, get_state_store

router = APIRouter(tags=["control"])


def _latest_balance(db: Database) -> float:
    curve = db.get_equity_curve(limit=1)
    if curve:
        return float(curve[-1]["balance"])
    return settings.initial_balance


def _build_state(risk: RiskManager, db: Database) -> SystemState:
    balance = _latest_balance(db)
    open_orders = db.get_open_trade_count()
    return risk.state(balance, open_orders)


@router.get("/state", response_model=SystemState)
def read_state(
    store: SystemStateStore = Depends(get_state_store),
    risk: RiskManager = Depends(get_risk_manager),
    db: Database = Depends(get_database),
) -> SystemState:
    """Current mode, kill-switch/pause flags and whether trading is allowed."""
    return _build_state(risk, db)


@router.post("/mode", response_model=MessageResponse)
def set_mode(
    payload: ModeRequest,
    db: Database = Depends(get_database),
) -> MessageResponse:
    try:
        mode = SystemStateStore(db).set_mode(payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(ok=True, message=f"Trading mode set to {mode.value}")


@router.post("/pause", response_model=MessageResponse)
def pause(
    payload: ReasonRequest | None = None,
    db: Database = Depends(get_database),
) -> MessageResponse:
    reason = (payload.reason if payload else "") or "Paused by operator"
    SystemStateStore(db).pause(reason)
    return MessageResponse(ok=True, message="Trading paused", detail=reason)


@router.post("/resume", response_model=MessageResponse)
def resume(db: Database = Depends(get_database)) -> MessageResponse:
    SystemStateStore(db).resume()
    return MessageResponse(ok=True, message="Trading resumed")


@router.post("/kill-switch", response_model=MessageResponse)
def engage_kill_switch(
    payload: ReasonRequest | None = None,
    db: Database = Depends(get_database),
) -> MessageResponse:
    reason = (payload.reason if payload else "") or "Manual emergency stop"
    SystemStateStore(db).engage_kill_switch(reason)
    return MessageResponse(ok=True, message="Kill switch engaged", detail=reason)


@router.post("/reset-kill-switch", response_model=MessageResponse)
def reset_kill_switch(db: Database = Depends(get_database)) -> MessageResponse:
    SystemStateStore(db).release_kill_switch()
    return MessageResponse(ok=True, message="Kill switch released - review before trading")


@router.post("/emergency-stop", response_model=MessageResponse)
def emergency_stop(
    payload: ReasonRequest | None = None,
    db: Database = Depends(get_database),
) -> MessageResponse:
    """Engage the kill switch and pause. The EA reacts by closing positions."""
    reason = (payload.reason if payload else "") or "Emergency stop requested"
    store = SystemStateStore(db)
    store.engage_kill_switch(reason)
    store.pause(reason)
    return MessageResponse(
        ok=True,
        message="Emergency stop engaged: kill switch on, trading paused, EA told to close all",
        detail=reason,
    )
