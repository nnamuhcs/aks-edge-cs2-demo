from datetime import date
from typing import Optional

from pydantic import BaseModel


class SkinRead(BaseModel):
    id: int
    name: str
    rarity: str
    category: str
    image_url: Optional[str] = None
    listing_url: Optional[str] = None
    thesis: Optional[str] = None

    class Config:
        from_attributes = True


class PriceSnapshotRead(BaseModel):
    skin_id: Optional[int] = None
    snapshot_date: date
    price_usd: float
    volume_24h: int
    source: Optional[str] = None
    source_ref: Optional[str] = None

    class Config:
        from_attributes = True


class RecommendationRead(BaseModel):
    skin_id: int
    skin_name: str
    skin_image_url: Optional[str] = None
    listing_url: Optional[str] = None
    thesis: Optional[str] = None
    score: float
    confidence: float
    latest_price_usd: float
    momentum_7d_pct: float
    volatility_7d_pct: float
    liquidity_score: float
    rank: int
    total_candidates: int
    reason: str


class PortfolioSimPointRead(BaseModel):
    date: date
    equity: float
    day_return_pct: float
    benchmark_equity: float


class PortfolioSimRead(BaseModel):
    initial_capital: float
    ending_capital: float
    total_return_pct: float
    benchmark_ending_capital: float
    benchmark_return_pct: float
    days_traded: int
    win_days: int
    loss_days: int
    max_drawdown_pct: float
    cagr_pct: float
    points: list[PortfolioSimPointRead]
