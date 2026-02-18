.PHONY: help install run dev lint format clean \
        docker-build docker-run docker-stop docker-logs docker-shell docker-push

# Variables
IMAGE_NAME ?= gateway-ia
IMAGE_TAG ?= latest
CONTAINER_NAME ?= gateway-ia

# Default target
help:
	@echo "gateway-ia - Commandes disponibles:"
	@echo ""
	@echo "  make install      - Installer les dépendances"
	@echo "  make run          - Lancer le proxy (production)"
	@echo "  make dev          - Lancer le proxy (développement avec reload)"
	@echo "  make lint         - Vérifier le code avec ruff"
	@echo "  make format       - Formater le code avec ruff"
	@echo "  make clean        - Nettoyer les fichiers temporaires"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build - Construire l'image Docker"
	@echo "  make docker-run   - Lancer le conteneur"
	@echo "  make docker-stop  - Arrêter le conteneur"
	@echo "  make docker-logs  - Afficher les logs du conteneur"
	@echo "  make docker-shell - Ouvrir un shell dans le conteneur"
	@echo "  make docker-push  - Pousser l'image (REGISTRY=...)"
	@echo ""

# Installer les dépendances
install:
	uv sync

# Lancer le proxy en mode production
run:
	uv run python -m gateway_ia

# Lancer le proxy en mode développement (avec auto-reload)
dev:
	uv run uvicorn gateway_ia.app:create_app --factory --reload --host 0.0.0.0 --port 8080

# Vérifier le code
lint:
	uv run ruff check gateway_ia/

# Formater le code
format:
	uv run ruff format gateway_ia/
	uv run ruff check --fix gateway_ia/

# Nettoyer les fichiers temporaires
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/
	@echo "Cleaned!"

# =============================================================================
# Docker
# =============================================================================

# Construire l'image Docker
docker-build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

# Lancer le conteneur
docker-run:
	docker run -d \
		--name $(CONTAINER_NAME) \
		-p 8080:8080 \
		$(IMAGE_NAME):$(IMAGE_TAG)

# Arrêter et supprimer le conteneur
docker-stop:
	docker stop $(CONTAINER_NAME) 2>/dev/null || true
	docker rm $(CONTAINER_NAME) 2>/dev/null || true

# Afficher les logs
docker-logs:
	docker logs -f $(CONTAINER_NAME)

# Ouvrir un shell dans le conteneur
docker-shell:
	docker exec -it $(CONTAINER_NAME) /bin/bash

# Pousser l'image vers un registry (usage: make docker-push REGISTRY=ghcr.io/user)
docker-push:
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
	docker push $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
