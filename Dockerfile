# syntax=docker/dockerfile:1.7
# AutoGrader image - follows the same rules its DevOps agent grades students on:
# pinned bases, multi-stage, deps-before-source layer caching, non-root, healthcheck, exec-form CMD.

# Stage 1: only used to borrow the static docker CLI binary (for the optional build sandbox).
FROM docker:27.3-cli AS dockercli

# Stage 2: runtime
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AUTOGRADER_WORK_DIR=/data
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
# Dependencies first: source edits do not invalidate this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web

RUN useradd --create-home --uid 10001 autograder && mkdir -p /data && chown autograder:autograder /data
USER autograder

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1
# One worker on purpose: job state + SSE fan-out live in-process (see docs/ARCHITECTURE.md §9).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
