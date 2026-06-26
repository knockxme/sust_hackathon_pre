# QueueStorm Investigator — Production Dockerfile
# Multi-stage build for minimal image size

FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Python dependencies into a separate layer
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─── Final Stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Security: non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/

# Set ownership
RUN chown -R appuser:appuser /app

USER appuser

# Environment defaults (override with --env-file or -e)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run with uvicorn bound to all interfaces
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 2 --log-level info"]
