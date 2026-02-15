#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="cs2-skin-ai:latest"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required"
  exit 1
fi

echo "Building image ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" .

if command -v kind >/dev/null 2>&1; then
  cluster_name=$(kind get clusters | head -n 1 || true)
  if [[ -n "${cluster_name}" ]]; then
    echo "Loading image into kind cluster ${cluster_name}..."
    kind load docker-image "${IMAGE_NAME}" --name "${cluster_name}"
  fi
fi

echo "Applying Kubernetes manifests..."
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

echo "Waiting for deployment rollout..."
kubectl rollout status deployment/cs2-skin-ai --timeout=120s

echo "Deployment ready. Port-forward with: kubectl port-forward svc/cs2-skin-ai 8000:80"
