FROM python:3.12.8 AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

EXPOSE 8080

CMD ["gunicorn", "your_project.wsgi:application", "--bind", "0.0.0.0:8080"]