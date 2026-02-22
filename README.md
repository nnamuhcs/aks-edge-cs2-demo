# CS2 Skin AI Intelligence

Professional CS2 skin investment intelligence app — an AKS Edge Essentials demo.

## What it does
- Pulls real-time CS2 prices from Steam Community Market (`priceoverview`).
- Backfills historical trend data from Steam listing history (`line1`) for real day-by-day charts.
- Stores all snapshots in SQLite with source metadata for auditability.
- Ranks top 5 candidates with AI-driven scoring (momentum, volatility, liquidity, rarity).
- Explains why each top candidate was selected vs non-top candidates.
- Shows a tracked universe of 25 skins with strategy rationale (thesis) and images.

## Preloaded Demo Data (Included in Repo)
- `data/skins.db` is committed with current snapshots/history and image URLs.
- Docker image embeds a seed DB at `/app/seed/skins.db`.
- On startup, if `sqlite` DB file is missing, app auto-copies seed DB, so first deploy already has data before clicking sync/backfill/image refresh.
- Missing external image metadata is pre-filled with `/web/placeholder.svg` so every tracked/recommended row has a picture.

## Architecture
- `FastAPI` backend + dashboard UI.
- `APScheduler` daily sync.
- `SQLite` storage.
- Default provider: `steam` (real data).
- Optional providers: `mock`, `http`.

## Quick Deploy (Pre-built Image from GHCR)

No build needed — just `kubectl apply`:

```bash
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deployment/cs2-skin-ai
```

Image: `ghcr.io/nnamuhcs/k8s-cs2-demo:latest`

Open [http://localhost:30080](http://localhost:30080)

## Quick Start (Local Dev)
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

## Build & Push Image
```bash
make build          # Build locally
make push           # Push to ghcr.io/nnamuhcs/k8s-cs2-demo:latest
```

Image is also auto-built on push to `main` via GitHub Actions.

## Deploy on AKS Edge (PVC, Persistent)
Option A (`.sh`):
```bash
bash scripts/deploy_local_k8s.sh
# Preferred (NodePort)
open http://localhost:30080

# Fallback
kubectl port-forward svc/cs2-skin-ai 8000:80
```

Option B (`kubectl apply`):
```bash
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl rollout status deployment/cs2-skin-ai
# Preferred (NodePort)
open http://localhost:30080

# Fallback
kubectl port-forward svc/cs2-skin-ai 8000:80
```

## Deploy on AKS Edge (No-PV, Ephemeral)
Option A (`.sh`):
```bash
bash scripts/deploy_local_k8s.sh no-pv
# Preferred (NodePort)
open http://localhost:30080

# Fallback
kubectl port-forward svc/cs2-skin-ai 8000:80
```

Option B (`kubectl apply`):
```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment-no-pv.yaml
kubectl apply -f k8s/service.yaml
kubectl rollout status deployment/cs2-skin-ai
# Preferred (NodePort)
open http://localhost:30080

# Fallback
kubectl port-forward svc/cs2-skin-ai 8000:80
```

## Architecture Doc (Slides)
- `/Users/verve/Documents/demo-cs2/docs/ARCHITECTURE.md`

`deploy_local_k8s.sh` supports mode argument:
- `pv` (default): uses `k8s/pvc.yaml` + `k8s/deployment.yaml`
- `no-pv`: uses `k8s/deployment-no-pv.yaml` (`emptyDir`)

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
