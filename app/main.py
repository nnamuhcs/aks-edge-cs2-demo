from datetime import date
from pathlib import Path
import urllib.parse
from typing import Union

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine, ensure_schema_columns, get_db
from app.models import PriceSnapshot, Skin
from app.providers.catalog import CS2_SKIN_CATALOG
from app.schemas import PriceSnapshotRead, RecommendationRead, SkinRead
from app.services.provider_factory import build_provider
from app.services.recommendation import build_recommendations
from app.services.tracker import (
    backfill_history,
    backfill_seed_data,
    ensure_tracked_universe,
    ingest_ticks,
    track_prices_for_date,
)

app = FastAPI(title=settings.app_name)

base_dir = Path(__file__).resolve().parent.parent
app.mount("/web", StaticFiles(directory=str(base_dir / "web")), name="web")
templates = Jinja2Templates(directory=str(base_dir / "web"))

scheduler = BackgroundScheduler(timezone="UTC")


def _listing_url(name: str) -> str:
    return f"https://steamcommunity.com/market/listings/730/{urllib.parse.quote(name, safe='')}"


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns()
    db = SessionLocal()
    try:
        ensure_tracked_universe(db, enrich_images=False)
        backfill_seed_data(db, settings.tracker_seed_days)
    finally:
        db.close()

    scheduler.add_job(_daily_track_job, "interval", hours=settings.track_interval_hours, id="daily-tracker", replace_existing=True)
    scheduler.start()


@app.on_event("shutdown")
def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _daily_track_job() -> None:
    db = SessionLocal()
    try:
        track_prices_for_date(db, date.today())
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    catalog_by_name = {item["name"]: item for item in CS2_SKIN_CATALOG}
    tracked_names = list(catalog_by_name.keys())
    recs = build_recommendations(db, limit=5)
    db_skins = db.scalars(select(Skin).where(Skin.name.in_(tracked_names))).all()
    db_skin_map = {skin.name: skin for skin in db_skins}
    tracked = []
    for name in tracked_names:
        item = catalog_by_name[name]
        skin = db_skin_map.get(name)
        tracked.append(
            {
                "id": skin.id if skin else None,
                "name": name,
                "rarity": item["rarity"],
                "category": item["category"],
                "image_url": skin.image_url if skin else None,
                "listing_url": skin.listing_url if skin and skin.listing_url else _listing_url(name),
                "thesis": item.get("thesis"),
            }
        )
    total_skins = len(tracked_names)
    total_snapshots = len(db.scalars(select(PriceSnapshot)).all())
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "recommendations": recs,
            "tracked_skins": tracked,
            "total_skins": total_skins,
            "total_snapshots": total_snapshots,
            "today": date.today().isoformat(),
        },
    )


@app.post("/track")
def manual_track(db: Session = Depends(get_db)) -> dict[str, Union[int, str]]:
    created = track_prices_for_date(db, date.today())
    return {"date": date.today().isoformat(), "created_snapshots": created}


@app.post("/backfill")
def manual_backfill(days: int = 180, db: Session = Depends(get_db)) -> dict[str, Union[int, str]]:
    days = max(7, min(730, days))
    created = backfill_history(db, days)
    return {"days": days, "created_snapshots": created}


@app.post("/maintenance/rebuild-real")
def rebuild_real_dataset(days: int = 180, db: Session = Depends(get_db)) -> dict[str, int]:
    days = max(30, min(730, days))
    provider = build_provider()
    try:
        history_ticks = provider.fetch_history_ticks(days)
    except Exception:
        return {"deleted_snapshots": 0, "historical_created": 0, "latest_created": 0}
    if not history_ticks:
        return {"deleted_snapshots": 0, "historical_created": 0, "latest_created": 0}

    tracked_names = [item["name"] for item in CS2_SKIN_CATALOG]
    tracked_ids = db.scalars(select(Skin.id).where(Skin.name.in_(tracked_names))).all()
    deleted = 0
    if tracked_ids:
        deleted = db.execute(delete(PriceSnapshot).where(PriceSnapshot.skin_id.in_(tracked_ids))).rowcount or 0
        db.commit()

    historical_created = ingest_ticks(db, history_ticks)
    latest_created = track_prices_for_date(db, date.today())
    return {
        "deleted_snapshots": int(deleted),
        "historical_created": int(historical_created),
        "latest_created": int(latest_created),
    }


@app.post("/maintenance/enrich-images")
def enrich_images(db: Session = Depends(get_db)) -> dict[str, int]:
    touched = ensure_tracked_universe(db, enrich_images=True)
    return {"updated_records": int(touched)}


@app.get("/skins", response_model=list[SkinRead])
def list_skins(db: Session = Depends(get_db)) -> list[SkinRead]:
    tracked_names = [item["name"] for item in CS2_SKIN_CATALOG]
    return db.scalars(select(Skin).where(Skin.name.in_(tracked_names)).order_by(Skin.name)).all()


@app.get("/history/{skin_id}", response_model=list[PriceSnapshotRead])
def skin_history(skin_id: int, db: Session = Depends(get_db)) -> list[PriceSnapshotRead]:
    skin = db.scalar(select(Skin).where(Skin.id == skin_id))
    if not skin:
        raise HTTPException(status_code=404, detail="Skin not found")

    return db.scalars(
        select(PriceSnapshot)
        .where(PriceSnapshot.skin_id == skin_id)
        .order_by(PriceSnapshot.snapshot_date.desc())
    ).all()


@app.get("/recommendations", response_model=list[RecommendationRead])
def recommendations(limit: int = 5, db: Session = Depends(get_db)) -> list[RecommendationRead]:
    return [RecommendationRead(**vars(r)) for r in build_recommendations(db, limit=max(1, min(20, limit)))]


@app.get("/audit/summary")
def audit_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    tracked_names = [item["name"] for item in CS2_SKIN_CATALOG]
    total_snapshots = int(db.scalar(select(func.count()).select_from(PriceSnapshot)) or 0)
    covered_skins = int(db.scalar(select(func.count()).select_from(Skin).where(Skin.name.in_(tracked_names))) or 0)
    distinct_dates = int(db.scalar(select(func.count(func.distinct(PriceSnapshot.snapshot_date)))) or 0)
    first_date = db.scalar(select(func.min(PriceSnapshot.snapshot_date)))
    last_date = db.scalar(select(func.max(PriceSnapshot.snapshot_date)))

    sources = db.execute(
        select(PriceSnapshot.source, func.count()).group_by(PriceSnapshot.source).order_by(func.count().desc())
    ).all()
    unknown_count = int(
        db.scalar(select(func.count()).select_from(PriceSnapshot).where(PriceSnapshot.source == "unknown")) or 0
    )
    verified_count = max(0, total_snapshots - unknown_count)

    return {
        "tracked_skins": len(tracked_names),
        "covered_skins": covered_skins,
        "tracked_universe_target": len(tracked_names),
        "total_snapshots": total_snapshots,
        "distinct_days": distinct_dates,
        "first_snapshot_date": str(first_date) if first_date else None,
        "last_snapshot_date": str(last_date) if last_date else None,
        "verified_snapshots": verified_count,
        "unverified_snapshots": unknown_count,
        "source_breakdown": [{"source": source, "count": int(count)} for source, count in sources],
    }


@app.get("/audit/snapshots")
def audit_snapshots(limit: int = 50, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    tracked_names = [item["name"] for item in CS2_SKIN_CATALOG]
    rows = db.execute(
        select(
            PriceSnapshot.id,
            PriceSnapshot.snapshot_date,
            PriceSnapshot.price_usd,
            PriceSnapshot.volume_24h,
            PriceSnapshot.source,
            PriceSnapshot.source_ref,
            Skin.name,
        )
        .join(Skin, Skin.id == PriceSnapshot.skin_id)
        .where(Skin.name.in_(tracked_names))
        .order_by(PriceSnapshot.snapshot_date.desc(), PriceSnapshot.id.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    return [
        {
            "snapshot_id": int(row[0]),
            "snapshot_date": str(row[1]),
            "price_usd": float(row[2]),
            "volume_24h": int(row[3]),
            "source": row[4],
            "source_ref": row[5],
            "skin_name": row[6],
        }
        for row in rows
    ]


@app.get("/audit/tracked-universe")
def audit_tracked_universe(db: Session = Depends(get_db)) -> dict[str, object]:
    catalog_by_name = {item["name"]: item for item in CS2_SKIN_CATALOG}
    tracked_names = list(catalog_by_name.keys())
    skins = db.scalars(select(Skin).where(Skin.name.in_(tracked_names))).all()
    skin_map = {skin.name: skin for skin in skins}
    return {
        "count": len(tracked_names),
        "covered_skins": len(skins),
        "target": len(tracked_names),
        "selection_criteria": (
            "Universe is a curated basket favoring high liquidity, recognizable skins, "
            "cross-weapon coverage, and investable volatility."
        ),
        "skins": [
            {
                "id": skin_map[name].id if name in skin_map else None,
                "name": name,
                "category": catalog_by_name[name]["category"],
                "rarity": catalog_by_name[name]["rarity"],
                "thesis": catalog_by_name[name].get("thesis"),
                "image_url": skin_map[name].image_url if name in skin_map else None,
                "listing_url": skin_map[name].listing_url if name in skin_map and skin_map[name].listing_url else _listing_url(name),
            }
            for name in tracked_names
        ],
    }
