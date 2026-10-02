FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

LABEL org.opencontainers.image.title="laya-api" \
      org.opencontainers.image.description="Laya typed-decision prediction API" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/data/hf \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

# Install dependencies first so this layer is cached against the lockfile.
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY --chown=appuser:appuser app ./app

# Prepare the cache before downloading so the model layer is not duplicated by
# a later recursive chown.
RUN mkdir -p /data/hf && chown -R appuser:appuser /app /data/hf

USER appuser

# Optional: bake the checkpoint(s) into the image for instant/offline startup.
# Build with --build-arg PRELOAD_MODEL=1 (adds ~1 GB, needs network at build).
ARG PRELOAD_MODEL=0
ARG MODELS=english
ENV MODELS=${MODELS}
RUN if [ "$PRELOAD_MODEL" = "1" ]; then \
        MODELS="$MODELS" uv run --no-dev python -c \
            "import os; from laya import Router; Router().preload([m.strip() for m in os.environ['MODELS'].split(',') if m.strip()])"; \
    fi

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'))"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
