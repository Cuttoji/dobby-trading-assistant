"""FastAPI entry point for Dobby Trade Assistant."""

from fastapi import FastAPI

from .api.control import router as control_router
from .api.market import router as market_router

app = FastAPI(
    title="Dobby Trade Assistant",
    description="Signal analysis and risk controls for MT5 demo/backtest workflows.",
    version="0.1.0",
)
app.include_router(market_router)
app.include_router(control_router, prefix="/control")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "signal-analysis"}