PORT ?= 8000
TORCH_CUDA ?= cu126

.PHONY: help run format check test fix update openapi up down build build-model build-cuda build-model-cuda up-cuda logs

help:
	@echo "make run     - run the API locally (uvicorn --reload on $(PORT))"
	@echo "make format  - format Python with ruff"
	@echo "make check   - check lint, docstrings, formatting and static types"
	@echo "make test    - run service and HTTP regression tests"
	@echo "make fix     - lint and auto-fix with ruff"
	@echo "make update  - upgrade dependencies and bump pyproject.toml lower bounds"
	@echo "make openapi - regenerate openapi.json"
	@echo "make up      - docker compose up --build (detached)"
	@echo "make down    - docker compose down"
	@echo "make build   - docker build the image"
	@echo "make build-model MODEL=english - build an image with one model baked in"
	@echo "make build-cuda - docker build the CUDA image (TORCH_CUDA=$(TORCH_CUDA))"
	@echo "make build-model-cuda MODEL=english - CUDA image with one model baked in"
	@echo "make up-cuda - docker compose with the CUDA override (needs an NVIDIA GPU)"
	@echo "make logs    - follow container logs"

run:
	uv run uvicorn app.main:app --reload --port $(PORT)

format:
	uv run ruff format .

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run pyright

test:
	uv run pytest

fix:
	uv run ruff check --fix .

update:
	uv lock --upgrade
	uv run --no-dev --no-sync python scripts/update_dependency_floors.py
	uv lock

openapi:
	uv run --no-dev python -c 'import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))' > openapi.json

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker build -t laya-api:latest .

build-model:
	docker build --build-arg PRELOAD_MODEL=1 --build-arg MODELS=$(MODEL) -t laya-api:$(MODEL) .

build-cuda:
	docker build \
		--build-arg TORCH_INDEX=https://download.pytorch.org/whl/$(TORCH_CUDA) \
		--build-arg TORCH_DISABLE_NATIVE_JIT=1 \
		-t laya-api:cuda .

build-model-cuda:
	docker build \
		--build-arg TORCH_INDEX=https://download.pytorch.org/whl/$(TORCH_CUDA) \
		--build-arg TORCH_DISABLE_NATIVE_JIT=1 \
		--build-arg PRELOAD_MODEL=1 --build-arg MODELS=$(MODEL) \
		-t laya-api:$(MODEL)-cuda .

up-cuda:
	docker compose -f docker-compose.yml -f docker-compose.cuda.yml up -d --build

logs:
	docker compose logs -f
