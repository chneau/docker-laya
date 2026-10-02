# docker-laya

[![Publish Docker image](https://github.com/chneau/docker-laya/actions/workflows/publish.yml/badge.svg)](https://github.com/chneau/docker-laya/actions/workflows/publish.yml)
[![Docker Image](https://img.shields.io/badge/docker_image-ghcr.io%2Fchneau%2Flaya-blue?logo=docker)](https://ghcr.io/chneau/laya)

Dockerized [Laya](https://huggingface.co/convaiinnovations/laya) prediction
service: loads one or more checkpoints behind a router, then serves typed
decisions (choice / score / noul) over HTTP, auto-routed by language or pinned
with `model`. Also supports TypeSafe API compatibility via `/v1/systemone`.

Built and published for `linux/amd64` and `linux/arm64`.

---

## ✨ Features

- 🔀 **Multi-Checkpoint Routing**: bundles `english`, `multilingual` and
  `typed-decisions`, auto-selected by language or pinned per request.
- 🎯 **Typed Decisions**: `choice` / `score` / `noul` questions with calibrated
  probabilities, confidence and action probability.
- 🤝 **TypeSafe API Compatibility**: drop-in `/v1/systemone` endpoint compatible
  with TypeSafe request/response schemas.
- 🔐 **Timing-Safe Auth**: API keys (`X-API-Key` / `Authorization: Bearer`) and
  HTTP Basic, compared in constant time.
- 📑 **Interactive OpenAPI Docs**: Swagger UI (`/docs`), ReDoc (`/redoc`) and the
  raw schema at `/openapi.json`.
- 🧰 **Built-in Presets**: ready-made question sets (`triage`, `email`, `guard`,
  `moderation`, `router`).
- 📦 **Bulk Inference**: `/predict/bulk` over many states, with per-state
  questions/model and isolated errors.
- 🔎 **Detection & Email Helpers**: `/detect` (script/language) and
  `/email/state` (clean + structure an email).
- 🧩 **Flexible State**: string, JSON object, or conversation turns; criteria
  values may be any JSON (dicts/lists/numbers are rendered as compact JSON).
- 🛡️ **Non-Root**: runs as unprivileged `appuser` (uid `10001`).
- 📦 **Multi-Architecture**: supports both `linux/amd64` and `linux/arm64`.
- 🩺 **Healthcheck**: dedicated `/healthz` endpoint and container `HEALTHCHECK`.
- 🪶 **CPU-Only Torch**: uses the PyTorch CPU wheel index (no CUDA), roughly
  `0.35s` per predict on CPU.
- 🎮 **Optional CUDA Variant**: `Dockerfile.cuda` installs the CUDA torch wheel
  (`cu126` by default) for GPU inference.
- 🧠 **Memory-Aware Loading**: skips random weight initialization before loading
  checkpoints and trims the heap afterwards, avoiding the OOM spike on large encoders.

---

## 🚀 Quickstart

Pull and run the published image:

```bash
docker pull ghcr.io/chneau/laya
docker run -d -p 8000:8000 -e API_KEYS=key1 -v hf-cache:/data/hf ghcr.io/chneau/laya
```

### 🏷️ Docker Image Tags & Model Variants

Multi-architecture images (`linux/amd64` and `linux/arm64`) are published to GitHub Container Registry under several tags:

| Image Tag | Preloaded Models | Image Size | Description |
| :--- | :--- | :--- | :--- |
| `ghcr.io/chneau/laya:latest` (or `v0.6.1`) | None (Dynamic) | ~300 MB | **Slim / Default**: Small image size. Downloads model on first run into `/data/hf`. |
| `ghcr.io/chneau/laya:english` | `english` | ~1.3 GB | **Instant Startup (English)**: Pre-baked English checkpoint, offline-ready. |
| `ghcr.io/chneau/laya:multilingual` | `multilingual` | ~1.8 GB | **Instant Startup (Multilingual)**: Pre-baked multilingual checkpoint. |
| `ghcr.io/chneau/laya:typed-decisions` | `typed-decisions` | ~1.3 GB | **Instant Startup (Typed Decisions)**: Pre-baked typed decisions checkpoint. |
| `ghcr.io/chneau/laya:all` | All 3 models | ~3.5 GB | **Full Bundle**: All checkpoints pre-baked for zero-latency multi-model routing. |

The same variants are also published with CUDA torch for **`linux/amd64` only**
(PyTorch's CUDA wheels are not available for arm64), as `:cuda`, `:english-cuda`,
`:multilingual-cuda`, `:typed-decisions-cuda` and `:all-cuda`. They need the NVIDIA
container runtime at run time. See [CUDA (GPU) Variant](#cuda-gpu-variant).

#### Running a Pre-baked Image (Instant Startup & Air-gapped / Offline)

```bash
docker run -d -p 8000:8000 -e API_KEYS=key1 ghcr.io/chneau/laya:english
```

### Check Health

```bash
curl http://localhost:8000/healthz
```

### View Interactive API Documentation

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Raw OpenAPI Specification**:
  [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

### Examples

The [`examples/`](examples/README.md) folder contains ready-to-run HTTP requests and
a small Python client that classifies documents into categories. It only calls the
HTTP API and does not load checkpoints, so no local model setup is required.

---

## 📇 Endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/healthz` | no | Liveness + resident models |
| `GET` | `/models` | yes* | Available and loaded checkpoints |
| `GET` | `/presets` | yes* | Built-in question sets |
| `POST` | `/detect` | yes* | Script/language detection (what routing uses) |
| `POST` | `/email/state` | yes* | Clean + structure an email as a state |
| `POST` | `/predict` | yes* | Typed questions over one state |
| `POST` | `/predict/bulk` | yes* | Same questions over many states |
| `POST` | `/v1/systemone` | yes* | SystemOne / TypeSafe compatible prediction |

\* Enforced only when `API_KEYS` and/or `BASIC_AUTH` is set. Any of these works:

```bash
-H 'X-API-Key: key1'
-H 'Authorization: Bearer key1'
-u admin:secret              # HTTP Basic
```

---

## 🧠 Predicting

### Standard Prediction (`POST /predict`)

```bash
curl -X POST localhost:8000/predict -H 'X-API-Key: key1' -H 'Content-Type: application/json' -d '{
  "state": "I was billed twice. Please refund the duplicate today.",
  "questions": {
    "department": {"type": "choice", "instructions": "Which team?", "criteria": {"billing": "refunds", "technical": "bugs", "sales": "purchases"}},
    "urgency":    {"type": "score",  "instructions": "How urgent?", "criteria": ["not urgent", "soon", "critical"]},
    "refund":     {"type": "noul",   "instructions": "Does the customer ask for money back?"}
  }
}'
```

```json
{
  "model": "laya-rl-agent",
  "answers": {
    "department": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.96, "technical": 0.02, "sales": 0.02}, "confidence": 0.82},
    "urgency":    {"type": "score", "score": 1.36, "legend": {"0": "not urgent", "1": "soon", "2": "critical"}, "confidence": 0.09},
    "refund":     {"type": "noul", "noul": 0.82, "confidence": 0.82}
  },
  "usage": {"input_tokens": 132, "output_tokens": 0},
  "routing": {"model": "english", "reason": "English Latin text"}
}
```

`state` accepts a string, JSON object, or list of conversation turns. Criteria
values may be strings or any JSON value (dicts/lists/numbers are rendered as
compact JSON), and `noul` accepts optional `{"true": ..., "false": ...}` text.

**Routing** — omit `model` to auto-select by language (see `/detect`), or pin
`"model": "english" | "multilingual" | "typed-decisions"`. The response includes
`routing` with the chosen checkpoint and reason.

**Presets** — skip `questions` and pass `"preset": "triage"` (one of `triage`,
`email`, `guard`, `moderation`, `router`); list them at `GET /presets`.

**Bulk** — use `states` with shared `questions`/`preset`/`model`, or `items` to
override questions and model per state. Returns `{"count": N, "results": [...]}`
with per-state errors isolated as `{"ok": false, "error": "..."}`.

---

### SystemOne / TypeSafe Compatible Prediction (`POST /v1/systemone`)

```bash
curl -X POST localhost:8000/v1/systemone -H 'Authorization: Bearer key1' -H 'Content-Type: application/json' -d '{
  "state": "I was billed twice. Please refund the duplicate today.",
  "model": "laya-english",
  "questions": {
    "department": {"type": "choice", "instructions": "Which team?", "criteria": {"billing": "refunds", "technical": "bugs", "sales": "purchases"}},
    "urgency":    {"type": "score",  "instructions": "How urgent?", "criteria": ["not urgent", "soon", "critical"]},
    "refund":     {"type": "noul",   "instructions": "Does the customer ask for money back?"}
  }
}'
```

```json
{
  "model": "laya-english",
  "answers": {
    "department": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.96, "technical": 0.02, "sales": 0.02}, "confidence": 0.82},
    "urgency":    {"type": "score", "score": 1.36, "legend": {"0": "not urgent", "1": "soon", "2": "critical"}, "confidence": 0.09},
    "refund":     {"type": "noul", "noul": 0.82}
  },
  "usage": {"input_tokens": 132, "output_tokens": 0}
}
```

Supported model names for TypeSafe requests:
`laya-english`, `laya-multilingual`, `laya-typed-decisions`.

---

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `API_KEYS` | *(empty)* | Comma-separated keys; empty disables API-key auth. |
| `BASIC_AUTH` | *(empty)* | Comma-separated `user:password` pairs. |
| `MAX_BULK_ITEMS` | *(empty / unlimited)* | Optional limit on states per `/predict/bulk` (unlimited by default). |
| `PORT` | `8000` | HTTP port (host and container). |
| `MODELS` | `english` | Checkpoints to preload: `english`, `multilingual`, `typed-decisions`. |
| `MODEL_ID` | `convaiinnovations/laya` | Optional repo override (mirror/local path). |
| `MODEL_SUBFOLDER` | *(empty)* | Subfolder for the English checkpoint. |
| `DEVICE` | `cpu` | `cpu` or `cuda`. |
| `HF_HOME` | `/data/hf` | HF cache (persisted via volume). |
| `HF_TOKEN` | *(empty)* | Optional Hugging Face token for authenticated checkpoint downloads. |

Preload `MODELS=english,multilingual` to route languages without reloading. On
startup the app also loads the repository `.env` (without overriding existing process
variables), so `make run` picks up local settings automatically.

---

## 🐳 Docker Compose Example

```yaml
services:
  laya:
    image: ghcr.io/chneau/laya
    ports:
      - "8000:8000"
    environment:
      - API_KEYS=replace_with_your_strong_api_key
      - MODELS=english,multilingual
    volumes:
      - hf-cache:/data/hf
    restart: unless-stopped

volumes:
  hf-cache:
```

### Build Locally

```bash
cp .env.example .env          # set API_KEYS
make up                       # docker compose up -d --build
```

### CUDA (GPU) Variant

The default image is CPU-only. For GPU inference, build `Dockerfile.cuda`, which
swaps the CPU torch wheel for the CUDA one (`cu126`, torch `2.14.0`). It needs the
NVIDIA container toolkit and a host driver supporting the chosen CUDA version
(cu126 requires R560+; override with `--build-arg TORCH_CUDA=cu130`).

```bash
# Build and run a local CUDA image
make build-cuda
docker run --rm --gpus all -p 8000:8000 -e API_KEYS=key1 -v hf-cache:/data/hf laya-api:cuda

# Or use the Compose override (adds the GPU device reservation and DEVICE=cuda)
make up-cuda
```

Bake checkpoints into the CUDA image with `make build-model-cuda MODEL=english`.

The workflow builds the CUDA image on pull requests as a check, and publishes the
`linux/amd64` variants (`cuda`, `english-cuda`, `multilingual-cuda`,
`typed-decisions-cuda`, `all-cuda`) alongside the CPU images on branches, tags and
manual runs. A GPU is not required to build the image, only to run it.

---

## 🛠️ Generating Client SDKs

The full OpenAPI 3.1 schema is saved directly in the repository as
[`openapi.json`](./openapi.json) (and served at `/openapi.json`). You can
generate type-safe API clients for TypeScript, Go, Python, etc.:

### TypeScript / Fetch Client (using `openapi-typescript`)

```bash
npx openapi-typescript ./openapi.json -o laya-client.d.ts
```

### Multi-language Client (using OpenAPI Generator)

```bash
# Generate Python SDK
npx @openapitools/openapi-generator-cli generate -i openapi.json -g python -o ./clients/python

# Generate Go SDK
npx @openapitools/openapi-generator-cli generate -i openapi.json -g go -o ./clients/go
```

To regenerate the schema file at any time:

```bash
make openapi
```

---

## 🧪 Testing Locally

The project requires **Python 3.14+** and uses **uv** for dependencies:

```bash
uv sync --group dev          # install runtime and development dependencies
make test                    # service and HTTP contract tests
make check                   # ruff, ruff format, mypy (strict) and pyright
```

The test suite substitutes the Laya boundary, so it never downloads checkpoints or
runs inference. The CI workflow also runs a container smoke test (`/healthz` +
`/predict`) before publishing.

```bash
# Build and run the container
docker build -t laya-api:test .
docker run --rm -p 8000:8000 -e API_KEYS=test laya-api:test
```

### Make targets

```sh
make openapi                    # regenerate openapi.json
make test                       # pytest
make run                        # uvicorn --reload on :8000
make format / check / fix       # ruff, format and static checks
make up / down / build / logs   # docker compose
make build-cuda                 # CUDA image (Dockerfile.cuda)
make up-cuda                    # docker compose with the CUDA override
```

### Project layout

```text
app/
├── main.py             # ASGI entry point: app.main:app
├── application.py      # app factory and composition root
├── api.py              # HTTP routes
├── authentication.py   # API key, bearer and Basic auth
├── backend.py          # typed boundary to the Laya library
├── config.py           # per-instance immutable settings
├── schemas.py          # Pydantic request/response contracts
└── services.py         # runtime, prediction and SystemOne adapter
examples/               # HTTP requests and the category client
tests/                  # service and HTTP contract tests
```

Laya is imported lazily, so `openapi.json` can be generated and validated without
torch installed.

---

## 📝 Notes

- Runs as non-root (`appuser`, uid 10001); the `hf-cache` volume inherits that
  ownership. If you bind-mount your own cache, make sure uid 10001 can write it.
- Torch uses the CPU wheel index (`pyproject.toml`); ~0.35s per predict on CPU.
  `Dockerfile.cuda` swaps in the CUDA wheel for GPU inference.
- Checkpoints load inside `transformers.initialization.no_init_weights()` and the
  glibc heap is trimmed afterwards, which avoids the >3.7 GB peak of the multilingual
  encoder and returns freed load buffers to the OS.
- The router loads once behind a lock, so requests are serialised per process.
- `/predict/bulk` loops (laya's public API is single-state); it does not batch.

---

## 📄 License

MIT © [chneau](https://github.com/chneau)
