from datetime import date, datetime, timedelta
import json
import re
import time
import urllib.parse
from typing import Optional

import httpx

from app.config import settings
from app.providers.base import MarketDataProvider, SkinMarketTick
from app.providers.catalog import CS2_SKIN_CATALOG


class SteamMarketDataProvider(MarketDataProvider):
    supports_historical = True

    def __init__(self) -> None:
        self.base_url = "https://steamcommunity.com/market/priceoverview/"
        self.listing_base_url = "https://steamcommunity.com/market/listings/730/"
        self.currency = settings.steam_currency
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "application/json",
            "Referer": "https://steamcommunity.com/market/",
        }
        self._icon_cache: dict[str, str] = {}

    @staticmethod
    def _parse_price(price_text: str) -> float:
        # Keep digits and separators, then normalize to decimal point.
        cleaned = re.sub(r"[^0-9,\.]+", "", price_text)
        if cleaned.count(",") > 0 and cleaned.count(".") > 0:
            cleaned = cleaned.replace(",", "")
        elif cleaned.count(",") > 0 and cleaned.count(".") == 0:
            cleaned = cleaned.replace(",", ".")
        return float(cleaned)

    @staticmethod
    def _parse_volume(volume_text: str) -> int:
        digits = re.sub(r"[^0-9]", "", volume_text)
        return int(digits) if digits else 0

    def fetch_daily_ticks(self, for_date: date) -> list[SkinMarketTick]:
        ticks: list[SkinMarketTick] = []
        snapshot_date = for_date

        with httpx.Client(timeout=20.0, headers=self.headers) as client:
            for skin in CS2_SKIN_CATALOG:
                params = {
                    "appid": 730,
                    "currency": self.currency,
                    "market_hash_name": skin["name"],
                }
                resp = client.get(self.base_url, params=params)
                if resp.status_code != 200:
                    continue
                payload = resp.json()
                if not payload.get("success"):
                    continue

                lowest_price = payload.get("lowest_price") or payload.get("median_price")
                if not lowest_price:
                    continue

                try:
                    price = self._parse_price(lowest_price)
                except ValueError:
                    continue

                volume = self._parse_volume(payload.get("volume", "0"))
                ticks.append(
                    SkinMarketTick(
                        name=skin["name"],
                        rarity=skin["rarity"],
                        category=skin["category"],
                        snapshot_date=snapshot_date,
                        price_usd=round(price, 2),
                        volume_24h=volume,
                        source="steam_priceoverview",
                        source_ref=(
                            "https://steamcommunity.com/market/priceoverview/?"
                            f"appid=730&currency={self.currency}&market_hash_name={urllib.parse.quote(skin['name'])}"
                        ),
                    )
                )
                time.sleep(0.12)

        if not ticks:
            raise RuntimeError("Steam provider returned no market ticks")

        return ticks

    @staticmethod
    def _parse_history_date(raw_date: str) -> date:
        # Steam date example: "Feb 21 2014 01: +0"
        date_part = " ".join(raw_date.split(" ")[:3])
        return datetime.strptime(date_part, "%b %d %Y").date()

    def fetch_history_ticks(self, days: int) -> list[SkinMarketTick]:
        cutoff = date.today() - timedelta(days=max(1, days) - 1)
        ticks: list[SkinMarketTick] = []

        with httpx.Client(timeout=25.0, headers=self.headers) as client:
            for skin in CS2_SKIN_CATALOG:
                encoded_name = urllib.parse.quote(skin["name"], safe="")
                url = f"{self.listing_base_url}{encoded_name}"
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                html = resp.text

                match = re.search(r"var line1=(\[[\s\S]*?\]);", html)
                if not match:
                    continue

                try:
                    history_points = json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

                latest_by_date: dict[date, tuple[float, int]] = {}
                for point in history_points:
                    if not isinstance(point, list) or len(point) < 3:
                        continue
                    try:
                        point_date = self._parse_history_date(str(point[0]))
                        if point_date < cutoff:
                            continue
                        point_price = float(point[1])
                        point_volume = self._parse_volume(str(point[2]))
                    except (ValueError, TypeError):
                        continue

                    latest_by_date[point_date] = (point_price, point_volume)

                for point_date, (point_price, point_volume) in sorted(latest_by_date.items()):
                    ticks.append(
                        SkinMarketTick(
                            name=skin["name"],
                            rarity=skin["rarity"],
                            category=skin["category"],
                            snapshot_date=point_date,
                            price_usd=round(point_price, 2),
                            volume_24h=point_volume,
                            source="steam_listing_line1",
                            source_ref=self.build_listing_url(skin["name"]),
                        )
                    )
                time.sleep(0.15)

        return ticks

    def build_listing_url(self, skin_name: str) -> str:
        encoded_name = urllib.parse.quote(skin_name, safe="")
        return f"{self.listing_base_url}{encoded_name}"

    def resolve_skin_image_url(self, skin_name: str) -> Optional[str]:
        if skin_name in self._icon_cache:
            return self._icon_cache[skin_name]

        with httpx.Client(timeout=20.0, headers=self.headers) as client:
            encoded_name = urllib.parse.quote(skin_name, safe="")
            render_url = (
                f"{self.listing_base_url}{encoded_name}/render/"
                "?query=&start=0&count=1&search_descriptions=0&sort_column=popular&sort_dir=desc"
                f"&currency={self.currency}&format=json"
            )
            resp = client.get(render_url)
            if resp.status_code != 200:
                return None
            payload = resp.json()
            assets = payload.get("assets", {})
            icon_url = None
            for app_assets in assets.values():
                for context_assets in app_assets.values():
                    for _, item in context_assets.items():
                        icon_url = item.get("icon_url")
                        if icon_url:
                            break
                    if icon_url:
                        break
                if icon_url:
                    break

            if not icon_url:
                listing_page = client.get(self.build_listing_url(skin_name))
                if listing_page.status_code == 200:
                    match = re.search(r'property="og:image" content="([^"]+)"', listing_page.text)
                    if match:
                        full_url = match.group(1)
                        self._icon_cache[skin_name] = full_url
                        return full_url
                return None

            full_url = f"https://community.fastly.steamstatic.com/economy/image/{icon_url}/128fx128f"
            self._icon_cache[skin_name] = full_url
            return full_url
