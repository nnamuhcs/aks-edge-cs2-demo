from datetime import date
from pathlib import Path
import shutil
import subprocess
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
from app.schemas import PortfolioSimRead, PriceSnapshotRead, RecommendationRead, SkinRead
from app.services.provider_factory import build_provider
from app.services.recommendation import build_recommendations
from app.services.simulation import simulate_ai_portfolio
from app.services.tracker import (
    backfill_history,
    backfill_seed_data,
    ensure_tracked_universe,
    ingest_ticks,
    track_prices_for_date,
)

from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title=settings.app_name)
Instrumentator().instrument(app).expose(app)

base_dir = Path(__file__).resolve().parent.parent
app.mount("/web", StaticFiles(directory=str(base_dir / "web")), name="web")
templates = Jinja2Templates(directory=str(base_dir / "web"))

scheduler = BackgroundScheduler(timezone="UTC")


def _listing_url(name: str) -> str:
    return f"https://steamcommunity.com/market/listings/730/{urllib.parse.quote(name, safe='')}"


def _bootstrap_seed_database_if_missing() -> None:
    if not settings.database_url.startswith("sqlite:///"):
        return

    raw_path = settings.database_url.replace("sqlite:///", "", 1)
    db_path = Path(raw_path) if raw_path.startswith("/") else (base_dir / raw_path)
    if db_path.exists():
        return

    seed_candidates = [base_dir / "seed" / "skins.db", base_dir / "data" / "skins.db"]
    seed_path = next((p for p in seed_candidates if p.exists()), None)
    if not seed_path:
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_path, db_path)


@app.on_event("startup")
def startup() -> None:
    _bootstrap_seed_database_if_missing()
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


@app.get("/simulation/ai-portfolio", response_model=PortfolioSimRead)
def ai_portfolio_simulation(
    initial_capital: float = 8000.0, top_n: int = 5, db: Session = Depends(get_db)
) -> PortfolioSimRead:
    result = simulate_ai_portfolio(db, initial_capital=max(1000.0, min(initial_capital, 250000.0)), top_n=top_n)
    if result is None:
        raise HTTPException(status_code=404, detail="Not enough historical data to run simulation")
    payload = vars(result).copy()
    payload["points"] = [vars(p) for p in result.points]
    return PortfolioSimRead(**payload)


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


# ── K8s Monitoring ─────────────────────────────────────────

import json
import os
import ssl

_K8S_HOST = os.environ.get("KUBERNETES_SERVICE_HOST", "")
_K8S_PORT = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
_K8S_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_K8S_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"


def _k8s_api_get(path: str) -> dict | list | None:
    """Call Kubernetes API from inside a pod using the mounted service account."""
    try:
        import httpx as _httpx
        token = Path(_K8S_TOKEN_PATH).read_text().strip()
        base = f"https://{_K8S_HOST}:{_K8S_PORT}"
        resp = _httpx.get(
            f"{base}{path}",
            headers={"Authorization": f"Bearer {token}"},
            verify=_K8S_CA_PATH,
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _run_kubectl(args: list[str], timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            ["kubectl"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _age_str(ts: str) -> str:
    """Convert ISO timestamp to a human-readable age string."""
    from datetime import datetime, timezone
    try:
        created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - created
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h"
        return f"{secs // 86400}d"
    except Exception:
        return ts


def _k8s_info_from_api() -> dict[str, object] | None:
    """Fetch cluster info via the Kubernetes REST API (in-cluster)."""
    if not _K8S_HOST:
        return None

    pods_data = _k8s_api_get("/api/v1/pods")
    svc_data = _k8s_api_get("/api/v1/services")
    deploy_data = _k8s_api_get("/apis/apps/v1/deployments")
    node_data = _k8s_api_get("/api/v1/nodes")
    ns_data = _k8s_api_get("/api/v1/namespaces")

    if pods_data is None:
        return None

    pods = []
    for item in (pods_data.get("items") or []):
        meta = item.get("metadata", {})
        status = item.get("status", {})
        cs = (status.get("containerStatuses") or [{}])[0] if status.get("containerStatuses") else {}
        ready_conds = [c for c in (status.get("conditions") or []) if c.get("type") == "Ready"]
        ready_val = ready_conds[0].get("status", "False") if ready_conds else "False"
        pods.append({
            "name": meta.get("name", ""),
            "namespace": meta.get("namespace", ""),
            "status": status.get("phase", "Unknown"),
            "ready": ready_val,
            "restarts": str(cs.get("restartCount", 0)),
            "node": item.get("spec", {}).get("nodeName", ""),
            "age": _age_str(meta.get("creationTimestamp", "")),
        })

    svcs = []
    for item in ((svc_data or {}).get("items") or []):
        meta = item.get("metadata", {})
        spec = item.get("spec", {})
        ports = ",".join(str(p.get("port", "")) for p in (spec.get("ports") or []))
        svcs.append({
            "name": meta.get("name", ""),
            "namespace": meta.get("namespace", ""),
            "type": spec.get("type", ""),
            "cluster_ip": spec.get("clusterIP", ""),
            "ports": ports,
            "age": _age_str(meta.get("creationTimestamp", "")),
        })

    deploys = []
    for item in ((deploy_data or {}).get("items") or []):
        meta = item.get("metadata", {})
        spec = item.get("spec", {})
        st = item.get("status", {})
        desired = spec.get("replicas", 1)
        ready = st.get("readyReplicas", 0) or 0
        deploys.append({
            "name": meta.get("name", ""),
            "namespace": meta.get("namespace", ""),
            "ready": f"{ready}/{desired}",
            "up_to_date": str(st.get("updatedReplicas", 0) or 0),
            "available": str(st.get("availableReplicas", 0) or 0),
            "desired": str(desired),
            "age": _age_str(meta.get("creationTimestamp", "")),
        })

    nodes = []
    for item in ((node_data or {}).get("items") or []):
        meta = item.get("metadata", {})
        ni = item.get("status", {}).get("nodeInfo", {})
        labels = meta.get("labels", {})
        conds = item.get("status", {}).get("conditions", [])
        ready_conds = [c for c in conds if c.get("type") == "Ready"]
        status_val = "Ready" if ready_conds and ready_conds[0].get("status") == "True" else "NotReady"
        role = "control-plane" if "node-role.kubernetes.io/control-plane" in labels else "worker"
        nodes.append({
            "name": meta.get("name", ""),
            "status": status_val,
            "roles": role,
            "version": ni.get("kubeletVersion", ""),
            "os": ni.get("osImage", ""),
            "arch": ni.get("architecture", ""),
            "age": _age_str(meta.get("creationTimestamp", "")),
        })

    nses = []
    for item in ((ns_data or {}).get("items") or []):
        meta = item.get("metadata", {})
        nses.append({
            "name": meta.get("name", ""),
            "status": item.get("status", {}).get("phase", ""),
            "age": _age_str(meta.get("creationTimestamp", "")),
        })

    return {"pods": pods, "services": svcs, "deployments": deploys, "nodes": nodes, "namespaces": nses}


def _k8s_info_from_kubectl() -> dict[str, object]:
    """Fallback: fetch cluster info via kubectl CLI."""
    pods_raw = _run_kubectl(["get", "pods", "--all-namespaces", "--no-headers",
                             "-o", "custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,"
                             "STATUS:.status.phase,READY:.status.conditions[?(@.type=='Ready')].status,"
                             "RESTARTS:.status.containerStatuses[0].restartCount,"
                             "NODE:.spec.nodeName,AGE:.metadata.creationTimestamp"])
    pods = []
    for line in (pods_raw or "").strip().splitlines():
        parts = line.split(None, 6)
        if len(parts) >= 7:
            pods.append({
                "name": parts[0], "namespace": parts[1], "status": parts[2],
                "ready": parts[3], "restarts": parts[4], "node": parts[5], "age": _age_str(parts[6]),
            })

    svc_raw = _run_kubectl(["get", "svc", "--all-namespaces", "--no-headers",
                            "-o", "custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,"
                            "TYPE:.spec.type,CLUSTER-IP:.spec.clusterIP,"
                            "PORTS:.spec.ports[*].port,AGE:.metadata.creationTimestamp"])
    svcs = []
    for line in (svc_raw or "").strip().splitlines():
        parts = line.split(None, 5)
        if len(parts) >= 6:
            svcs.append({
                "name": parts[0], "namespace": parts[1], "type": parts[2],
                "cluster_ip": parts[3], "ports": parts[4], "age": _age_str(parts[5]),
            })

    deploy_raw = _run_kubectl(["get", "deployments", "--all-namespaces", "--no-headers",
                               "-o", "custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,"
                               "READY:.status.readyReplicas,UP-TO-DATE:.status.updatedReplicas,"
                               "AVAILABLE:.status.availableReplicas,DESIRED:.spec.replicas,"
                               "AGE:.metadata.creationTimestamp"])
    deploys = []
    for line in (deploy_raw or "").strip().splitlines():
        parts = line.split(None, 6)
        if len(parts) >= 7:
            ready_count = parts[2] if parts[2] != "<none>" else "0"
            desired_count = parts[5] if parts[5] != "<none>" else "1"
            deploys.append({
                "name": parts[0], "namespace": parts[1],
                "ready": f"{ready_count}/{desired_count}",
                "up_to_date": parts[3] if parts[3] != "<none>" else "0",
                "available": parts[4] if parts[4] != "<none>" else "0",
                "desired": desired_count,
                "age": _age_str(parts[6]),
            })

    node_raw = _run_kubectl(["get", "nodes", "--no-headers",
                             "-o", "custom-columns=NAME:.metadata.name,"
                             "STATUS:.status.conditions[?(@.type=='Ready')].status,"
                             "ROLES:.metadata.labels.node-role\\.kubernetes\\.io/control-plane,"
                             "VERSION:.status.nodeInfo.kubeletVersion,"
                             "OS:.status.nodeInfo.osImage,ARCH:.status.nodeInfo.architecture,"
                             "AGE:.metadata.creationTimestamp"])
    nodes = []
    for line in (node_raw or "").strip().splitlines():
        parts = line.split(None, 6)
        if len(parts) >= 7:
            status_val = "Ready" if parts[1] == "True" else "NotReady"
            role_val = "control-plane" if parts[2] != "<none>" else "worker"
            nodes.append({
                "name": parts[0], "status": status_val, "roles": role_val,
                "version": parts[3], "os": parts[4], "arch": parts[5], "age": _age_str(parts[6]),
            })

    ns_raw = _run_kubectl(["get", "namespaces", "--no-headers",
                           "-o", "custom-columns=NAME:.metadata.name,"
                           "STATUS:.status.phase,AGE:.metadata.creationTimestamp"])
    nses = []
    for line in (ns_raw or "").strip().splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 3:
            nses.append({"name": parts[0], "status": parts[1], "age": _age_str(parts[2])})

    return {"pods": pods, "services": svcs, "deployments": deploys, "nodes": nodes, "namespaces": nses}


@app.get("/k8s/info")
def k8s_info() -> dict[str, object]:
    # Try in-cluster API first, then kubectl fallback
    result = _k8s_info_from_api()
    if result is not None:
        return result
    return _k8s_info_from_kubectl()
