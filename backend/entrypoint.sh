#!/bin/bash

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

# 4. Start the server
echo "Starting server..."
exec daphne -b 0.0.0.0 -p 8000 summary_backend.asgi:application