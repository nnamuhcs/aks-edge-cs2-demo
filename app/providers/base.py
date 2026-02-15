from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class SkinMarketTick:
    name: str
    rarity: str
    category: str
    snapshot_date: date
    price_usd: float
    volume_24h: int
    source: str = "unknown"
    source_ref: Optional[str] = None


class MarketDataProvider:
    supports_historical = True

    def fetch_daily_ticks(self, for_date: date) -> list[SkinMarketTick]:
        raise NotImplementedError

    def fetch_history_ticks(self, days: int) -> list[SkinMarketTick]:
        return []

    def resolve_skin_image_url(self, skin_name: str) -> Optional[str]:
        return None

    def build_listing_url(self, skin_name: str) -> Optional[str]:
        return None
