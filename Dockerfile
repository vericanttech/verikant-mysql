# Google Cloud Run: listens on $PORT (default 8080)
FROM python:3.11-slim

WORKDIR /app

# Some wheels build from source; keep image minimal
RUN apt-get update \
  && apt-get install -y --no-install-recommends gcc libffi-dev \
  && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

COPY requirements-cloud.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt

COPY . .

# SQLite fallback (ephemeral on Cloud Run — use DATABASE_URL for Postgres)
RUN mkdir -p instance

# run.py exposes `app` for Gunicorn
CMD exec gunicorn \
  --bind 0.0.0.0:${PORT} \
  --workers 2 \
  --threads 4 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  "run:app"
