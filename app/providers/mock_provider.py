from datetime import date
import hashlib
import random

from app.providers.base import MarketDataProvider, SkinMarketTick
from app.providers.catalog import CS2_SKIN_CATALOG


class MockMarketDataProvider(MarketDataProvider):
    def fetch_daily_ticks(self, for_date: date) -> list[SkinMarketTick]:
        ticks: list[SkinMarketTick] = []
        ordinal = for_date.toordinal()
        for skin in CS2_SKIN_CATALOG:
            name = skin["name"]
            rarity = skin["rarity"]
            category = skin["category"]
            seed_material = f"{name}:{ordinal}".encode("utf-8")
            seed = int(hashlib.sha256(seed_material).hexdigest(), 16) % (10**8)
            rng = random.Random(seed)

            base_price = 30 + (abs(hash(name)) % 1500) / 10
            trend = (ordinal % 30 - 15) / 250
            noise = rng.uniform(-0.05, 0.05)
            rarity_boost = {"Contraband": 1.35, "Covert": 1.18, "Classified": 1.1}.get(rarity, 1.0)

            price = round(max(1.5, base_price * rarity_boost * (1 + trend + noise)), 2)
            volume = int(max(20, rng.gauss(420, 140)))
            ticks.append(
                SkinMarketTick(
                    name=name,
                    rarity=rarity,
                    category=category,
                    snapshot_date=for_date,
                    price_usd=price,
                    volume_24h=volume,
                )
            )
        return ticks
