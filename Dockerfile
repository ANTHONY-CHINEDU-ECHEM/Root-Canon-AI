# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY ingestion ./ingestion
COPY evaluation ./evaluation
RUN pip install --upgrade pip && pip install ".[ml]" --extra-index-url https://download.pytorch.org/whl/cpu

# Bake the embedding and reranker weights into the image so cold starts are fast
# and the service runs without internet access in a clinical network.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-base-en-v1.5'); CrossEncoder('BAAI/bge-reranker-base')"

RUN useradd --create-home --uid 10001 rootcanon && mkdir -p /app/data && chown -R rootcanon /app /models
USER rootcanon
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
