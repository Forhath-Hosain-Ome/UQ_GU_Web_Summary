FROM python:3.12.8 AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libreoffice-writer \
    fonts-dejavu \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*
    
COPY --from=builder /install /usr/local

COPY . .

EXPOSE 8000

# Default to development server, can be overridden in docker-compose
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]