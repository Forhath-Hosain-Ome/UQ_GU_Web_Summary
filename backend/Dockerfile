FROM python:3.12.8-slim AS builder
WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────
FROM python:3.12.8-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd -m -u 1001 -G root appuser && \
    mkdir -p /app/media /app/logs /app/media/uploads /app/media/output /tmp/batch_uploads && \
    touch /app/logs/app.log && \
    touch /app/db.sqlite3 && \
    chown -R appuser:appuser /app/logs /app/db.sqlite3 /app

# Make media and temp directories writable by all users (for uploads)
RUN chmod -R 777 /app/media /app/media/uploads /app/media/output /tmp/batch_uploads 2>/dev/null || true

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY --chown=appuser:appuser . .

USER appuser

# Dev: manage.py runserver | Prod: gunicorn (overridden in compose)
CMD ["gunicorn", "summary_backend.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "5", \
     "--timeout", "120"]
# Default to development server, can be overridden in docker-compose
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]