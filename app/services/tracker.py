from datetime import date, timedelta
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.providers.base import SkinMarketTick
from app.providers.catalog import CS2_SKIN_CATALOG
from app.models import PriceSnapshot, Skin
from app.services.provider_factory import build_provider

CATALOG_BY_NAME = {item["name"]: item for item in CS2_SKIN_CATALOG}
logger = logging.getLogger(__name__)


def _upsert_ticks(db: Session, ticks: list[SkinMarketTick]) -> int:
    provider = build_provider()
    created = 0
    for tick in ticks:
        catalog_item = CATALOG_BY_NAME.get(tick.name, {})
        skin = db.scalar(select(Skin).where(Skin.name == tick.name))
        if not skin:
            skin = Skin(
                name=tick.name,
                rarity=tick.rarity,
                category=tick.category,
                listing_url=provider.build_listing_url(tick.name),
                image_url=provider.resolve_skin_image_url(tick.name),
                thesis=catalog_item.get("thesis"),
            )
            db.add(skin)
            db.flush()
        else:
            updated = False
            if not skin.listing_url:
                skin.listing_url = provider.build_listing_url(tick.name)
                updated = True
            if not skin.image_url:
                skin.image_url = provider.resolve_skin_image_url(tick.name)
                updated = True
            if not skin.thesis and catalog_item.get("thesis"):
                skin.thesis = catalog_item["thesis"]
                updated = True
            if updated:
                db.add(skin)

        exists = db.scalar(
            select(PriceSnapshot).where(
                PriceSnapshot.skin_id == skin.id,
                PriceSnapshot.snapshot_date == tick.snapshot_date,
            )
        )
        if exists:
            if (not exists.source or exists.source == "unknown") and tick.source != "unknown":
                exists.source = tick.source
                exists.source_ref = tick.source_ref
                exists.price_usd = tick.price_usd
                exists.volume_24h = tick.volume_24h
                db.add(exists)
            continue

        db.add(
            PriceSnapshot(
                skin_id=skin.id,
                snapshot_date=tick.snapshot_date,
                price_usd=tick.price_usd,
                volume_24h=tick.volume_24h,
                source=tick.source,
                source_ref=tick.source_ref,
            )
        )
        created += 1

    db.commit()
    return created


def ingest_ticks(db: Session, ticks: list[SkinMarketTick]) -> int:
    return _upsert_ticks(db, ticks)


def track_prices_for_date(db: Session, run_date: date) -> int:
    provider = build_provider()
    try:
        ticks = provider.fetch_daily_ticks(run_date)
    except Exception as exc:
        logger.warning("daily tick fetch failed for %s: %s", run_date.isoformat(), exc)
        return 0
    return ingest_ticks(db, ticks)


def backfill_history(db: Session, days: int) -> int:
    provider = build_provider()
    if not provider.supports_historical:
        return 0

    try:
        ticks = provider.fetch_history_ticks(days)
    except Exception as exc:
        logger.warning("historical backfill fetch failed for %s days: %s", days, exc)
        return 0
    if not ticks:
        return 0
    return ingest_ticks(db, ticks)


def backfill_seed_data(db: Session, days: int) -> None:
    from app.config import settings

    if days <= 0:
        return

    provider = build_provider()
    existing_days = db.scalar(select(func.count(func.distinct(PriceSnapshot.snapshot_date))))
    existing_days = int(existing_days or 0)

    if existing_days >= days:
        return

    if provider.supports_historical:
        created = backfill_history(db, days)
        if created > 0:
            return

    if existing_days > 0:
        return

    # For providers like Steam, avoid N daily remote calls on startup.
    # Seed only with today's snapshot when historical fetch is unavailable.
    if provider.supports_historical:
        track_prices_for_date(db, date.today())
        return

    today = date.today()
    start = today - timedelta(days=settings.tracker_seed_days - 1)
    for i in range(days):
        track_prices_for_date(db, start + timedelta(days=i))


def ensure_tracked_universe(db: Session, enrich_images: bool = False) -> int:
    provider = build_provider()
    created = 0
    updated = 0
    for item in CS2_SKIN_CATALOG:
        skin = db.scalar(select(Skin).where(Skin.name == item["name"]))
        if not skin:
            image_url = provider.resolve_skin_image_url(item["name"]) if enrich_images else None
            skin = Skin(
                name=item["name"],
                rarity=item["rarity"],
                category=item["category"],
                thesis=item.get("thesis"),
                listing_url=provider.build_listing_url(item["name"]),
                image_url=image_url,
            )
            db.add(skin)
            created += 1
            continue

        changed = False
        if not skin.rarity:
            skin.rarity = item["rarity"]
            changed = True
        if not skin.category:
            skin.category = item["category"]
            changed = True
        if not skin.thesis and item.get("thesis"):
            skin.thesis = item.get("thesis")
            changed = True
        if not skin.listing_url:
            skin.listing_url = provider.build_listing_url(item["name"])
            changed = True
        if enrich_images and not skin.image_url:
            skin.image_url = provider.resolve_skin_image_url(item["name"])
            changed = True
        if changed:
            db.add(skin)
            updated += 1

    db.commit()
    return created + updated
