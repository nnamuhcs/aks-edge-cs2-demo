from dataclasses import dataclass
from math import sqrt
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PriceSnapshot, Skin
from app.providers.catalog import CS2_SKIN_CATALOG


@dataclass
class Recommendation:
    skin_id: int
    skin_name: str
    skin_image_url: Optional[str]
    listing_url: Optional[str]
    thesis: Optional[str]
    score: float
    confidence: float
    latest_price_usd: float
    momentum_7d_pct: float
    volatility_7d_pct: float
    liquidity_score: float
    rank: int
    total_candidates: int
    reason: str


def _volatility(prices: list[float]) -> float:
    if len(prices) < 2:
        return 0.0
    mean = sum(prices) / len(prices)
    if mean == 0:
        return 0.0
    variance = sum((p - mean) ** 2 for p in prices) / len(prices)
    return (sqrt(variance) / mean) * 100


def _mean_reversion_signal(prices: list[float]) -> float:
    if len(prices) < 2:
        return 0.0
    mean = sum(prices) / len(prices)
    variance = sum((p - mean) ** 2 for p in prices) / len(prices)
    std = sqrt(variance)
    if std == 0:
        return 0.0
    z = (prices[-1] - mean) / std
    return max(-100.0, min(100.0, -z * 10.0))


def build_recommendations(db: Session, limit: int = 5) -> list[Recommendation]:
    tracked_names = {item["name"] for item in CS2_SKIN_CATALOG}
    skins = db.scalars(select(Skin).where(Skin.name.in_(tracked_names))).all()
    recs: list[Recommendation] = []
    snapshot_count_by_skin: dict[int, int] = {}
    rarity_bonus_map = {
        "Consumer": 2.0,
        "Industrial": 3.0,
        "Mil-Spec": 4.0,
        "Restricted": 5.5,
        "Classified": 7.0,
        "Covert": 8.5,
        "Contraband": 10.0,
    }

    for skin in skins:
        snapshot_count_by_skin[skin.id] = int(
            db.scalar(select(func.count()).select_from(PriceSnapshot).where(PriceSnapshot.skin_id == skin.id)) or 0
        )

    min_required = 7 if any(v >= 7 for v in snapshot_count_by_skin.values()) else 1

    for skin in skins:
        snapshots = db.scalars(
            select(PriceSnapshot)
            .where(PriceSnapshot.skin_id == skin.id)
            .order_by(PriceSnapshot.snapshot_date.desc())
            .limit(14)
        ).all()
        if len(snapshots) < min_required:
            continue

        latest = snapshots[0]
        window = list(reversed(snapshots[: min(8, len(snapshots))]))
        prices = [s.price_usd for s in window]

        first = prices[0]
        last = prices[-1]
        momentum = ((last - first) / first) * 100 if first else 0.0
        vol = _volatility(prices)
        avg_volume = sum(s.volume_24h for s in window) / len(window)
        liquidity = min(100.0, avg_volume / 7)
        mean_reversion = _mean_reversion_signal(prices)
        rarity_bonus = rarity_bonus_map.get(skin.rarity, 5.0)

        # Weighted composite model: momentum + risk + liquidity + mean reversion + rarity.
        score = (
            (momentum * 0.45)
            + ((100 - min(vol, 100)) * 0.20)
            + (liquidity * 0.20)
            + (mean_reversion * 0.10)
            + (rarity_bonus * 0.05)
        )
        confidence = max(0.1, min(0.99, (len(window) / 10) * (1 - min(vol, 100) / 100)))

        recs.append(
            Recommendation(
                skin_id=skin.id,
                skin_name=skin.name,
                skin_image_url=skin.image_url,
                listing_url=skin.listing_url,
                thesis=skin.thesis,
                score=round(score, 2),
                confidence=round(confidence, 2),
                latest_price_usd=latest.price_usd,
                momentum_7d_pct=round(momentum, 2),
                volatility_7d_pct=round(vol, 2),
                liquidity_score=round(liquidity, 2),
                rank=0,
                total_candidates=0,
                reason="",
            )
        )

    recs.sort(key=lambda x: x.score, reverse=True)
    total = len(recs)
    for idx, rec in enumerate(recs, start=1):
        rec.rank = idx
        rec.total_candidates = total
        momentum_note = "strong momentum" if rec.momentum_7d_pct >= 0 else "negative momentum"
        volatility_note = "controlled volatility" if rec.volatility_7d_pct <= 8 else "elevated volatility"
        liquidity_note = "high liquidity" if rec.liquidity_score >= 50 else "lower liquidity"
        rec.reason = (
            f"Rank #{idx}/{total}: {momentum_note}, {volatility_note}, and {liquidity_note}. "
            f"Composite includes momentum, mean-reversion, and risk controls; non-top skins have weaker balance."
        )

    return recs[:limit]
