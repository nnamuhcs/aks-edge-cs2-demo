from datetime import date
import os

import httpx

from app.providers.base import MarketDataProvider, SkinMarketTick


class HttpMarketDataProvider(MarketDataProvider):
    def __init__(self) -> None:
        self.base_url = os.getenv("MARKET_API_URL", "")
        self.api_key = os.getenv("MARKET_API_KEY", "")

    def fetch_daily_ticks(self, for_date: date) -> list[SkinMarketTick]:
        if not self.base_url:
            raise ValueError("MARKET_API_URL is required when PROVIDER_NAME=http")

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(self.base_url, params={"date": for_date.isoformat()}, headers=headers)
            resp.raise_for_status()
            payload = resp.json()

        ticks: list[SkinMarketTick] = []
        for item in payload.get("skins", []):
            ticks.append(
                SkinMarketTick(
                    name=item["name"],
                    rarity=item.get("rarity", "Unknown"),
                    category=item.get("category", "Unknown"),
                    snapshot_date=for_date,
                    price_usd=float(item["price_usd"]),
                    volume_24h=int(item.get("volume_24h", 0)),
                )
            )
        return ticks
