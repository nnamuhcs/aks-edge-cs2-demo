from app.config import settings
from app.providers.base import MarketDataProvider
from app.providers.http_provider import HttpMarketDataProvider
from app.providers.mock_provider import MockMarketDataProvider
from app.providers.steam_provider import SteamMarketDataProvider


def build_provider() -> MarketDataProvider:
    if settings.provider_name == "http":
        return HttpMarketDataProvider()
    if settings.provider_name == "mock":
        return MockMarketDataProvider()
    if settings.provider_name == "steam":
        return SteamMarketDataProvider()
    return MockMarketDataProvider()
