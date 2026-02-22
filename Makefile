APP_NAME=cs2-skin-ai
IMAGE=$(APP_NAME):latest
REGISTRY_IMAGE=ghcr.io/nnamuhcs/aks-edge-cs2-demo:latest

.PHONY: install run test build push deploy-k8s

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -q

build:
	docker build -t $(IMAGE) -t $(REGISTRY_IMAGE) .

push: build
	docker push $(REGISTRY_IMAGE)

deploy-k8s:
	bash scripts/deploy_local_k8s.sh
