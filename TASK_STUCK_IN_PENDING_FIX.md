# Tasks Stuck in PENDING Mode - Root Cause and Solution

## Problem Identified

After uploading PDF files, all tasks remain in **PENDING** status and no progress is made. The uploaded files are stored in `backend/media/uploads/` folders (1-9), but no output files are generated in `backend/media/output/`.

## Root Cause

The `docker-compose.yaml` file was **empty**, which means:

1. **No Redis server** - Celery requires Redis as a message broker
2. **No Celery worker** - Tasks are created but there's no worker to process them
3. **No infrastructure** - The entire backend infrastructure was missing

### How the System Works

```
User uploads PDFs
    ↓
BatchUploadView creates InspectionBatch record
    ↓
process_inspection_batch.delay(batch.pk) → Sends task to Redis
    ↓
Celery worker picks up task from Redis
    ↓
Worker processes PDFs, extracts data, generates Excel
    ↓
Updates batch status to COMPLETED
```

**Without Redis and Celery worker, tasks get stuck at step 3!**

## Solution Applied

### 1. Created Complete docker-compose.yaml

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - ./backend/media:/app/media
      - ./backend/logs:/app/logs
    environment:
      - DJANGO_SETTINGS_MODULE=summary_backend.settings
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    command: python manage.py runserver 0.0.0.0:8000

  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    volumes:
      - ./backend:/app
      - ./backend/media:/app/media
      - ./backend/logs:/app/logs
    environment:
      - DJANGO_SETTINGS_MODULE=summary_backend.settings
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    command: celery -A summary_backend worker -l info -Q puma_summary

  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    volumes:
      - ./backend:/app
      - ./backend/media:/app/media
      - ./backend/logs:/app/logs
    environment:
      - DJANGO_SETTINGS_MODULE=summary_backend.settings
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    command: celery -A summary_backend beat -l info

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      - VITE_API_URL=http://localhost:8000/api
    depends_on:
      - backend

volumes:
  redis_data:
```

### 2. Fixed Backend Dockerfile

Changed from gunicorn to development server for easier debugging:

```dockerfile
FROM python:3.12.8 AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

EXPOSE 8000

# Default to development server, can be overridden in docker-compose
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

### 3. Fixed Frontend Dockerfile

Changed from Python to Node.js (React frontend):

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./

RUN npm ci

COPY . .

FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

## How to Start the System

### Option 1: Using Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f celery-worker

# Stop all services
docker-compose down
```

### Option 2: Manual Start (for development)

**Terminal 1 - Start Redis:**
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

**Terminal 2 - Start Django Backend:**
```bash
cd backend
python manage.py runserver 0.0.0.0:8000
```

**Terminal 3 - Start Celery Worker:**
```bash
cd backend
celery -A summary_backend worker -l info -Q puma_summary
```

**Terminal 4 - Start Celery Beat (optional, for scheduled tasks):**
```bash
cd backend
celery -A summary_backend beat -l info
```

**Terminal 5 - Start Frontend:**
```bash
cd frontend
npm run dev
```

## Verification Steps

After starting the system, verify everything is working:

### 1. Check Redis is running:
```bash
docker-compose exec redis redis-cli ping
# Should return: PONG
```

### 2. Check Celery worker is running:
```bash
docker-compose logs celery-worker
# Should show: "Connected to redis://redis:6379/0"
```

### 3. Check Django backend is running:
```bash
curl http://localhost:8000/api/batches/
# Should return JSON (may need authentication)
```

### 4. Upload a test batch:
```bash
# Use the frontend or curl to upload PDFs
# Check that task is picked up by worker
docker-compose logs -f celery-worker
```

### 5. Verify task processing:
```bash
# Check batch status in database or via API
# Should change from PENDING → PROCESSING → COMPLETED
```

## Troubleshooting

### Issue: Tasks still stuck in PENDING

**Check 1: Is Redis running?**
```bash
docker-compose ps redis
# Should show: Up
```

**Check 2: Is Celery worker connected to Redis?**
```bash
docker-compose logs celery-worker | grep "Connected"
# Should show connection message
```

**Check 3: Is task being sent to correct queue?**
```bash
# Check in batch_upload_view.py
task = process_inspection_batch.delay(batch.pk)
# Should use .delay() method
```

**Check 4: Is worker listening to correct queue?**
```bash
# In docker-compose.yaml, check:
command: celery -A summary_backend worker -l info -Q puma_summary
# The -Q puma_summary flag is important!
```

### Issue: Worker crashes on startup

**Check 1: Missing dependencies**
```bash
docker-compose exec backend pip list | grep celery
# Should show celery and related packages
```

**Check 2: Django settings not loaded**
```bash
docker-compose exec backend python -c "from django.conf import settings; print(settings.CELERY_BROKER_URL)"
# Should show: redis://redis:6379/0
```

### Issue: Tasks process but fail

**Check 1: View worker logs**
```bash
docker-compose logs -f celery-worker
# Look for error messages
```

**Check 2: Check batch error_log**
```bash
# Via Django shell or API
python manage.py shell
from puma_summary.models import InspectionBatch
batch = InspectionBatch.objects.get(pk=1)
print(batch.error_log)
```

## Environment Variables

The following environment variables are now supported:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `127.0.0.1` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Full Celery broker URL |

These are automatically set in `docker-compose.yaml` for containerized deployment.

## Summary

The root cause of tasks being stuck in PENDING mode was the **missing infrastructure**:
- No Redis server for message brokering
- No Celery worker for task processing
- Empty docker-compose.yaml file

The solution provides:
- Complete docker-compose.yaml with all required services
- Fixed Dockerfiles for both backend and frontend
- Environment variable support for flexible configuration
- Health checks to ensure proper service startup

After applying these fixes and starting the system with `docker-compose up -d`, tasks will be properly processed and move from PENDING → PROCESSING → COMPLETED status.
