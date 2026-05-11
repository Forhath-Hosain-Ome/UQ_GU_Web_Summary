(Files content cropped to 300k characters, download full ingest to see more)
================================================
FILE: docker-compose.yaml
================================================
services:
  postgres:
    # image: postgres:16-alpine
    image: postgres:18
    container_name: postgres
    environment:
      - POSTGRES_DB=summary_db
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app_network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512m
  pgadmin:
    image: dpage/pgadmin4
    container_name: pgadmin_container
    restart: unless-stopped
    environment:
      - PGADMIN_DEFAULT_EMAIL=omehasan3@gmail.com
      - PGADMIN_DEFAULT_PASSWORD=admin
    ports:
      - "5050:80"
    networks:
      - app_network
    depends_on:
      - postgres


  redis:
    image: redis:7-alpine
    container_name: redis
    # Don't expose Redis port publicly in production
    # ports: - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app_network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256m

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: backend
    # No port exposure — Nginx proxies to it
    volumes:
      - ./backend/media:/app/media   # persist uploads
      - ./backend/logs:/app/logs     # persist logs
      - batch_uploads:/tmp/batch_uploads  # shared temp storage for celery tasks
    env_file:
      - .env                         # secrets stay out of compose file
    environment:
      - DJANGO_SETTINGS_MODULE=summary_backend.settings
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=summary_db
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    networks:
      - app_network
    command: ["/bin/bash", "/app/entrypoint.sh"]
    restart: unless-stopped

  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: celery-worker
    volumes:
      - ./backend/media:/app/media
      - ./backend/logs:/app/logs
      - batch_uploads:/tmp/batch_uploads  # shared temp storage for celery tasks
    env_file:
      - .env
    environment:
      - DJANGO_SETTINGS_MODULE=summary_backend.settings
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=summary_db
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    command: celery -A summary_backend worker -l info -Q puma_summary,celery,image_processor --concurrency=4
    networks:
      - app_network
    restart: unless-stopped

  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: celery-beat
    volumes:
      - ./backend/logs:/app/logs
    env_file:
      - .env
    environment:
      - DJANGO_SETTINGS_MODULE=summary_backend.settings
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=summary_db
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    command: celery -A summary_backend beat -l info
    networks:
      - app_network
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: frontend
    ports:
      - "8080:80"       # Nginx now listens on 80, not 5173
    depends_on:
      - backend
    networks:
      - app_network
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  batch_uploads:
    driver: local

networks:
  app_network:
    driver: bridge


================================================
FILE: backend/Dockerfile
================================================
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


================================================
FILE: backend/entrypoint.sh
================================================
#!/bin/bash

# 0. Ensure required directories exist with proper permissions
echo "Setting up directories..."
if [ "$(stat -c %u /app/media)" != "1001" ]; then
    chown -R 1001:1001 /app/media /app/logs 2>/dev/null || true
fi

# Create all needed directories (in case they don't exist in mounted volume)
mkdir -p /app/media/uploads/batch_uploads
mkdir -p /app/media/output/defect_image
mkdir -p /app/media/output/puma
mkdir -p /app/media/output/top_five
mkdir -p /app/media/templates
mkdir -p /app/logs/puma_summary
mkdir -p /app/logs/image_processor
mkdir -p /app/logs/final_summary
mkdir -p /app/logs/top_five
mkdir -p /tmp/batch_uploads

# Fix ownership to appuser (UID 1001) - this ensures the container user can write
# Even if volumes are mounted from host with root ownership, this fixes it
chown -R 1001:1001 /app/media /app/logs /tmp/batch_uploads 2>/dev/null || chmod -R 777 /app/media /app/logs /tmp/batch_uploads


# 1. Wait for Postgres to be ready (Prevents migration crashes)
echo "Waiting for database..."
# If you have 'netcat' installed in your Dockerfile, you can use:
# while ! nc -z db 5432; do sleep 1; done

# 2. Run Migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# 3. Create Superuser
# It will use DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD from .env
echo "Creating superuser..."
python manage.py createsuperuser --noinput || echo "Superuser already exists or skip."

python manage.py makemigrations

python manage.py migrate

# 4. Start the server
echo "Starting server..."
exec daphne -b 0.0.0.0 -p 8000 summary_backend.asgi:application


================================================
FILE: backend/manage.py
================================================
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'summary_backend.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()



================================================
FILE: backend/requirements.txt
================================================
aioredis==1.3.1
amqp==5.3.1
asgiref==3.11.1
async-timeout==5.0.1
attrs==26.1.0
autobahn==25.12.2
Automat==25.4.16
billiard==4.2.4
cbor2==5.9.0
celery==5.6.3
certifi==2026.2.25
cffi==2.0.0
channels==3.0.5
channels-redis==3.4.1
charset-normalizer==3.4.6
click==8.3.1
click-didyoumean==0.3.1
click-plugins==1.1.1.2
click-repl==0.3.0
constantly==23.10.4
cron-descriptor==1.4.5
cryptography==46.0.6
daphne==3.0.2
Django==6.0.3
django-celery-beat==2.9.0
django-channels==0.7.0
django-cors-headers==4.9.0
django-timezone-field==7.2.1
djangorestframework==3.17.1
djangorestframework_simplejwt==5.5.1
et_xmlfile==2.0.0
google-api-core==2.30.0
google-api-python-client==2.193.0
google-auth==2.49.1
google-auth-httplib2==0.3.0
google-auth-oauthlib==1.3.0
googleapis-common-protos==1.73.1
gunicorn==25.3.0
hiredis==3.3.1
httplib2==0.31.2
hyperlink==21.0.0
idna==3.11
Incremental==24.11.0
kombu==5.6.2
lxml==6.0.2
msgpack==1.1.2
numpy==2.4.3
oauthlib==3.3.1
openpyxl==3.1.5
packaging==26.0
pandas==3.0.1
pdfminer.six==20251230
pdfplumber==0.11.9
pillow==12.1.1
prompt_toolkit==3.0.52
proto-plus==1.27.2
protobuf==6.33.6
py-ubjson==0.16.1
pyasn1==0.6.3
pyasn1_modules==0.4.2
pycparser==3.0
PyJWT==2.12.1
pyOpenSSL==26.0.0
pyparsing==3.3.2
psycopg2-binary==2.9.10
pypdf==6.9.2
pypdfium2==5.6.0
python-crontab==3.3.0
python-dateutil==2.9.0.post0
python-docx==1.2.0
redis==7.4.0
requests==2.33.0
requests-oauthlib==2.0.0
service-identity==24.2.0
six==1.17.0
sqlparse==0.5.5
Twisted==25.5.0
txaio==25.12.2
typing_extensions==4.15.0
tzdata==2025.3
tzlocal==5.3.1
ujson==5.12.0
uritemplate==4.2.0
urllib3==2.6.3
vine==5.1.0
wcwidth==0.6.0
xlrd==2.0.2
zope.interface==8.2



================================================
FILE: backend/.dockerignore
================================================
.venv


================================================
FILE: backend/final_summary/__init__.py
================================================
[Empty file]


================================================
FILE: backend/final_summary/apps.py
================================================
from django.apps import AppConfig


class FinalSummaryConfig(AppConfig):
    name = 'final_summary'
    verbose_name = "Final Summary"



================================================
FILE: backend/final_summary/consumers.py
================================================
import json
import logging
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class AuditBatchProgressConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.batch_pk   = self.scope["url_route"]["kwargs"]["pk"]
        self.group_name = f"audit_batch_{self.batch_pk}"
        exists = await self._batch_exists(self.batch_pk)
        if not exists:
            await self.close(code=4404)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        snapshot = await self._get_snapshot(self.batch_pk)
        if snapshot:
            await self.send(text_data=json.dumps(snapshot))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass

    async def audit_progress(self, event):
        await self.send(text_data=json.dumps({
            "event": "progress", "batch_id": event["batch_id"],
            "status": event["status"], "stage": event.get("stage", ""),
            "progress_percent": event["progress_percent"],
            "processed": event["processed"], "total": event["total"], "failed": event["failed"],
        }))

    async def audit_complete(self, event):
        await self.send(text_data=json.dumps({
            "event": "complete", "batch_id": event["batch_id"],
            "status": event["status"], "progress_percent": 100,
            "processed": event["processed"], "total": event["total"],
            "failed": event["failed"], "report_count": event.get("report_count", 0),
        }))

    async def audit_error(self, event):
        await self.send(text_data=json.dumps({
            "event": "error", "batch_id": event["batch_id"],
            "status": "FAILED", "error_message": event.get("error_message", "Unknown error"),
        }))

    @database_sync_to_async
    def _batch_exists(self, pk):
        from final_summary.models import UploadBatch
        return UploadBatch.objects.filter(pk=pk).exists()

    @database_sync_to_async
    def _get_snapshot(self, pk):
        from final_summary.models import UploadBatch
        try:
            batch = UploadBatch.objects.get(pk=pk)
        except UploadBatch.DoesNotExist:
            return None
        done = batch.status in (UploadBatch.Status.COMPLETED, UploadBatch.Status.PARTIAL, UploadBatch.Status.FAILED)
        base = {"batch_id": batch.pk, "status": batch.status,
                "progress_percent": batch.progress_percent,
                "processed": batch.processed_files, "total": batch.total_files, "failed": batch.failed_files}
        if done:
            return {**base, "event": "complete", "report_count": batch.reports.count()}
        return {**base, "event": "progress", "stage": ""}


================================================
FILE: backend/final_summary/process.MD
================================================
[Binary file]


================================================
FILE: backend/final_summary/routing.py
================================================
from django.urls import re_path
from final_summary.consumers import AuditBatchProgressConsumer


websocket_urlpatterns = [
    re_path(r"^ws/audit-batches/(?P<pk>\d+)/progress/$", AuditBatchProgressConsumer.as_asgi(),),
]
 


================================================
FILE: backend/final_summary/urls.py
================================================
from django.urls import path
from final_summary.views import (
    AuditUploadView,
    AuditBatchListView,
    AuditBatchDetailView,
    AuditFilterOptionsView,
    AuditExportView,
    AuditRetryView,
    AuditBatchLogsView,
    AuditBatchErrorJsonView,
    AuditReportGenerateView,
)

app_name = "final_summary"

urlpatterns = [
    # ── 1. Bulk upload ─────────────────────────────────────────────────────────
    # POST  multipart/form-data, field "files" (one or many .xlsx/.xls)
    path("upload/",           AuditUploadView.as_view(),        name="upload"),

    # ── 2. Download summary ────────────────────────────────────────────────────
    # GET   ?factory=X&client=Y&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    #       &style=optional&po=optional
    # Returns .xlsx file download
    path("export/",           AuditExportView.as_view(),        name="export"),

    # ── 3. Retry (upload fixed JSON) ───────────────────────────────────────────
    # POST  JSON body: { batch_id: int, records: [...] }
    # Download the error JSON first via GET batches/<pk>/logs/error-json/
    path("retry/",            AuditRetryView.as_view(),          name="retry"),

    # ── Batch tracking ─────────────────────────────────────────────────────────
    path("batches/",          AuditBatchListView.as_view(),     name="batch_list"),
    path("batches/<int:pk>/", AuditBatchDetailView.as_view(),   name="batch_detail"),

    # ── 4. Logs ────────────────────────────────────────────────────────────────
    # GET structured error log
    path("batches/<int:pk>/logs/",            AuditBatchLogsView.as_view(),      name="batch_logs"),
    # GET downloadable error JSON for retry
    path("batches/<int:pk>/logs/error-json/", AuditBatchErrorJsonView.as_view(), name="batch_error_json"),

    # ── Filter options (for export form dropdowns) ─────────────────────────────
    path("options/",          AuditFilterOptionsView.as_view(), name="filter_options"),


    path("top-5", AuditReportGenerateView.as_view(), name="top-5",
    ),
]


================================================
FILE: backend/final_summary/admin/__init__.py
================================================
[Empty file]


================================================
FILE: backend/final_summary/db/__init__.py
================================================
[Empty file]


================================================
FILE: backend/final_summary/db/db_manager.py
================================================
"""
db_manager.py
-------------
All SQLite database operations for the audit extraction system.

Responsibilities
----------------
- Initialise the database (create tables from schema.sql)
- Upsert lookup rows (factories, clients, styles, purchase_orders)
- Insert / update audit_reports and all child tables
- Duplicate detection: block re-insertion of same file_name OR
  same (report_no + date_of_issue) combination
- Query helpers for the Writer script

Usage
-----
    from db.db_manager import DBManager

    db = DBManager("audit.db")
    db.init_db()
    db.save_record(audit_record)
    rows = db.query_records(factory="BABL Factory", client="BABL",
                            start_date="2026-01-01", end_date="2026-03-31")
    db.close()

All public methods wrap their work in a transaction. One bad record never
aborts the batch — errors are logged and re-raised to the caller.
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.audit_record import AuditRecord


# ---------------------------------------------------------------------------
# Date normalisation for DB storage
# ---------------------------------------------------------------------------
# All dates are stored as YYYY-MM-DD so SQLite string comparison works
# correctly for range queries (>= / <=).
# The validator outputs MM/DD/YYYY; we convert here before INSERT.

def _to_iso_date(value: str) -> Optional[str]:
    """
    Convert any recognised date string to YYYY-MM-DD for DB storage.
    Returns None if blank or unparseable.

    Handles every format that Excel / the validator can produce:
      MM/DD/YYYY   01/05/2026  ← validator always outputs this
      YYYY-MM-DD   2026-01-05  ← already ISO
      YYYY/MM/DD   2026/01/05
      DD-MMM-YY    05-Jan-26
      DD-MMM-YYYY  05-Jan-2026
      MM-DD-YYYY   01-05-2026
      YYYY-MM-DD HH:MM:SS  (Excel datetime — time part stripped first)
    """
    if not value or not str(value).strip():
        return None

    from datetime import datetime as _dt

    s = str(value).strip()

    # Strip time component first: "2026-01-05 00:00:00" → "2026-01-05"
    # Handles space-separated and T-separated datetimes
    if len(s) > 10 and (s[10] in (" ", "T")):
        s = s[:10]

    # Try every known format in order of likelihood
    formats = [
        "%m/%d/%Y",   # 01/05/2026  ← validator always outputs this — FIRST
        "%Y-%m-%d",   # 2026-01-05  ← already ISO
        "%Y/%m/%d",   # 2026/01/05
        "%d-%b-%y",   # 05-Jan-26
        "%d-%b-%Y",   # 05-Jan-2026
        "%m-%d-%Y",   # 01-05-2026
        "%d/%m/%Y",   # 05/01/2026  ← LAST (ambiguous with MM/DD/YYYY)
    ]
    for fmt in formats:
        try:
            return _dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return s   # store as-is if nothing matches; never block an insert


# Resolve schema.sql path whether running as a script or frozen exe
if getattr(sys, 'frozen', False):
    # Running inside PyInstaller bundle — schema.sql is in the 'db' subfolder
    _SCHEMA_PATH = Path(sys._MEIPASS) / "db" / "schema.sql"  # type: ignore[attr-defined]
else:
    # Running as plain script — schema.sql is in the same directory as this file
    _SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DBManager:
    """SQLite wrapper for the audit extraction system."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the database connection."""
        self._conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "DBManager":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """
        Create all tables, indexes, triggers, and views from schema.sql.
        Safe to call on an already-initialised database (IF NOT EXISTS).
        Also runs migrate_dates() to normalise any existing non-ISO dates.
        """
        if not _SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found: {_SCHEMA_PATH}")

        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = OFF")
            self.conn.executescript(sql)
            self.conn.execute("PRAGMA foreign_keys = ON")
        logging.info(f"Database initialised: {self.db_path}")

        # Load static defect master data if the file exists next to schema.sql
        _master_path = _SCHEMA_PATH.parent / "defect_master.sql"
        if _master_path.exists():
            master_sql = _master_path.read_text(encoding="utf-8")
            with self.conn:
                self.conn.executescript(master_sql)
            logging.info("Defect master data loaded from defect_master.sql")

        # Add any columns introduced after the DB was first created
        self.migrate_schema()
        # Always normalise dates — safe to run multiple times (idempotent)
        self.migrate_dates()
        # Migrate old defect_items rows into the new normalised tables
        self.migrate_defect_items()

    # ------------------------------------------------------------------
    # Schema migration  (idempotent ALTER TABLE for new columns)
    # ------------------------------------------------------------------

    def migrate_schema(self) -> None:
        """
        Idempotent ALTER TABLE migrations for columns added after the initial
        DB was first created.  Each entry checks whether the column already
        exists before issuing ALTER TABLE, so this is safe to call every startup.
        """
        _MIGRATIONS = [
            # (table, column, column_definition)
            (
                "audit_reports",
                "defect_template_id",
                "INTEGER REFERENCES defect_templates(id) ON DELETE SET NULL",
            ),
            (
                "audit_reports",
                "audit_report_no",
                "TEXT",
            ),
        ]

        existing: dict = {}
        for table, column, definition in _MIGRATIONS:
            if table not in existing:
                rows = self.conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
                existing[table] = {row[1] for row in rows}
            if column not in existing[table]:
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )
                self.conn.commit()
                existing[table].add(column)
                logging.info(
                    f"migrate_schema: added column '{column}' to '{table}'"
                )

    # ------------------------------------------------------------------
    # Defect template matching
    # ------------------------------------------------------------------

    _TEMPLATE_TOLERANCE = 4   # ±4 items counts as a match

    def match_defect_template(self, defect_count: int) -> Optional[int]:
        """
        Given the number of defect items extracted from an Excel file,
        return the matching defect_templates.id (or None if no match).

        Matches within ±TEMPLATE_TOLERANCE of any template's item_count.
        When two templates are equally close, the smaller item_count wins.
        """
        rows = self.conn.execute(
            "SELECT id, item_count FROM defect_templates ORDER BY item_count"
        ).fetchall()

        best_id:   Optional[int] = None
        best_diff: int = self._TEMPLATE_TOLERANCE + 1

        for row in rows:
            diff = abs(defect_count - row["item_count"])
            if diff <= self._TEMPLATE_TOLERANCE and diff < best_diff:
                best_id   = row["id"]
                best_diff = diff

        if best_id:
            logging.info(
                f"  Defect template matched: id={best_id} "
                f"(extracted={defect_count}, tolerance=±{self._TEMPLATE_TOLERANCE})"
            )
        else:
            logging.info(
                f"  No defect template matched for count={defect_count}"
            )
        return best_id
    
    def _ensure_defect_entries_table(self):
        """Ensure defect_entries table exists before trying to insert."""
        try:
            self.conn.execute("SELECT 1 FROM defect_entries LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            # Table doesn't exist - create it
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS defect_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_report_id INTEGER NOT NULL,
                    defect_type_id INTEGER NOT NULL,
                    major INTEGER DEFAULT 0,
                    minor INTEGER DEFAULT 0,
                    comment TEXT,
                    FOREIGN KEY (audit_report_id) REFERENCES audit_reports(id) ON DELETE CASCADE,
                    FOREIGN KEY (defect_type_id) REFERENCES defect_types(id) ON DELETE CASCADE,
                    UNIQUE(audit_report_id, defect_type_id)
                )
            """)
            self.conn.commit()

    def get_defect_item_def_id(
        self,
        template_id: int,
        category_name: str,
        item_name: str,
    ) -> Optional[int]:
        """
        Look up defect_items_def.id for a given template + category + item name.
        Matching is case-insensitive and ignores leading/trailing whitespace.
        Returns None if not found (item will be saved to defect_types/entries
        without a static definition link).
        """
        row = self.conn.execute(
            """
            SELECT did.id
            FROM   defect_items_def  did
            JOIN   defect_categories dc  ON dc.id  = did.category_id
            JOIN   defect_templates  dt  ON dt.id  = dc.template_id
            WHERE  dt.id = ?
              AND  UPPER(TRIM(did.name))        = UPPER(TRIM(?))
            LIMIT 1
            """,
            (template_id, item_name),
        ).fetchone()
        return row["id"] if row else None

    def migrate_dates(self) -> None:
        """
        Convert any date fields stored in non-ISO formats to YYYY-MM-DD.

        Safe to run multiple times — records already in YYYY-MM-DD are
        left unchanged. Covers audit_reports.date_of_issue and all five
        date columns in shipment_dates.
        """
        _DATE_COLS_AUDIT    = ["date_of_issue"]
        _DATE_COLS_SHIPMENT = ["exf", "po_edt", "po_wh", "plan_edt", "plan_wh"]

        fixed_total = 0

        # ── audit_reports ─────────────────────────────────────────────────────
        rows = self.conn.execute(
            "SELECT id, date_of_issue FROM audit_reports "
            "WHERE date_of_issue IS NOT NULL"
        ).fetchall()

        updates = []
        for row in rows:
            original = row["date_of_issue"]
            converted = _to_iso_date(original)
            # Only update if the value actually changed
            if converted and converted != original:
                updates.append((converted, row["id"]))

        if updates:
            with self.conn:
                self.conn.executemany(
                    "UPDATE audit_reports SET date_of_issue = ? WHERE id = ?",
                    updates,
                )
            fixed_total += len(updates)
            logging.info(f"migrate_dates: fixed {len(updates)} audit_reports.date_of_issue rows")

        # ── shipment_dates ────────────────────────────────────────────────────
        for col in _DATE_COLS_SHIPMENT:
            rows = self.conn.execute(
                f"SELECT audit_report_id, {col} FROM shipment_dates "
                f"WHERE {col} IS NOT NULL"
            ).fetchall()

            updates = []
            for row in rows:
                original  = row[col]
                converted = _to_iso_date(original)
                if converted and converted != original:
                    updates.append((converted, row["audit_report_id"]))

            if updates:
                with self.conn:
                    self.conn.executemany(
                        f"UPDATE shipment_dates SET {col} = ? "
                        f"WHERE audit_report_id = ?",
                        updates,
                    )
                fixed_total += len(updates)
                logging.info(
                    f"migrate_dates: fixed {len(updates)} shipment_dates.{col} rows"
                )

        if fixed_total:
            logging.info(f"migrate_dates: total {fixed_total} date value(s) normalised to ISO")
        else:
            logging.debug("migrate_dates: all dates already in ISO format — nothing to do")

    def migrate_defect_items(self) -> None:
        """
        One-time migration: move data from the old defect_items table (if it
        exists and has rows) into the new defect_types + defect_entries tables.

        Safe to run multiple times — already-migrated rows are skipped via
        INSERT OR IGNORE on the UNIQUE constraint of defect_entries.
        Drops defect_items table after all rows are migrated.
        """
        # Check if the old table still exists
        old_exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='defect_items'"
        ).fetchone()
        if not old_exists:
            return

        rows = self.conn.execute(
            "SELECT audit_report_id, category, item, major_count, minor_count, comment "
            "FROM defect_items"
        ).fetchall()

        if not rows:
            # Nothing to migrate — drop the empty table
            with self.conn:
                self.conn.execute("DROP TABLE IF EXISTS defect_items")
            return

        migrated = 0
        with self.conn:
            for row in rows:
                cat     = (row["category"] or "").strip()
                item    = (row["item"] or "").strip()
                major   = int(row["major_count"] or 0)
                minor   = int(row["minor_count"] or 0)
                comment = row["comment"]
                report_id = row["audit_report_id"]

                if not cat or not item:
                    continue

                # Get-or-create defect_type
                self.conn.execute(
                    "INSERT OR IGNORE INTO defect_types (category, item_name, sort_order) "
                    "VALUES (?, ?, 0)",
                    (cat, item),
                )
                type_row = self.conn.execute(
                    "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
                    (cat, item),
                ).fetchone()
                if not type_row:
                    continue
                type_id = type_row["id"]

                # Insert entry (skip if already migrated)
                self.conn.execute(
                    "INSERT OR IGNORE INTO defect_entries "
                    "(audit_report_id, defect_type_id, major, minor, comment) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (report_id, type_id, major, minor, comment),
                )
                migrated += 1

        logging.info(f"migrate_defect_items: migrated {migrated} row(s) into defect_entries")

        # Drop the old table once migration is complete
        with self.conn:
            self.conn.execute("DROP TABLE IF EXISTS defect_items")
        logging.info("migrate_defect_items: defect_items table removed")
    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def is_duplicate(self, file_name: str, report_no: str, date_of_issue: str) -> bool:
        """
        Return True if this audit record already exists in the DB.

        Duplicate criteria (checked separately, either is sufficient):
          1. Same file_name
          2. Same (report_no + date_of_issue) — catches re-named files
        """
        cur = self.conn.cursor()

        # Check 1: file_name
        cur.execute(
            "SELECT 1 FROM audit_reports WHERE file_name = ? LIMIT 1",
            (file_name,),
        )
        if cur.fetchone():
            logging.info(f"Duplicate (file_name): {file_name}")
            return True

        # Check 2: report_no + date_of_issue (normalise to ISO before comparing)
        if report_no and date_of_issue:
            iso = _to_iso_date(date_of_issue) or date_of_issue
            cur.execute(
                "SELECT 1 FROM audit_reports "
                "WHERE report_no = ? AND date_of_issue = ? LIMIT 1",
                (report_no, iso),
            )
            if cur.fetchone():
                logging.info(
                    f"Duplicate (report_no+date): {report_no} / {date_of_issue}"
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Lookup upserts (get-or-create)
    # ------------------------------------------------------------------

    def _upsert_factory(self, name: str) -> int:
        """Return the factory.id for *name*, inserting if necessary."""
        name = (name or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO factories(name) VALUES (?)", (name,)
            )
        row = self.conn.execute(
            "SELECT id FROM factories WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    def _upsert_client(self, name: str) -> int:
        """Return the client.id for *name*, inserting if necessary."""
        name = (name or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO clients(name) VALUES (?)", (name,)
            )
        row = self.conn.execute(
            "SELECT id FROM clients WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    def _upsert_style(
        self,
        client_id: int,
        style_no: str,
        item_name: str,
        country: str,
    ) -> int:
        """Return style.id, inserting or updating item_name/country."""
        style_no = (style_no or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO styles(client_id, style_no, item_name, country)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(style_no) DO UPDATE SET
                    item_name = COALESCE(excluded.item_name, item_name),
                    country   = COALESCE(excluded.country,   country)
                """,
                (client_id, style_no, item_name or None, country or None),
            )
        row = self.conn.execute(
            "SELECT id FROM styles WHERE style_no = ?", (style_no,)
        ).fetchone()
        return row["id"]

    def _upsert_purchase_order(
        self,
        style_id: int,
        po_no: str,
        po_qty_raw: str,
        po_qty_pcs: int,
        po_qty_pack: int,
        po_qty_set: int,
    ) -> Optional[int]:
        """Return po.id, inserting or updating qty fields. Returns None if no po_no."""
        if not po_no or not po_no.strip():
            return None
        po_no = po_no.strip()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO purchase_orders
                    (style_id, po_no, po_qty_raw, po_qty_pcs, po_qty_pack, po_qty_set)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(po_no) DO UPDATE SET
                    po_qty_raw  = COALESCE(excluded.po_qty_raw,  po_qty_raw),
                    po_qty_pcs  = COALESCE(excluded.po_qty_pcs,  po_qty_pcs),
                    po_qty_pack = COALESCE(excluded.po_qty_pack, po_qty_pack),
                    po_qty_set  = COALESCE(excluded.po_qty_set,  po_qty_set)
                """,
                (style_id, po_no, po_qty_raw or None,
                 po_qty_pcs or None, po_qty_pack or None, po_qty_set or None),
            )
        row = self.conn.execute(
            "SELECT id FROM purchase_orders WHERE po_no = ?", (po_no,)
        ).fetchone()
        return row["id"]

    def _upsert_defect_type(self, category: str, item_name: str) -> int:
        """
        Return defect_types.id for the given (category, item_name) pair,
        inserting a new row if one does not already exist.

        sort_order is set to max+1 on first insert so new defect types
        always appear after the pre-seeded master list.
        """
        category  = (category  or "").strip()
        item_name = (item_name or "").strip()

        row = self.conn.execute(
            "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
            (category, item_name),
        ).fetchone()
        if row:
            return row["id"]

        max_row = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM defect_types"
        ).fetchone()
        next_sort = (max_row[0] or 0) + 1

        self.conn.execute(
            """
            INSERT OR IGNORE INTO defect_types (category, item_name, sort_order)
            VALUES (?, ?, ?)
            """,
            (category, item_name, next_sort),
        )

        row = self.conn.execute(
            "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
            (category, item_name),
        ).fetchone()
        return row["id"]

    # ------------------------------------------------------------------
    # Main record save
    # ------------------------------------------------------------------

    def save_record(self, record: AuditRecord) -> Optional[int]:
        """
        Persist a single AuditRecord to the database.

        Returns the new audit_reports.id, or None if:
          - record has blocking_errors  (user must fix via error JSON)
          - record is a duplicate

        Steps:
          1. Blocking check — return None with reason logged
          2. Duplicate check — return None if already present
          3. Upsert lookup rows (factory, client, style, PO)
          4. Detect defect template (28 / 35 / 78)
          5. Insert audit_reports row
          6. Insert audit_times, shipment_dates
          7. Insert defect_entries (linked to static defect_items_def if available)
          8. Insert delivery_orders
          9. Insert validation_errors (soft warnings)
        """
        # 1. Blocking check
        if record.blocking_errors:
            logging.info(
                f"SKIP (blocking errors) [{record.file_name}]: "
                + " | ".join(record.blocking_errors)
            )
            return None

        # 2. Duplicate check
        if self.is_duplicate(record.file_name, record.report_no, record.date_of_issue):
            return None

        # 2. Upsert lookups
        factory_id = self._upsert_factory(record.factory)
        client_id  = self._upsert_client(record.client)
        style_id   = self._upsert_style(
            client_id, record.style_no, record.item_name, record.country
        )
        po_id = self._upsert_purchase_order(
            style_id,
            record.po_no,
            record.po_qty,
            record.po_qty_pcs,
            record.po_qty_pack,
            record.po_qty_set,
        )

        # 4. Detect defect template from defect row count
        defect_count = len([
            d for d in record.defect_rows
            if isinstance(d, dict) and (
                int(d.get("major", 0) or 0) > 0 or
                int(d.get("minor", 0) or 0) > 0
            )
        ])
        # Use total rows (including zero-count) for template matching — the
        # template is determined by the Excel file's column structure, not
        # just the rows that happen to have defects.
        total_defect_rows = len([d for d in record.defect_rows if isinstance(d, dict)])
        template_id = self.match_defect_template(total_defect_rows) if total_defect_rows else None

        # Helper: convert "" to None for DB storage
        def _v(val: Any) -> Any:
            if val == "" or val == "-":
                return None
            return val

        # Helper: parse defect_percentage ("3.71%" → 3.71)
        def _pct(val: str) -> Optional[float]:
            if not val:
                return None
            try:
                return float(str(val).replace("%", "").strip())
            except (ValueError, TypeError):
                return None

        # Helper: safe int
        def _int(val: Any) -> Optional[int]:
            if val is None or val == "":
                return None
            try:
                return int(float(str(val).strip()))
            except (ValueError, TypeError):
                return None

        try:
            with self.conn:
                # 3. Insert audit_reports
                cur = self.conn.execute(
                    """
                    INSERT INTO audit_reports (
                        factory_id, client_id, style_id, po_id,
                        file_name, report_no, audit_report_no,
                        inspection_type, audit_result, date_of_issue,
                        do_qty, ship_qty, audit_qty,
                        defect_qty, acceptable_defect_qty, defect_percentage,
                        inspector, person,
                        carton, needle_detector, remarks, do_set_col_size, do_note,
                        has_validation_errors, defect_template_id
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?
                    )
                    """,
                    (
                        factory_id, client_id, style_id, po_id,
                        record.file_name,
                        _v(record.report_no),
                        _v(record.audit_report),
                        _v(record.inspection_type),
                        _v(record.audit_result) or "-",
                        _to_iso_date(record.date_of_issue),
                        _int(record.do_qty),
                        _int(record.ship_qty),
                        _int(record.audit_qty),
                        _int(record.defect_qty),
                        _v(record.acceptable_defect_qty),
                        _pct(record.defect_percentage),
                        _v(record.inspector),
                        _v(record.person),
                        _v(record.carton),
                        _v(record.needle_detector),
                        _v(record.remarks),
                        _v(record.do_set_col_size),
                        _v(record.do_note),
                        1 if record.validation_errors else 0,
                        template_id,
                    ),
                )
                report_id = cur.lastrowid

                # 4. audit_times
                self.conn.execute(
                    """
                    INSERT INTO audit_times
                        (audit_report_id, factory_in, factory_out, factory_total_hours,
                         audit_start, audit_end, audit_total_hours)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        _v(record.factory_in_time),
                        _v(record.factory_out_time),
                        _v(record.factory_total_hours),
                        _v(record.audit_start_time),
                        _v(record.audit_end_time),
                        _v(record.audit_total_hours),
                    ),
                )

                # shipment_dates
                self.conn.execute(
                    """
                    INSERT INTO shipment_dates
                        (audit_report_id, exf, po_edt, po_wh, plan_edt, plan_wh)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        _to_iso_date(record.exf),
                        _to_iso_date(record.po_edt),
                        _to_iso_date(record.po_wh),
                        _to_iso_date(record.plan_edt),
                        _to_iso_date(record.plan_wh),
                    ),
                )

                # 5. defect_entries (via defect_types lookup/upsert)

                self._ensure_defect_entries_table()
                
                for d in record.defect_rows:
                    if not isinstance(d, dict):
                        continue
                    cat  = (d.get("category") or "").strip()
                    item = (d.get("item") or "").strip()
                    if not cat or not item:
                        continue

                    major   = int(d.get("major", 0) or 0)
                    minor   = int(d.get("minor", 0) or 0)
                    comment = d.get("comment") or None

                    # Skip rows with no data at all
                    if major == 0 and minor == 0 and not comment:
                        continue

                    # Get-or-create the defect_type master row
                    type_id = self._upsert_defect_type(cat, item)

                    # Insert the per-audit entry
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO defect_entries
                            (audit_report_id, defect_type_id, major, minor, comment)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (report_id, type_id, major, minor, comment),
                    )

                # 6. delivery_orders
                for idx, do_row in enumerate(record.do_orders):
                    if not isinstance(do_row, dict):
                        continue
                    self.conn.execute(
                        """
                        INSERT INTO delivery_orders (
                            audit_report_id, do_date, po_qty, do_no, do_qty,
                            ship_qty, audit_qty, do_balance_and_extra, po_balance,
                            remarks, special_note, row_order
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            report_id,
                            do_row.get("date"),
                            do_row.get("po_qty"),
                            do_row.get("do_no"),
                            do_row.get("do_qty"),
                            do_row.get("ship_qty"),
                            do_row.get("audit_qty"),
                            do_row.get("do_balance_and_extra"),
                            do_row.get("po_balance"),
                            do_row.get("remarks"),
                            do_row.get("special_note"),
                            idx,
                        ),
                    )

                # 7. validation_errors
                for err in record.validation_errors:
                    self.conn.execute(
                        "INSERT INTO validation_errors (audit_report_id, error_message) "
                        "VALUES (?, ?)",
                        (report_id, err),
                    )

            logging.info(f"Saved record id={report_id}: {record.file_name}")
            return report_id

        except sqlite3.IntegrityError as exc:
            logging.warning(f"IntegrityError saving {record.file_name}: {exc}")
            return None
        except Exception as exc:
            logging.exception(f"Error saving {record.file_name}: {exc}")
            raise

    # ------------------------------------------------------------------
    # Query helpers (used by Writer script)
    # ------------------------------------------------------------------

    def query_records(
        self,
        factory: str = "",
        client: str = "",
        style: str = "",
        po: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Return audit rows matching the given filters as a list of dicts.

        All parameters are optional; omitting them returns all records.
        Dates should be in 'MM/DD/YYYY' or 'YYYY-MM-DD' format.
        """
        conditions = []
        params: List[Any] = []

        if factory:
            conditions.append("LOWER(factory) LIKE LOWER(?)")
            params.append(f"%{factory}%")

        if client:
            conditions.append("LOWER(client) LIKE LOWER(?)")
            params.append(f"%{client}%")

        if style:
            conditions.append("LOWER(style_no) LIKE LOWER(?)")
            params.append(f"%{style}%")

        if po:
            conditions.append("LOWER(po_no) LIKE LOWER(?)")
            params.append(f"%{po}%")

        if start_date:
            conditions.append("date_of_issue >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("date_of_issue <= ?")
            params.append(end_date)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM v_audit_full {where} ORDER BY date_of_issue, report_id"

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_defect_items(self, report_id: int) -> List[Dict[str, Any]]:
        """Return all defect items for a given audit_reports.id.

        Queries defect_entries + defect_types (current schema) and returns
        legacy-compatible column names used by summary_writer.py:
            audit_report_id, category, item, major_count, minor_count, comment
        """
        rows = self.conn.execute(
            """
            SELECT
                de.audit_report_id,
                dt.category,
                dt.item_name        AS item,
                de.major            AS major_count,
                de.minor            AS minor_count,
                de.comment
            FROM defect_entries de
            JOIN defect_types   dt ON dt.id = de.defect_type_id
            WHERE de.audit_report_id = ?
            ORDER BY dt.sort_order, dt.category, dt.item_name
            """,
            (report_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_defect_items_for_reports(
        self, report_ids: List[int]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Batch-fetch defect items for multiple report IDs.
        Returns {report_id: [defect_item_dict, ...]}
        """
        if not report_ids:
            return {}
        placeholders = ",".join("?" * len(report_ids))
        rows = self.conn.execute(
            f"""
            SELECT
                de.audit_report_id,
                dt.category,
                dt.item_name        AS item,
                de.major            AS major_count,
                de.minor            AS minor_count,
                de.comment
            FROM defect_entries de
            JOIN defect_types   dt ON dt.id = de.defect_type_id
            WHERE de.audit_report_id IN ({placeholders})
            ORDER BY de.audit_report_id, dt.sort_order, dt.category, dt.item_name
            """,
            report_ids,
        ).fetchall()
        result: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            d = dict(r)
            result.setdefault(d["audit_report_id"], []).append(d)
        return result

    def get_all_factories(self) -> List[str]:
        """Return sorted list of all factory names in the DB."""
        rows = self.conn.execute(
            "SELECT name FROM factories ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_all_clients(self) -> List[str]:
        """Return sorted list of all client names in the DB."""
        rows = self.conn.execute(
            "SELECT name FROM clients ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_date_range(self) -> tuple:
        """
        Return (min_date, max_date) of date_of_issue across all records,
        both as YYYY-MM-DD strings. Returns ('', '') if no records exist.
        """
        row = self.conn.execute(
            "SELECT MIN(date_of_issue), MAX(date_of_issue) FROM audit_reports"
        ).fetchone()
        if row and row[0]:
            return row[0], row[1]
        return "", ""


================================================
FILE: backend/final_summary/db/defect_master.sql
================================================
-- =============================================================================
-- defect_master.sql
-- =============================================================================
-- Static defect definitions for the three Excel templates used in production.
--
-- HOW TO USE
-- ----------
-- 1. Fill in the INSERT statements below with your actual defect item names.
-- 2. The names MUST match exactly what appears in your Excel defect tables
--    (the extractor matches by name, case-insensitive).
-- 3. Run this file against your audit.db once:
--      sqlite3 C:\AuditSystem\audit.db < defect_master.sql
-- 4. After that the extractor will auto-match each file to the right template.
--
-- TEMPLATE MATCHING
-- -----------------
-- The extractor counts how many defect columns it extracts from each Excel
-- file and picks the nearest template (tolerance ±4):
--   31 items  →  TEMPLATE_31
--   37 items  →  TEMPLATE_37
--   78 items  →  TEMPLATE_78
-- If no template matches, defect_template_id is left NULL (items still saved).
--
-- CATEGORY CODES
-- --------------
--   A = Fabrics / Materials
--   B = Sewing
--   C = Accessories / Trims
--   D = Finishing / Packing
--   E = Safety / Compliance
--   F = Others
-- =============================================================================

-- Re-runnable (INSERT OR IGNORE so safe to run multiple times)

-- ---------------------------------------------------------------------------
-- Templates
-- ---------------------------------------------------------------------------

INSERT OR IGNORE INTO defect_templates (name, item_count) VALUES ('TEMPLATE_31', 31);
INSERT OR IGNORE INTO defect_templates (name, item_count) VALUES ('TEMPLATE_37', 37);
INSERT OR IGNORE INTO defect_templates (name, item_count) VALUES ('TEMPLATE_78', 78);


-- =============================================================================
-- TEMPLATE_31  (31 items)
-- =============================================================================

-- ── Categories ────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_categories (template_id, code, label, sort_order)
SELECT t31.id, cats.code, cats.label, cats.sort_order
FROM (SELECT id FROM defect_templates WHERE name = 'TEMPLATE_31') t31
CROSS JOIN (
    SELECT 'A' AS code, 'SPEC' AS label, 1 AS sort_order
    UNION ALL SELECT 'B', 'LOOKING FOR FINISH GOOD', 2
    UNION ALL SELECT 'C', 'FABRIC', 3
    UNION ALL SELECT 'D', 'SEWING PROCESS', 4
    UNION ALL SELECT 'E', 'ACCESSORY', 5
    UNION ALL SELECT 'F', 'OTHER', 6
) AS cats;

-- ── Items ─────────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_items_def (category_id, item_no, name, sort_order)
SELECT dc.id, items.item_no, items.name, items.sort_order
FROM defect_categories dc
JOIN defect_templates dt ON dc.template_id = dt.id
CROSS JOIN (
    -- A : SPEC
    SELECT 'A' AS category_code, 1 AS item_no, 'Size Mix サイズ間違い' AS name, 1 AS sort_order
    UNION ALL SELECT 'A', 2, 'Size Label Wrong ラベル間違い', 2
    UNION ALL SELECT 'A', 3, 'Measurement Problem 寸法不良', 3
    -- B : LOOKING FOR FINISH GOOD
    UNION ALL SELECT 'B', 4, 'Bad Looking 形状不良、不対象、段差', 4
    UNION ALL SELECT 'B', 5, 'Shading Problem 仕上げアイロン不良', 5
    UNION ALL SELECT 'B', 6, 'Ironing Problem アタリ、しわ', 6
    UNION ALL SELECT 'B', 7, 'Twist ねじれ', 7
    UNION ALL SELECT 'B', 8, 'Oil Dirty 油汚れ', 8
    UNION ALL SELECT 'B', 9, 'Other Dirty 汚れ、しみ', 9
    -- C : FABRIC
    UNION ALL SELECT 'C', 10, 'Em+Prt. Problem 刺繍、プリント不良', 10
    UNION ALL SELECT 'C', 11, 'Weaving/Knitting Defect 織りキズ、ムラ', 11
    UNION ALL SELECT 'C', 12, 'Hole or Broken Fabric 穴、傷、破れ', 12
    UNION ALL SELECT 'C', 13, 'Dust/Loosed Thread Insert 縫い目笑い', 13
    UNION ALL SELECT 'C', 14, 'Crease Marks リードマーク', 14
    UNION ALL SELECT 'C', 15, 'Dyeing problem 染色むら', 15
    UNION ALL SELECT 'C', 16, 'Strengtheners in Fabric 伸度不足', 16
    -- D : SEWING PROCESS
    UNION ALL SELECT 'D', 17, 'Thread is Broken 縫い糸切れ', 17
    UNION ALL SELECT 'D', 18, 'Seam Defect 縫いはずれ', 18
    UNION ALL SELECT 'D', 19, 'Missing Stitch 縫い忘れ', 19
    UNION ALL SELECT 'D', 20, 'Drop Stitch 縫い落ち', 20
    UNION ALL SELECT 'D', 21, 'Skip Stitch 目飛び', 21
    UNION ALL SELECT 'D', 22, 'Needle Hole 針落ち痕', 22
    UNION ALL SELECT 'D', 23, 'Thread tension loosed 糸調子不良', 23
    UNION ALL SELECT 'D', 24, 'Bad Sewing 縫製不良', 24
    -- E : ACCESSORY
    UNION ALL SELECT 'E', 25, 'Accessory Wrong Attach 付け位置違い', 25
    UNION ALL SELECT 'E', 26, 'Accessory Mistake 取付け不良', 26
    UNION ALL SELECT 'E', 27, 'Accessory Damaging 材質不良', 27
    UNION ALL SELECT 'E', 28, 'Accessory Missing 付け忘れ，脱落', 28
    -- F : OTHER
    UNION ALL SELECT 'F', 29, 'Uncut Thread 糸始末不良', 29
    UNION ALL SELECT 'F', 30, 'QC Sticker Appear シール取り忘れ', 30
    UNION ALL SELECT 'F', 31, 'Others その他', 31
) AS items
WHERE dt.name = 'TEMPLATE_31'
  AND dc.code = items.category_code;


-- =============================================================================
-- TEMPLATE_37  (37 items)
-- =============================================================================

-- ── Categories ────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_categories (template_id, code, label, sort_order)
SELECT t37.id, cats.code, cats.label, cats.sort_order
FROM (SELECT id FROM defect_templates WHERE name = 'TEMPLATE_37') t37
CROSS JOIN (
    SELECT 'A' AS code, '素材不良 Material Defects' AS label, 1 AS sort_order
    UNION ALL SELECT 'B', '縫製不良 Sewing Defects', 2
    UNION ALL SELECT 'C', '付属不良 Trim Defects', 3
    UNION ALL SELECT 'D', '仕上げ不良 Finishing Defects', 4
    UNION ALL SELECT 'E', '他 Others', 5
) AS cats;

-- ── Items ─────────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_items_def (category_id, item_no, name, sort_order)
SELECT dc.id, items.item_no, items.name, items.sort_order
FROM defect_categories dc
JOIN defect_templates dt ON dc.template_id = dt.id
CROSS JOIN (
    SELECT 'A' AS category_code, 1 AS item_no, 'Nep, slub, fly' AS name, 1 AS sort_order
    UNION ALL SELECT 'A', 2, 'Holes, scratches, tears', 2
    UNION ALL SELECT 'A', 3, 'Uneven Dyeing, Color shading,warp/weft streak', 3
    UNION ALL SELECT 'A', 4, 'Poor Texture, Bad handfeel, Bad surface', 4
    UNION ALL SELECT 'A', 5, 'Skew', 5
    UNION ALL SELECT 'A', 6, 'Bad smell/ Odor', 6
    UNION ALL SELECT 'A', 7, 'Other', 7
    UNION ALL SELECT 'B', 8, 'Poor Shape (Bad form), non-symmetrical, dislocation', 8
    UNION ALL SELECT 'B', 9, 'Poor Joining of pattern/ Poor print/embroidery', 9
    UNION ALL SELECT 'B', 10, 'Staggered seams,spirality,wrinkles', 10
    UNION ALL SELECT 'B', 11, 'Puckering, gathered stitching', 11
    UNION ALL SELECT 'B', 12, 'Broken Stitches/ Broken Seam', 12
    UNION ALL SELECT 'B', 13, 'Broken Material ( From Stitching)', 13
    UNION ALL SELECT 'B', 14, 'Insufficient stretch in seams', 14
    UNION ALL SELECT 'B', 15, 'Poor stitch length, poor thred tension', 15
    UNION ALL SELECT 'B', 16, 'Insufficient seam allowance, run-off stitches', 16
    UNION ALL SELECT 'B', 17, 'Needle marks, restitched seams', 17
    UNION ALL SELECT 'B', 18, 'Exposed lining', 18
    UNION ALL SELECT 'B', 19, 'Skipped stitches', 19
    UNION ALL SELECT 'B', 20, 'Sewn by mistake, puckered seams,pleated', 20
    UNION ALL SELECT 'B', 21, 'Missing stitches, missing bartacks', 21
    UNION ALL SELECT 'B', 22, 'Insufficient strength /Bad reinforce stitch', 22
    UNION ALL SELECT 'B', 23, 'Other', 23
    UNION ALL SELECT 'C', 24, 'Poor Quality (faded,burred,rusty,dirty)', 24
    UNION ALL SELECT 'C', 25, 'Poorly attached trim (deformed,damaged)', 25
    UNION ALL SELECT 'C', 26, 'Missing Trim ( detached)', 26
    UNION ALL SELECT 'C', 27, 'Misplaced/ incorrect trim', 27
    UNION ALL SELECT 'C', 28, 'Poorly functioning', 28
    UNION ALL SELECT 'D', 29, 'Bad thread trimming ,lint ( thread end left)', 29
    UNION ALL SELECT 'D', 30, 'Dirty, Stains', 30
    UNION ALL SELECT 'D', 31, 'Poor shape, Bad form, non-symmetrical', 31
    UNION ALL SELECT 'D', 32, 'Shining mark, wrinkles', 32
    UNION ALL SELECT 'D', 33, 'Poor wash Treatment', 33
    UNION ALL SELECT 'D', 34, 'Poor Measurment /wrong Measurement', 34
    UNION ALL SELECT 'E', 35, 'Poor Packaging', 35
    UNION ALL SELECT 'E', 36, 'Wrong quantity Packed', 36
    UNION ALL SELECT 'E', 37, 'Other', 37
) AS items
WHERE dt.name = 'TEMPLATE_37'
  AND dc.code = items.category_code;


-- =============================================================================
-- TEMPLATE_78  (78 items)
-- =============================================================================

-- ── Categories ────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_categories (template_id, code, label, sort_order)
SELECT t78.id, cats.code, cats.label, cats.sort_order
FROM (SELECT id FROM defect_templates WHERE name = 'TEMPLATE_78') t78
CROSS JOIN (
    SELECT 'A' AS code, 'Fabrics' AS label, 1 AS sort_order
    UNION ALL SELECT 'B', 'Sewing', 2
    UNION ALL SELECT 'C', 'ACC', 3
    UNION ALL SELECT 'D', 'Finish', 4
    UNION ALL SELECT 'E', 'Safety', 5
    UNION ALL SELECT 'F', 'Others', 6
) AS cats;

-- ── Items ─────────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_items_def (category_id, item_no, name, sort_order)
SELECT dc.id, items.item_no, items.name, items.sort_order
FROM defect_categories dc
JOIN defect_templates dt ON dc.template_id = dt.id
CROSS JOIN (
    -- A : Fabrics
    SELECT 'A' AS category_code, 1 AS item_no, 'Damage' AS name, 1 AS sort_order
    UNION ALL SELECT 'A', 2, 'Needle breakage defect', 2
    UNION ALL SELECT 'A', 3, 'Hole, tear', 3
    UNION ALL SELECT 'A', 4, 'NEP', 4
    UNION ALL SELECT 'A', 5, 'SLUB', 5
    UNION ALL SELECT 'A', 6, 'Weft defect', 6
    UNION ALL SELECT 'A', 7, 'Unexpected things interwoven', 7
    UNION ALL SELECT 'A', 8, 'Bowing', 8
    UNION ALL SELECT 'A', 9, 'Odor', 9
    UNION ALL SELECT 'A', 10, 'Uneven dyeing', 10
    UNION ALL SELECT 'A', 11, 'Texture, surface defect', 11
    UNION ALL SELECT 'A', 12, 'Warp and weft defect', 12
    -- B : Sewing
    UNION ALL SELECT 'B', 1, 'Hue difference', 13
    UNION ALL SELECT 'B', 2, 'Unevenness', 14
    UNION ALL SELECT 'B', 3, 'Pieces not symmetrical', 15
    UNION ALL SELECT 'B', 4, 'Deformation (Defect in shape)', 16
    UNION ALL SELECT 'B', 5, 'Tight or loose part of fabric', 17
    UNION ALL SELECT 'B', 6, 'Uneven seam', 18
    UNION ALL SELECT 'B', 7, 'Spiralty, wrinkle', 19
    UNION ALL SELECT 'B', 8, 'PUCKERING', 20
    UNION ALL SELECT 'B', 9, 'Corrugation', 21
    UNION ALL SELECT 'B', 10, 'Thread breakage', 22
    UNION ALL SELECT 'B', 11, 'Lack of elasticity', 23
    UNION ALL SELECT 'B', 12, 'Incorrect stitching number', 24
    UNION ALL SELECT 'B', 13, 'Stitches out of seam allowance', 25
    UNION ALL SELECT 'B', 14, 'Missing stitch', 26
    UNION ALL SELECT 'B', 15, 'Lack of seam allowance', 27
    UNION ALL SELECT 'B', 16, 'Unexpected tuck', 28
    UNION ALL SELECT 'B', 17, 'Unexpected fullness', 29
    UNION ALL SELECT 'B', 18, 'Needle mark', 30
    UNION ALL SELECT 'B', 19, 'Sewing defects caused by machine', 31
    UNION ALL SELECT 'B', 20, 'Incorrect size of lining', 32
    UNION ALL SELECT 'B', 21, 'Skipped stitch', 33
    UNION ALL SELECT 'B', 22, 'Sewing involving unexpected parts', 34
    UNION ALL SELECT 'B', 23, 'Missing sewing process', 35
    UNION ALL SELECT 'B', 24, 'Mislocated bar-tack', 36
    UNION ALL SELECT 'B', 25, 'Incorrect thread tension', 37
    UNION ALL SELECT 'B', 26, 'Falling off of a thread', 38
    UNION ALL SELECT 'B', 27, 'Lack of reverse stitch', 39
    UNION ALL SELECT 'B', 28, 'Incorrect easing', 40
    UNION ALL SELECT 'B', 29, 'Piecing defect', 41
    UNION ALL SELECT 'B', 30, 'Incorrect lapped seam', 42
    UNION ALL SELECT 'B', 31, 'Incorrect trimming', 43
    UNION ALL SELECT 'B', 32, 'Lack of strength', 44
    UNION ALL SELECT 'B', 33, 'Incorrect buttonhole sewing', 45
    UNION ALL SELECT 'B', 34, 'Incorrect brand label sewing', 46
    UNION ALL SELECT 'B', 35, 'Sewing slip', 47
    UNION ALL SELECT 'B', 36, 'Incorrect position', 48
    UNION ALL SELECT 'B', 37, 'Incorrect pattern matching', 49
    UNION ALL SELECT 'B', 38, 'Peel off glue/delamination', 50
    UNION ALL SELECT 'B', 39, 'Visible/see through glue', 51
    UNION ALL SELECT 'B', 40, 'Bonding seam uneven/wavy', 52
    UNION ALL SELECT 'B', 41, 'Bonding seam not catch up/bad selvaged', 53
    UNION ALL SELECT 'B', 42, 'Stick glue/leaking glue', 54
    UNION ALL SELECT 'B', 43, 'Mold Shape', 55
    UNION ALL SELECT 'B', 44, 'Poor application glue position', 56
    UNION ALL SELECT 'B', 45, 'Yarn severance', 57
    -- C : ACC
    UNION ALL SELECT 'C', 1, 'Unsecured rivet and snap buttons', 58
    UNION ALL SELECT 'C', 2, 'Incorrect swaging', 59
    UNION ALL SELECT 'C', 3, 'Falling off of buttons', 60
    UNION ALL SELECT 'C', 4, 'Burr', 61
    UNION ALL SELECT 'C', 5, 'Incorrect zippers', 62
    UNION ALL SELECT 'C', 6, 'Incorrect indication of sub materials', 63
    UNION ALL SELECT 'C', 7, 'Incorrect quality of materials', 64
    UNION ALL SELECT 'C', 8, 'Missing accessories', 65
    UNION ALL SELECT 'C', 9, 'Adhesive interlining', 66
    -- D : Finish
    UNION ALL SELECT 'D', 1, 'Dust, lint', 67
    UNION ALL SELECT 'D', 2, 'Smear, stain', 68
    UNION ALL SELECT 'D', 3, 'Size', 69
    UNION ALL SELECT 'D', 4, 'Peel off and misalignment of prints', 70
    UNION ALL SELECT 'D', 5, 'Pressure mark', 71
    UNION ALL SELECT 'D', 6, 'Wash finish', 72
    -- E : Safety
    UNION ALL SELECT 'E', 1, 'Thread', 73
    UNION ALL SELECT 'E', 2, 'Hazardous object/ foreign bodies', 74
    UNION ALL SELECT 'E', 3, 'Odor', 75
    -- F : Others
    UNION ALL SELECT 'F', 1, 'Bad packing', 76
    UNION ALL SELECT 'F', 2, 'Wrong quantity packed', 77
    UNION ALL SELECT 'F', 3, 'Others', 78
) AS items
WHERE dt.name = 'TEMPLATE_78'
  AND dc.code = items.category_code;


================================================
FILE: backend/final_summary/db/schema.sql
================================================
-- =============================================================================
-- AUDIT REPORT DATABASE SCHEMA
-- =============================================================================
-- Database  : PostgreSQL 15+
-- Purpose   : Store extracted audit report data for fast querying by
--             factory, buyer, style, PO number, and date.
--
-- Table Map
-- ---------
--   factories          → one row per unique factory name
--   buyers             → one row per unique buyer/brand (e.g. UNIQLO)
--   styles             → one row per unique style (links to buyer + country)
--   purchase_orders    → one row per PO number (links to style)
--   audit_reports      → core audit record (one per Excel file)
--   audit_times        → factory/audit in-out times (1:1 with audit_reports)
--   shipment_dates     → EXF, PO EDT, PO WH, PLAN EDT, PLAN WH dates
--   defect_items       → one row per defect line (major/minor/comment)
--   delivery_orders    → D.O. plan table rows
--   validation_errors  → any validation errors found during extraction
--
-- Key design decisions
-- --------------------
--   1. Normalised lookup tables (factories, buyers, styles, POs) enable
--      fast JOINs and avoid scanning audit_reports for text matches.
--   2. Composite and partial indexes cover every common query pattern.
--   3. All date columns are DATE type for range queries.
--   4. Percentages stored as NUMERIC(6,3) — e.g. 3.714 for 3.714%.
--   5. Quantities stored as INTEGER; raw extracted string kept in po_qty_raw.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- trigram index for LIKE searches


-- ---------------------------------------------------------------------------
-- LOOKUP TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE factories (
    id          SERIAL      PRIMARY KEY,
    name        TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_factory_name UNIQUE (name)
);
COMMENT ON TABLE factories IS 'One row per unique factory name.';

-- --

CREATE TABLE buyers (
    id          SERIAL      PRIMARY KEY,
    name        TEXT        NOT NULL,    -- e.g. "UNIQLO", "H&M"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_buyer_name UNIQUE (name)
);
COMMENT ON TABLE buyers IS 'One row per unique buyer / brand.';

-- --

CREATE TABLE styles (
    id              SERIAL      PRIMARY KEY,
    buyer_id        INTEGER     NOT NULL REFERENCES buyers (id) ON DELETE RESTRICT,
    style_no        TEXT        NOT NULL,   -- e.g. "04336N068B"
    item_name       TEXT,                   -- e.g. "Premium linen shirt/L/YD"
    country         TEXT,                   -- destination country derived from style prefix
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_style_no UNIQUE (style_no)
);
COMMENT ON TABLE styles IS
    'One row per style number. Linked to buyer. country is derived from '
    'the first 2 characters of style_no (STYLE_COUNTRY_MAP).';

-- --

CREATE TABLE purchase_orders (
    id          SERIAL      PRIMARY KEY,
    style_id    INTEGER     NOT NULL REFERENCES styles (id) ON DELETE RESTRICT,
    po_no       TEXT        NOT NULL,   -- e.g. "P0426-485655-006"
    po_qty_raw  TEXT,                   -- raw extracted string e.g. "1200 PCS"
    po_qty_pcs  INTEGER     DEFAULT 0,
    po_qty_pack INTEGER     DEFAULT 0,
    po_qty_set  INTEGER     DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_po_no UNIQUE (po_no)
);
COMMENT ON TABLE purchase_orders IS
    'One row per PO number. Quantities are split by unit type.';


-- ---------------------------------------------------------------------------
-- CORE AUDIT REPORT TABLE
-- ---------------------------------------------------------------------------

CREATE TABLE audit_reports (
    id                  SERIAL          PRIMARY KEY,
    factory_id          INTEGER         NOT NULL REFERENCES factories (id) ON DELETE RESTRICT,
    style_id            INTEGER         NOT NULL REFERENCES styles (id)    ON DELETE RESTRICT,
    po_id               INTEGER         REFERENCES purchase_orders (id)    ON DELETE SET NULL,

    -- File source
    file_name           TEXT            NOT NULL,

    -- Report identity
    report_no           TEXT,           -- PO-format: P0426-485655-006-1-1
    audit_report_no     TEXT,           -- Report-format: EU26-02CIPL-001
    inspection_type     TEXT,           -- FINAL / RE-FINAL / INLINE / CMF / SAMPLE
    audit_result        TEXT,           -- PASS / FAIL / "-"
    date_of_issue       DATE,

    -- Quantities
    do_qty              INTEGER,
    ship_qty            INTEGER,
    audit_qty           INTEGER,
    defect_qty          INTEGER,
    acceptable_defect_qty INTEGER,
    defect_percentage   NUMERIC(6, 3),  -- e.g. 3.714 (stored without % sign)

    -- Personnel
    inspector           TEXT,
    person              TEXT,

    -- Additional checks
    carton              TEXT,
    needle_detector     TEXT,
    remarks             TEXT,
    do_set_col_size     TEXT,
    do_note             TEXT,

    -- Validation
    has_validation_errors BOOLEAN       NOT NULL DEFAULT FALSE,

    -- Audit trail
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT uq_file_name UNIQUE (file_name)
);
COMMENT ON TABLE audit_reports IS
    'One row per extracted Excel audit file. Central fact table.';


-- ---------------------------------------------------------------------------
-- 1-to-1 EXTENSION TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE audit_times (
    audit_report_id     INTEGER     PRIMARY KEY REFERENCES audit_reports (id) ON DELETE CASCADE,
    factory_in          TIME,
    factory_out         TIME,
    factory_total_hours NUMERIC(5, 2),
    audit_start         TIME,
    audit_end           TIME,
    audit_total_hours   NUMERIC(5, 2)
);
COMMENT ON TABLE audit_times IS
    'Factory in/out and audit start/end times. 1-to-1 with audit_reports.';

-- --

CREATE TABLE shipment_dates (
    audit_report_id     INTEGER     PRIMARY KEY REFERENCES audit_reports (id) ON DELETE CASCADE,
    exf                 DATE,       -- Ex-Factory date
    po_edt              DATE,       -- PO Estimated Delivery
    po_wh               DATE,       -- PO Warehouse / ship date
    plan_edt            DATE,       -- Plan Estimated Delivery
    plan_wh             DATE        -- Plan Warehouse
);
COMMENT ON TABLE shipment_dates IS
    'All 5 shipment-related dates. 1-to-1 with audit_reports.';


-- ---------------------------------------------------------------------------
-- 1-to-MANY CHILD TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE defect_items (
    id              SERIAL      PRIMARY KEY,
    audit_report_id INTEGER     NOT NULL REFERENCES audit_reports (id) ON DELETE CASCADE,
    category        TEXT        NOT NULL,   -- e.g. "B : Sewing"
    item            TEXT        NOT NULL,   -- e.g. "3.Pieces not symmetrical"
    major_count     INTEGER     NOT NULL DEFAULT 0,
    minor_count     INTEGER     NOT NULL DEFAULT 0,
    comment         TEXT
);
COMMENT ON TABLE defect_items IS
    'One row per defect line item with a non-zero count. '
    'Auto-extracted from the Defects table in the Excel sheet.';

-- --

CREATE TABLE delivery_orders (
    id                      SERIAL      PRIMARY KEY,
    audit_report_id         INTEGER     NOT NULL REFERENCES audit_reports (id) ON DELETE CASCADE,
    do_date                 DATE,
    po_qty                  INTEGER,
    do_no                   TEXT,
    do_qty                  INTEGER,
    ship_qty                INTEGER,
    audit_qty               INTEGER,
    do_balance_and_extra    INTEGER,
    po_balance              INTEGER,
    remarks                 TEXT,
    special_note            TEXT,
    row_order               SMALLINT    NOT NULL DEFAULT 0   -- preserves table order
);
COMMENT ON TABLE delivery_orders IS
    'D.O. plan table rows. One row per delivery order line in the Excel sheet.';

-- --

CREATE TABLE validation_errors (
    id              SERIAL      PRIMARY KEY,
    audit_report_id INTEGER     NOT NULL REFERENCES audit_reports (id) ON DELETE CASCADE,
    error_message   TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE validation_errors IS
    'One row per validation error message found for an audit report.';


-- =============================================================================
-- INDEXES
-- =============================================================================

-- factories
CREATE INDEX idx_factories_name_trgm
    ON factories USING gin (name gin_trgm_ops);

-- buyers
CREATE INDEX idx_buyers_name_trgm
    ON buyers USING gin (name gin_trgm_ops);

-- styles
CREATE INDEX idx_styles_buyer_id         ON styles (buyer_id);
CREATE INDEX idx_styles_country          ON styles (country);
CREATE INDEX idx_styles_style_no_trgm
    ON styles USING gin (style_no gin_trgm_ops);

-- purchase_orders
CREATE INDEX idx_po_style_id             ON purchase_orders (style_id);
CREATE INDEX idx_po_no_trgm
    ON purchase_orders USING gin (po_no gin_trgm_ops);

-- audit_reports — the most-queried table
CREATE INDEX idx_ar_factory_id           ON audit_reports (factory_id);
CREATE INDEX idx_ar_style_id             ON audit_reports (style_id);
CREATE INDEX idx_ar_po_id                ON audit_reports (po_id);
CREATE INDEX idx_ar_inspection_type      ON audit_reports (inspection_type);
CREATE INDEX idx_ar_audit_result         ON audit_reports (audit_result);
CREATE INDEX idx_ar_date_of_issue        ON audit_reports (date_of_issue);
CREATE INDEX idx_ar_date_of_issue_desc   ON audit_reports (date_of_issue DESC);
CREATE INDEX idx_ar_has_errors           ON audit_reports (has_validation_errors)
    WHERE has_validation_errors = TRUE;

-- Composite: factory + date (most common dashboard query)
CREATE INDEX idx_ar_factory_date
    ON audit_reports (factory_id, date_of_issue DESC);

-- Composite: style + date
CREATE INDEX idx_ar_style_date
    ON audit_reports (style_id, date_of_issue DESC);

-- Composite: PO + inspection type
CREATE INDEX idx_ar_po_type
    ON audit_reports (po_id, inspection_type);

-- shipment_dates
CREATE INDEX idx_sd_exf       ON shipment_dates (exf);
CREATE INDEX idx_sd_po_edt    ON shipment_dates (po_edt);
CREATE INDEX idx_sd_po_wh     ON shipment_dates (po_wh);
CREATE INDEX idx_sd_plan_edt  ON shipment_dates (plan_edt);
CREATE INDEX idx_sd_plan_wh   ON shipment_dates (plan_wh);

-- defect_items
CREATE INDEX idx_di_audit_report_id  ON defect_items (audit_report_id);
CREATE INDEX idx_di_category         ON defect_items (category);

-- delivery_orders
CREATE INDEX idx_do_audit_report_id  ON delivery_orders (audit_report_id);
CREATE INDEX idx_do_do_date          ON delivery_orders (do_date);

-- validation_errors
CREATE INDEX idx_ve_audit_report_id  ON validation_errors (audit_report_id);


-- =============================================================================
-- TRIGGER: auto-update updated_at on audit_reports
-- =============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_audit_reports_updated_at
    BEFORE UPDATE ON audit_reports
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- VIEWS  (pre-built for common queries)
-- =============================================================================

-- Full flat view: one row per audit report with all lookup names expanded
CREATE OR REPLACE VIEW v_audit_full AS
SELECT
    ar.id                       AS report_id,
    ar.file_name,
    f.name                      AS factory,
    b.name                      AS buyer,
    s.style_no,
    s.item_name,
    s.country,
    po.po_no,
    ar.inspection_type,
    ar.date_of_issue,
    ar.audit_result,
    ar.ship_qty,
    ar.audit_qty,
    ar.defect_qty,
    ar.defect_percentage,
    ar.inspector,
    ar.person,
    sd.exf,
    sd.po_edt,
    sd.po_wh,
    sd.plan_edt,
    sd.plan_wh,
    at_.factory_in,
    at_.factory_out,
    at_.factory_total_hours,
    at_.audit_start,
    at_.audit_end,
    at_.audit_total_hours,
    ar.has_validation_errors,
    ar.created_at
FROM       audit_reports     ar
JOIN       factories         f   ON f.id  = ar.factory_id
JOIN       styles            s   ON s.id  = ar.style_id
JOIN       buyers            b   ON b.id  = s.buyer_id
LEFT JOIN  purchase_orders   po  ON po.id = ar.po_id
LEFT JOIN  shipment_dates    sd  ON sd.audit_report_id = ar.id
LEFT JOIN  audit_times       at_ ON at_.audit_report_id = ar.id;

COMMENT ON VIEW v_audit_full IS
    'Flat denormalized view of every audit report. Use for reports and exports.';

-- --

-- Defect summary per report
CREATE OR REPLACE VIEW v_defect_summary AS
SELECT
    ar.id               AS report_id,
    ar.file_name,
    f.name              AS factory,
    s.style_no,
    ar.date_of_issue,
    ar.inspection_type,
    SUM(di.major_count) AS total_major,
    SUM(di.minor_count) AS total_minor,
    COUNT(di.id)        AS defect_line_count
FROM       audit_reports ar
JOIN       factories     f  ON f.id = ar.factory_id
JOIN       styles        s  ON s.id = ar.style_id
LEFT JOIN  defect_items  di ON di.audit_report_id = ar.id
GROUP BY ar.id, ar.file_name, f.name, s.style_no, ar.date_of_issue, ar.inspection_type;

COMMENT ON VIEW v_defect_summary IS
    'Aggregated major/minor defect counts per audit report.';



================================================
FILE: backend/final_summary/helpers/__init__.py
================================================
[Empty file]


================================================
FILE: backend/final_summary/helpers/extractor_service.py
================================================
import logging
from pathlib import Path

from ..helpers.core.cell_grid import CellGrid
from ..helpers.core.sheet_reader import read_sheet
from ..helpers.extraction.defect_extractor import extract_defect_table_from_file
from ..helpers.extraction.do_table_extractor import extract_do_table_to_record
from ..helpers.extraction.label_config import LABELS
from ..helpers.extraction.post_processor import post_process_record, refine_record
from ..helpers.extraction.rule_extractor import extract_fields
from ..models.audit_record import AuditRecord

logger = logging.getLogger(__name__)


def extract_record(path: Path, sheet_name: str = None) -> AuditRecord:
    """
    Extract and normalise one audit record from an Excel file.

    Parameters
    ----------
    path : Path
        Path to the Excel file.
    sheet_name : str, optional
        Name of the sheet to process. If None or not found, the first sheet is used.
    """
    # Read the specified sheet (or the first sheet if None)
    df = read_sheet(path, sheet_name=sheet_name)
    grid = CellGrid(df)
    extracted_data = extract_fields(grid, LABELS)

    known = set(AuditRecord.__dataclass_fields__.keys())  # type: ignore[attr-defined]
    safe_data = {k: v for k, v in extracted_data.items() if k in known and k != "file_name"}
    record = AuditRecord(file_name=path.name, **safe_data)

    # Extract defect table from the same sheet (or fallback to first sheet)
    defect_rows, defect_totals = extract_defect_table_from_file(path, sheet_name=sheet_name)
    record.defect_rows = defect_rows
    if not record.defect_qty and defect_totals.get("major") is not None:
        record.defect_qty = str(defect_totals["major"])

    record = post_process_record(record, path)
    extract_do_table_to_record(record, path)  # scans all sheets for DO table
    record = refine_record(record)

    logger.info(
        "Processed Excel file %s | sheet=%s | type=%s | client=%s",
        path.name,
        sheet_name if sheet_name else "first",
        record.inspection_type,
        record.client,
    )
    return record



================================================
FILE: backend/final_summary/helpers/summary_writer.py
================================================
[Binary file]


================================================
FILE: backend/final_summary/helpers/validator.py
================================================
"""
validator.py
------------
Multi-layer validation and refinement of AuditRecord objects.

Layers (applied in order)
--------------------------
Layer 1 – DATE STRIPPING
    Date fields must contain a date only.  If the raw value carries a time
    component (e.g. "2026-01-01 10:00:00") the time part is silently stripped
    and only the date is kept.

Layer 2 – DATE FORMATTING
    Accepted dates are normalised to MM/DD/YYYY.

Layer 3 – TIME VALIDATION
    Time fields (factory in/out, audit start/end) must be parseable as
    HH:MM.  Unparseable values → set to "" (null) rather than storing garbage.

Layer 4 – PATTERN VALIDATION
    Report numbers and PO numbers share the same Excel label in some sheets.
    Each field is validated against its expected regex:
      Report No : e.g.  JP26-02BABL-001   ->  [A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+
      PO No     : e.g.  P0426-482649-004  →  P\d{4}-\d{6}-\d{3}(-\d+)*

Layer 5 – BUSINESS RULES
    Mandatory field checks, numeric range validation, etc.

Adding a new validation rule
-----------------------------
1. Write a bool function  f(value) -> bool  (True = valid).
2. Add a tuple  (f, "human-readable error message")  to VALIDATION_RULES[FieldName.XXX].
"""

import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple

from ..models.audit_record import AuditRecord
from ..models.field_enums import FieldName


# ---------------------------------------------------------------------------
# Layer 1 + 2 : Date stripping and formatting
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%m/%d/%Y",  # target format – skip re-formatting if already correct
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%m.%d.%Y",
    "%d.%m.%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y/%d/%m",
    "%Y-%d-%m",
    "%d-%Y-%m",
    "%m/%Y/%d",
    "%d/%Y/%m",
]

# Regex that detects a datetime string with both a date and a time component.
# E.g. "2026-01-01 10:00:00" or "2026-01-01T10:00"
_DATETIME_RE = re.compile(
    r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"   # YYYY-MM-DD …
    r"\d{1,2}[-/]\d{1,2}[-/]\d{4})"       # DD/MM/YYYY …
    r"[\sT]"                               # separator
    r"\d{1,2}[:.]\d{2}"                   # time component
)


def _strip_time_from_date(value: str) -> str:
    """
    If *value* contains both a date and a time component, strip the time.

    "2026-01-01 10:00:00" → "2026-01-01"
    "01/15/2026 09:30"    → "01/15/2026"
    "2026-01-15"          → "2026-01-15"   (unchanged)
    """
    if not value:
        return value
    s = value.strip()
    if _DATETIME_RE.match(s):
        # Keep everything before the first space or T
        stripped = re.split(r"[\sT]", s, maxsplit=1)[0]
        logging.info(f"  date stripped of time component: '{s}' → '{stripped}'")
        return stripped
    return s


def _format_date(date_string: str) -> str:
    """
    Strip any time component, then normalise to MM/DD/YYYY.
    Returns the original string unchanged if no format matches.
    """
    if not isinstance(date_string, str) or not date_string.strip():
        return date_string or ""

    # Layer 1: strip time component
    date_string = _strip_time_from_date(date_string.strip())

    # Layer 2: normalise to MM/DD/YYYY
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_string, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue

    logging.warning(f"Date format not recognised: '{date_string}'")
    return date_string


# ---------------------------------------------------------------------------
# Layer 3 : Time validation
# ---------------------------------------------------------------------------

def _format_time(time_string: str) -> str:
    """
    Convert a loose time string to "HH:MM AM/PM" (12-hour with suffix).
    Returns "" (empty / null) if the value is not a valid time — this
    prevents storing garbage in the time fields.

    Examples
    --------
    "9:30"          → "09:30 AM"
    "14:00"         → "02:00 PM"
    "9.30AM"        → "09:30 AM"
    "2026-01-01..." → ""   (datetime strings are invalid as times)
    """
    if not isinstance(time_string, str) or not time_string.strip():
        return ""

    s = time_string.strip()

    # Reject strings that look like full dates / datetimes
    if re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", s):
        logging.info(
            f"  time field contains datetime '{s}' → set to null"
        )
        return ""

    match = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*([APap][Mm])?", s)
    if not match:
        logging.info(f"  time field '{s}' not parseable → set to null")
        return ""

    hour_str, minute_str, am_pm = match.groups()
    hour   = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        logging.info(
            f"  time field '{s}' out of range → set to null"
        )
        return ""

    if am_pm:
        am_pm_lower = am_pm.lower()
        if am_pm_lower.startswith("p") and hour != 12:
            hour += 12
        elif am_pm_lower.startswith("a") and hour == 12:
            hour = 0

    try:
        return datetime.strptime(f"{hour}:{minute}", "%H:%M").strftime("%I:%M %p")
    except ValueError:
        logging.info(f"  time field '{s}' failed strptime → set to null")
        return ""


# ---------------------------------------------------------------------------
# Layer 4 : Pattern validation helpers
# ---------------------------------------------------------------------------

_REPORT_NO_RE = re.compile(r"^[A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+$")
_PO_NO_RE     = re.compile(r"^P\d{4}-\d{6}-\d{3}(-\d+)*$")


def is_valid_report_no(value: str) -> bool:
    """True if value matches the Report Number pattern (e.g. JP26-02BABL-001)."""
    if not value:
        return False
    return bool(_REPORT_NO_RE.match(value.strip().rstrip(".,;:")))


def is_valid_po_no(value: str) -> bool:
    """True if value matches the PO Number pattern (e.g. P0426-482649-004)."""
    if not value:
        return False
    return bool(_PO_NO_RE.match(value.strip()))


# ---------------------------------------------------------------------------
# Layer 5 : Business rule validators
# ---------------------------------------------------------------------------

def is_not_empty(value: Any) -> bool:
    return bool(str(value).strip())


def is_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return True
    return str(value).strip().replace(".", "", 1).isdigit()


def is_date_mmddyyyy(value: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value.strip(), "%m/%d/%Y")
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Validation rules per field
# ---------------------------------------------------------------------------

ValidationRule = Callable[[Any], bool]
RuleList       = List[Tuple[ValidationRule, str]]

VALIDATION_RULES: Dict[str, RuleList] = {
    FieldName.FACTORY: [
        (is_not_empty, "Factory name should not be empty."),
    ],
    FieldName.DATE_OF_ISSUE: [
        (is_not_empty,    "Date of Issue should not be empty."),
        (is_date_mmddyyyy, "Date of Issue must be in MM/DD/YYYY format."),
    ],
    FieldName.EXF: [
        (is_date_mmddyyyy, "EXF date must be in MM/DD/YYYY format."),
    ],
    FieldName.PO_EDT: [
        (is_date_mmddyyyy, "PO EDT must be in MM/DD/YYYY format."),
    ],
    FieldName.PO_WH: [
        (is_date_mmddyyyy, "PO WH date must be in MM/DD/YYYY format."),
    ],
    FieldName.PLAN_EDT: [
        (is_date_mmddyyyy, "Plan EDT must be in MM/DD/YYYY format."),
    ],
    FieldName.PLAN_WH: [
        (is_date_mmddyyyy, "Plan WH must be in MM/DD/YYYY format."),
    ],
    FieldName.SHIP_QTY: [
        (is_numeric, "Ship Quantity should be a number."),
    ],
    FieldName.AUDIT_QTY: [
        (is_numeric, "Audit Quantity should be a number."),
    ],
    FieldName.REPORT_NO: [
        (
            lambda v: not v or is_valid_report_no(v),
            "Report No does not match expected pattern (e.g. JP26-02BABL-001).",
        ),
    ],
    FieldName.PO_NO: [
        (
            lambda v: not v or is_valid_po_no(v),
            "PO No does not match expected pattern (e.g. P0426-482649-004).",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Refinement map  (field → formatter)
# ---------------------------------------------------------------------------

_REFINEMENT_RULES: Dict[str, Callable[[str], str]] = {
    # Time fields → "HH:MM AM/PM" or "" on failure
    "factory_in_time":  _format_time,
    "factory_out_time": _format_time,
    "audit_start_time": _format_time,
    "audit_end_time":   _format_time,
    # Date fields → "MM/DD/YYYY" (time component stripped first)
    "date_of_issue":    _format_date,
    "exf":              _format_date,
    "po_wh":            _format_date,
    "po_edt":           _format_date,
    "plan_edt":         _format_date,
    "plan_wh":          _format_date,
}


def apply_refinement_rules(record: AuditRecord) -> AuditRecord:
    """Apply date/time formatting to all relevant fields in *record*."""
    for field_name, formatter in _REFINEMENT_RULES.items():
        raw = getattr(record, field_name, None)
        if not raw:
            continue
        refined = formatter(raw)
        if refined != raw:
            logging.info(f"  refined [{field_name}]: '{raw}' → '{refined}'")
        setattr(record, field_name, refined)
    return record


# ---------------------------------------------------------------------------
# Blocking validation  (records that FAIL these are never inserted into DB)
# ---------------------------------------------------------------------------

# Fields that MUST be present for a record to be usable.
# If any of these are missing the record goes to the error JSON instead.
_BLOCKING_REQUIRED_FIELDS: List[Tuple[str, str]] = [
    ("factory",         "Factory name is missing"),
    ("date_of_issue",   "Date of Issue is missing"),
    ("inspection_type", "Inspection Type is missing"),
    ("report_no",       "Report Number is missing"),
    ("ship_qty",        "Shipping Quantity is missing"),
    ("audit_qty",       "Audit Quantity is missing"),
]


def validate_blocking(record: AuditRecord) -> AuditRecord:
    """
    Run blocking validations.  Any failure appends to record.blocking_errors
    and the record will be written to the error JSON and skipped by the DB.

    Checks:
      1. Required fields must not be empty.
      2. Sum of extracted defect major counts must equal record.defect_qty.
         A mismatch means the defect table was not read correctly.
    """
    errors: List[str] = []

    # Check 1: required fields
    for field_key, msg in _BLOCKING_REQUIRED_FIELDS:
        val = getattr(record, field_key, None)
        if not val or not str(val).strip():
            errors.append(f"REQUIRED_FIELD | {field_key} | {msg}")
            logging.warning(f"[{record.file_name}] BLOCKING: {msg}")

    # Check 2: defect count integrity
    if record.defect_qty and record.defect_rows:
        try:
            header_qty = int(str(record.defect_qty).strip())
            extracted_sum = sum(
                int(d.get("major", 0) or 0) + int(d.get("minor", 0) or 0)
                for d in record.defect_rows
                if isinstance(d, dict)
            )
            if header_qty != extracted_sum:
                msg = (
                    f"DEFECT_MISMATCH | "
                    f"header says {header_qty} total defects but "
                    f"extracted defect rows sum to {extracted_sum}"
                )
                errors.append(msg)
                logging.warning(f"[{record.file_name}] BLOCKING: {msg}")
        except (ValueError, TypeError):
            pass   # can't compare — don't block on this

    record.blocking_errors.extend(errors)
    return record


def validate_blocking_all(records: List[AuditRecord]) -> List[AuditRecord]:
    """Apply validate_blocking to every record and return the list."""
    for r in records:
        validate_blocking(r)
    blocked = sum(1 for r in records if r.blocking_errors)
    logging.info(f"Blocking validation: {blocked}/{len(records)} records blocked")
    return records


# ---------------------------------------------------------------------------
# Per-record validation
# ---------------------------------------------------------------------------

def validate_record(record: AuditRecord) -> AuditRecord:
    """
    1. Apply refinement rules (date stripping, date/time formatting).
    2. Run all VALIDATION_RULES and collect error messages.
    Returns the mutated record.
    """
    record = apply_refinement_rules(record)

    errors: List[str] = []

    for field_name, rules in VALIDATION_RULES.items():
        value = getattr(record, field_name, None)
        if not value:
            continue  # only validate fields that were actually extracted
        for rule_fn, error_msg in rules:
            if not rule_fn(value):
                full_msg = f"'{field_name}': {error_msg}"
                errors.append(full_msg)
                logging.warning(
                    f"Validation [{record.file_name}] – {full_msg}"
                )

    record.validation_errors.extend(errors)

    if errors:
        logging.warning(
            f"[{record.file_name}] {len(errors)} validation error(s)"
        )
    else:
        logging.info(f"[{record.file_name}] passed all validations")

    return record


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------

def validate_all_records(records: List[AuditRecord]) -> List[AuditRecord]:
    """
    Validate every record and log a summary.
    Returns the same list with validation_errors populated.
    """
    logging.info("=" * 60)
    logging.info("VALIDATION PHASE")
    logging.info("=" * 60)

    validated = [validate_record(r) for r in records]

    files_with_errors = sum(1 for r in validated if r.validation_errors)
    total_errors      = sum(len(r.validation_errors) for r in validated)

    logging.info(f"Total validated  : {len(records)}")
    logging.info(f"Files with errors: {files_with_errors}")
    logging.info(f"Total errors     : {total_errors}")
    logging.info("=" * 60)

    return validated



================================================
FILE: backend/final_summary/helpers/core/__init__.py
================================================
[Empty file]


================================================
FILE: backend/final_summary/helpers/core/cell_grid.py
================================================
"""
cell_grid.py
------------
Thin wrapper around a pandas DataFrame providing safe zero-based cell access
and label-search helpers used throughout the extraction pipeline.
"""

import re
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd


def normalize_text(value: str) -> str:
    """
    Lowercase, strip, collapse whitespace, and remove non-alphanumeric chars.

    Used for fuzzy label matching so that e.g.:
      "Factory Name:" == "factory name" == "FACTORY NAME"
    """
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class CellGrid:
    """
    Wraps a raw pandas DataFrame (loaded with header=None, dtype=str) and
    exposes safe, boundary-checked cell reads plus label-search utilities.

    Attributes
    ----------
    df    : the underlying DataFrame (NaN replaced with "")
    nrows : row count
    ncols : column count
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df.replace({np.nan: ""})
        self.nrows, self.ncols = self.df.shape

    # ------------------------------------------------------------------
    # Cell access
    # ------------------------------------------------------------------

    def get(self, row: int, col: int) -> str:
        """Return the string value at (row, col), or "" if out of bounds."""
        if row < 0 or col < 0 or row >= self.nrows or col >= self.ncols:
            return ""
        value = self.df.iat[row, col]
        return "" if value is None else str(value).strip()

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_cells(self) -> Iterable[Tuple[int, int, str]]:
        """Yield (row, col, value) for every non-empty cell in reading order."""
        for row in range(self.nrows):
            for col in range(self.ncols):
                value = self.get(row, col)
                if value:
                    yield row, col, value

    # ------------------------------------------------------------------
    # Label searching
    # ------------------------------------------------------------------

    def find_label_positions(self, synonyms: List[str]) -> List[Tuple[int, int, str]]:
        """
        Find all cells whose normalised text exactly matches or starts with
        any of the given synonyms.

        Returns a list of (row, col, raw_cell_value) in discovery order.
        Empty strings in synonyms are silently ignored.
        """
        normalised_synonyms = [normalize_text(s) for s in synonyms if s]

        positions: List[Tuple[int, int, str]] = []

        for row, col, value in self.iter_cells():
            normalised_cell = normalize_text(value)
            for label in normalised_synonyms:
                if not label:
                    continue
                if normalised_cell == label or normalised_cell.startswith(label):
                    positions.append((row, col, value))
                    break

        return positions



================================================
FILE: backend/final_summary/helpers/core/folder_loader.py
================================================
"""
folder_loader.py
----------------
Recursively discovers Excel files starting from a root directory.

Strategy
--------
- Walk the directory tree recursively.
- At each level, if Excel files (.xlsx / .xls) are found, yield them.
- Skips temporary Office lock files (those beginning with "~$").
- Skips the "Summary" output folder to avoid re-processing outputs.

This handles any nesting depth:
  Mother / file.xlsx                         (flat)
  Mother / Month / file.xlsx                 (one level)
  Mother / Month / Date / file.xlsx          (two levels)
  Mother / Factory / Month / Date / file.xlsx (three levels)
"""

from pathlib import Path
from typing import Iterator


# Folder names to always skip during traversal
_SKIP_DIRS = {"summary", "Summary", "__pycache__", ".git"}


def find_xlsx_files(root: Path) -> Iterator[Path]:
    """
    Recursively yield all .xlsx and .xls files under *root*.

    Files are yielded in sorted order per directory for reproducibility.
    Temporary Office lock files (~$...) are silently skipped.
    The "Summary" output folder is excluded from traversal.
    """
    if not root.is_dir():
        return

    for item in sorted(root.iterdir()):
        if item.is_dir():
            if item.name in _SKIP_DIRS:
                continue
            yield from find_xlsx_files(item)

        elif item.is_file():
            if item.name.startswith("~$"):
                continue
            if item.suffix.lower() in (".xlsx", ".xls"):
                yield item


def find_xlsx_files_with_stats(root: Path) -> dict:
    """
    Scan *root* recursively and return a summary dict:
        {
            "files": [Path, ...],
            "total": int,
            "by_folder": {str: [Path, ...]}  # relative folder → files
        }
    """
    files = list(find_xlsx_files(root))
    by_folder: dict = {}

    for f in files:
        rel = str(f.parent.relative_to(root))
        by_folder.setdefault(rel, []).append(f)

    return {
        "files": files,
        "total": len(files),
        "by_folder": by_folder,
    }



================================================
FILE: backend/final_summary/helpers/core/sheet_reader.py
================================================
"""
sheet_reader.py
---------------
Thin wrappers around pandas.read_excel for consistent sheet loading.

All sheets are loaded with:
  - header=None  (no automatic header detection; row 0 is data row 0)
  - dtype=str    (everything comes in as strings; no type guessing)
  - fillna("")   (NaN replaced with empty string for safe .strip() calls)
"""

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd


def read_first_sheet(path: Path) -> pd.DataFrame:
    """
    Load only the first worksheet from *path*.
    Raises on file-read errors (caller is responsible for handling).
    """
    return pd.read_excel(path, sheet_name=0, header=None, dtype=str).fillna("")


def read_sheet(path: Path, sheet_name: Optional[str] = None, skip_rows: int = 0) -> pd.DataFrame:
    """
    Load a specific worksheet from *path*.

    Parameters
    ----------
    path : Path
        Excel file path.
    sheet_name : str, optional
        Name of the sheet to load. If None, loads the first sheet.
    skip_rows : int, optional
        Number of rows to skip from the top before reading data (useful for
        templates where data starts at a specific row).

    Returns
    -------
    pd.DataFrame
    """
    if sheet_name is None:
        return read_first_sheet(path)
    return pd.read_excel(
        path,
        sheet_name=sheet_name,
        header=None,
        dtype=str,
        skiprows=skip_rows if skip_rows > 0 else None,
    ).fillna("")


def read_all_sheets(path: Path) -> List[pd.DataFrame]:
    """
    Load every worksheet from *path* and return them as a list of DataFrames.

    Falls back to reading just the first sheet if multi-sheet loading fails
    (e.g. corrupt or password-protected files).
    """
    try:
        xls = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
        sheets = [df.fillna("") for df in xls.values()]
        logging.info(f"Loaded {len(sheets)} sheet(s) from '{path.name}'")
        return sheets
    except Exception as exc:  # BUG FIX: was 'except Exception:' — exc was unbound
        logging.warning(
            f"Multi-sheet read failed for '{path.name}' ({exc}); "
            "falling back to first sheet only."
        )
        return [read_first_sheet(path)]



================================================
FILE: backend/final_summary/helpers/extraction/__init__.py
================================================
[Empty file]


================================================
FILE: backend/final_summary/helpers/extraction/audit_type_resolver.py
================================================
"""
audit_type_resolver.py
----------------------
Infers the audit type from the Excel *file name* when the sheet itself does
not contain an explicit "Inspection Type" / "Audit Type" label.

Decision tree (evaluated top-to-bottom):
  1. RE-FINAL  (e.g. "2nd time RE-FINAL 50%")
  2. FINAL     (e.g. "FACTORY_FINAL_AUDIT")
  3. INLINE / SAMPLE / CMF  (keyword match, returned as-is)
  4. UNKNOWN   (no keyword matched)

BUG FIXED: RE-FINAL fall-through
----------------------------------
Previously the RE-FINAL branch only returned inside the `if nth_match` block,
so filenames like "RE-FINAL_audit.xlsx" (no ordinal) fell through to the FINAL
branch and were incorrectly typed as "FINAL N%".  Now the function returns
unconditionally from the RE-FINAL branch.
"""

import logging
import re

from ...models.audit_record import AuditRecord
from .label_config import AUDIT_PATTERNS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pct(audit_qty: str, ship_qty: str) -> str:
    """Return 'NN.NN' percentage string, or '' if either quantity is invalid."""
    try:
        pct = round(int(audit_qty) / int(ship_qty) * 100, 2)
        return str(pct)
    except (ValueError, TypeError, ZeroDivisionError):
        logging.warning(
            f"Cannot compute audit % – audit_qty={audit_qty!r}, "
            f"ship_qty={ship_qty!r}"
        )
        return ""


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_audit_type(record: AuditRecord) -> str:
    """
    Derive the inspection type string from the record's file name.

    Returns one of:
      - "NN.NN% RE-FINAL"
      - "NTH TIME NN.NN% RE-FINAL"
      - "NN.NN% FINAL AUDIT"
      - "INLINE" | "SAMPLE" | "CMF"
      - "UNKNOWN"
    """
    if not record.file_name:
        return "UNKNOWN"

    name = record.file_name.lower().strip()

    # ── RE-FINAL ─────────────────────────────────────────────────────────────
    if re.search(AUDIT_PATTERNS["RE-FINAL"], name):
        pct       = _safe_pct(record.audit_qty, record.ship_qty)
        nth_match = re.search(r"\b(\d+(?:st|nd|rd|th))\s+time\b", name)

        if nth_match:
            nth_time = nth_match.group(1).upper()
            return f"{nth_time} RE-FINAL {pct}%" if pct else f"{nth_time} RE-FINAL"

        # BUG FIX: always return from the RE-FINAL branch; never fall through
        return f"RE-FINAL {pct}%" if pct else "RE-FINAL"

    # ── FINAL ─────────────────────────────────────────────────────────────────
    if re.search(AUDIT_PATTERNS["FINAL"], name):
        pct = _safe_pct(record.audit_qty, record.ship_qty)
        return f"FINAL {pct}%" if pct else "FINAL"

    # ── Other known types ─────────────────────────────────────────────────────
    for audit_type in ("INLINE", "SAMPLE", "CMF"):
        if re.search(AUDIT_PATTERNS[audit_type], name):
            return audit_type

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Convenience wrapper used by post_processor
# ---------------------------------------------------------------------------

def extract_and_set_audit_type(record: AuditRecord) -> AuditRecord:
    """
    Set record.inspection_type from the file name if not already populated.
    Returns the (possibly mutated) record.
    """
    if not record.inspection_type:
        record.inspection_type = resolve_audit_type(record)
    return record



================================================
FILE: backend/final_summary/helpers/extraction/defect_extractor.py
================================================
"""
defect_extractor.py
-------------------
Auto-discovers and extracts the structured defect table from an Excel sheet.

Structure understood from samples
----------------------------------
The defect table always follows this layout:

  Row N   : "Defects" | ... | "Major Defect" | "Minor Defect" | "Comment"
  Row N+1 : "A : Fabrics" | "1.Damage" | ...
  ...
  Row M   : "F : Others" | ... | "3.Others" | ...   ← last data row

Detection strategy
------------------
1. Find the header row containing the cell "Defects" in column A.
2. The "Major Defect", "Minor Defect", and "Comment" column indices are
   discovered from that same header row — NO hardcoded columns.
3. Scan downward, carrying the current category (A:Fabrics, B:Sewing …)
   forward across merged/blank category cells.
4. Stop when the cell in column A equals "DO/Set/Col/Size" or when an
   empty row is followed by a non-defect section (robust sentinel).

Output
------
A list of dicts, one per defect item that has at least one non-zero count:

    [
        {
            "category": "B : Sewing",
            "item":     "3.Pieces not symmetrical",
            "major":    1,
            "minor":    0,
            "comment":  "CUFF POINT UP-DOWN",
        },
        ...
    ]

Also returns the totals dict:
    {"major": 9, "minor": 0}

Both are stored on AuditRecord by the caller.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from pathlib import Path


# ---------------------------------------------------------------------------
# Sentinel – the cell value that marks the end of the defect table
# ---------------------------------------------------------------------------

_END_SENTINEL_PATTERN = re.compile(r"do\s*/\s*set\s*/\s*col\s*/\s*size", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: Any) -> int:
    """Convert a cell value to int, returning 0 on failure."""
    if value is None:
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _is_end_sentinel(value: Any) -> bool:
    if value is None:
        return False
    return bool(_END_SENTINEL_PATTERN.search(str(value)))


def _is_category_cell(value: Any) -> bool:
    """True for section-header cells like 'A : Fabrics', 'B : Sewing' etc."""
    if not value:
        return False
    return bool(re.match(r"^[A-F]\s*:", str(value).strip()))


# ---------------------------------------------------------------------------
# Main extractor – uses openpyxl for raw cell access (preserves merged cells)
# ---------------------------------------------------------------------------

def extract_defect_table_from_file(
    path: Path,
    sheet_name: str = "Inspection Report",
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Open *path* with openpyxl and extract the defect table from *sheet_name*.

    Returns
    -------
    (defect_rows, totals)
      defect_rows : list of dicts with keys category/item/major/minor/comment
      totals      : {"major": N, "minor": N}  (summed across all rows)

    Falls back to the first sheet if *sheet_name* is not found.
    """
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        logging.error(f"Cannot open '{path.name}': {exc}")
        return [], {}

    # Resolve sheet
    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        # Try case-insensitive match
        match = next(
            (s for s in wb.sheetnames if s.lower() == sheet_name.lower()), None
        )
        ws = wb[match] if match else wb[wb.sheetnames[0]]

    # Load all rows into a plain list of lists for easy indexing
    rows = list(ws.iter_rows(values_only=True))

    # ── Step 1: Find the header row ─────────────────────────────────────────
    header_row_idx: Optional[int] = None
    major_col: Optional[int] = None
    minor_col: Optional[int] = None
    comment_col: Optional[int] = None

    for r_idx, row in enumerate(rows):
        if row and str(row[0] or "").strip().lower() == "defects":
            header_row_idx = r_idx
            # Discover Major / Minor / Comment column indices
            for c_idx, cell in enumerate(row):
                if cell is None:
                    continue
                normalised = str(cell).strip().lower()
                if "major" in normalised and major_col is None:
                    major_col = c_idx
                elif "minor" in normalised and minor_col is None:
                    minor_col = c_idx
                elif "comment" in normalised and comment_col is None:
                    comment_col = c_idx
            break

    if header_row_idx is None:
        logging.warning(f"[{path.name}] Defect table header ('Defects') not found")
        return [], {}

    if major_col is None:
        logging.warning(f"[{path.name}] 'Major Defect' column not found in header")
        return [], {}

    logging.info(
        f"[{path.name}] Defect table header at row {header_row_idx + 1}; "
        f"major_col={major_col}, minor_col={minor_col}, comment_col={comment_col}"
    )

    # ── Step 2: Scan data rows ───────────────────────────────────────────────
    defect_rows: List[Dict[str, Any]] = []
    current_category: str = ""

    for r_idx in range(header_row_idx + 1, len(rows)):
        row = rows[r_idx]
        col_a = row[0] if row else None

        # Stop at sentinel (DO/Set/Col/Size section)
        if _is_end_sentinel(col_a):
            break

        # Update current category if this row starts a new section
        if _is_category_cell(col_a):
            current_category = str(col_a).strip()

        # Item name is always in column B (index 1)
        item_name = str(row[1]).strip() if (row and row[1] is not None) else ""
        # if not item_name:
        #     continue  # skip blank rows

        major   = _to_int(row[major_col] if major_col < len(row) else None)
        minor   = _to_int(row[minor_col] if minor_col is not None and minor_col < len(row) else None)
        comment = ""
        if comment_col is not None and comment_col < len(row) and row[comment_col]:
            comment = str(row[comment_col]).strip()

        # Only include rows that have at least some defect data
        # if major == 0 and minor == 0 and not comment:
        #     continue

        defect_rows.append({
            "category": current_category,
            "item":     item_name,
            "major":    major,
            "minor":    minor,
            "comment":  comment,
        })

    # ── Step 3: Compute totals ────────────────────────────────────────────────
    totals = {
        "major": sum(r["major"] for r in defect_rows),
        "minor": sum(r["minor"] for r in defect_rows),
    }

    logging.info(
        f"[{path.name}] Defect table: {len(defect_rows)} item(s) with defects; "
        f"totals={totals}"
    )

    wb.close()
    return defect_rows, totals



================================================
FILE: backend/final_summary/helpers/extraction/defect_qty_extractor.py
================================================
"""
defect_qty_extractor.py
-----------------------
Fallback extraction strategy for the defect quantity field.

Primary extraction (via rule_extractor) matches the "Major Defects" header.
If that fails, this module's custom logic scans for the *second* occurrence of
any cell containing the word "major" and reads the integer to its right.

Why second?  Audit sheets typically have:
  Row N   – "Major" as a column *header* in the defect table
  Row M   – "Major" as a *sub-total* row  ← we want this one
"""

import logging
import re
from typing import Tuple, List
from ..core.cell_grid import CellGrid

# ---------------------------------------------------------------------------
# Text helper (local, keeps the module self-contained)
# ---------------------------------------------------------------------------

def _normalize(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

# ---------------------------------------------------------------------------
# Label finder
# ---------------------------------------------------------------------------

def _find_major_labels(grid: CellGrid) -> list[Tuple[int, int, str]]:
    """
    Return all (row, col, raw_value) tuples where the cell contains the
    word "major", sorted top-to-bottom.
    """
    major_labels = []
    
    for row in range(grid.nrows):
        for col in range(grid.ncols):
            cell_val = grid.get(row, col)
            if cell_val and "major" in _normalize(cell_val):
                major_labels.append((row, col, cell_val))
    
    major_labels.sort(key=lambda x: x[0])
    logging.info(f"Found {len(major_labels)} 'Major' labels: {[(r, c, v) for r, c, v in major_labels]}")
    return major_labels

# ---------------------------------------------------------------------------
# Custom (fallback) extractor
# ---------------------------------------------------------------------------

def _extract_defect_qty_custom(grid: CellGrid, known_audit_qty: str = "") -> str:
    """
    Scan for the second "major" occurrence and return the integer value
    found to its right.  Returns "" if not found.
    """
    major_labels = _find_major_labels(grid)
    
    if len(major_labels) < 2:
        logging.warning(f"Found only {len(major_labels)} 'Major' label(s), need at least 2 for fallback")
        return ""

    _, second_major_col, _ = major_labels[1]
    second_row = major_labels[1][0]
    
    # Scan up to 5 cells to the right of the second "Major" cell
    for c in range(second_major_col + 1, min(second_major_col + 6, grid.ncols)):
        raw = grid.get(second_row, c).strip()
        if not raw:
            continue
        try:
            # Accept integers only (defect count should be a whole number)
            int(float(raw))
            return raw
        except (ValueError, TypeError):
            continue
    return ""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_defect_qty_with_fallback(grid: CellGrid, primary_value: str, audit_qty: str = "") -> str:
    """
    Return *primary_value* if it is non-empty; otherwise run the custom
    fallback search and return its result (or "").

    Parameters
    ----------
    grid          : CellGrid for the first sheet
    primary_value : value already found by the standard rule extractor
    """
    if primary_value and primary_value.strip():
        return primary_value
    
    logging.info("defect_qty primary extraction empty – running fallback")
    return _extract_defect_qty_custom(grid, audit_qty)


================================================
FILE: backend/final_summary/helpers/extraction/do_table_extractor.py
================================================
"""
do_table_extractor.py
---------------------
Finds and extracts the Delivery Order (D.O.) plan table from any sheet in
an Excel workbook, then stores the rows directly on AuditRecord.do_orders.

This module is fully config-driven: column headers are discovered by matching
normalised cell text against  DO_TABLE_LABELS  in label_config.py —
no column letters or positions are hardcoded.

Where to make changes
---------------------
- New header spelling       → enums/field_enums.py  (DOLabelSynonym)
                              extraction/label_config.py  (DO_TABLE_LABELS)
- New column                → enums/field_enums.py  (DOFieldName + DOLabelSynonym)
                              extraction/label_config.py  (DO_TABLE_LABELS)
                              _build_do_row() below  (read the new field)
- Fill-down (merged cells)  → extraction/label_config.py  (DO_FILL_DOWN_FIELDS)

Output stored on record
-----------------------
record.do_orders = [
    {
        "date":                 "22-Jan-26",
        "po_qty":               48000,
        "do_no":                "01",
        "do_qty":               48000,
        "ship_qty":             15132,
        "audit_qty":            378,
        "do_balance_and_extra": -32868,
        "po_balance":           -17688,
        "remarks":              "PO & DO BALANCE",
        "special_note":         null
    },
    ...
]
record.do_totals  = {"ship_qty": 30312, "audit_qty": 1636}
record.do_note    = "#OUR INSPECTION CARTON NUMBER: ..."
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..core.cell_grid import CellGrid, normalize_text
from ..core.sheet_reader import read_all_sheets
from .label_config import DO_TABLE_LABELS, DO_FILL_DOWN_FIELDS


# ---------------------------------------------------------------------------
# Row classification helpers
# ---------------------------------------------------------------------------

_TOTAL_KEYWORDS = {"total", "totals", "grand total"}


def _is_total_row(cells: List[str]) -> bool:
    return any(normalize_text(c) in _TOTAL_KEYWORDS for c in cells if c.strip())


def _is_note_row(cells: List[str]) -> bool:
    for c in cells:
        if c.strip():
            return c.strip()[0] in {"#", "*"}
    return False


def _is_special_note(value: str) -> bool:
    """Cells like 'RANDOM FINAL (15,180) PCS' or '1st TIME RE-FINAL AUDIT…'."""
    return bool(re.search(r"(random|re.?final|re.?audit|audit)", value, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Numeric helper
# ---------------------------------------------------------------------------

def _to_int_or_none(value: str) -> Optional[int]:
    if not value or not value.strip():
        return None
    # Strip everything except digits, minus, dot
    cleaned = re.sub(r"[^\d\-\.]", "", value.replace(",", ""))
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _format_date(value: str) -> Optional[str]:
    """Convert '2026-01-22 00:00:00' or datetime objects to '22-Jan-26'."""
    if not value:
        return None
    s = str(value).strip()
    # Already a nice string like "22-Jan-26"
    if re.match(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}", s):
        return s
    # Excel datetime string "2026-01-22 00:00:00"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        from datetime import datetime
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d-%b-%y")
        except ValueError:
            pass
    return s


# ---------------------------------------------------------------------------
# Header discovery  (driven by DO_TABLE_LABELS config)
# ---------------------------------------------------------------------------

def _find_header_row(
    grid: CellGrid,
    min_row_0: int,
    max_row_0: int,
    min_col_0: int,
    max_col_0: int,
) -> Tuple[Optional[int], Dict[str, int]]:
    """
    Scan rows looking for the header row of the D.O. table.
    Matches each cell against every synonym defined in DO_TABLE_LABELS.

    Returns (header_row_0, {field_name: col_index_0}) or (None, {}).
    """
    # Search the full sheet range - table can be anywhere (not just top 5 rows)
    for row in range(min_row_0, max_row_0 + 1):
        col_map: Dict[str, int] = {}

        for col in range(min_col_0, max_col_0 + 1):
            raw = grid.get(row, col)
            if not raw:
                continue
            normalised = normalize_text(raw)

            for field_name, synonyms in DO_TABLE_LABELS.items():
                if field_name in col_map:
                    continue
                for syn in synonyms:
                    syn_str = syn.value if hasattr(syn, "value") else str(syn)
                    if normalised == syn_str or normalised.startswith(syn_str):
                        col_map[field_name] = col
                        logging.debug(
                            f"  DO header: col {col} '{raw}' "
                            f"→ '{field_name}' via '{syn_str}'"
                        )
                        break

        # Valid header: must match at least 4 defined columns
        if len(col_map) >= 4:
            logging.info(
                f"DO table header at row {row}: {dict(col_map)}"
            )
            return row, col_map

    return None, {}


# ---------------------------------------------------------------------------
# Auto-detect which sheet and row range contains the D.O. table
# ---------------------------------------------------------------------------

def _find_do_table_in_sheets(
    all_sheets: List[CellGrid],
) -> Tuple[Optional[CellGrid], Optional[int], Dict[str, int]]:
    """
    Try every sheet until a D.O. header row is found.

    Returns (grid, header_row_0, col_map) or (None, None, {}).
    """
    for grid in all_sheets:
        header_row_0, col_map = _find_header_row(
            grid,
            min_row_0=0,
            max_row_0=grid.nrows - 1,
            min_col_0=0,
            max_col_0=grid.ncols - 1,
        )
        if header_row_0 is not None:
            return grid, header_row_0, col_map

    return None, None, {}


# ---------------------------------------------------------------------------
# Single data-row builder
# ---------------------------------------------------------------------------

def _build_do_row(
    grid: CellGrid,
    row: int,
    col_map: Dict[str, int],
    fill_down: Dict[str, str],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Build one D.O. row dict from grid row *row*.

    fill_down is mutated in place to carry merged-cell values forward.
    Returns (row_dict, special_note_str_or_None).
    """
    def _cell(field: str) -> str:
        col = col_map.get(field)
        return grid.get(row, col).strip() if col is not None else ""

    # ── Update fill-down for merged-cell columns ──────────────────────────────
    for field in DO_FILL_DOWN_FIELDS:
        field_str = field.value if hasattr(field, "value") else str(field)
        raw = _cell(field_str)
        if raw:
            fill_down[field_str] = raw

    # ── Detect special audit note in D.O QTY cell (merged-cell special rows) ─
    do_qty_raw   = _cell("do_qty")
    do_no_raw    = _cell("do_no")
    special_note = None

    if _is_special_note(do_qty_raw):
        special_note = do_qty_raw
        do_qty_raw   = ""
    elif _is_special_note(do_no_raw):
        special_note = do_no_raw
        do_no_raw    = ""

    row_dict: Dict[str, Any] = {
        # Carry-forward (merged) fields
        "date":    _format_date(fill_down.get("date", "")) if fill_down.get("date") else None,
        "po_qty":  _to_int_or_none(fill_down.get("po_qty", "")),

        # Per-row fields
        "do_no":                do_no_raw or None,
        "do_qty":               _to_int_or_none(do_qty_raw),
        "ship_qty":             _to_int_or_none(_cell("ship_qty")),
        "audit_qty":            _to_int_or_none(_cell("audit_qty")),
        "do_balance_and_extra": _to_int_or_none(_cell("do_balance")),
        "po_balance":           _to_int_or_none(_cell("po_balance")),
        "remarks":              _cell("remarks") or None,
        "special_note":         special_note,
    }

    return row_dict, special_note


# ---------------------------------------------------------------------------
# Public API  –  called from main.py / process_file()
# ---------------------------------------------------------------------------

def extract_do_table_to_record(record: Any, path: Any) -> None:
    """
    Find the D.O. plan table anywhere in the workbook, extract all rows,
    and store them on record.do_orders / record.do_totals / record.do_note.

    Parameters
    ----------
    record : AuditRecord  (mutated in place)
    path   : pathlib.Path to the Excel file
    """
    from ..core.cell_grid import CellGrid
    from ..core.sheet_reader import read_all_sheets

    all_dfs   = read_all_sheets(path)
    all_grids = [CellGrid(df) for df in all_dfs]

    grid, header_row_0, col_map = _find_do_table_in_sheets(all_grids)

    if grid is None or header_row_0 is None:
        logging.warning(f"[{record.file_name}] DO table not found in any sheet")
        return

    # ── Walk data rows ────────────────────────────────────────────────────────
    do_orders: List[Dict[str, Any]] = []
    totals:    Dict[str, Any]       = {}
    note:      str                  = ""
    fill_down: Dict[str, str]       = {}

    for row in range(header_row_0 + 1, grid.nrows):
        row_cells = [grid.get(row, c) for c in range(grid.ncols)]
        non_empty = [c for c in row_cells if c.strip()]

        if not non_empty:
            continue

        if _is_note_row(row_cells):
            note = " ".join(non_empty).strip()
            logging.info(f"  DO note: '{note[:80]}...'")
            continue

        if _is_total_row(row_cells):
            def _cell_t(field: str) -> str:
                col = col_map.get(field)
                return grid.get(row, col).strip() if col is not None else ""
            totals = {
                "ship_qty":  _to_int_or_none(_cell_t("ship_qty")),
                "audit_qty": _to_int_or_none(_cell_t("audit_qty")),
            }
            logging.info(f"  DO totals: {totals}")
            continue

        do_row, _ = _build_do_row(grid, row, col_map, fill_down)

        # Skip rows that have absolutely no data
        values = [v for k, v in do_row.items()
                  if k not in ("date", "po_qty") and v is not None]
        if not values:
            continue

        do_orders.append(do_row)
        logging.debug(f"  DO row: {do_row}")

    # ── Store on record ───────────────────────────────────────────────────────
    record.do_orders = do_orders
    record.do_totals = totals if totals else {}
    record.do_note   = note or ""

    logging.info(
        f"[{record.file_name}] DO table: "
        f"{len(do_orders)} row(s), totals={totals}"
    )



================================================
FILE: backend/final_summary/helpers/extraction/label_config.py
================================================
"""
label_config.py
---------------
Central configuration for the extraction system.

This is the PRIMARY place to make changes when:
  - A new Excel format uses different label text  →  add to a LabelSynonym list
  - A label value lives in a different direction →  change DirectionRule
  - A new country code appears                  →  add to STYLE_COUNTRY_MAP
  - A new audit type keyword appears             →  update AUDIT_PATTERNS

Structure of LABELS dict
------------------------
Simple form (default direction = right_then_down):
    FieldName.FOO: [LabelSynonym.A, LabelSynonym.B]

Extended form (custom direction):
    FieldName.FOO: {
        "synonyms":  [LabelSynonym.A, LabelSynonym.B],
        "direction": DirectionRule.RIGHT,          # or a list of rules
    }
"""

from ...models.field_enums import (
    FieldName,
    LabelSynonym,
    DirectionRule,
    AuditPattern,
    StyleCountryPrefix,
)


# ---------------------------------------------------------------------------
# LABELS – field → (synonyms + optional direction rule)
# ---------------------------------------------------------------------------

LABELS: dict = {

    # ── Identity / header ──────────────────────────────────────────────────
    FieldName.FACTORY: [
        LabelSynonym.FACTORY_NAME,
        LabelSynonym.FACTORY,
    ],

    FieldName.DATE_OF_ISSUE: [
        LabelSynonym.DATE_OF_ISSUE,
        LabelSynonym.ISSUE_DATE,
        LabelSynonym.REPORT_DATE,
        LabelSynonym.INSPECTION_DATE,
    ],

    FieldName.INSPECTION_TYPE: [
        LabelSynonym.INSPECTION_TYPE,
        LabelSynonym.AUDIT_TYPE,
    ],

    FieldName.REPORT_NO: [
        LabelSynonym.REPORT_NO,
        LabelSynonym.REPORT_NUMBER,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    FieldName.ITEM_NAME: [
        LabelSynonym.ITEM_NAME,
        LabelSynonym.DESCRIPTION,
    ],

    FieldName.STYLE_NO: [
        LabelSynonym.STYLE_NO,
        LabelSynonym.STYLE_NUMBER,
        LabelSynonym.STYLE,
        LabelSynonym.LOCAL_SAMPLE_CODE,
    ],

    FieldName.PO_NO: [
        LabelSynonym.PO_NO,
        LabelSynonym.PO_NO_DASH,
        LabelSynonym.PURCHASE_ORDER_NO,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    FieldName.AUDIT_REPORT: [
        LabelSynonym.REPORT_NUMBER,
        LabelSynonym.REPORT_NO,
        LabelSynonym.INSPECTION_REPORT_NO,
    ],

    # ── Time fields ────────────────────────────────────────────────────────
    FieldName.FACTORY_IN_TIME: [
        LabelSynonym.FACTORY_IN_TIME,
        LabelSynonym.FACTORY_INTIME2,
        LabelSynonym.FACTORY_INTIME,
        LabelSynonym.IN_TIME,
    ],

    FieldName.FACTORY_OUT_TIME: [
        LabelSynonym.FACTORY_OUT_TIME,
        LabelSynonym.FACTORY_OUTTIME,
        LabelSynonym.FACTORY_OUTTIME2,
        LabelSynonym.OUT_TIME,
    ],

    FieldName.AUDIT_START_TIME: [
        LabelSynonym.AUDIT_START_TIME,
        LabelSynonym.START_TIME,
    ],

    FieldName.AUDIT_END_TIME: [
        LabelSynonym.AUDIT_END_TIME,
        LabelSynonym.END_TIME,
    ],

    # ── Audit outcome ──────────────────────────────────────────────────────
    FieldName.AUDIT_RESULT: [
        LabelSynonym.AUDIT_RESULT,
        LabelSynonym.RESULT,
        LabelSynonym.INSPECTION_RESULT,
    ],

    # ── Quantity fields ────────────────────────────────────────────────────

    # PO Qty: prefer integer value found below the label; fall back to right
    FieldName.PO_QTY: {
        "synonyms": [
            LabelSynonym.PO_QTY,
            LabelSynonym.PO_QUANTITY,
            LabelSynonym.PO_QTY_CAPS,
        ],
        "direction": [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT],
    },
    FieldName.DO_QTY: {
        "synonyms": [
            LabelSynonym.DO_QTY,
            LabelSynonym.DO_QUANTITY,
            LabelSynonym.DO_QTY_CAPS,
        ],
        "direction": [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT],
    },

    # --- Details OF Shipment ---
    # EXF: always to the right
    FieldName.EXF: {
        "synonyms": [
            LabelSynonym.EXF,
            LabelSynonym.EXF_,
            LabelSynonym.EXF__,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PO EDT: always to the right
    FieldName.PO_EDT: {
        "synonyms": [
            LabelSynonym.PO_EDT,
            LabelSynonym._PO_EDT,
            LabelSynonym.PO__EDT,
            LabelSynonym._PO__EDT,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PO W/H (warehouse / ship date): always to the right
    FieldName.PO_WH: {
        "synonyms": [
            LabelSynonym.PO_WH,
            LabelSynonym.WAREHOUSE,
            LabelSynonym.POWH,
            LabelSynonym.PO_WH_SLASH,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PLAN EDT: always to the right
    FieldName.PLAN_EDT: {
        "synonyms": [
            LabelSynonym.PLAN_ETD,
            LabelSynonym.PLAN__ETD,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # PLAN WH: always to the right
    FieldName.PLAN_WH: {
        "synonyms": [
            LabelSynonym.PLAN_WH,
            LabelSynonym.PLAN__WH,
        ],
        "direction": DirectionRule.RIGHT,
    },

    FieldName.SHIP_QTY: [
        LabelSynonym.SHIP_QTY,
        LabelSynonym.SHIPMENT_QTY,
        LabelSynonym.SHIPPING_QUANTITY,
        LabelSynonym.SHIPPING_QTY,
        LabelSynonym.AUDIT_FOR_SHIPPING_QTY,
        LabelSynonym.EXF_QTY,
    ],

    FieldName.AUDIT_QTY: [
        LabelSynonym.AUDIT_QTY,
        LabelSynonym.AUDITED_QUANTITY,
        LabelSynonym.QTY_INSPECTED,
    ],

    # Defect qty from the "Major Defects" column header → value is to the right
    FieldName.DEFECT_QTY: {
        "synonyms": [
            LabelSynonym.MAJOR_DEFECTS,
        ],
        "direction": DirectionRule.RIGHT,
    },

    # ── Personnel ──────────────────────────────────────────────────────────
    FieldName.INSPECTOR: [
        LabelSynonym.INSPECTOR,
    ],


    FieldName.PERSON: [
        LabelSynonym.PERSON,
    ],

    FieldName.CARTON: [
        LabelSynonym.CARTON_INSPECTION,
        LabelSynonym.INSPECTION_CTN,
        LabelSynonym.INSPECTION_CARTON,
        LabelSynonym.OUR_INSPECTION_CARTON,
        LabelSynonym.OUR_INSPECTION_CARTON_NUMBER,
    ],

    FieldName.NEEDLE_DETECTOR: {
        "synonyms": [
            LabelSynonym.NEEDLE_DETECTOR,
            LabelSynonym.NEEDLE_DETECTOR_CHECK,
        ],
        "direction": DirectionRule.DOWN,
    },

    FieldName.REMARKS: {
        "synonyms": [
            LabelSynonym.REMARKS,
            LabelSynonym.REMARK,
        ],
        "direction": DirectionRule.DOWN,
    },
    FieldName.DO_SET_COL_SIZE: {
        "synonyms": [
            LabelSynonym.DO_SET_COL_SIZE,
        ],
        "direction": DirectionRule.DOWN,
    },

    FieldName.CLIENT: [
        LabelSynonym.CLIENT,
        LabelSynonym.CLIENT_NAME,
        LabelSynonym.BUYER,
        LabelSynonym.BUYER_NAME,
    ],
}

# ---------------------------------------------------------------------------
# Style number prefix → destination country
# Update here when new country codes are discovered.
# ---------------------------------------------------------------------------

STYLE_COUNTRY_MAP: dict = {
    StyleCountryPrefix.JAPAN:  "JAPAN",
    StyleCountryPrefix.CHINA:  "CHINA",
    StyleCountryPrefix.USA:    "USA",
    StyleCountryPrefix.KOREA:  "KOREA",
    StyleCountryPrefix.EUROPE: "EUROPE",
    StyleCountryPrefix.TAIWAN: "TAIWAN",
    StyleCountryPrefix.AU:     "AU",
    StyleCountryPrefix.CANADA: "CANADA",
    StyleCountryPrefix.INDIA:  "INDIA",
}


# ---------------------------------------------------------------------------
# Fields that must hold a pure integer after extraction
# (non-numeric text will be stripped by post_processor.clean_numeric_fields)
# ---------------------------------------------------------------------------

NUMERIC_FIELDS: set = {
    FieldName.PO_QTY,
    FieldName.DO_QTY,
    FieldName.SHIP_QTY,
    FieldName.AUDIT_QTY,
}


# ---------------------------------------------------------------------------
# Regex patterns used to infer the audit type from the file name
# ---------------------------------------------------------------------------

AUDIT_PATTERNS: dict = {
    AuditPattern.RE_FINAL: r"re[-\s]?final",
    AuditPattern.FINAL:    r"\bfinal\b",
    AuditPattern.INLINE:   r"inline",
    AuditPattern.SAMPLE:   r"sample",
    AuditPattern.CMF:      r"cmf",
}


# ---------------------------------------------------------------------------
# DO_TABLE_LABELS – column header → synonyms for the D.O. plan table
# ---------------------------------------------------------------------------
# This is the ONLY place you need to change when:
#   - A new Excel format spells a header differently
#     → add the new DOLabelSynonym value and list it here
#   - A new column is added to the D.O. table
#     → add DOFieldName + DOLabelSynonym entries, then add a row below
#
# The engine reads these exactly like LABELS above:
#   key   = DOFieldName  (internal name used in the output JSON)
#   value = list of DOLabelSynonym  (all known text variants for that header)
# ---------------------------------------------------------------------------

from ...models.field_enums import DOFieldName, DOLabelSynonym

DO_TABLE_LABELS: dict = {

    DOFieldName.DATE: [
        DOLabelSynonym.DATE,
    ],

    DOFieldName.PO_QTY: [
        DOLabelSynonym.PO_QTY,
        DOLabelSynonym.P_O_QTY,
        DOLabelSynonym.PO_QUANTITY,
        DOLabelSynonym.P_O_QUANTITY,
    ],

    DOFieldName.DO_NO: [
        DOLabelSynonym.DO_NO,
        DOLabelSynonym.D_O_NO,
        DOLabelSynonym.DO_NUMBER,
        DOLabelSynonym.D_O_NUMBER,
        DOLabelSynonym.DELIVERY_ORDER_NO,
    ],

    DOFieldName.DO_QTY: [
        DOLabelSynonym.DO_QTY,
        DOLabelSynonym.D_O_QTY,
        DOLabelSynonym.DO_QUANTITY,
        DOLabelSynonym.D_O_QUANTITY,
    ],

    DOFieldName.SHIP_QTY: [
        DOLabelSynonym.SHIP_QTY,
        DOLabelSynonym.SHIP_QUANTITY,
        DOLabelSynonym.SHIPMENT_QTY,
        DOLabelSynonym.SHIPMENT_QUANTITY,
    ],

    DOFieldName.AUDIT_QTY: [
        DOLabelSynonym.AUDIT_QTY,
        DOLabelSynonym.AUDIT_QUANTITY,
        DOLabelSynonym.AUDITED_QTY,
    ],

    DOFieldName.DO_BALANCE: [
        DOLabelSynonym.DO_BALANCE,
        DOLabelSynonym.D_O_BALANCE,
        DOLabelSynonym.DO_BALANCE_EXTRA,
        DOLabelSynonym.DO_BALANCE_AND_EXTRA,
        DOLabelSynonym.BALANCE_EXTRA,
    ],

    DOFieldName.PO_EXTRA: [
        DOLabelSynonym.PO_EXTRA,
        DOLabelSynonym.P_O_EXTRA,
    ],

    DOFieldName.REMARKS: [
        DOLabelSynonym.REMARKS,
        DOLabelSynonym.BALANCE_QTY_PLAN,
        DOLabelSynonym.BALANCE_QTY_PLAN_DATE,
        DOLabelSynonym.BALANCE_QTY_PLAN_DATE_REMARKS,
        DOLabelSynonym.PLAN_DATE_REMARKS,
    ],

    DOFieldName.PO_BALANCE: [
        DOLabelSynonym.PO_BALANCE,
        DOLabelSynonym.PO_BAL,
    ],
}

# Columns whose values should be carried forward across merged/empty rows.
# e.g. DATE and PO_QTY span multiple D.O. rows in the same Excel table.
DO_FILL_DOWN_FIELDS: set = {
    DOFieldName.DATE,
    DOFieldName.PO_QTY,
    DOFieldName.PO_EXTRA,
}



================================================
FILE: backend/final_summary/helpers/extraction/post_processor.py
================================================
"""
post_processor.py
-----------------
Derives, cleans, and enriches an AuditRecord *after* raw extraction.

Processing stages (run in order by post_process_record)
--------------------------------------------------------
1.  refine_record       – normalise time strings, strip non-numeric chars
2.  calculate totals    – factory hours / audit hours from start→end times
3.  find_missing_fields – re-scan other sheets for any still-empty fields
4.  refine_record       – clean newly found values
5.  recalculate totals  – if new times were found in stage 3
6.  defect qty fallback – scan summary section for Major Defects total
7.  PO qty routing      – parse "1200 PCS" / "300 SET" into typed fields
8.  defect percentage   – defect_qty / audit_qty * 100
9.  country from style  – first 2 chars of style_no → country code
10. audit type from name– infer inspection_type from the file name
"""

import logging
import re
from dataclasses import fields
from datetime import datetime, timedelta
from pathlib import Path

from ...models.audit_record import AuditRecord
from ..core.sheet_reader import read_all_sheets
from ..core.cell_grid import CellGrid
from .label_config import LABELS, STYLE_COUNTRY_MAP, NUMERIC_FIELDS
from .rule_extractor import extract_fields
from .text_number_extractor import extract_first_number_only
from .defect_qty_extractor import extract_defect_qty_with_fallback
from .audit_type_resolver import resolve_audit_type


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_TIME_FIELDS = (
    "factory_in_time",
    "factory_out_time",
    "audit_start_time",
    "audit_end_time",
)


def _parse_hhmm(time_string: str) -> str:
    """
    Convert a loose time string to strict "HH:MM" (24-hour).
    Accepts: "9:30", "09:30", "9.30", "930", "9:30 AM", "09:30 PM", etc.
    Returns the original string unchanged if parsing fails.
    """
    if not isinstance(time_string, str):
        return ""

    time_string = time_string.strip()
    match = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*([APap][Mm])?", time_string)
    if not match:
        return time_string

    hour_str, minute_str, am_pm = match.groups()
    hour   = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return time_string

    if am_pm:
        am_pm_lower = am_pm.lower()
        if am_pm_lower.startswith("p") and hour != 12:
            hour += 12
        elif am_pm_lower.startswith("a") and hour == 12:
            hour = 0

    try:
        return datetime.strptime(f"{hour}:{minute}", "%H:%M").strftime("%H:%M")
    except ValueError:
        return time_string


def refine_record(record: AuditRecord) -> AuditRecord:
    """
    1. Format all time fields to HH:MM.
    2. Strip non-numeric characters from numeric-only fields.
    """
    for field_name in _TIME_FIELDS:
        raw = getattr(record, field_name, "")
        if raw:
            refined = _parse_hhmm(raw)
            if refined != raw:
                logging.debug(f"  time refined [{field_name}]: '{raw}' → '{refined}'")
            setattr(record, field_name, refined)

    for field_name in NUMERIC_FIELDS:
        raw = getattr(record, field_name, None)
        if raw and isinstance(raw, str):
            cleaned = extract_first_number_only(raw)
            if cleaned and cleaned != raw:
                logging.debug(f"  numeric cleaned [{field_name}]: '{raw}' → '{cleaned}'")
                setattr(record, field_name, cleaned)

    return record


# ---------------------------------------------------------------------------
# Duration calculation
# ---------------------------------------------------------------------------

def _duration_hours(start: str, end: str) -> str | None:
    """
    Return decimal hours between two "HH:MM" strings, or None on error.
    Handles overnight spans (end < start) by adding 24 h.
    """
    try:
        t0 = datetime.strptime(start, "%H:%M")
        t1 = datetime.strptime(end, "%H:%M")
        delta = t1 - t0
        if delta.total_seconds() < 0:
            delta += timedelta(days=1)
        total_minutes = int(delta.total_seconds() // 60)
        hours   = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"
    except ValueError as exc:
        logging.warning(f"Duration calc failed ('{start}' → '{end}'): {exc}")
        return None


# ---------------------------------------------------------------------------
# Missing-field search  (scans all other sheets)
# ---------------------------------------------------------------------------

def find_missing_fields(record: AuditRecord, path: Path) -> None:
    """
    For every still-empty field in *record*, scan all sheets of *path* and
    fill in any values found.  Modifies *record* in place.
    """
    missing = {
        f.name for f in fields(record)
        if not getattr(record, f.name)
        and f.name in LABELS
    }

    if not missing:
        return

    logging.info(f"Searching other sheets for: {missing}")
    targeted = {f: LABELS[f] for f in missing}

    for i, sheet_df in enumerate(read_all_sheets(path)):
        if not targeted:
            break

        grid = CellGrid(sheet_df)
        found = extract_fields(grid, targeted)

        for field_name, value in found.items():
            if value:
                setattr(record, field_name, value)
                del targeted[field_name]
                logging.info(f"  [{field_name}] found in sheet {i + 1}: '{value}'")


# ---------------------------------------------------------------------------
# Defect qty fallback
# ---------------------------------------------------------------------------

def apply_defect_qty_fallback(record: AuditRecord, path: Path) -> None:
    """
    If defect_qty is still empty, run the custom "second Major label" search
    on the first sheet.  Mutates *record* in place.
    """
    if record.defect_qty:
        return

    logging.info("defect_qty empty – running fallback extraction")
    df   = read_all_sheets(path)[0]
    grid = CellGrid(df)

    value = extract_defect_qty_with_fallback(grid, primary_value="")
    if value:
        record.defect_qty = value
        logging.info(f"  defect_qty (fallback): '{value}'")


# ---------------------------------------------------------------------------
# PO quantity routing
# ---------------------------------------------------------------------------

_PO_UNIT_MAP = {
    "pcs":  "po_qty_pcs",
    "pack": "po_qty_pack",
    "set":  "po_qty_set",
}


def apply_po_qty_extraction(record: AuditRecord) -> AuditRecord:
    """
    Parse record.po_qty ("1200 PCS", "300 SET", "500 PACK", bare "1200")
    and write the integer to the correct typed field (po_qty_pcs etc.).
    """
    raw = getattr(record, "po_qty", None)
    if not raw:
        return record

    raw_lower = raw.strip().lower()
    numeric_match = re.search(r"(\d+(?:\.\d+)?)", raw_lower)
    if not numeric_match:
        logging.warning(f"po_qty: no number found in '{raw}'")
        return record

    numeric_value = int(float(numeric_match.group(1)))
    target_field  = "po_qty_pcs"  # default

    for keyword, field_name in _PO_UNIT_MAP.items():
        if keyword in raw_lower:
            target_field = field_name
            break

    setattr(record, target_field, numeric_value)
    logging.debug(f"  po_qty '{raw}' → {target_field}={numeric_value}")
    return record


# ---------------------------------------------------------------------------
# Derived calculations
# ---------------------------------------------------------------------------

def _calc_defect_percentage(record: AuditRecord) -> None:
    """Set record.defect_percentage from defect_qty / audit_qty."""
    try:
        if not record.defect_qty or not record.audit_qty:
            record.defect_percentage = ""
            return

        defect_int = int(str(record.defect_qty).strip())
        audit_int  = int(str(record.audit_qty).strip())

        if audit_int == 0:
            record.defect_percentage = ""
            logging.warning(f"audit_qty=0 → cannot calc defect % for {record.file_name}")
            return

        pct = round(defect_int / audit_int * 100, 2)
        record.defect_percentage = f"{pct}%"

    except (ValueError, TypeError) as exc:
        record.defect_percentage = ""
        logging.warning(f"defect % calc failed for {record.file_name}: {exc}")


def _set_country_from_style(record: AuditRecord) -> None:
    """Derive record.country from the first 2 characters of style_no."""
    style = str(record.style_no).strip()
    if not style or len(style) < 2:
        record.country = "UNKNOWN"
        return
    record.country = STYLE_COUNTRY_MAP.get(style[:2], "UNKNOWN")


# ---------------------------------------------------------------------------
# Master post-processor
# ---------------------------------------------------------------------------

def post_process_record(record: AuditRecord, path: Path) -> AuditRecord:
    """
    Run all enrichment stages on *record* and return the updated record.
    This is the single entry point called from main.py.
    """
    # Stage 1 – normalise times & clean numeric fields
    record = refine_record(record)

    # Stage 2 – derive totals from times found in stage 1
    record.audit_total_hours   = _duration_hours(record.audit_start_time, record.audit_end_time)
    record.factory_total_hours = _duration_hours(record.factory_in_time, record.factory_out_time)

    # Stage 3 – search other sheets for still-missing fields
    find_missing_fields(record, path)

    # Stage 4 – re-clean newly found values
    record = refine_record(record)

    # Stage 5 – recalculate totals if new times were discovered
    if not record.audit_total_hours:
        record.audit_total_hours = _duration_hours(record.audit_start_time, record.audit_end_time)
    if not record.factory_total_hours:
        record.factory_total_hours = _duration_hours(record.factory_in_time, record.factory_out_time)

    # Stage 6 – defect qty fallback
    apply_defect_qty_fallback(record, path)

    # Stage 7 – route PO qty to typed sub-field
    record = apply_po_qty_extraction(record)

    # Stage 8 – calculated metrics
    _calc_defect_percentage(record)

    # Stage 9 – country from style prefix
    _set_country_from_style(record)

    # Stage 10 – inspection type from file name (if not already set)
    if not record.inspection_type:
        record.inspection_type = resolve_audit_type(record)
        logging.info(f"[{record.file_name}] inspection_type → '{record.inspection_type}'")

    return record



================================================
FILE: backend/final_summary/helpers/extraction/proximity.py
================================================
"""
proximity.py
------------
Functions that locate a field's VALUE relative to its LABEL cell.

Core function : resolve_value()
  Given a label position and a direction rule, scans adjacent cells until
  a non-empty string is found.

Special handlers
  resolve_po_wh_value()       – PO W/H date may span 3 cells (MM | DD | YYYY).
  resolve_po_or_report_number() – validates PO vs Report number patterns.
"""

import logging
import re
from typing import Any, List, Tuple

from ..core.cell_grid import CellGrid


# ---------------------------------------------------------------------------
# Type-check helpers
# ---------------------------------------------------------------------------

def is_int(s: str) -> bool:
    """True if *s* can be parsed as an integer."""
    try:
        int(s)
        return True
    except (ValueError, TypeError):
        return False


def is_date_format(s: str) -> bool:
    """True if *s* looks like a complete date (e.g. 12/31/2024)."""
    if not s:
        return False
    return bool(re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$", s.strip()))


def is_valid_month_or_day(value: str) -> bool:
    """True if *value* is an integer in [1, 31] (valid MM or DD)."""
    try:
        return 1 <= int(value.strip()) <= 31
    except (ValueError, TypeError):
        return False


def is_valid_year(value: str) -> bool:
    """True if *value* is a plausible 4-digit year (1900–2100)."""
    try:
        return 1900 <= int(value.strip()) <= 2100
    except (ValueError, TypeError):
        return False


def is_valid_po_no(value: str) -> bool:
    """
    True if *value* matches the PO number pattern.
    Valid: P0726-482920-005  or  P0726-482920-005-1-2
    """
    if not value:
        return False
    return bool(re.match(r"^P\d{4}-\d{6}-\d{3}(?:-\d+)*$", value.strip()))


def is_valid_report_no(value: str) -> bool:
    """
    True if *value* matches the Report number pattern.
    Valid: EU26-02CIPL-001 or EU26-02CIPL-001.
    Strips trailing punctuation before matching.
    """
    if not value:
        return False
    # Strip trailing punctuation (period, comma, etc.)
    cleaned = value.strip().rstrip('.,;:')
    return bool(re.match(r"^[A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+$", cleaned))


# ---------------------------------------------------------------------------
# Inline-value extraction  (e.g. "LABEL: value" in a single cell)
# ---------------------------------------------------------------------------

def find_inline_value(label_text: str, cell_text: str) -> str:
    """
    If *cell_text* contains the label followed by a separator and a value,
    return the value part.  Returns "" otherwise.

    Example
    -------
    label_text = "factory"
    cell_text  = "Factory: ABC Garments Ltd"
    → returns "ABC Garments Ltd"
    """
    if not cell_text or not label_text:
        return ""

    lower_cell  = cell_text.lower().strip()
    lower_label = label_text.lower().strip()

    # Cell is exactly the label — no trailing value
    if lower_cell == lower_label or lower_cell == lower_label.rstrip(":- "):
        return ""

    label_core = lower_label.rstrip(":- ").strip()
    if label_core not in lower_cell:
        return ""

    # Split on the first recognised separator
    for sep in [":", "-", "\u2013", "\u2014"]:  # colon, hyphen, en-dash, em-dash
        if sep in cell_text:
            parts = cell_text.split(sep, 1)
            if len(parts) == 2:
                value = parts[1].strip()
                if value and len(value) > 2:
                    return value

    # Newline-separated inline value
    if "\n" in cell_text or "\r" in cell_text:
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", cell_text) if ln.strip()]
        if len(lines) >= 2 and label_core in lines[0].lower():
            candidate = lines[1].strip()
            if candidate and len(candidate) > 2:
                return candidate

    # Simple "LABEL value" with whitespace separator
    m = re.match(rf"^{re.escape(label_core)}\s+(.+)$", lower_cell, flags=re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        if candidate and len(candidate) > 2:
            return candidate

    return ""


# ---------------------------------------------------------------------------
# Main proximity resolver
# ---------------------------------------------------------------------------

def resolve_value(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    direction_rule: Any = "right_then_down",
) -> str:
    """
    Scan cells adjacent to *label_pos* and return the first non-empty string.

    Parameters
    ----------
    grid          : CellGrid wrapping the sheet
    label_pos     : (row, col) of the label cell (0-based)
    direction_rule: DirectionRule value or list thereof.
                    Supported rules:
                      "right"           – scan right across the same row
                      "down"            – scan down the same column
                      "down_if_int"     – scan down but only accept integers
                      "right_then_down" (default)
                      "down_then_right"

    Returns
    -------
    First non-empty value found, or "" if nothing is found.
    """
    row, col = label_pos

    # Normalise to a list of rule strings
    if isinstance(direction_rule, list):
        rules: List[str] = [
            r.value if hasattr(r, "value") else str(r) for r in direction_rule
        ]
    elif direction_rule in ("right_then_down", "right then down"):
        rules = ["right", "down"]
    elif direction_rule in ("down_then_right", "down then right"):
        rules = ["down", "right"]
    else:
        rule_str = direction_rule.value if hasattr(direction_rule, "value") else str(direction_rule)
        rules = [rule_str]

    for rule in rules:

        if rule == "right":
            for c in range(col + 1, grid.ncols):
                value = grid.get(row, c)
                if value:
                    return value

        elif rule == "down":
            for r in range(row + 1, grid.nrows):
                value = grid.get(r, col)
                if value:
                    return value

        elif rule == "down_if_int":
            for r in range(row + 1, grid.nrows):
                value = grid.get(r, col)
                if value:
                    if is_int(value):
                        return value
                    break  # non-integer → stop looking

    return ""


# ---------------------------------------------------------------------------
# PO / Report number handler
# ---------------------------------------------------------------------------

def resolve_po_or_report_number(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    field_name: str = "audit_report",
) -> str:
    """
    Extract and validate a PO or Report number from cells to the right of the label.

    field_name controls which pattern is accepted:
      "po_no"       → only PO pattern   (P0726-482920-005)
      "report_no"   → only Report pattern (EU26-02CIPL-001)
      "audit_report"→ accept either; fall back to raw value if no pattern matches
    """
    row, col = label_pos
    logging.debug(f"PO_OR_REPORT: resolving '{field_name}' from ({row}, {col})")

    for c in range(col + 1, min(col + 10, grid.ncols)):
        value = grid.get(row, c)
        if not value:
            continue

        value = value.strip()

        if field_name == "po_no":
            if is_valid_po_no(value):
                logging.debug(f"PO_OR_REPORT: PO match → {value}")
                return value

        elif field_name == "report_no":
            # Strip trailing punctuation for validation and return
            cleaned = value.rstrip('.,;:')
            if is_valid_report_no(value):
                logging.debug(f"PO_OR_REPORT: Report match → {cleaned}")
                return cleaned

        elif field_name == "audit_report":
            if is_valid_po_no(value) or is_valid_report_no(value):
                # For report_no matches, strip trailing punctuation
                if is_valid_report_no(value):
                    cleaned = value.rstrip('.,;:')
                    logging.debug(f"PO_OR_REPORT: pattern match → {cleaned}")
                    return cleaned
                logging.debug(f"PO_OR_REPORT: pattern match → {value}")
                return value
            # Fallback: return raw value for audit_report even without a pattern match
            logging.debug(f"PO_OR_REPORT: no pattern, returning raw → {value}")
            return value

    logging.debug(f"PO_OR_REPORT: nothing found to the right for '{field_name}'")
    return ""


# ---------------------------------------------------------------------------
# PO W/H special handler  (date may be split across 3 cells: MM | DD | YYYY)
# ---------------------------------------------------------------------------

def resolve_po_wh_value(grid: CellGrid, label_pos: Tuple[int, int]) -> str:
    """
    Extract the PO W/H (warehouse / ship date) value.

    Handles two formats:
      - Single cell:   "12/31/2024"
      - Split cells:   "12"  |  "31"  |  "2024"  → "12/31/2024"
    """
    row, col = label_pos
    logging.debug(f"PO_WH: resolving from label at ({row}, {col})")

    # Find the first non-empty cell to the right
    first_col = None
    first_val = ""

    for c in range(col + 1, min(col + 10, grid.ncols)):
        val = grid.get(row, c)
        if val:
            first_col = c
            first_val = val.strip()
            break

    if not first_val:
        logging.debug("PO_WH: no value found to the right")
        return ""

    # Format 1: full date already in one cell
    if is_date_format(first_val):
        return first_val

    # Format 2: date split across three cells (MM | DD | YYYY)
    if is_valid_month_or_day(first_val):
        mm = first_val

        second_col = None
        second_val = ""
        for c in range(first_col + 1, min(first_col + 5, grid.ncols)):
            val = grid.get(row, c)
            if val:
                second_col = c
                second_val = val.strip()
                break

        if not second_val or not is_valid_month_or_day(second_val):
            return mm

        dd = second_val

        third_val = ""
        for c in range(second_col + 1, min(second_col + 5, grid.ncols)):
            val = grid.get(row, c)
            if val:
                third_val = val.strip()
                break

        if not third_val or not is_valid_year(third_val):
            return f"{mm}/{dd}"

        result = f"{mm}/{dd}/{third_val}"
        logging.debug(f"PO_WH: reconstructed split date → {result}")
        return result

    # Format 3: non-date value — return as-is
    return first_val



================================================
FILE: backend/final_summary/helpers/extraction/rule_extractor.py
================================================
"""
rule_extractor.py
-----------------
Drives the label-based extraction loop over a CellGrid.

For every field defined in the LABELS config it:
  1. Searches the grid for matching label cell(s).
  2. Tries to read the value inline (same cell, e.g. "Label: Value").
  3. Falls back to proximity search (adjacent cells).
  4. Uses dedicated handlers for special fields (po_wh, po_no, report_no, etc.).

BUG FIXED: Label position reuse across fields
----------------------------------------------
Previously, if two fields shared a synonym (e.g. "report no" matching both
po_no and report_no), the same cell position could be returned for both,
causing the first extracted value to be assigned to both fields.

Fix: a global `used_positions` set tracks every (row, col) already consumed.
Each field only uses positions not yet taken.
"""

import logging
from typing import Any, Dict, Set, Tuple

from ..core.cell_grid import CellGrid
from .proximity import (
    find_inline_value,
    resolve_value,
    resolve_po_wh_value,
    resolve_po_or_report_number,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve(
    grid: CellGrid,
    label_pos: Tuple[int, int],
    direction_rule: Any,
    field_name: str,
) -> str:
    """
    Route value resolution to the correct handler for the given field.
    Wraps exceptions so one bad cell never aborts the whole file.
    """
    try:
        if field_name in ("po_wh", "exf", "po_edt", "plan_edt", "plan_wh"):
            return resolve_po_wh_value(grid, label_pos)

        if field_name in ("po_no", "report_no", "audit_report"):
            return resolve_po_or_report_number(grid, label_pos, field_name)

        return resolve_value(grid, label_pos, direction_rule)

    except Exception as exc:
        logging.warning(
            f"resolve error – field='{field_name}' pos={label_pos}: {exc}"
        )
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_fields(
    grid: CellGrid,
    label_config: Dict[str, Any],
) -> Dict[str, str]:
    """
    Extract all fields specified in *label_config* from *grid*.

    Parameters
    ----------
    grid         : CellGrid for the sheet being processed
    label_config : mapping of  field_name → synonyms  OR
                              field_name → {"synonyms": [...], "direction": ...}

    Returns
    -------
    Dict mapping each field name to the extracted string value (or "").
    """
    extracted: Dict[str, str] = {}

    # Track which label positions have already been consumed by a field.
    # This prevents two fields from reading the same cell as their label.
    used_positions: Set[Tuple[int, int]] = set()

    for field_name, label_info in label_config.items():

        # ── Parse the config entry ────────────────────────────────────────────
        if isinstance(label_info, dict):
            synonyms       = label_info.get("synonyms", [])
            direction_rule = label_info.get("direction", "right_then_down")
        else:
            synonyms       = label_info
            direction_rule = "right_then_down"

        # ── Find where this label appears in the grid ─────────────────────────
        all_positions = grid.find_label_positions(synonyms)

        # Filter out positions already consumed by a previous field
        available_positions = [
            pos for pos in all_positions
            if (pos[0], pos[1]) not in used_positions
        ]

        if not available_positions:
            logging.debug(
                f"No available label for field '{field_name}' "
                f"(synonyms: {synonyms}, already-used: {len(all_positions) - len(available_positions)})"
            )
            extracted[field_name] = ""
            continue

        # ── Try each available position until a non-empty value is found ──────
        value = ""

        for label_row, label_col, label_text in available_positions:

            # Special-case fields that bypass inline extraction entirely
            if field_name == "needle_detector":
                # Use only the configured direction; do NOT check inline
                # to avoid matching patterns like "(Level-08)" in the label.
                value = _resolve(grid, (label_row, label_col), direction_rule, field_name)

            elif field_name in ("report_no", "po_no", "audit_report"):
                value = resolve_po_or_report_number(grid, (label_row, label_col), field_name)

            elif field_name == "po_wh":
                value = resolve_po_wh_value(grid, (label_row, label_col))

            elif field_name == "exf":
                value = resolve_po_wh_value(grid, (label_row, label_col))

            else:
                # 1) Inline: "LABEL: value" packed into the same cell?
                cell_text = grid.get(label_row, label_col)
                for syn in synonyms:
                    syn_text = syn.value if hasattr(syn, "value") else str(syn)
                    value = find_inline_value(syn_text, cell_text)
                    if value:
                        break

                # 2) Proximity: look in adjacent cells
                if not value:
                    value = _resolve(
                        grid, (label_row, label_col), direction_rule, field_name
                    )

            if value:
                # Mark this position as consumed so other fields won't reuse it
                used_positions.add((label_row, label_col))
                break

        extracted[field_name] = value

    return extracted



================================================
FILE: backend/final_summary/helpers/extraction/tabular_extractor.py
================================================
"""
tabular_extractor.py
--------------------
Extracts structured defect data from a rectangular Excel table range.

The caller supplies an Excel range string such as "B4:H38".  This module
converts that to row/column indices, identifies which column holds the
defect category names and which holds the "Major" counts, then reads every
row into a dict.

Column identification strategy (in order of priority)
------------------------------------------------------
1. Look for header cells containing the word "major" in the rows
   immediately above or at the top of the specified range.
2. If no header is found, pick the column with the most numeric values
   (heuristic – usually the major count column).
3. Fall back to the second column in the range.
"""

import logging
from typing import Dict, List, Tuple

from openpyxl.utils import range_boundaries

from ..core.cell_grid import CellGrid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: str) -> int:
    """Convert a string to int, returning 0 on failure."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Column identification
# ---------------------------------------------------------------------------

def _find_major_column(
    grid: CellGrid,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
) -> Tuple[int, int]:
    """
    Return (category_col, major_col) as 0-based column indices.

    Parameters use 1-based Excel coordinates (as returned by range_boundaries).
    """
    # Convert to 0-based for grid access
    min_col_0 = min_col - 1
    max_col_0 = max_col - 1
    min_row_0 = min_row - 1
    num_rows  = max_row - min_row + 1

    category_col = min_col_0   # first column → defect category names
    major_col: int | None = None

    # ── Strategy 1: scan header rows for a cell containing "major" ──────────
    # Check up to 3 rows above the table, plus the first row of the table.
    header_rows = list(range(max(1, min_row - 3), min_row + 1))
    header_rows_0 = [r - 1 for r in header_rows]   # convert to 0-based

    for hr in header_rows_0:
        for col in range(min_col_0, max_col_0 + 1):
            header_val = grid.get(hr, col)
            if header_val and "major" in header_val.strip().lower():
                major_col = col
                break
        if major_col is not None:
            break

    # ── Strategy 2: column with the most numeric values ──────────────────────
    if major_col is None:
        numeric_counts: Dict[int, int] = {}
        for col in range(min_col_0 + 1, max_col_0 + 1):
            count = sum(
                1 for row in range(min_row_0, min_row_0 + num_rows)
                if _is_numeric(grid.get(row, col))
            )
            numeric_counts[col] = count

        if numeric_counts:
            major_col = max(numeric_counts, key=numeric_counts.get)

    # ── Strategy 3: hard fallback ────────────────────────────────────────────
    if major_col is None:
        major_col = min_col_0 + 1

    return category_col, major_col


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_defect_table(
    grid: CellGrid,
    table_range: str,
) -> Dict[str, Dict[str, int]]:
    """
    Parse a rectangular defect table and return a nested dict.

    Return structure
    ----------------
    {
        "Incorrect Sewing": {"major": 3},
        "Wrong Label":      {"major": 1},
        ...
    }

    Parameters
    ----------
    grid        : CellGrid for the sheet containing the table
    table_range : Excel range string, e.g. "B4:H38"

    Returns an empty dict on any parse error.
    """
    if not table_range:
        logging.warning("extract_defect_table: no table_range provided")
        return {}

    # ── Parse range ──────────────────────────────────────────────────────────
    try:
        min_col, min_row, max_col, max_row = range_boundaries(table_range)
    except Exception as exc:
        logging.error(f"Invalid Excel range '{table_range}': {exc}")
        return {}

    if (max_col - min_col + 1) < 3:
        logging.error(
            f"Defect range '{table_range}' must be at least 3 columns wide "
            f"(category + major + minor)."
        )
        return {}

    # ── Identify columns ─────────────────────────────────────────────────────
    category_col, major_col = _find_major_column(
        grid, min_row, max_row, min_col, max_col
    )

    # ── Read data rows ───────────────────────────────────────────────────────
    defects: Dict[str, Dict[str, int]] = {}

    for row_1based in range(min_row, max_row + 1):
        row = row_1based - 1   # convert to 0-based

        category = grid.get(row, category_col)
        if not category or not category.strip():
            continue   # skip blank / header rows

        major_count = _to_int(grid.get(row, major_col))
        defects[category.strip()] = {"major": major_count}

    logging.info(
        f"extract_defect_table: extracted {len(defects)} defect categories "
        f"from range '{table_range}'"
    )
    return defects



================================================
FILE: backend/final_summary/helpers/extraction/text_number_extractor.py
================================================
"""
text_number_extractor.py
------------------------
Utility functions for pulling numeric values out of messy strings.

Common use-case: Excel cells that mix quantity and unit,
e.g. "1,200 PCS" → "1200" or  "3,500 SET" → "3500".
"""

import re
import logging


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def extract_numbers_only(value: str) -> str:
    """
    Extract ALL numbers from *value* and return them space-joined.

    "1,200 PCS + 300 SET" → "1200 300"
    """
    if not value:
        return ""

    value = value.strip()
    matches = re.findall(r"[\d,]+\.?\d*", value)

    if not matches:
        logging.debug(f"No numbers found in: '{value}'")
        return ""

    cleaned = [m.replace(",", "") for m in matches]
    return " ".join(cleaned) if len(cleaned) > 1 else cleaned[0]


def extract_first_number_only(value: str) -> str:
    """
    Extract only the FIRST number from *value*.

    "1,200 PCS" → "1200"
    "PO: 3500"  → "3500"
    """
    if not value:
        return ""

    value = value.strip()
    match = re.search(r"[\d,]+\.?\d*", value)

    if not match:
        logging.debug(f"No number found in: '{value}'")
        return ""

    return match.group().replace(",", "")


def extract_integer_only(value: str) -> str:
    """
    Extract the first contiguous run of *digits* (no decimal point).

    "12.5 hours" → "12"
    "3,500 SET"  → "3"   (use extract_first_number_only if commas matter)
    """
    if not value:
        return ""

    match = re.search(r"\d+", value)
    return match.group() if match else ""


def is_mostly_numeric(value: str) -> bool:
    """Return True if *value* contains at least one digit."""
    return bool(re.search(r"\d", value))



================================================
FILE: backend/final_summary/migrations/__init__.py
================================================
[Empty file]


================================================
FILE: backend/final_summary/models/__init__.py
================================================
from .upload_batch import UploadBatch
from .audit_report import AuditReport
from .defect_entry import DefectEntry


================================================
FILE: backend/final_summary/models/audit_record.py
================================================
"""
audit_record.py
---------------
Data model for a single audit report.

All fields default to sensible empty values so the object can be created
immediately after extraction without every value being present.

Notes
-----
- `po_qty` holds the *raw* extracted string (e.g. "1,200 PCS").
  Processed integers live in po_qty_pcs / po_qty_pack / po_qty_set.

- `client` is extracted from the Excel using the label "client".  It maps
  to the buyers/clients table in the DB and the factory+client combination
  determines the output Excel filename.

- `defect_rows` is the structured defect list (auto-discovered from sheet).
  Each element is:
      {"category": "B : Sewing", "item": "3.Pieces not symmetrical",
       "major": 1, "minor": 0, "comment": "CUFF POINT UP-DOWN"}

- `validation_errors` is serialised as a comma-joined string in to_dict().
"""

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List


@dataclass
class AuditRecord:
    """Represents one audit report extracted from an Excel file."""

    # Source
    file_name: str

    # Identity / header
    factory:         str = ""
    client :         str = ""
    date_of_issue:   str = ""   # normalised to MM/DD/YYYY by validator
    inspection_type: str = ""
    report_no:       str = ""
    audit_report:    str = ""
    item_name:       str = ""
    style_no:        str = ""
    po_no:           str = ""
    country:         str = ""

    # Time fields
    factory_in_time:     str = ""
    factory_out_time:    str = ""
    factory_total_hours: str = ""
    audit_start_time:    str = ""
    audit_end_time:      str = ""
    audit_total_hours:   str = ""

    # Audit outcome
    audit_result: str = "-"

    # Quantity fields
    po_qty:      str = ""  # raw extracted string e.g. "1200 PCS"
    po_qty_pcs:  int = 0   # populated by post_processor
    po_qty_pack: int = 0
    po_qty_set:  int = 0
    do_qty:      int = 0

    # Shipment date fields
    exf:      str = ""
    po_edt:   str = ""
    po_wh:    str = ""
    plan_edt: str = ""
    plan_wh:  str = ""

    shipment_dates: str = ""

    ship_qty:  str = ""
    audit_qty: str = ""

    # Defect summary
    defect_qty:            str = ""
    acceptable_defect_qty: str = "-"
    defect_percentage:     str = ""

    # Personnel
    person:    str = ""
    inspector: str = ""

    # Additional checks
    carton:          str = ""
    needle_detector: str = ""
    remarks:         str = ""
    do_set_col_size: str = ""

    # Structured defect data (auto-discovered from the defect table)
    defect_rows: List[Dict[str, Any]] = field(default_factory=list)

    # D.O. plan table
    do_orders: List[Dict[str, Any]] = field(default_factory=list)
    do_totals: Dict[str, Any]       = field(default_factory=dict)
    do_note:   str                  = ""

    # Validation
    validation_errors: List[str] = field(default_factory=list)

    # Blocking errors — records with these are NEVER inserted into the DB.
    # Populated by validate_blocking() in validator.py.
    # Examples: required field empty, defect sum ≠ header defect_qty.
    blocking_errors: List[str] = field(default_factory=list)

    # Which static defect template was matched (28 / 35 / 78 item list).
    # Set by db_manager when saving; None until then.
    defect_template_id: int = 0

    # -------------------------------------------------------------------------
    # Serialisation
    # -------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """
        Flat dict suitable for DataFrame / Excel row creation.

        `defect_rows` is excluded from the flat dict (handled separately
        by summary_writer). `validation_errors` is joined into a single
        comma-separated string.
        """
        data = asdict(self)
        data.pop("defect_rows", None)
        data["validation_errors"] = ", ".join(self.validation_errors)
        return data

    def to_json_dict(self) -> Dict[str, Any]:
        """
        Full dict for JSON serialisation — includes defect_rows, do_orders,
        do_totals, and validation_errors as a list (not joined string).
        Used by json_writer for export and round-trip import.
        """
        return asdict(self)



================================================
FILE: backend/final_summary/models/audit_report.py
================================================
from django.db import models
from django.contrib.auth.models import User
from shared.models import BaseModel
from .upload_batch import UploadBatch


class AuditReport(BaseModel):
    """
    One row per successfully extracted Excel audit file.
    Stores all fields from AuditRecord in a fully relational Django model.
    Lookup fields (factory, client, style_no, po_no, country) are stored
    as plain text — they are the "dimension" values used for filtering.
    """

    batch = models.ForeignKey(
        UploadBatch, on_delete=models.CASCADE, related_name="reports",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_reports",
    )

    # Source file
    file_name = models.CharField(max_length=512, db_index=True)

    # ── Identity / header ─────────────────────────────────────────────────────
    factory         = models.CharField(max_length=255, blank=True, db_index=True)
    client          = models.CharField(max_length=255, blank=True, db_index=True)
    date_of_issue   = models.DateField(null=True, blank=True, db_index=True)
    inspection_type = models.CharField(max_length=100, blank=True)
    report_no       = models.CharField(max_length=100, blank=True)
    audit_report    = models.CharField(max_length=100, blank=True)
    item_name       = models.CharField(max_length=512, blank=True)
    style_no        = models.CharField(max_length=100, blank=True, db_index=True)
    po_no           = models.CharField(max_length=100, blank=True, db_index=True)
    country         = models.CharField(max_length=100, blank=True)

    # ── Time fields ────────────────────────────────────────────────────────────
    factory_in_time     = models.CharField(max_length=20, blank=True)
    factory_out_time    = models.CharField(max_length=20, blank=True)
    factory_total_hours = models.CharField(max_length=20, blank=True)
    audit_start_time    = models.CharField(max_length=20, blank=True)
    audit_end_time      = models.CharField(max_length=20, blank=True)
    audit_total_hours   = models.CharField(max_length=20, blank=True)

    # ── Audit outcome ──────────────────────────────────────────────────────────
    audit_result = models.CharField(max_length=20, blank=True, default="-")

    # ── Quantity fields ────────────────────────────────────────────────────────
    po_qty      = models.CharField(max_length=50, blank=True)   # raw string e.g. "1200 PCS"
    po_qty_pcs  = models.PositiveIntegerField(default=0)
    po_qty_pack = models.PositiveIntegerField(default=0)
    po_qty_set  = models.PositiveIntegerField(default=0)
    do_qty      = models.PositiveIntegerField(default=0)
    ship_qty    = models.CharField(max_length=50, blank=True)
    audit_qty   = models.CharField(max_length=50, blank=True)

    # ── Shipment dates ─────────────────────────────────────────────────────────
    exf      = models.DateField(null=True, blank=True)
    po_edt   = models.DateField(null=True, blank=True)
    po_wh    = models.DateField(null=True, blank=True)
    plan_edt = models.DateField(null=True, blank=True)
    plan_wh  = models.DateField(null=True, blank=True)

    # ── Defect summary ─────────────────────────────────────────────────────────
    defect_qty            = models.CharField(max_length=20, blank=True)
    acceptable_defect_qty = models.CharField(max_length=20, blank=True, default="-")
    defect_percentage     = models.CharField(max_length=20, blank=True)

    # ── Personnel ──────────────────────────────────────────────────────────────
    person    = models.CharField(max_length=255, blank=True)
    inspector = models.CharField(max_length=255, blank=True)

    # ── Additional checks ──────────────────────────────────────────────────────
    carton          = models.CharField(max_length=512, blank=True)
    needle_detector = models.CharField(max_length=512, blank=True)
    remarks         = models.TextField(blank=True)
    do_set_col_size = models.CharField(max_length=512, blank=True)
    do_note         = models.TextField(blank=True)

    # ── Validation ─────────────────────────────────────────────────────────────
    has_validation_errors = models.BooleanField(default=False)
    validation_errors     = models.TextField(blank=True)   # comma-joined
    blocking_errors       = models.TextField(blank=True)   # comma-joined

    # ── DO plan (JSON) ─────────────────────────────────────────────────────────
    # Stored as JSON text — preserves the list-of-dicts structure from AuditRecord
    do_orders_json = models.TextField(blank=True, default="[]")

    class Meta:
        ordering = ["-date_of_issue", "factory", "style_no"]
        verbose_name = "Audit Report"
        verbose_name_plural = "Audit Reports"

    def __str__(self):
        return f"{self.factory} | {self.style_no} | {self.date_of_issue}"


================================================
FILE: backend/final_summary/models/defect_entry.py
================================================
from django.db import models
from django.contrib.auth.models import User
from shared.models import BaseModel
from .audit_report import AuditReport


class DefectEntry(BaseModel):
    """
    One row per defect line item in an audit report.
    Replaces the flat JSON defect_rows list with a proper relational table
    so defects can be aggregated across reports for the summary output.
    """

    report      = models.ForeignKey(
        AuditReport, on_delete=models.CASCADE, related_name="defect_entries",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="defect_entries",
    )

    category    = models.CharField(max_length=100, blank=True, db_index=True)
    item        = models.CharField(max_length=512, blank=True)
    major       = models.PositiveIntegerField(default=0)
    minor       = models.PositiveIntegerField(default=0)
    comment     = models.TextField(blank=True)

    class Meta:
        ordering = ['category', 'item']
        verbose_name = 'Defect Entry'
        verbose_name_plural = 'Defect Entries'

    def __str__(self):
        return f"{self.category} / {self.item} — {self.major}M/{self.minor}m"


================================================
FILE: backend/final_summary/models/field_enums.py
================================================
"""
field_enums.py
--------------
All Enum definitions for the audit extraction system.

To add a new field:
  1. Add the field name to FieldName.
  2. Add synonyms to LabelSynonym.
  3. Wire them together in label_config.py → LABELS.

To add a new country prefix:
  - Add to StyleCountryPrefix and update STYLE_COUNTRY_MAP in label_config.py.
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Field Names  (must match AuditRecord attribute names exactly)
# ---------------------------------------------------------------------------

class FieldName(str, Enum):
    """Internal names for every field extracted from Excel audit reports."""

    # Identity / header
    FACTORY           = "factory"
    DATE_OF_ISSUE     = "date_of_issue"
    INSPECTION_TYPE   = "inspection_type"
    REPORT_NO         = "report_no"
    AUDIT_REPORT      = "audit_report"
    ITEM_NAME         = "item_name"
    STYLE_NO          = "style_no"
    PO_NO             = "po_no"
    COUNTRY           = "country"

    # Time fields
    FACTORY_IN_TIME     = "factory_in_time"
    FACTORY_OUT_TIME    = "factory_out_time"
    FACTORY_TOTAL_HOURS = "factory_total_hours"
    AUDIT_START_TIME    = "audit_start_time"
    AUDIT_END_TIME      = "audit_end_time"
    AUDIT_TOTAL_HOURS   = "audit_total_hours"

    # Audit outcome
    AUDIT_RESULT = "audit_result"

    # Quantity fields
    PO_QTY    = "po_qty"
    DO_QTY    = "do_qty"
    SHIP_QTY  = "ship_qty"
    AUDIT_QTY = "audit_qty"

    # Details of shipment dates
    EXF      = "exf"
    PO_EDT   = "po_edt"
    PO_WH    = "po_wh"
    PLAN_EDT = "plan_edt"
    PLAN_WH  = "plan_wh"

    # Defect summary
    DEFECT_QTY            = "defect_qty"
    ACCEPTABLE_DEFECT_QTY = "acceptable_defect_qty"
    DEFECT_PERCENTAGE     = "defect_percentage"

    # Personnel
    PERSON    = "person"
    INSPECTOR = "inspector"

    # Additional checks
    CARTON           = "carton"
    NEEDLE_DETECTOR  = "needle_detector"
    REMARKS          = "remarks"
    DO_SET_COL_SIZE  = "do_set_col_size"
    CARTON_NUMBER    = "carton_number"

    DETAILS_OF_SHIPMENT = "details_of_shipment"

    # Client / buyer (extracted from Excel label "client")
    CLIENT = "client"


# ---------------------------------------------------------------------------
# Label Synonyms  (all text variants that appear in Excel headers)
# ---------------------------------------------------------------------------

class LabelSynonym(str, Enum):
    """
    Synonyms for column/row labels found in Excel audit sheets.
    Add new spellings here when a new sheet format is encountered.
    """

    # Factory
    FACTORY      = "factory"
    FACTORY_NAME = "factory name"

    # Date of Issue
    DATE_OF_ISSUE   = "date of issue"
    ISSUE_DATE      = "issue date"
    REPORT_DATE     = "report date"
    INSPECTION_DATE = "inspection date"

    # Inspection Type
    INSPECTION_TYPE = "inspection type"
    AUDIT_TYPE      = "audit type"

    # Factory Times
    FACTORY_IN_TIME  = "factory in time"
    FACTORY_INTIME   = "factory in-time"
    FACTORY_INTIME2  = "factory intime"
    IN_TIME          = "in time"
    FACTORY_OUT_TIME = "factory out time"
    FACTORY_OUTTIME  = "factory out-time"
    FACTORY_OUTTIME2 = "factory outtime"
    OUT_TIME         = "out time"

    # Audit Times
    AUDIT_START_TIME = "audit start time"
    START_TIME       = "start time"
    AUDIT_END_TIME   = "audit end time"
    END_TIME         = "end time"

    # Audit Result
    AUDIT_RESULT      = "audit result"
    RESULT            = "result"
    INSPECTION_RESULT = "inspection result"

    # Report / PO numbers
    REPORT_NO            = "report no"
    REPORT_NUMBER        = "report number"
    INSPECTION_REPORT_NO = "inspection report no"

    # Item Name
    ITEM_NAME   = "item name"
    DESCRIPTION = "description"

    # Style No
    STYLE_NO          = "style no"
    STYLE_NUMBER      = "style number"
    STYLE             = "style"
    LOCAL_SAMPLE_CODE = "local sample code"

    # PO No
    PO_NO             = "po no"
    PO_NO_DASH        = "po-no"
    PURCHASE_ORDER_NO = "purchase order no"

    # PO Quantity
    PO_QTY      = "po qty"
    PO_QUANTITY = "po quantity"
    PO_QTY_CAPS = "p.o qty"

    # DO Quantity
    DO_QTY      = "do qty"
    DO_QUANTITY = "do quantity"
    DO_QTY_CAPS = "d.o qty"

    # EXF date
    EXF   = "exf"
    EXF_  = "exf:"
    EXF__ = "exf :"

    # PO EDT
    PO_EDT   = "po. etd"
    _PO_EDT  = "po etd"
    PO__EDT  = "po.  etd"
    _PO__EDT = "po  etd"

    # PO Warehouse
    PO_WH       = "po wh"
    WAREHOUSE   = "warehouse"
    POWH        = "powh"
    PO_WH_SLASH = "po w/h"

    # Plan EDT
    PLAN_ETD  = "plan etd"
    PLAN__ETD = "plan  etd"

    # Plan WH
    PLAN_WH  = "plan wh"
    PLAN__WH = "plan  wh"

    # Ship Quantity
    SHIP_QTY               = "ship qty"
    SHIPMENT_QTY           = "shipment qty"
    SHIPPING_QUANTITY      = "shipping quantity"
    SHIPPING_QTY           = "shipping qty"
    AUDIT_FOR_SHIPPING_QTY = "audit for shipping qty"
    EXF_QTY                = "exf qty"

    # Audit Quantity
    AUDIT_QTY        = "audit qty"
    AUDITED_QUANTITY = "audited quantity"
    QTY_INSPECTED    = "qty.\ninspected"

    # Personnel
    INSPECTOR = "inspector"
    PERSON    = "person"

    # Defect qty (major column header in summary section)
    MAJOR_DEFECTS = "major\ndefects"

    # Carton / inspection carton
    OUR_INSPECTION_CARTON_NUMBER = "our inspection carton number"
    CARTON_INSPECTION            = "carton inspection"
    INSPECTION_CARTON            = "inspection carton"
    INSPECTION_CTN               = "inspection ctn"
    OUR_INSPECTION_CARTON        = "our inspection carton"

    # Needle detector
    NEEDLE_DETECTOR       = "needle detector"
    NEEDLE_DETECTOR_CHECK = "needle detector check"

    # Remarks
    REMARKS = "remarks"
    REMARK  = "remark"

    # DO/Set/Col/Size
    DO_SET_COL_SIZE = "do/set/col/size"

    # Client / buyer
    CLIENT       = "client"
    CLIENT_NAME  = "client name"
    BUYER        = "buyer"
    BUYER_NAME   = "buyer name"


# ---------------------------------------------------------------------------
# Direction Rules
# ---------------------------------------------------------------------------

class DirectionRule(str, Enum):
    """
    Controls where resolve_value() looks for the field value relative to the
    label cell.

    RIGHT            → scan right across the same row
    DOWN             → scan down the same column
    DOWN_IF_INT      → scan down but only accept integer values
    RIGHT_THEN_DOWN  → try right first, fall back to down
    DOWN_THEN_RIGHT  → try down first, fall back to right
    """
    RIGHT           = "right"
    DOWN            = "down"
    DOWN_IF_INT     = "down_if_int"
    RIGHT_THEN_DOWN = "right_then_down"
    DOWN_THEN_RIGHT = "down_then_right"


# ---------------------------------------------------------------------------
# Audit Type Patterns
# ---------------------------------------------------------------------------

class AuditPattern(str, Enum):
    """Keys used in AUDIT_PATTERNS regex map (label_config.py)."""
    RE_FINAL = "RE-FINAL"
    FINAL    = "FINAL"
    INLINE   = "INLINE"
    SAMPLE   = "SAMPLE"
    CMF      = "CMF"


# ---------------------------------------------------------------------------
# Style Number Country Prefixes
# ---------------------------------------------------------------------------

class StyleCountryPrefix(str, Enum):
    """
    First two characters of a style number that encode the destination country.
    Update STYLE_COUNTRY_MAP in label_config.py if new prefixes are added.
    """
    JAPAN  = "01"
    CHINA  = "03"
    USA    = "04"
    KOREA  = "05"
    EUROPE = "07"
    TAIWAN = "10"
    AU     = "14"
    CANADA = "17"
    INDIA  = "36"


# ---------------------------------------------------------------------------
# D.O. Table Column Names
# ---------------------------------------------------------------------------

class DOFieldName(str, Enum):
    """Internal names for every column in the Delivery Order plan table."""
    DATE       = "date"
    PO_QTY     = "po_qty"
    DO_NO      = "do_no"
    DO_QTY     = "do_qty"
    SHIP_QTY   = "ship_qty"
    AUDIT_QTY  = "audit_qty"
    DO_BALANCE = "do_balance"
    PO_EXTRA   = "po_extra"
    REMARKS    = "remarks"
    PO_BALANCE = "po_balance"


# ---------------------------------------------------------------------------
# D.O. Table Label Synonyms
# ---------------------------------------------------------------------------

class DOLabelSynonym(str, Enum):
    """All header text variants that can identify a D.O. table column."""

    DATE = "date"

    PO_QTY       = "po qty"
    P_O_QTY      = "p o qty"
    PO_QUANTITY  = "po quantity"
    P_O_QUANTITY = "p o quantity"

    DO_NO             = "do no"
    D_O_NO            = "d o no"
    DO_NUMBER         = "do number"
    D_O_NUMBER        = "d o number"
    DELIVERY_ORDER_NO = "delivery order no"

    DO_QTY       = "do qty"
    D_O_QTY      = "d o qty"
    DO_QUANTITY  = "do quantity"
    D_O_QUANTITY = "d o quantity"

    SHIP_QTY          = "ship qty"
    SHIP_QUANTITY     = "ship quantity"
    SHIPMENT_QTY      = "shipment qty"
    SHIPMENT_QUANTITY = "shipment quantity"

    AUDIT_QTY      = "audit qty"
    AUDIT_QUANTITY = "audit quantity"
    AUDITED_QTY    = "audited qty"

    DO_BALANCE           = "do balance"
    D_O_BALANCE          = "d o balance"
    DO_BALANCE_EXTRA     = "do balance extra"
    DO_BALANCE_AND_EXTRA = "do balance and extra"
    BALANCE_EXTRA        = "balance extra"

    PO_EXTRA  = "po extra"
    P_O_EXTRA = "p o extra"

    REMARKS                       = "remarks"
    BALANCE_QTY_PLAN              = "balance qty plan"
    BALANCE_QTY_PLAN_DATE         = "balance qty plan date"
    BALANCE_QTY_PLAN_DATE_REMARKS = "balance qty plan date remarks"
    PLAN_DATE_REMARKS             = "plan date remarks"

    PO_BALANCE = "po balance"
    PO_BAL     = "po bal"



================================================
FILE: backend/final_summary/models/upload_batch.py
================================================
from django.db import models
from django.contrib.auth.models import User
from shared.models import BaseModel


class UploadBatch(BaseModel):
    """
    Represents one bulk-upload session of Excel files.
    Each batch contains many AuditReports extracted from those files.
    """

    class Status(models.TextChoices):
        PENDING    = "PENDING",    "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED  = "COMPLETED",  "Completed"
        PARTIAL    = "PARTIAL",    "Partial"   # some files failed
        FAILED     = "FAILED",     "Failed"

    FORMAT_CHOICES = [
        ("SPI",     "SPI Format (78)"),
        ("REGULAR", "Regular Format (35)"),
        ("SWEATER", "Sweater Format (37)"),
    ]

    created_by     = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_upload_batches",
    )
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    format_type    = models.CharField(max_length=20, choices=FORMAT_CHOICES, default="SPI")

    # Counters
    total_files     = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    failed_files    = models.PositiveIntegerField(default=0)

    # Raw error dump
    error_log = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Upload Batch"
        verbose_name_plural = "Upload Batches"

    def __str__(self):
        user = self.created_by.username if self.created_by_id else "unknown"
        return f"AuditBatch #{self.pk} | {self.status} | by {user}"

    @property
    def success_rate(self):
        if not self.total_files:
            return 0.0
        return round(self.processed_files / self.total_files * 100, 1)

    @property
    def progress_percent(self):
        if self.status in (self.Status.COMPLETED, self.Status.PARTIAL):
            return 100
        if not self.total_files:
            return 0
        return int(self.processed_files / self.total_files * 100)


================================================
FILE: backend/final_summary/serializers/__init__.py
================================================
[Binary file]


================================================
FILE: backend/final_summary/tasks/__init__.py
================================================
from .process_audit_upload import process_audit_upload
 
__all__ = ["process_audit_upload"]


================================================
FILE: backend/final_summary/tasks/process_audit_upload.py
================================================
"""
tasks/process_audit_upload.py
------------------------------
Celery task: full audit-extraction pipeline for one UploadBatch.

Pipeline
--------
1. Discover all .xlsx / .xls files in the temp upload folder
2. extract_record()   — runs the existing rule-extractor on each file
3. validate_all_records() + validate_blocking_all()
4. _save_record()     — persist AuditReport + DefectEntry rows
5. Update UploadBatch counters / status
6. Push WebSocket events at each stage
7. Always clean up the temp folder in finally
"""

import json
import logging
import shutil
from pathlib import Path

from celery import shared_task
from django.utils.dateparse import parse_date

from final_summary.models import UploadBatch, AuditReport, DefectEntry

logger = logging.getLogger(__name__)


# ── WebSocket helpers ─────────────────────────────────────────────────────────

def _group_name(batch_id: int) -> str:
    return f"audit_batch_{batch_id}"


def _push(group: str, message: dict):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(group, message)
    except Exception as exc:
        logger.debug("WS push failed: %s", exc)


def _push_progress(batch: UploadBatch, stage: str = ""):
    _push(_group_name(batch.pk), {
        "type":             "audit.progress",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "stage":            stage,
        "progress_percent": batch.progress_percent,
        "processed":        batch.processed_files,
        "total":            batch.total_files,
        "failed":           batch.failed_files,
    })


def _push_complete(batch: UploadBatch):
    _push(_group_name(batch.pk), {
        "type":             "audit.complete",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "progress_percent": 100,
        "processed":        batch.processed_files,
        "total":            batch.total_files,
        "failed":           batch.failed_files,
        "report_count":     batch.reports.count(),
    })


def _push_error(batch: UploadBatch, message: str):
    _push(_group_name(batch.pk), {
        "type":          "audit.error",
        "batch_id":      batch.pk,
        "status":        UploadBatch.Status.FAILED,
        "error_message": message,
    })


# ── Date coercion ─────────────────────────────────────────────────────────────

def _to_date(value):
    """Coerce any date-like value to a Python date, or return None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Try ISO first
    d = parse_date(s)
    if d:
        return d
    # Try common regional formats
    from datetime import datetime
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    logger.debug("Could not parse date: %r", s)
    return None


# ── Persist one record ────────────────────────────────────────────────────────

def _save_record(batch: UploadBatch, record) -> bool:
    """
    Persist one AuditRecord (dataclass from extractor_service) to the DB.
    Returns True on success, False if skipped or failed.
    """
    # Skip exact duplicates within this batch
    if AuditReport.objects.filter(batch=batch, file_name=record.file_name).exists():
        logger.info("Duplicate skipped: %s", record.file_name)
        return False

    try:
        report = AuditReport.objects.create(
            batch               = batch,
            file_name           = record.file_name,
            factory             = record.factory or "",
            client              = record.client or "",
            date_of_issue       = _to_date(record.date_of_issue),
            inspection_type     = record.inspection_type or "",
            report_no           = record.report_no or "",
            audit_report        = record.audit_report or "",
            item_name           = record.item_name or "",
            style_no            = record.style_no or "",
            po_no               = record.po_no or "",
            country             = record.country or "",
            factory_in_time     = record.factory_in_time or "",
            factory_out_time    = record.factory_out_time or "",
            factory_total_hours = record.factory_total_hours or "",
            audit_start_time    = record.audit_start_time or "",
            audit_end_time      = record.audit_end_time or "",
            audit_total_hours   = record.audit_total_hours or "",
            audit_result        = record.audit_result or "-",
            po_qty              = record.po_qty or "",
            po_qty_pcs          = int(record.po_qty_pcs or 0),
            po_qty_pack         = int(record.po_qty_pack or 0),
            po_qty_set          = int(record.po_qty_set or 0),
            do_qty              = int(record.do_qty or 0),
            ship_qty            = str(record.ship_qty or ""),
            audit_qty           = str(record.audit_qty or ""),
            exf                 = _to_date(record.exf),
            po_edt              = _to_date(record.po_edt),
            po_wh               = _to_date(record.po_wh),
            plan_edt            = _to_date(record.plan_edt),
            plan_wh             = _to_date(record.plan_wh),
            defect_qty            = str(record.defect_qty or ""),
            acceptable_defect_qty = str(record.acceptable_defect_qty or "-"),
            defect_percentage     = str(record.defect_percentage or ""),
            person              = record.person or "",
            inspector           = record.inspector or "",
            carton              = record.carton or "",
            needle_detector     = record.needle_detector or "",
            remarks             = record.remarks or "",
            do_set_col_size     = record.do_set_col_size or "",
            do_note             = record.do_note or "",
            has_validation_errors = bool(record.validation_errors),
            validation_errors     = ", ".join(record.validation_errors or []),
            blocking_errors       = ", ".join(record.blocking_errors or []),
            do_orders_json        = json.dumps(record.do_orders or []),
        )

        # Bulk-save defect entries
        defect_objects = []
        for d in (record.defect_rows or []):
            if not isinstance(d, dict):
                continue
            cat     = (d.get("category") or "").strip()
            item    = (d.get("item") or "").strip()
            major   = int(d.get("major", 0) or 0)
            minor   = int(d.get("minor", 0) or 0)
            comment = (d.get("comment") or "").strip()

            # Skip empty rows
            if not cat and not item:
                continue
            if major == 0 and minor == 0 and not comment:
                continue

            defect_objects.append(DefectEntry(
                report=report, category=cat, item=item,
                major=major, minor=minor, comment=comment,
            ))

        if defect_objects:
            DefectEntry.objects.bulk_create(defect_objects)

        logger.info("Saved: %s → AuditReport #%s", record.file_name, report.pk)
        return True

    except Exception as exc:
        logger.exception("Failed to save %s: %s", record.file_name, exc)
        return False


# ── Main task ─────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=0,       # no retry — temp folder is deleted in finally
    soft_time_limit=1800,
    time_limit=2100,
    name="final_summary.process_audit_upload",
)
def process_audit_upload(self, batch_id: int, upload_folder: str, format_type: str = "SPI") -> dict:
    """
    Parameters
    ----------
    batch_id      : UploadBatch PK
    upload_folder : absolute path to the temp dir containing uploaded Excel files
    """
    # Lazy imports keep circular-import risk low
    from final_summary.helpers.extractor_service import extract_record
    from final_summary.helpers.validator import validate_all_records, validate_blocking_all

    try:
        batch = UploadBatch.objects.get(pk=batch_id)
    except UploadBatch.DoesNotExist:
        logger.error("Batch #%s not found", batch_id)
        return {"error": "Batch not found"}

    batch.status = UploadBatch.Status.PROCESSING
    batch.save(update_fields=["status"])
    _push_progress(batch, stage="EXTRACTING")

    try:
        upload_path = Path(upload_folder)
        if not upload_path.exists():
            raise FileNotFoundError(f"Upload folder missing: {upload_folder}")

        # Discover files (skip temp files Excel creates)
        excel_files = sorted(
            p for p in upload_path.rglob("*")
            if p.suffix.lower() in (".xlsx", ".xls") and not p.name.startswith("~$")
        )

        if not excel_files:
            raise ValueError("No Excel files found in upload folder.")

        # Do not set total_files yet — determine after sheet expansion
        batch.save(update_fields=["status"])
        _push_progress(batch, stage="EXTRACTING")

        # ── Stage 1: Extract ──────────────────────────────────────────────────
        # Sheet configuration based on format_type
        fmt = format_type.upper() if format_type else "SPI"
        SHEET_CONFIG = {
            "SPI":     ["Final", "Re-Final", "INLINE"],
            "REGULAR": ["Final", "Refinal", "Inline", "Sample"],
            "SWEATER": ["Final", "Refinal", "Sample"],
        }
        target_sheets = SHEET_CONFIG.get(fmt, SHEET_CONFIG["SPI"])

        extracted        = []
        extract_failures = []

        for excel_path in excel_files:
            # Determine which sheets exist in this workbook
            try:
                import openpyxl
                wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
                sheet_names = wb.sheetnames
                wb.close()
            except Exception as exc:
                logger.exception("Failed to read workbook sheets: %s", exc)
                extract_failures.append(f"{excel_path.name}: cannot read sheets")
                continue

            # Match target sheets (case-insensitive)
            sheets_to_process = []
            for tname in target_sheets:
                match = next((s for s in sheet_names if s.lower() == tname.lower()), None)
                if match:
                    sheets_to_process.append(match)

            # If none found, fall back to first sheet to preserve backward compatibility
            if not sheets_to_process:
                if sheet_names:
                    sheets_to_process = [sheet_names[0]]
                else:
                    extract_failures.append(f"{excel_path.name}: no sheets found")
                    continue

            for sheet_name in sheets_to_process:
                try:
                    record = extract_record(excel_path, sheet_name=sheet_name)
                    # Tag record with sheet for uniqueness
                    record.file_name = f"{excel_path.name} ({sheet_name})"
                    extracted.append(record)
                except Exception as exc:
                    logger.exception("Extraction failed: %s (%s) — %s", excel_path.name, sheet_name, exc)
                    extract_failures.append(f"{excel_path.name} ({sheet_name}): {exc}")

        # Update total expected records
        batch.total_files = len(extracted)
        batch.save(update_fields=["total_files"])
        _push_progress(batch, stage="VALIDATING")

        # ── Stage 2: Validate ─────────────────────────────────────────────────
        validated = validate_all_records(extracted)
        validated = validate_blocking_all(validated)

        clean   = [r for r in validated if not r.blocking_errors]
        blocked = [r for r in validated if r.blocking_errors]

        _push_progress(batch, stage="SAVING")

        # ── Stage 3: Save ─────────────────────────────────────────────────────
        saved = 0
        for record in clean:
            if _save_record(batch, record):
                saved += 1
                batch.processed_files += 1
            else:
                batch.failed_files += 1
            batch.save(update_fields=["processed_files", "failed_files"])
            _push_progress(batch, stage="SAVING")

        # Blocked + extract failures count as failed
        batch.failed_files += len(blocked) + len(extract_failures)
        batch.save(update_fields=["failed_files"])

        # ── Finalise status ───────────────────────────────────────────────────
        if batch.failed_files == 0:
            batch.status = UploadBatch.Status.COMPLETED
        elif saved == 0:
            batch.status = UploadBatch.Status.FAILED
        else:
            batch.status = UploadBatch.Status.PARTIAL

        error_lines = extract_failures + [
            f"{r.file_name}: {'; '.join(r.blocking_errors)}" for r in blocked
        ]
        if error_lines:
            batch.error_log = "\n".join(error_lines)

        batch.save(update_fields=["status", "error_log"])
        _push_complete(batch)

        logger.info(
            "Batch #%s done — saved:%d blocked:%d extract_fail:%d",
            batch_id, saved, len(blocked), len(extract_failures),
        )
        return {
            "batch_id": batch_id, "status": batch.status,
            "saved": saved, "blocked": len(blocked),
            "failed_extract": len(extract_failures),
        }

    except Exception as exc:
        logger.exception("Batch #%s fatal error: %s", batch_id, exc)
        batch.status    = UploadBatch.Status.FAILED
        batch.error_log = str(exc)
        batch.save(update_fields=["status", "error_log"])
        _push_error(batch, str(exc))
        return {"error": str(exc)}

    finally:
        # Always clean up temp folder
        shutil.rmtree(upload_folder, ignore_errors=True)
        logger.info("Cleaned up temp folder: %s", upload_folder)


================================================
FILE: backend/final_summary/tasks/process_excel_upload.py
================================================
import logging
from pathlib import Path

from celery import shared_task

from ..utils.config import DB_PATH, ensure_app_dir
from ..db.db_manager import DBManager
from ..helpers.extractor_service import extract_record
from ..helpers.validator import validate_all_records, validate_blocking_all

logger = logging.getLogger(__name__)


@shared_task(name="final_summary.process_excel_upload")
def process_excel_upload(upload_folder: str) -> dict:
    upload_path = Path(upload_folder)
    if not upload_path.exists() or not upload_path.is_dir():
        logger.error("Excel upload folder not found: %s", upload_folder)
        return {"status": "error", "message": "Upload folder not found."}

    ensure_app_dir()
    db = DBManager(DB_PATH)
    db.connect()
    db.init_db()

    excel_files = sorted(upload_path.glob("*.xlsx")) + sorted(upload_path.glob("*.xls"))
    processed = 0
    failed = []
    extracted_records = []

    for excel_path in excel_files:
        try:
            record = extract_record(excel_path)
            extracted_records.append(record)
            processed += 1
        except Exception as exc:
            logger.exception("Failed to extract Excel file %s: %s", excel_path, exc)
            failed.append({"file": excel_path.name, "error": str(exc)})

    validated_records = validate_all_records(extracted_records)
    validated_records = validate_blocking_all(validated_records)

    clean_records = [r for r in validated_records if not r.blocking_errors]
    blocked_records = [r for r in validated_records if r.blocking_errors]

    saved = 0
    skipped = 0
    for record in clean_records:
        result = db.save_record(record)
        if result is None:
            skipped += 1
        else:
            saved += 1

    blocked_data = None
    if blocked_records:
        blocked_data = [r.to_json_dict() for r in blocked_records]
        logger.info("Blocked records prepared for response: %d records", len(blocked_records))

    db.close()

    result = {
        "status": "completed",
        "upload_folder": upload_path.name,
        "processed_files": processed,
        "saved_records": saved,
        "skipped_records": skipped,
        "blocked_records_count": len(blocked_records),
        "failed_files": failed,
    }
    if blocked_data:
        result["blocked_records"] = blocked_data

    return result



================================================
FILE: backend/final_summary/utils/config.py
================================================
"""
config.py
---------
Central application configuration.

DB_PATH is the single fixed location of the SQLite database.
It is created once on first run and reused on every subsequent run,
enabling duplicate detection across all extraction sessions.

When packaged with PyInstaller the exe sits next to the repository root
and the DB lives next to it at backend/audit.db.
"""

from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = WORKSPACE_ROOT / "backend"
APP_DIR = BACKEND_DIR
DB_PATH = APP_DIR / "audit.db"


def ensure_app_dir() -> None:
    """
    Create the backend directory if it does not exist.
    Called once at startup by both scripts.
    Raises PermissionError if the directory cannot be created.
    """
    APP_DIR.mkdir(parents=True, exist_ok=True)


================================================
FILE: backend/final_summary/utils/error_json_writer.py
================================================
"""
error_json_writer.py
--------------------
Writes audit records that failed BLOCKING validation to a JSON file so
the user can manually fix them and re-upload via the Extractor GUI.

File format
-----------
{
  "version": "1.0",
  "generated_at": "2026-01-05T10:30:00",
  "total_blocked": 3,
  "instructions": "Fix the fields listed in 'blocking_errors' for each record,
                   then upload this file via the Extractor's 'Upload Error JSON'
                   button.  Do NOT change the 'file_name' field.",
  "records": [
    {
      "file_name":       "DH26-01ABC-001.xlsx",
      "blocking_errors": ["REQUIRED_FIELD | factory | Factory name is missing"],
      "validation_errors": [...],
      -- all other AuditRecord fields --
      "defect_rows": [...],
      "do_orders":   [...]
    }
  ]
}

Re-import rules
---------------
- All fields in the JSON are editable EXCEPT 'file_name'.
- A record is only inserted if it passes blocking validation after the fix.
- Records that still fail after the upload remain in a new error JSON.
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.audit_record import AuditRecord


_VERSION = "1.0"

_INSTRUCTIONS = (
    "Fix the fields listed in 'blocking_errors' for each record, "
    "then upload this file via the Extractor → 'Upload & Fix Error JSON' button. "
    "Do NOT change the 'file_name' field. "
    "Records that still fail after upload will produce a new error file."
)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_error_json(records: List[AuditRecord], path: Path) -> int:
    """
    Write *records* (all of which should have blocking_errors) to *path*.
    Returns the number of records written.
    """
    if not records:
        logging.info("write_error_json: no blocked records — file not written")
        return 0

    def _serialise(r: AuditRecord) -> Dict[str, Any]:
        d = asdict(r)
        # Put blocking/validation errors at the top for visibility
        return {
            "file_name":         d.pop("file_name", r.file_name),
            "blocking_errors":   d.pop("blocking_errors", []),
            "validation_errors": d.pop("validation_errors", []),
            **d,
        }

    payload = {
        "version":       _VERSION,
        "generated_at":  datetime.now().isoformat(timespec="seconds"),
        "total_blocked": len(records),
        "instructions":  _INSTRUCTIONS,
        "records":       [_serialise(r) for r in records],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"Error JSON written: {path}  ({len(records)} blocked record(s))")
    return len(records)


# ---------------------------------------------------------------------------
# Read (re-import after user edits)
# ---------------------------------------------------------------------------

def read_error_json(path: Path) -> List[AuditRecord]:
    """
    Load a previously written error JSON file and return a list of
    AuditRecord objects with the user's fixes applied.

    Fields that don't map to AuditRecord attributes are silently ignored.
    """
    if not path.exists():
        raise FileNotFoundError(f"Error JSON not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    # Support both wrapped {records: [...]} and bare list
    if isinstance(raw, list):
        items = raw
    else:
        items = raw.get("records", [])

    records: List[AuditRecord] = []
    import dataclasses

    valid_fields = {f.name for f in dataclasses.fields(AuditRecord)}

    for item in items:
        if not isinstance(item, dict):
            continue
        # Only keep keys that are valid AuditRecord fields
        kwargs = {k: v for k, v in item.items() if k in valid_fields}
        try:
            record = AuditRecord(**kwargs)
            # Clear blocking/validation errors — they will be re-evaluated
            record.blocking_errors    = []
            record.validation_errors  = []
            records.append(record)
        except Exception as exc:
            fname = item.get("file_name", "?")
            logging.warning(f"  Could not load record '{fname}' from error JSON: {exc}")

    logging.info(f"read_error_json: loaded {len(records)} record(s) from {path}")
    return records



================================================
FILE: backend/final_summary/utils/summary_writer.py
================================================
"""
summary_writer.py
-----------------
Generates the output summary Excel workbook from queried DB records.

Layout (matches the uploaded sample exactly)
--------------------------------------------
  Row 1  : Title row  +  category group headers (merged spans)
           e.g. "A : FABRICS" spanning columns 24-36
  Row 2  : Individual column headers
  Row 3  : (skipped — no averages row)
  Row 4  : 合計  totals row
  Row 5+ : One data row per audit record

  After the data rows:
    If ENABLE_PLACEHOLDER_ROWS = True (future feature):
      Each record block is followed by 5 stub rows:
        1. Carton
        2. Shipment dates
        3. Needle detector
        4. Remarks
        5. DO Set Col Size

Column order (fixed prefix, then dynamic defect columns)
---------------------------------------------------------
  factory, date_of_issue, inspection_type,
  factory_in_time, factory_out_time, factory_total_hours,
  audit_start_time, audit_end_time,  audit_total_hours,
  audit_result, report_no, item_name, style_no, po_no,
  country, po_qty_display, po_wh, ship_qty, audit_qty,
  acceptable_defect_qty, defect_qty, defect_percentage, person,
  [dynamic defect columns grouped by category ...]

Defect columns
--------------
Built dynamically from whatever defect types appear in the data.
Grouped by category (A:FABRICS, B:SEWING, …) in the row-1 merged header.

Called from writer_main.py as:
    write_summary(records, defect_map, output_path)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.chart import PieChart, Reference, Series
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# from output.chart_generator import ChartGenerator

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

ENABLE_PLACEHOLDER_ROWS: bool = False   # set True when placeholder logic is ready


# ---------------------------------------------------------------------------
# Fixed prefix columns
# (column key → display header label)
# ---------------------------------------------------------------------------

PREFIX_COLUMNS: List[Tuple[str, str]] = [
    ("factory",            "Factory"),
    ("date_of_issue",      "Date of issue"),
    ("inspection_type",    "Inspection Type"),
    ("factory_in",         "Factory In Time"),
    ("factory_out",        "Factory Out Time"),
    ("factory_total_hours","Total Hours"),
    ("audit_start",        "Audit Start Time"),
    ("audit_end",          "Audit End Time"),
    ("audit_total_hours",  "Total Hours"),
    ("audit_result",       "Audit Result"),
    ("report_no",          "Report Number"),
    ("item_name",          "Item Name"),
    ("style_no",           "Style NO."),
    ("po_no",              "POーNO"),
    ("country",            "Country"),
    ("po_qty_pcs",         "PO Qty.(PCS)"),
    ("po_qty_pack",        "PO Qty.(PACK)"),
    ("po_qty_set",         "PO Qty.(SET)"),
    ("po_wh",              "PO  WH"),
    ("ship_qty",           "Shipping Qty"),
    ("audit_qty",          "Audit Qty."),
    ("acceptable_defect_qty", "Acceptable Defect Qty"),
    ("defect_qty",         "Defect Qty."),
    ("defect_percentage",  "Defect %"),
    ("person",             "Person"),
]

PREFIX_KEY_SET = {k for k, _ in PREFIX_COLUMNS}

# ---------------------------------------------------------------------------
# Placeholder row labels (used when ENABLE_PLACEHOLDER_ROWS = True)
# ---------------------------------------------------------------------------

_PLACEHOLDER_LABELS = [
    ("carton",          "carton"),
    ("shipment_dates",  "shipment_dates"),
    ("needle_detector", "needle_detector"),
    ("remarks",         "remarks"),
    ("do_set_col_size", "Do Set Col Size"),
]

# ---------------------------------------------------------------------------
# Layout defaults
# ---------------------------------------------------------------------------

# Default width units for sheet columns. These are Excel column width units,
# not pixels. Column width can be tuned by column key below.
DEFAULT_COLUMN_WIDTH = 10.0
DEFECT_COLUMN_WIDTH  = 6.0

# Default height for all rows. Special rows can override this default.
DEFAULT_ROW_HEIGHT = 16.0
ROW_HEIGHT_OVERRIDES = {
    1: 22.0,
    2: 150.0,
    3: 1.0,
    4: 16.0,
}

# Manual per-column width overrides for fixed prefix columns.
COLUMN_WIDTHS_BY_KEY: Dict[str, float] = {
    "factory": 25.29,
    "date_of_issue": 7.86,
    "inspection_type": 22.71,
    "factory_in": 10.43,
    "factory_out": 10.43,
    "factory_total_hours": 7.0,
    "audit_start": 10.43,
    "audit_end": 10.43,
    "audit_total_hours": 7.0,
    "audit_result": 3,
    "report_no": 19.71,
    "item_name": 25.71,
    "style_no": 16.14,
    "po_no": 19.43,
    "country": 10.0,
    "po_qty_pcs": 10.0,
    "po_qty_pack": 10.0,
    "po_qty_set": 10.0,
    "po_wh": 13.86,
    "ship_qty": 7.0,
    "audit_qty": 8.29,
    "acceptable_defect_qty": 3.0,
    "defect_qty": 4.0,
    "defect_percentage": 8.14,
    "person": 3.0,
}

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_WHITE   = "FFFFFF"
_BLACK   = "000000"
_YELLOW  = "FFFF00"
_DARK_BLUE   = "2F5496"
_ORANGE      = "C65911"
_LIGHT_GRAY  = "808080"
_TOTALS_FILL = _LIGHT_GRAY   # light gray for 合計 row

_TOP_BAR_FONT  = Font(bold=True, color=_BLACK, size=9)
_TOP_BAR_FILL  = PatternFill("solid", fgColor=_WHITE)

_HEADER_FONT   = Font(bold=True, color=_BLACK, size=9)
_DATA_FONT     = Font(size=9)
_TOTALS_FONT   = Font(bold=True, color=_WHITE, size=9)
_TITLE_FONT    = Font(bold=True, color=_WHITE, size=10)

_HEADER_FILL  = PatternFill("solid", fgColor=_YELLOW)
_TOTALS_FILL_STYLE = PatternFill("solid", fgColor=_TOTALS_FILL)
_PLACEHOLDER_FILL  = PatternFill("solid", fgColor=_LIGHT_GRAY)

_CENTRE = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT   = Alignment(horizontal="left",   vertical="center", wrap_text=False)
_RIGHT  = Alignment(horizontal="right",  vertical="center")

_THIN = Side(style="thin", color=_BLACK)
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CELL_BORDER_TOP_RIGHT_LEFT = Border(left=_THIN, right=_THIN, top=_THIN)
_CELL_BORDER_BOTTOM = Border(bottom=_THIN)
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_ROTATE_TEXT_UP_ALIGNMENT = Alignment(horizontal="center", vertical="center", textRotation=90, wrap_text=True)


# ---------------------------------------------------------------------------
# Category colour map (matches sample colouring)
# ---------------------------------------------------------------------------

_CATEGORY_FILLS = {
    "A": PatternFill("solid", fgColor=_WHITE),  # White
    "B": PatternFill("solid", fgColor=_WHITE),  # White
    "C": PatternFill("solid", fgColor=_WHITE),  # White
    "D": PatternFill("solid", fgColor=_WHITE),  # White
    "E": PatternFill("solid", fgColor=_WHITE),  # White
    "F": PatternFill("solid", fgColor=_WHITE),  # White
}


def _cat_fill(category: str) -> PatternFill:
    letter = category.strip()[:1].upper()
    return _CATEGORY_FILLS.get(letter, _TOP_BAR_FILL)

def pts_to_cm(pts):
    return pts * 0.03528
# ---------------------------------------------------------------------------
# Defect column plan builder
# ---------------------------------------------------------------------------

def build_defect_column_plan(
    defect_rows_by_report: Dict[int, List[Dict[str, Any]]],
) -> List[Tuple[str, str]]:
    """
    Build an ordered list of (category, item) pairs from all defect data.
    Sorted by category letter then item text.

    Returns [(category, item), ...]
    """
    seen: Dict[Tuple[str, str], None] = {}
    for rows in defect_rows_by_report.values():
        for d in rows:
            if isinstance(d, dict):
                cat  = (d.get("category") or "").strip()
                item = (d.get("item") or "").strip()
                if cat and item:
                    seen[(cat, item)] = None
    return sorted(seen.keys(), key=lambda x: (x[0], x[1]))


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def _get_prefix_value(row: Dict[str, Any], key: str) -> Any:
    """Extract the display value for a prefix column from a DB row dict."""
    if key == "po_qty_display":
        # Prefer pcs, then pack, then set, then raw string
        for sub in ("po_qty_pcs", "po_qty_pack", "po_qty_set"):
            v = row.get(sub)
            if v:
                return v
        return row.get("po_qty_raw", "")
    return row.get(key, "")


def _pct_float(val: Any) -> Optional[float]:
    """Convert defect_percentage stored as float or '3.71%' to float."""
    if val is None:
        return None
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Sheet writer
# ---------------------------------------------------------------------------

def _write_sheet(
    ws,
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    defect_plan: List[Tuple[str, str]],
) -> None:
    """Write all rows to worksheet *ws*."""

    total_prefix = len(PREFIX_COLUMNS)
    total_defect = len(defect_plan)
    total_cols   = total_prefix + total_defect

    # ── Row 1: title + category group headers ────────────────────────────────
    ws.row_dimensions[1].height = 22

    # Left title span (fixed prefix area)
    ws.merge_cells(start_row=1, start_column=1,
                   end_row=1, end_column=total_prefix)
    title_cell = ws.cell(row=1, column=1, value="出荷前監査報告書")
    title_cell.font      = _TOP_BAR_FONT
    title_cell.fill      = _TOP_BAR_FILL
    title_cell.alignment = _CENTRE
    title_cell.border    = _CELL_BORDER

    # Category merged spans
    if defect_plan:
        col_idx = total_prefix + 1
        i = 0
        while i < len(defect_plan):
            cat = defect_plan[i][0]
            j = i
            while j < len(defect_plan) and defect_plan[j][0] == cat:
                j += 1
            span = j - i
            if span > 1:
                ws.merge_cells(
                    start_row=1, start_column=col_idx,
                    end_row=1,   end_column=col_idx + span - 1
                )
            cell = ws.cell(row=1, column=col_idx, value=cat)
            cell.font      = _TOP_BAR_FONT
            cell.fill      = _cat_fill(cat)
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER
            col_idx += span
            i = j

    # ── Rows 2-3: column headers (each cell merged vertically across both rows) ─
    # Row 2 holds the value; row 3 is merged into it so headers appear taller.
    ws.row_dimensions[2].height = 150
    ws.row_dimensions[3].height = 1    # collapsed — fully absorbed by merge

    def _write_header_cell(col_idx: int, label: str, fill: PatternFill) -> None:
        """Merge rows 2-3 for this column and write the header label."""
        # Clear row 3 first (BEFORE merging — MergedCell is read-only after)
        r3 = ws.cell(row=3, column=col_idx)
        r3.value = None

        # Unmerge first (safe no-op if not already merged)
        try:
            ws.unmerge_cells(
                start_row=2, start_column=col_idx,
                end_row=3,   end_column=col_idx,
            )
        except Exception:
            pass

        ws.merge_cells(
            start_row=2, start_column=col_idx,
            end_row=3,   end_column=col_idx,
        )
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.font      = _HEADER_FONT
        cell.fill      = fill
        cell.alignment = _ROTATE_TEXT_UP_ALIGNMENT
        cell.border    = _CELL_BORDER

    for col_idx, (_, label) in enumerate(PREFIX_COLUMNS, start=1):
        _write_header_cell(col_idx, label, _HEADER_FILL)

    for k, (cat, item) in enumerate(defect_plan, start=total_prefix + 1):
        _write_header_cell(k, item, _HEADER_FILL)
        # _write_header_cell(k, item, _cat_fill(cat))

    # ── Row 4: 合計 totals ────────────────────────────────────────────────────
    totals_row = 4
    ws.row_dimensions[totals_row].height = 16

    totals_label = ws.cell(row=totals_row, column=1, value="合計")
    totals_label.font      = _TOTALS_FONT
    totals_label.fill      = _TOTALS_FILL_STYLE
    totals_label.alignment = _LEFT
    totals_label.border    = _CELL_BORDER

    # We'll fill totals after writing data rows; store column sums here
    _ship_col  = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "ship_qty"),  None)
    _audit_col = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "audit_qty"), None)
    _defect_col = next((i+1 for i, (k, _) in enumerate(PREFIX_COLUMNS) if k == "defect_qty"), None)

    total_ship  = 0
    total_audit = 0
    total_defect_count = 0
    defect_col_totals: Dict[int, int] = {}   # col_idx → total

    # ── Rows 5+: data rows ───────────────────────────────────────────────────
    current_row = 5

    for rec in records:
        report_id = rec.get("report_id")

        # Build defect lookup for this record: (category, item) → major_count
        defect_lookup: Dict[Tuple[str, str], int] = {}
        if report_id is not None:
            for d in defect_items_by_report.get(report_id, []):
                cat  = (d.get("category") or "").strip()
                item = (d.get("item") or "").strip()
                if cat and item:
                    defect_lookup[(cat, item)] = int(d.get("major_count", 0))

        # Write prefix columns
        for col_idx, (key, _) in enumerate(PREFIX_COLUMNS, start=1):
            val  = _get_prefix_value(rec, key)
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font      = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER

        # Write defect columns
        for k, (cat, item) in enumerate(defect_plan, start=total_prefix + 1):
            count = defect_lookup.get((cat, item), "")
            cell  = ws.cell(row=current_row, column=k, value=count if count else "")
            cell.font      = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border    = _CELL_BORDER
            if isinstance(count, int) and count > 0:
                defect_col_totals[k] = defect_col_totals.get(k, 0) + count

        # Accumulate totals
        try:
            total_ship  += int(rec.get("ship_qty")  or 0)
            total_audit += int(rec.get("audit_qty") or 0)
            total_defect_count += int(rec.get("defect_qty") or 0)
        except (TypeError, ValueError):
            pass

        current_row += 1

        # Placeholder rows (controlled by flag)
        if ENABLE_PLACEHOLDER_ROWS:
            _write_placeholder_rows(ws, rec, PREFIX_COLUMNS, total_cols, current_row)
            current_row += len(_PLACEHOLDER_LABELS)

    # ── Fill totals row ───────────────────────────────────────────────────────
    if _ship_col:
        cell = ws.cell(row=totals_row, column=_ship_col, value=total_ship)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
    if _audit_col:
        cell = ws.cell(row=totals_row, column=_audit_col, value=total_audit)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
    if _defect_col:
        # defect % = total_defect / total_audit
        cell = ws.cell(row=totals_row, column=_defect_col, value=total_defect_count)
        cell.font = _TOTALS_FONT; cell.fill = _TOTALS_FILL_STYLE
        pct_col = _defect_col + 1
        if total_audit > 0:
            ws.cell(row=totals_row, column=pct_col,
                    value=round(total_defect_count / total_audit, 8)).fill = _TOTALS_FILL_STYLE

    for col_idx, total in defect_col_totals.items():
        cell = ws.cell(row=totals_row, column=col_idx, value=total)
        cell.font = _TOTALS_FONT
        cell.fill = _TOTALS_FILL_STYLE
        cell.alignment = _CENTRE

    # Fill remaining totals cells with fill colour
    for col_idx in range(2, total_cols + 1):
        cell = ws.cell(row=totals_row, column=col_idx)
        if cell.fill.fgColor.rgb in ("00000000", "FFFFFFFF", "00FFFFFF"):
            cell.fill = _TOTALS_FILL_STYLE

    # ── Column widths ─────────────────────────────────────────────────────────
    _set_column_widths(ws, total_prefix, total_defect)

    # ── Apply default row heights after the sheet content exists -------
    _apply_default_row_heights(ws, DEFAULT_ROW_HEIGHT, ROW_HEIGHT_OVERRIDES)

    # ── Freeze panes: rows 1-4 (title + merged header + totals) ─────────────
    ws.freeze_panes = "A5"

    # ── Charts below the data rows ────────────────────────────────────────────
    # Leave 2 blank rows as a visual gap, then draw:
    #   Col 1 : Top-5 pie chart  +  category summary table  (stacked vertically)
    #   Col 2 : Full-defect bar chart  (right of pie, matching screenshot layout)
    chart_start_row = current_row + 1   # 1-row gap between data and charts
    _write_inline_charts(ws, chart_start_row, defect_plan, total_prefix)


def _write_inline_charts(
    ws,
    start_row: int,
    defect_plan: List[Tuple[str, str]],
    total_prefix: int,
) -> None:
    """
    Draw charts immediately below the data rows (1-row gap).

    Layout
    ------
    chart_row  : pie chart (cols A–K)  |  summary table (cols L onward)  |  bar chart (after table)

    Both charts share the same fixed height (PIE_BAR_CHART_HEIGHT_CM).
    Table row heights are distributed evenly to match that height.
    Zero-count rows are removed from the top-5 table; their percentage
    share is redistributed proportionally to the remaining rows.
    """
    if not defect_plan:
        return

    # ── Static chart size constants (cm) ─────────────────────────────────────
    PIE_CHART_WIDTH_CM  = pts_to_cm(190.15)   # pie chart width  in cm
    BAR_CHART_WIDTH_CM  = 35.34   # bar chart width  in cm
    CHART_HEIGHT_CM     = 3.0    # SHARED height for both pie and bar chart in cm

    # ── Color palettes (hex, no '#') ──────────────────────────────────────────
    # Pie chart slice colours (up to 5 slices)
    PIE_SLICE_COLORS  = ["4472C4", "ED7D31", "A9D18E", "FF0000", "FFC000"]
    # Bar chart bar colour (single series — one colour for all bars)
    BAR_COLOR         = "4472C4"
    # Table row alternating fill colours (data rows only, not header)
    TABLE_ROW_COLORS  = [
        "DCE6F1",  # row 1 — light blue
        "EBF3E8",  # row 2 — light green
        "FFF2CC",  # row 3 — light yellow
        "FCE4D6",  # row 4 — light orange
        "E2EFDA",  # row 5 — pale green
    ]

    from openpyxl.chart import BarChart, Reference, Series
    from openpyxl.chart.label import DataLabelList
    from openpyxl.chart.shapes import GraphicalProperties
    from openpyxl.styles import PatternFill as _PF

    n         = len(defect_plan)
    col_start = total_prefix + 1
    col_end   = col_start + n - 1

    # ── Read (category, defect name, total) from sheet rows 2 and 4 ──────────
    defect_totals: List[Tuple[str, str, int]] = []
    for idx, (category, name) in enumerate(defect_plan, start=col_start):
        val = ws.cell(row=4, column=idx).value
        try:
            total = int(val or 0)
        except (TypeError, ValueError):
            total = 0
        defect_totals.append((category, str(name), total))

    # Keep only non-zero entries
    nonzero = [e for e in defect_totals if e[2] > 0]
    if not nonzero:
        return

    nonzero.sort(key=lambda x: (-x[2], x[1]))
    total_defect_count = sum(c for _, _, c in nonzero)

    # ── Build top-5 table rows, removing any zero rows ───────────────────────
    def _build_top5(items: List[Tuple[str, str, int]]) -> List[Tuple[str, str, int, float]]:
        """
        Take up to 5 highest-count items, drop any whose count == 0,
        then redistribute percentages so they sum to 100 %.
        Returns [(category, name, count, pct), ...].
        """
        top = items[:5]
        top = [(cat, nm, cnt) for cat, nm, cnt in top if cnt > 0]
        subtotal = sum(c for _, _, c in top)
        rows = []
        for cat, nm, cnt in top:
            pct = (cnt / subtotal * 100) if subtotal else 0.0
            rows.append((cat, nm, cnt, pct))
        return rows

    top5_table_rows = _build_top5(nonzero)
    top5_pie_rows   = [(nm, cnt, pct) for _, nm, cnt, pct in top5_table_rows]
    n_table_rows    = len(top5_table_rows)   # may be < 5 if zeros removed

    # ── Factory name for bar chart title ─────────────────────────────────────
    try:
        factory_name = ws.cell(row=5, column=1).value or ""
    except Exception:
        factory_name = ""
    bar_title = str(factory_name).strip()

    chart_row = start_row    # no extra gap — caller already added 1-row gap

    # ── Pie chart anchor columns ──────────────────────────────────────────────
    PIE_START_COL = 1
    PIE_END_COL   = 11   # columns A–K

    # ── Table position: starts at col L (PIE_END_COL + 1) ────────────────────
    TABLE_START_COL = PIE_END_COL + 1     # col 12 = L
    TABLE_HEADERS   = ("SL", "Category", "Defect", "Count", "Percentage")
    TABLE_COLS      = len(TABLE_HEADERS)  # 5

    # ── Distribute chart height evenly across table rows ─────────────────────
    # Total rows = 1 header + n_table_rows data rows
    total_table_rows  = 1 + n_table_rows
    # Convert CHART_HEIGHT_CM to points: 1 cm = 28.3465 pt
    chart_height_pt   = CHART_HEIGHT_CM * 28.3465
    row_height_pt     = chart_height_pt / total_table_rows

    # Apply heights to table rows
    ws.row_dimensions[chart_row].height = row_height_pt          # header row
    for i in range(1, n_table_rows + 1):
        ws.row_dimensions[chart_row + i].height = row_height_pt  # data rows

    # ── Write table header ────────────────────────────────────────────────────
    _HEADER_FILL_LOCAL = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    _HEADER_FONT_LOCAL = Font(color="FFFFFF", bold=True, size=9)
    _THIN = Side(style="thin")
    _BORDER_LOCAL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

    for offset, hdr in enumerate(TABLE_HEADERS):
        c = ws.cell(row=chart_row, column=TABLE_START_COL + offset)
        c.value     = hdr
        c.font      = _HEADER_FONT_LOCAL
        c.fill      = _HEADER_FILL_LOCAL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border    = _BORDER_LOCAL

    # ── Write table data rows with alternating row colours ───────────────────
    for i, (category, name, count, pct) in enumerate(top5_table_rows):
        r        = chart_row + 1 + i
        row_fill = _PF(start_color=TABLE_ROW_COLORS[i % len(TABLE_ROW_COLORS)],
                       end_color  =TABLE_ROW_COLORS[i % len(TABLE_ROW_COLORS)],
                       fill_type  ="solid")
        cells_vals = [
            (TABLE_START_COL,     i + 1,       Alignment(horizontal="center", vertical="center")),
            (TABLE_START_COL + 1, category,    Alignment(horizontal="left",   vertical="center")),
            (TABLE_START_COL + 2, name,        Alignment(horizontal="left",   vertical="center", wrap_text=True)),
            (TABLE_START_COL + 3, count,       Alignment(horizontal="center", vertical="center")),
            (TABLE_START_COL + 4, pct / 100,   Alignment(horizontal="center", vertical="center")),
        ]
        for col, val, align in cells_vals:
            c = ws.cell(row=r, column=col, value=val)
            c.fill      = row_fill
            c.border    = _BORDER_LOCAL
            c.alignment = align
            c.font      = Font(size=9)
            if col == TABLE_START_COL + 3:
                c.number_format = "#,##0"
            elif col == TABLE_START_COL + 4:
                c.number_format = "0.00%"

    # Table ends at this column
    table_end_col = TABLE_START_COL + TABLE_COLS  # exclusive, i.e. first col after table

    # ── Write hidden data columns for pie chart (Defect name + Count) ─────────
    # We write a tiny 2-col helper table starting at table_end_col so the pie
    # chart can reference real cell data (openpyxl PieChart needs References).
    PIE_DATA_COL   = table_end_col        # "Defect" label
    PIE_COUNT_COL  = table_end_col + 1    # count value
    for i, (_, name, count, _pct) in enumerate(top5_table_rows):
        r = chart_row + 1 + i
        ws.cell(row=r, column=PIE_DATA_COL,  value=name)
        ws.cell(row=r, column=PIE_COUNT_COL, value=count)
    # Hide these helper columns
    from openpyxl.utils import get_column_letter as _gcl
    for _hc in (PIE_DATA_COL, PIE_COUNT_COL):
        ws.column_dimensions[_gcl(_hc)].hidden = True

    # ── Build pie chart ───────────────────────────────────────────────────────
    pie = PieChart()
    pie.title  = "Top 5 Defect"
    pie.style  = 10
    pie.width  = PIE_CHART_WIDTH_CM
    pie.height = CHART_HEIGHT_CM

    pie.dataLabels = DataLabelList()
    pie.dataLabels.showPercent   = True
    pie.dataLabels.showCatName   = True
    pie.dataLabels.showVal       = False
    pie.dataLabels.showSerName   = False
    pie.dataLabels.showLegendKey = False
    pie.dataLabels.dLblPos       = "bestFit"

    _lbl_ref  = Reference(ws,
                           min_col=PIE_DATA_COL,  min_row=chart_row + 1,
                           max_row=chart_row + n_table_rows)
    _data_ref = Reference(ws,
                           min_col=PIE_COUNT_COL, min_row=chart_row + 1,
                           max_row=chart_row + n_table_rows)
    _pie_series = Series(_data_ref, title="Defect Count")
    pie.append(_pie_series)
    pie.set_categories(_lbl_ref)

    # Apply explicit slice colours
    from openpyxl.chart.data_source import NumDataSource, NumRef
    from openpyxl.drawing.fill import PatternFillProperties
    try:
        from openpyxl.chart.series import DataPoint
        for i in range(n_table_rows):
            pt = DataPoint(idx=i)
            pt.graphicalProperties.solidFill = PIE_SLICE_COLORS[i % len(PIE_SLICE_COLORS)]
            _pie_series.dPt.append(pt)
    except Exception:
        pass  # colour assignment is best-effort

    ws.add_chart(pie, f"{_gcl(PIE_START_COL)}{chart_row}")

    # ── Build bar chart ───────────────────────────────────────────────────────
    BAR_COL = table_end_col + 2   # one col after hidden helper cols

    bar = BarChart()
    bar.title    = bar_title
    bar.style    = 10
    bar.type     = "col"           # vertical column chart
    bar.width    = BAR_CHART_WIDTH_CM
    bar.height   = CHART_HEIGHT_CM  # same height as pie
    bar.gapWidth = 50
    bar.legend   = None

    # Axis labels
    bar.x_axis.title       = "Defect"
    bar.y_axis.title       = "Count"
    bar.x_axis.tickLblPos  = "low"   # labels shown BELOW the bars
    bar.x_axis.delete      = False
    bar.y_axis.delete      = False

    _bar_data = Reference(ws, min_col=col_start, max_col=col_end,
                          min_row=4, max_row=4)
    _bar_cats = Reference(ws, min_col=col_start, max_col=col_end,
                          min_row=2, max_row=2)

    _bar_series = Series(_bar_data, title="Defect Count")
    # Apply a single solid fill colour to all bars
    try:
        _bar_series.graphicalProperties.solidFill = BAR_COLOR
    except Exception:
        pass
    bar.series.append(_bar_series)
    bar.set_categories(_bar_cats)

    # Value labels on top of bars
    bar.dataLabels = DataLabelList()
    bar.dataLabels.showVal     = True
    bar.dataLabels.showCatName = False
    bar.dataLabels.showSerName = False
    bar.dataLabels.dLblPos     = "outEnd"
    bar.dataLabels.numFmt      = "#,##0"

    ws.add_chart(bar, f"{_gcl(BAR_COL)}{chart_row}")

def _write_placeholder_rows(
    ws,
    rec: Dict[str, Any],
    prefix_columns: List[Tuple[str, str]],
    total_cols: int,
    start_row: int,
) -> None:
    """Write the 5 placeholder rows below a data record."""
    file_name = rec.get("file_name", "")
    factory   = rec.get("factory", "")

    for offset, (field_key, label) in enumerate(_PLACEHOLDER_LABELS):
        row = start_row + offset
        ws.row_dimensions[row].height = 13

        for col_idx, (key, _) in enumerate(prefix_columns, start=1):
            cell = ws.cell(row=row, column=col_idx)
            cell.fill = _PLACEHOLDER_FILL
            cell.font = Font(size=8, italic=True)
            cell.alignment = _LEFT

            if key == "factory":
                cell.value = label
            elif key == "date_of_issue" and field_key in rec:
                cell.value = rec.get(field_key, "")

        # merge remaining columns
        if total_cols > len(prefix_columns):
            ws.merge_cells(
                start_row=row, start_column=len(prefix_columns) + 1,
                end_row=row,   end_column=total_cols,
            )


def _apply_default_row_heights(
    ws,
    default_height: float,
    overrides: Optional[Dict[int, float]] = None,
) -> None:
    """Apply a row height default to every row, with optional overrides."""
    overrides = overrides or {}
    for row_idx in range(1, ws.max_row + 1):
        if row_idx in overrides:
            ws.row_dimensions[row_idx].height = overrides[row_idx]
        else:
            ws.row_dimensions[row_idx].height = default_height


def _get_column_width(key: str) -> float:
    """Return the configured width for a prefix column key."""
    return COLUMN_WIDTHS_BY_KEY.get(key, DEFAULT_COLUMN_WIDTH)


def _set_column_widths(ws, total_prefix: int, total_defect: int) -> None:
    """Set column widths based on configured defaults and fixed overrides."""
    for col_idx in range(1, total_prefix + 1):
        key, _ = PREFIX_COLUMNS[col_idx - 1]
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = _get_column_width(key)

    for col_idx in range(total_prefix + 1, total_prefix + total_defect + 1):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = DEFECT_COLUMN_WIDTH


# ---------------------------------------------------------------------------
# Template-based sheet writer (completes the _fill_template_sheet stub)
# ---------------------------------------------------------------------------

def _fill_template_sheet(
    ws,
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    defect_plan: List[Tuple[str, str]],
    start_row: int,
) -> None:
    """
    Fill a template sheet starting at the given start_row.
    The template already has headers - we just fill the data rows.
    """
    # Read defect column headers from row 2 to get the template's column order
    template_defect_cols: List[Tuple[str, str]] = []
    for col_idx in range(21, ws.max_column + 1):
        header = ws.cell(row=2, column=col_idx).value
        if header is not None:
            # Template doesn't include categories, just item names
            template_defect_cols.append(("", str(header).strip()))

    total_prefix = 20  # Template has 20 prefix columns
    current_row = start_row

    for rec in records:
        report_id = rec.get("report_id")

        # Build defect lookup for this record: (item) → major_count
        defect_lookup: Dict[str, int] = {}
        if report_id is not None:
            for d in defect_items_by_report.get(report_id, []):
                item = (d.get("item") or "").strip()
                if item:
                    defect_lookup[item] = int(d.get("major_count", 0))

        # Write prefix columns (template has fixed mapping)
        col_map = {
            "factory": 1, "date_of_issue": 2, "inspection_type": 3,
            "factory_in": 4, "factory_out": 5, "factory_total_hours": 6,
            "audit_start": 7, "audit_end": 8, "audit_total_hours": 9,
            "audit_result": 10, "report_no": 11, "item_name": 12,
            "style_no": 13, "po_no": 14, "country": 15,
            "audit_qty": 16, "acceptable_defect_qty": 17, "defect_qty": 18,
            "defect_percentage": 19, "person": 20,
        }
        for key, col_idx in col_map.items():
            val = _get_prefix_value(rec, key)
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border = _CELL_BORDER

        # Write defect columns based on template's column order
        for idx, (_, item_name) in enumerate(template_defect_cols):
            count = defect_lookup.get(item_name, "")
            col_idx = total_prefix + 1 + idx
            cell = ws.cell(row=current_row, column=col_idx, value=count if count else "")
            cell.font = _DATA_FONT
            cell.alignment = _CENTRE
            cell.border = _CELL_BORDER

        current_row += 1


def _write_summary_from_scratch(
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """
    Build summary from scratch (no template) - used as fallback.
    Groups records by inspection type and writes sheets using _write_sheet.
    """
    import openpyxl

    # Group records by canonical inspection type
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        itype = (rec.get("inspection_type") or "").upper().strip()
        if "PRE" in itype and "FINAL" in itype:
            key = "PRE-FINAL"
        elif "RE" in itype and "FINAL" in itype:
            key = "RE-FINAL"
        elif "FINAL" in itype:
            key = "FINAL"
        elif "INLINE" in itype:
            key = "INLINE"
        elif "CMF" in itype:
            key = "CMF"
        elif "SAMPLE" in itype:
            key = "SAMPLE"
        else:
            key = "UNKNOWN"
        by_type.setdefault(key, []).append(rec)

    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # Build global defect plan
    defect_plan = build_defect_column_plan(defect_items_by_report)

    for sheet_name in ["FINAL", "RE-FINAL", "PRE-FINAL", "INLINE", "CMF", "SAMPLE", "UNKNOWN"]:
        type_records = by_type.get(sheet_name)
        if not type_records:
            continue

        ws = wb.create_sheet(title=sheet_name[:31])
        _write_sheet(ws, type_records, defect_items_by_report, defect_plan)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logging.info(f"Summary saved (from scratch): {output_path}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_summary(
    records: List[Dict[str, Any]],
    defect_items_by_report: Dict[int, List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """
    Generate the summary Excel workbook using the SPI-Final-78.xlsx template.

    Parameters
    ----------
    records                : list of row dicts from v_audit_full (DB query)
    defect_items_by_report : {report_id: [defect_item_dict, ...]}
    output_path            : destination .xlsx path

    The template defines sheets: Final, Re-Final, INLINE (and Sample if needed).
    Data rows start at row 12 for Final/Re-Final, row 5 for INLINE/Sample.
    Prefix columns (A-W) are populated directly. Defect quantities are
    distributed across columns Z onward (78 columns total for SPI template).
    """
    import openpyxl
    from pathlib import Path
    from django.conf import settings

    # ── Select template based on defect column count ──────────────────────────
    # Build the global defect plan to count columns
    defect_plan = build_defect_column_plan(defect_items_by_report)
    num_defect_cols = len(defect_plan)

    # SPI template has 78 defect columns; other formats may use template.xlsx (Analysis)
    # For now, use SPI-Final-78.xlsx for any format with > 30 defect cols
    if num_defect_cols >= 70:
        template_name = "SPI-Final-78.xlsx"
        template_path = Path(settings.BASE_DIR) / "media" / "templates" / template_name
        start_rows = {"FINAL": 12, "RE-FINAL": 12, "PRE-FINAL": 12, "INLINE": 5, "SAMPLE": 5, "CMF": 12, "UNKNOWN": 12}
    else:
        # Fallback: use the generic Analysis template (template.xlsx) or build from scratch
        template_name = "template.xlsx"
        template_path = Path(settings.BASE_DIR) / "media" / "templates" / template_name
        if not template_path.exists():
            # No template available — build from scratch (original behavior)
            _write_summary_from_scratch(records, defect_items_by_report, output_path)
            return
        start_rows = {"FINAL": 5, "RE-FINAL": 5, "PRE-FINAL": 5, "INLINE": 5, "SAMPLE": 5, "CMF": 5, "UNKNOWN": 5}

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # Load template workbook (keep all sheets)
    wb = openpyxl.load_workbook(template_path, data_only=False)

    # Map records to sheets by canonical inspection type
    def _canonical(itype: str) -> str:
        import re as _re
        u = (itype or "").upper().strip()
        if _re.search(r"PRE[\s\-]?FINAL", u):
            return "PRE-FINAL"
        if _re.search(r"(?<!PRE[\-\s])RE[\s\-]?FINAL|REFINAL", u):
            return "RE-FINAL"
        if _re.search(r"\bFINAL\b|SHIPMENT\s*AUDIT|PRE[\s\-]?SHIPMENT", u):
            return "FINAL"
        if _re.search(r"IN[\s\-]?LINE", u):
            return "INLINE"
        if _re.search(r"\bCMF\b|COUNTER\s*MASTER", u):
            return "CMF"
        if _re.search(r"\bSAMPLE\b|PRE[\s\-]?PROD|PP\s*SAMPLE|\bPP\b", u):
            return "SAMPLE"
        return "UNKNOWN"

    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        key = _canonical(rec.get("inspection_type") or "")
        by_type.setdefault(key, []).append(rec)

    # Determine which sheets to write (only those with data AND that exist in template)
    # Sheet names in template are mixed-case (Final, Re-Final, INLINE)
    # Map our canonical names to template sheet names
    template_sheet_names = {s.lower(): s for s in wb.sheetnames}
    sheet_name_map = {
        "FINAL": "Final",
        "RE-FINAL": "Re-Final",
        "PRE-FINAL": None,  # No Pre-Final in template
        "INLINE": "INLINE",
        "CMF": None,  # No CMF in template
        "SAMPLE": None,  # No Sample in template
        "UNKNOWN": None,
    }
    display_order = [
        sheet_name_map.get(s) 
        for s in ["FINAL", "RE-FINAL", "PRE-FINAL", "INLINE", "CMF", "SAMPLE", "UNKNOWN"] 
        if sheet_name_map.get(s) and s in by_type
    ]

    for sheet_name in display_order:
        # Find the canonical key for this sheet
        reverse_map = {v: k for k, v in sheet_name_map.items() if v}
        canonical_key = reverse_map.get(sheet_name, "FINAL")
        type_records = by_type.get(canonical_key, [])
        start_row = start_rows.get(canonical_key, 12)
        ws = wb[sheet_name]
        _fill_template_sheet(ws, type_records, defect_items_by_report, defect_plan, start_row)

    # Ensure any other sheets (Helper-1, Helper-2) remain untouched — their formulas already reference data ranges

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logging.info(f"Summary saved using template '{template_name}': {output_path}")


================================================
FILE: backend/final_summary/views/__init__.py
================================================
from .retry_view import AuditRetryView
from .logs_view import AuditBatchLogsView, AuditBatchErrorJsonView

from .upload_view import AuditUploadView
from .batch_views import AuditBatchListView, AuditBatchDetailView
from .export_view import AuditExportView
from .filter_options_view import AuditFilterOptionsView

from .top_5_view import AuditReportGenerateView



================================================
FILE: backend/final_summary/views/batch_views.py
================================================
import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from final_summary.models import UploadBatch
from final_summary.serializers import UploadBatchListSerializer, UploadBatchDetailSerializer

logger = logging.getLogger(__name__)


class AuditBatchListView(generics.ListAPIView):
    """GET /api/final-summary/batches/ — paginated list of upload batches."""
    permission_classes = [IsAuthenticated]
    serializer_class   = UploadBatchListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = UploadBatch.objects.all().select_related("created_by").prefetch_related("reports")
        if not user.is_staff:
            qs = qs.filter(created_by=user)
        return qs.order_by("-created_at")


class AuditBatchDetailView(generics.RetrieveAPIView):
    """GET /api/final-summary/batches/<pk>/ — full batch with nested reports."""
    permission_classes = [IsAuthenticated]
    serializer_class   = UploadBatchDetailSerializer

    def get_queryset(self):
        user = self.request.user
        qs = UploadBatch.objects.all().select_related("created_by").prefetch_related("reports")
        if not user.is_staff:
            qs = qs.filter(created_by=user)
        return qs


================================================
FILE: backend/final_summary/views/excel_upload_view.py
================================================
import logging
import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.tasks.process_excel_upload import process_excel_upload

logger = logging.getLogger(__name__)


class FinalSummaryExcelUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"files": ["At least one Excel file is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        upload_root = (
            settings.BASE_DIR
            / "media"
            / "uploads"
            / "final_summary"
            / uuid.uuid4().hex
        )
        upload_root.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for f in files:
            if not f.name.lower().endswith((".xlsx", ".xls")):
                return Response(
                    {"files": [f"Unsupported file type: {f.name}"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            dest = upload_root / f.name
            with open(dest, "wb") as out:
                for chunk in f.chunks():
                    out.write(chunk)
            saved_files.append(dest.name)

        task = process_excel_upload.delay(str(upload_root))
        logger.info(
            "Excel upload received: %s files saved to %s, task=%s",
            len(saved_files),
            upload_root,
            task.id,
        )

        return Response(
            {
                "upload_id": upload_root.name,
                "task_id": task.id,
                "message": "Excel upload received and processing started.",
                "files": saved_files,
            },
            status=status.HTTP_201_CREATED,
        )



================================================
FILE: backend/final_summary/views/export_view.py
================================================
"""
export_view.py
--------------
GET /api/final-summary/export/

Query parameters:
  factory    : exact factory name (required)
  client     : exact client/buyer name (required)
  date_from  : YYYY-MM-DD (required)
  date_to    : YYYY-MM-DD (required)
  style      : comma-separated partial matches on style_no (optional)
               e.g. style=A001,B002  → style_no LIKE %A001% OR style_no LIKE %B002%
  po         : comma-separated partial matches on po_no (optional)
               e.g. po=P001,P002    → po_no LIKE %P001% OR po_no LIKE %P002%

Filter logic:
  (factory AND client AND date_range)
  AND (style_1 OR style_2 OR ... OR po_1 OR po_2 OR ...)

Format-type mismatch:
  If filtered records come from batches with different format_type values,
  the export is blocked and the conflicting records are surfaced for the
  user to fix/skip via the Stage 3 Retry flow.

Template selection (by UploadBatch.format_type):
  SPI     → SPI-Final-78.xlsx
  REGULAR → General-Final-37.xlsx
  SWEATER → General-Final-37.xlsx  (same column layout as REGULAR/37)
"""

import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.http import FileResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import AuditReport, DefectEntry, UploadBatch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_csv_param(value: str) -> list[str]:
    """
    Split a comma-separated query param into a stripped list of non-empty strings.
    '  A001 , B002,  ' → ['A001', 'B002']
    """
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _build_style_po_filter(styles: list[str], pos: list[str]) -> Q | None:
    """
    Build an OR filter across all supplied styles and POs.
    style_A OR style_B OR po_X OR po_Y
    Returns None when both lists are empty (no filter applied).
    """
    if not styles and not pos:
        return None

    q = Q()
    for s in styles:
        q |= Q(style_no__icontains=s)
    for p in pos:
        q |= Q(po_no__icontains=p)
    return q


def _build_records_for_writer(reports):
    """
    Convert a Django AuditReport QuerySet/list into the list-of-dicts format
    that summary_writer.write_summary() expects (mirrors v_audit_full).
    Also batch-fetches DefectEntry rows and returns defect_map.
    """
    report_ids = [r.pk for r in reports]

    defect_map: dict[int, list[dict]] = {}
    for de in (
        DefectEntry.objects
        .filter(report_id__in=report_ids)
        .order_by("category", "item")
    ):
        defect_map.setdefault(de.report_id, []).append({
            "audit_report_id": de.report_id,
            "category":        de.category,
            "item":            de.item,
            "major_count":     de.major,
            "minor_count":     de.minor,
            "comment":         de.comment,
        })

    records = []
    for r in reports:
        records.append({
            "report_id":             r.pk,
            "file_name":             r.file_name,
            "factory":               r.factory,
            "buyer":                 r.client,
            "client":                r.client,
            "style_no":              r.style_no,
            "item_name":             r.item_name,
            "country":               r.country,
            "po_no":                 r.po_no,
            "inspection_type":       r.inspection_type,
            "date_of_issue":         str(r.date_of_issue) if r.date_of_issue else "",
            "audit_result":          r.audit_result,
            "ship_qty":              r.ship_qty,
            "audit_qty":             r.audit_qty,
            "defect_qty":            r.defect_qty,
            "defect_percentage":     r.defect_percentage,
            "inspector":             r.inspector,
            "person":                r.person,
            "po_qty_pcs":            r.po_qty_pcs,
            "po_qty_pack":           r.po_qty_pack,
            "po_qty_set":            r.po_qty_set,
            "po_wh":                 str(r.po_wh)    if r.po_wh    else "",
            "exf":                   str(r.exf)      if r.exf      else "",
            "po_edt":                str(r.po_edt)   if r.po_edt   else "",
            "plan_edt":              str(r.plan_edt) if r.plan_edt else "",
            "plan_wh":               str(r.plan_wh)  if r.plan_wh  else "",
            "factory_in":            r.factory_in_time,
            "factory_out":           r.factory_out_time,
            "factory_total_hours":   r.factory_total_hours,
            "audit_start":           r.audit_start_time,
            "audit_end":             r.audit_end_time,
            "audit_total_hours":     r.audit_total_hours,
            "acceptable_defect_qty": r.acceptable_defect_qty,
            "has_validation_errors": r.has_validation_errors,
            "created_at":            r.created_at,
            # batch format_type for mismatch detection (not written to sheet)
            "_format_type":          r.batch.format_type if r.batch_id else "SPI",
        })

    return records, defect_map


def _detect_format_mismatch(records: list[dict]) -> tuple[str | None, list[dict]]:
    """
    Check that all records share the same format_type.

    Returns
    -------
    (dominant_format, mismatched_records)
      dominant_format   : the format_type that appears most (or None if empty)
      mismatched_records: records whose format_type differs from dominant_format
    """
    if not records:
        return None, []

    from collections import Counter
    counts = Counter(r["_format_type"] for r in records)
    dominant = counts.most_common(1)[0][0]
    mismatched = [r for r in records if r["_format_type"] != dominant]
    return dominant, mismatched


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class AuditExportView(APIView):
    """
    GET /api/final-summary/export/

    Required params : factory, client, date_from, date_to
    Optional params : style (CSV), po (CSV)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ── 1. Parse & validate params ────────────────────────────────────────
        factory   = request.query_params.get("factory",   "").strip()
        client    = request.query_params.get("client",    "").strip()
        date_from = request.query_params.get("date_from", "").strip()
        date_to   = request.query_params.get("date_to",   "").strip()
        styles    = _parse_csv_param(request.query_params.get("style", ""))
        pos       = _parse_csv_param(request.query_params.get("po",    ""))

        missing = []
        if not factory:   missing.append("factory")
        if not client:    missing.append("client")
        if not date_from: missing.append("date_from")
        if not date_to:   missing.append("date_to")

        if missing:
            return Response(
                {"detail": f"Required parameters missing: {', '.join(missing)}"},
                status=400,
            )

        # ── 2. Build queryset ─────────────────────────────────────────────────
        try:
            qs = (
                AuditReport.objects
                .select_related("batch")
                .filter(
                    factory__iexact=factory,
                    client__iexact=client,
                    date_of_issue__gte=date_from,
                    date_of_issue__lte=date_to,
                )
                .order_by("date_of_issue", "style_no")
            )

            # Optional style / PO OR filter
            sp_filter = _build_style_po_filter(styles, pos)
            if sp_filter is not None:
                qs = qs.filter(sp_filter)

            reports = list(qs)

        except Exception as exc:
            logger.exception("Export query failed: %s", exc)
            return Response({"detail": "Query failed."}, status=500)

        if not reports:
            return Response(
                {"detail": "No records found for the given filters."},
                status=404,
            )

        # ── 3. Build writer data ──────────────────────────────────────────────
        records, defect_map = _build_records_for_writer(reports)

        # ── 4. Format-type mismatch check ─────────────────────────────────────
        dominant_format, mismatched = _detect_format_mismatch(records)

        if mismatched:
            mismatch_details = [
                {
                    "file_name":    r["file_name"],
                    "format_type":  r["_format_type"],
                    "expected":     dominant_format,
                    "factory":      r["factory"],
                    "date_of_issue": r["date_of_issue"],
                }
                for r in mismatched
            ]
            return Response(
                {
                    "detail": (
                        f"Format-type mismatch detected. "
                        f"Dominant format is '{dominant_format}' but "
                        f"{len(mismatched)} record(s) use a different format. "
                        f"Please fix or skip these records via the Retry flow "
                        f"before exporting."
                    ),
                    "dominant_format":  dominant_format,
                    "mismatch_count":   len(mismatched),
                    "mismatched_records": mismatch_details,
                },
                status=409,
            )

        # Strip internal key before passing to writer
        for r in records:
            r.pop("_format_type", None)

        # ── 5. Select template ────────────────────────────────────────────────
        TEMPLATE_MAP = {
            "SPI":     "SPI-Final-78.xlsx",
            "REGULAR": "General-Final-37.xlsx",
            "SWEATER": "General-Final-37.xlsx",
        }
        template_name = TEMPLATE_MAP.get(dominant_format, "SPI-Final-78.xlsx")
        template_path = (
            Path(settings.BASE_DIR) / "media" / "templates" / template_name
        )

        if not template_path.exists():
            logger.error("Template not found: %s", template_path)
            return Response(
                {"detail": f"Template file '{template_name}' not found on server."},
                status=500,
            )

        # ── 6. Generate Excel ─────────────────────────────────────────────────
        output_dir = Path(settings.BASE_DIR) / "media" / "output" / "final_summary"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename  = (
            f"audit_summary_{factory.replace(' ', '_')}_"
            f"{client.replace(' ', '_')}_{timestamp}.xlsx"
        )
        output_path = output_dir / filename

        try:
            from final_summary.helpers.summary_writer import write_summary
            write_summary(
                records=records,
                defect_items_by_report=defect_map,
                output_path=output_path,
                template_path=template_path,
                format_type=dominant_format,
            )
        except Exception as exc:
            logger.exception("Summary generation failed: %s", exc)
            return Response(
                {"detail": f"Could not generate Excel file: {exc}"},
                status=500,
            )

        # ── 7. Stream file ────────────────────────────────────────────────────
        logger.info(
            "Export generated: factory=%r client=%r %s→%s template=%s records=%d",
            factory, client, date_from, date_to, template_name, len(records),
        )
        return FileResponse(
            open(output_path, "rb"),
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )


================================================
FILE: backend/final_summary/views/filter_options_view.py
================================================
import logging
from django.db.models import Min, Max
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import AuditReport

logger = logging.getLogger(__name__)


class AuditFilterOptionsView(APIView):
    """
    GET /api/audit/options/

    Returns all distinct dimension values that exist in the DB, scoped to
    the current user's batches (staff see everything).

    Response shape:
      {
        "factories":  [...],
        "clients":    [...],
        "min_date":   "YYYY-MM-DD" | null,
        "max_date":   "YYYY-MM-DD" | null,
        "styles":     [...],
        "po_numbers": [...]
      }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            qs = AuditReport.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(batch__created_by=request.user)

            factories  = sorted(
                qs.exclude(factory="").values_list("factory",  flat=True).distinct()
            )
            clients    = sorted(
                qs.exclude(client="").values_list("client",    flat=True).distinct()
            )
            styles     = sorted(
                qs.exclude(style_no="").values_list("style_no", flat=True).distinct()
            )
            po_numbers = sorted(
                qs.exclude(po_no="").values_list("po_no",      flat=True).distinct()
            )

            date_range = qs.filter(date_of_issue__isnull=False).aggregate(
                min_date=Min("date_of_issue"),
                max_date=Max("date_of_issue"),
            )

            return Response({
                "factories":  factories,
                "clients":    clients,
                "min_date":   date_range["min_date"],
                "max_date":   date_range["max_date"],
                "styles":     styles,
                "po_numbers": po_numbers,
            })

        except Exception as exc:
            logger.exception("Filter options error: %s", exc)
            return Response({"detail": "Could not load filter options."}, status=500)



================================================
FILE: backend/final_summary/views/logs_view.py
================================================
"""
views/logs_view.py
-------------------
Two read-only endpoints for batch error/log inspection:

GET /final-summary/batches/<pk>/logs/
  Returns a structured breakdown of what failed in a batch — each error
  line from batch.error_log split into file_name + reason.

GET /final-summary/batches/<pk>/logs/error-json/
  Returns a downloadable JSON payload that the user can fix and re-POST
  to /final-summary/retry/.  Only blocked records (those in error_log)
  are included — successfully extracted records are not re-exported.

Error-JSON shape (same as utils/error_json_writer.py):
  {
    "version":       "1.0",
    "batch_id":      42,
    "generated_at":  "2026-01-05T10:30:00",
    "total_blocked": 3,
    "instructions":  "...",
    "records": [
      {
        "file_name":       "DH26-01ABC-001.xlsx",
        "blocking_errors": ["REQUIRED_FIELD | factory | Factory name is missing"],
        "validation_errors": [],
        "factory": "",
        "client":  "",
        ... (all other AuditRecord fields the user can edit)
      }
    ]
  }
"""
import logging
from datetime import datetime

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import UploadBatch, AuditReport

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "Fix the fields listed in 'blocking_errors' for each record. "
    "Then POST this file (with batch_id) to /final-summary/retry/. "
    "Do NOT change the 'file_name' field — it is the unique identifier."
)


def _parse_error_lines(error_log: str) -> list[dict]:
    """
    Split batch.error_log into structured dicts.

    Each line has the format:
      "<file_name>: <reason>"
    or just a plain reason string if no colon is present.
    """
    parsed = []
    for raw_line in (error_log or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ": " in line:
            file_name, _, reason = line.partition(": ")
            parsed.append({
                "file_name": file_name.strip(),
                "reason":    reason.strip(),
            })
        else:
            parsed.append({
                "file_name": "",
                "reason":    line,
            })
    return parsed


class AuditBatchLogsView(APIView):
    """
    GET /final-summary/batches/<pk>/logs/
    Returns structured error log for a batch.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            qs = UploadBatch.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            batch = qs.get(pk=pk)
        except UploadBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        error_lines = _parse_error_lines(batch.error_log)

        return Response({
            "batch_id":      batch.pk,
            "status":        batch.status,
            "total_files":   batch.total_files,
            "processed":     batch.processed_files,
            "failed":        batch.failed_files,
            "success_rate":  batch.success_rate,
            "error_count":   len(error_lines),
            "errors":        error_lines,
            "raw_error_log": batch.error_log or "",
        })


class AuditBatchErrorJsonView(APIView):
    """
    GET /final-summary/batches/<pk>/logs/error-json/

    Returns a JSON payload containing one record stub per failed file.
    The user fills in the missing/wrong fields and POSTs the result
    to /final-summary/retry/ to save them to the DB.

    For files that were blocked during extraction (no AuditReport row
    was created), we return a minimal stub with only the file_name and
    blocking_errors populated — the user must fill in the rest.

    For files that were extracted but blocked during validation, we
    return the full AuditReport data pre-populated so the user only
    needs to fix the flagged fields.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            qs = UploadBatch.objects.all()
            if not request.user.is_staff:
                qs = qs.filter(created_by=request.user)
            batch = qs.get(pk=pk)
        except UploadBatch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        error_lines = _parse_error_lines(batch.error_log)

        if not error_lines:
            return Response({
                "batch_id":      batch.pk,
                "total_blocked": 0,
                "records":       [],
                "message":       "No errors — nothing to retry.",
            })

        records_out = []

        for err in error_lines:
            file_name = err["file_name"]
            reason    = err["reason"]

            # Try to find an existing (partially-saved) AuditReport for this file
            existing = None
            if file_name:
                existing = AuditReport.objects.filter(
                    batch=batch, file_name=file_name
                ).first()

            if existing:
                # Pre-populate from DB so user fixes as little as possible
                records_out.append({
                    "file_name":         existing.file_name,
                    "blocking_errors":   [r for r in (existing.blocking_errors or "").split(", ") if r],
                    "validation_errors": [r for r in (existing.validation_errors or "").split(", ") if r],
                    "factory":           existing.factory,
                    "client":            existing.client,
                    "date_of_issue":     str(existing.date_of_issue) if existing.date_of_issue else "",
                    "inspection_type":   existing.inspection_type,
                    "report_no":         existing.report_no,
                    "audit_report":      existing.audit_report,
                    "item_name":         existing.item_name,
                    "style_no":          existing.style_no,
                    "po_no":             existing.po_no,
                    "country":           existing.country,
                    "factory_in_time":   existing.factory_in_time,
                    "factory_out_time":  existing.factory_out_time,
                    "factory_total_hours": existing.factory_total_hours,
                    "audit_start_time":  existing.audit_start_time,
                    "audit_end_time":    existing.audit_end_time,
                    "audit_total_hours": existing.audit_total_hours,
                    "audit_result":      existing.audit_result,
                    "po_qty":            existing.po_qty,
                    "po_qty_pcs":        existing.po_qty_pcs,
                    "po_qty_pack":       existing.po_qty_pack,
                    "po_qty_set":        existing.po_qty_set,
                    "do_qty":            existing.do_qty,
                    "ship_qty":          existing.ship_qty,
                    "audit_qty":         existing.audit_qty,
                    "exf":               str(existing.exf) if existing.exf else "",
                    "po_edt":            str(existing.po_edt) if existing.po_edt else "",
                    "po_wh":             str(existing.po_wh) if existing.po_wh else "",
                    "plan_edt":          str(existing.plan_edt) if existing.plan_edt else "",
                    "plan_wh":           str(existing.plan_wh) if existing.plan_wh else "",
                    "defect_qty":        existing.defect_qty,
                    "acceptable_defect_qty": existing.acceptable_defect_qty,
                    "defect_percentage": existing.defect_percentage,
                    "person":            existing.person,
                    "inspector":         existing.inspector,
                    "carton":            existing.carton,
                    "needle_detector":   existing.needle_detector,
                    "remarks":           existing.remarks,
                    "do_set_col_size":   existing.do_set_col_size,
                    "do_note":           existing.do_note,
                    "defect_rows":       [],   # user cannot edit these; defects stay as-is
                    "do_orders":         [],
                })
            else:
                # Extraction failed entirely — return a minimal stub
                records_out.append({
                    "file_name":         file_name,
                    "blocking_errors":   [reason],
                    "validation_errors": [],
                    # All editable fields blank — user must fill in
                    "factory":           "",
                    "client":            "",
                    "date_of_issue":     "",
                    "inspection_type":   "",
                    "report_no":         "",
                    "audit_report":      "",
                    "item_name":         "",
                    "style_no":          "",
                    "po_no":             "",
                    "country":           "",
                    "factory_in_time":   "",
                    "factory_out_time":  "",
                    "factory_total_hours": "",
                    "audit_start_time":  "",
                    "audit_end_time":    "",
                    "audit_total_hours": "",
                    "audit_result":      "-",
                    "po_qty":            "",
                    "po_qty_pcs":        0,
                    "po_qty_pack":       0,
                    "po_qty_set":        0,
                    "do_qty":            0,
                    "ship_qty":          "",
                    "audit_qty":         "",
                    "exf":               "",
                    "po_edt":            "",
                    "po_wh":             "",
                    "plan_edt":          "",
                    "plan_wh":           "",
                    "defect_qty":        "",
                    "acceptable_defect_qty": "-",
                    "defect_percentage": "",
                    "person":            "",
                    "inspector":         "",
                    "carton":            "",
                    "needle_detector":   "",
                    "remarks":           "",
                    "do_set_col_size":   "",
                    "do_note":           "",
                    "defect_rows":       [],
                    "do_orders":         [],
                })

        return Response({
            "version":       "1.0",
            "batch_id":      batch.pk,
            "generated_at":  datetime.utcnow().isoformat(timespec="seconds"),
            "total_blocked": len(records_out),
            "instructions":  _INSTRUCTIONS,
            "records":       records_out,
        })


================================================
FILE: backend/final_summary/views/retry_view.py
================================================
"""
views/retry_view.py
--------------------
POST /final-summary/retry/

After a bulk upload some records fail blocking validation (e.g. factory
name missing, date unreadable).  The task writes those blocked records into
batch.error_log as a newline list.  The frontend can download a structured
error JSON via GET /final-summary/batches/<pk>/logs/error-json/ and let the
user fix the fields manually, then re-upload the corrected JSON here.

Flow
----
1. Frontend downloads  GET /final-summary/batches/<pk>/logs/error-json/
   → returns { batch_id, records: [{file_name, factory, client, ...}, ...] }
2. User opens JSON, fixes the flagged fields.
3. Frontend POSTs the fixed JSON to this endpoint.
4. We re-validate every record in the JSON.
5. Records that now pass → saved to DB, linked to the original batch.
6. Records that still fail → returned in the response as "still_blocked".

Request body (JSON):
  {
    "batc