FROM debian:bookworm-slim

# uv is copied in as a static binary and provisions the interpreter itself, so
# the image is not tied to whichever Python version a base tag happens to ship.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

LABEL org.opencontainers.image.title="laya-api" \
      org.opencontainers.image.description="Laya typed-decision prediction API" \
      org.opencontainers.image.licenses="MIT"

# Torch is installed explicitly so this one Dockerfile builds both variants:
# the CPU image (defaults) and the CUDA image (TORCH_INDEX=.../cu126 plus
# TORCH_DISABLE_NATIVE_JIT=1). The NVIDIA driver comes from the host via the
# NVIDIA container runtime (--gpus all / compose device reservations).
#
# cu126 needs a host driver with CUDA >= 12.6 (R560+); use .../cu130 on newer ones.
ARG TORCH_VERSION=2.14.1
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG TORCH_DISABLE_NATIVE_JIT=0

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    HF_HOME=/data/hf \
    PORT=8000 \
    TORCH_DISABLE_NATIVE_JIT=${TORCH_DISABLE_NATIVE_JIT} \
    PATH="/app/.venv/bin:$PATH"

# ca-certificates/netbase/tzdata mirror Astral's own bookworm-slim image. The
# interpreter is installed into a world-readable prefix because the venv links
# to it and the container runs as the unprivileged appuser.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates netbase tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && uv python install 3.15

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

# The lockfile pins the CPU torch wheel, so keep it out of `uv sync` and install
# the requested wheel from the index chosen above instead.
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-package torch \
 && uv pip install --python /app/.venv/bin/python \
        "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX}"

COPY --chown=appuser:appuser app ./app

# Prepare the cache before downloading so the model layer is not duplicated by
# a later recursive chown.
RUN mkdir -p /data/hf && chown -R appuser:appuser /app /data/hf

USER appuser

# Optional: bake the checkpoint(s) into the image for instant/offline startup.
# Build with --build-arg PRELOAD_MODEL=1 (adds ~1 GB, needs network at build).
# Plain `python`, not `uv run`: uv run would re-sync and replace the torch wheel.
# Preloading on CPU keeps a CUDA host driver out of the build.
# TORCH_DISABLE_NATIVE_JIT=1 avoids Triton JIT builds that need a compiler the
# slim image does not have; it is read as an integer, so an explicit 0 is required.
ARG PRELOAD_MODEL=0
ARG MODELS=english
ENV MODELS=${MODELS}
RUN if [ "$PRELOAD_MODEL" = "1" ]; then \
        python -c "import os; from laya import Router; Router(device='cpu').preload([m.strip() for m in os.environ['MODELS'].split(',') if m.strip()])"; \
    fi

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'))"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
