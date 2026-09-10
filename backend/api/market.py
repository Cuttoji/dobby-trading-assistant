"""Market analysis endpoint used by the MT5 EA."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..models import AnalysisResponse, MarketRequest
from ..trading_service import TradingService
from .deps import get_trading_service

router = APIRouter(tags=["market"])


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_market(
    request: MarketRequest,
    service: TradingService = Depends(get_trading_service),
) -> AnalysisResponse:
    """Analyse a candle batch and return the signal plus the risk decision."""
    return service.analyze(request)
