# CS2 Skin AI Intelligence

Professional CS2 skin investment intelligence app that runs locally and in local Kubernetes.

## What it does
- Pulls real-time CS2 prices from Steam Community Market (`priceoverview`).
- Backfills historical trend data from Steam listing history (`line1`) for real day-by-day charts.
- Stores all snapshots in SQLite with source metadata for auditability.
- Ranks top 5 candidates with AI-style scoring (momentum, volatility, liquidity, rarity).
- Explains why each top candidate was selected vs non-top candidates.
- Shows a tracked universe of 25 skins with strategy rationale (thesis) and images.

## Architecture
- `FastAPI` backend + dashboard UI.
- `APScheduler` daily sync.
- `SQLite` storage.
- Default provider: `steam` (real data).
- Optional providers: `mock`, `http`.

## Quick Start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

## Core API
- `GET /health`
- `POST /track` - sync latest prices
- `POST /backfill?days=180` - historical backfill for trend chart
- `POST /maintenance/rebuild-real?days=180` - clear tracked snapshots and rebuild from Steam
- `POST /maintenance/enrich-images` - refresh missing skin image metadata from Steam
- `GET /recommendations?limit=5`
- `GET /history/{skin_id}`
- `GET /skins`

## Transparency / Audit API
- `GET /audit/summary` - counts, date span, source breakdown
- `GET /audit/snapshots?limit=50` - recent rows with source links
- `GET /audit/tracked-universe` - why these 25 skins are tracked

## Local K8s
```bash
bash scripts/deploy_local_k8s.sh
kubectl port-forward svc/cs2-skin-ai 8000:80
```

## Providers / Env
Default live mode:
- `PROVIDER_NAME=steam`
- `STEAM_CURRENCY=1`

Options:
- `PROVIDER_NAME=mock`
- `PROVIDER_NAME=http`
- `MARKET_API_URL=...`
- `MARKET_API_KEY=...`

## Tests
```bash
pytest -q
```
