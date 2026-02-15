from pydantic import BaseModel
import os


class Settings(BaseModel):
    app_name: str = "CS2 Skin AI Intelligence"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/skins.db")
    tracker_seed_days: int = int(os.getenv("TRACKER_SEED_DAYS", "30"))
    provider_name: str = os.getenv("PROVIDER_NAME", "steam")
    track_interval_hours: int = int(os.getenv("TRACK_INTERVAL_HOURS", "24"))
    steam_currency: int = int(os.getenv("STEAM_CURRENCY", "1"))


settings = Settings()
