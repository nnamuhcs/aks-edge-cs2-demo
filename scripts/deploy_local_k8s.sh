#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="cs2-skin-ai:latest"
REGISTRY_IMAGE="ghcr.io/nnamuhcs/aks-edge-cs2-demo:latest"
MODE="${1:-pv}"

if [[ "${MODE}" != "pv" && "${MODE}" != "no-pv" ]]; then
  echo "Usage: bash scripts/deploy_local_k8s.sh [pv|no-pv]"
  echo "  pv    : persistent mode using PVC (default)"
  echo "  no-pv : ephemeral mode using emptyDir"
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required"
  exit 1
fi

echo "Building image ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" -t "${REGISTRY_IMAGE}" .

if command -v kind >/dev/null 2>&1; then
  cluster_name=$(kind get clusters | head -n 1 || true)
  if [[ -n "${cluster_name}" ]]; then
    echo "Loading image into kind cluster ${cluster_name}..."
    kind load docker-image "${IMAGE_NAME}" --name "${cluster_name}"
  fi
fi

echo "Applying AKS Edge manifests (mode=${MODE})..."
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/configmap.yaml

if [[ "${MODE}" == "pv" ]]; then
  kubectl apply -f k8s/pvc.yaml
  kubectl apply -f k8s/deployment.yaml
else
  kubectl apply -f k8s/deployment-no-pv.yaml
fi

echo "Waiting for deployment rollout..."
kubectl rollout status deployment/cs2-skin-ai --timeout=120s

echo "Deployment ready (${MODE})."
echo "NodePort access: http://localhost:30080 (or http://<node-ip>:30080)"
echo "Fallback port-forward: kubectl port-forward svc/cs2-skin-ai 8000:80"
