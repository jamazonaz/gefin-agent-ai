# Build context: repo root (see render.yaml dockerContext / docker-compose.yml build.context)
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY catalog ./catalog

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV CATALOG_PATH=/app/catalog/metrics.yaml

EXPOSE 8000

# APP_ENV=development (set by docker-compose.yml locally) enables --reload.
# Unset (Render) runs without --reload.
CMD ["sh", "-c", "if [ \"$APP_ENV\" = development ]; then uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload; else uvicorn app.main:app --host 0.0.0.0 --port 8000; fi"]
