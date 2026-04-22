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