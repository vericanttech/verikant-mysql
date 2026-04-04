# Deploy this Flask app to Google Cloud Run

This project is a standard Flask factory app (`create_app` in `app/__init__.py`, WSGI `app` in `run.py`).

## What you get

- **`Dockerfile`** — runs **Gunicorn** on **`0.0.0.0:$PORT`** (required by Cloud Run).
- **`requirements-cloud.txt`** — same as `requirements.txt` plus **`psycopg2-binary`** for PostgreSQL.
- **`.dockerignore`** — excludes `.local/`, `.npm/`, venvs, and local DBs so builds stay small.

## Important: database

The app defaults to **SQLite** under `instance/shop.db`. On Cloud Run the container filesystem is **ephemeral** — data is lost when the revision is replaced or scaled.

For production, set a managed database and point the app at it:

```bash
# Cloud SQL Postgres (or any Postgres) connection string
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@/DBNAME?host=/cloudsql/PROJECT:REGION:INSTANCE
```

(Exact socket/host format depends on how you connect Cloud Run to Cloud SQL — use the Google doc for “Cloud Run + Cloud SQL”.)

If `DATABASE_URL` or `SQLALCHEMY_DATABASE_URI` is set, the app uses it (with a small `postgres://` → `postgresql://` fix for some providers).

## Environment variables

| Variable | Required | Notes |
|----------|----------|--------|
| `SECRET_KEY` | **Yes** (prod) | Flask session signing; use a long random string |
| `DATABASE_URL` or `SQLALCHEMY_DATABASE_URI` | Recommended | Postgres (or other) SQLAlchemy URL |
| `PORT` | No | Set automatically by Cloud Run |

`K_SERVICE` is set by Cloud Run; the app uses it to enable **ProxyFix** (correct URLs behind HTTPS termination).

## Build and deploy (CLI sketch)

Prereqs: `gcloud` authenticated, APIs enabled (Cloud Run, Artifact Registry or Container Registry), billing enabled.

```bash
cd verikant-mysql

# Pick project / region
gcloud config set project YOUR_PROJECT_ID
export REGION=europe-west1
export SERVICE=vericant-flask

# Build with Cloud Build and deploy (example)
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-secrets "SECRET_KEY=your-secret:latest" \
  --set-env-vars "DATABASE_URL=postgresql+psycopg2://..."
```

Adjust secrets/env to your setup (`--set-secrets` vs `--set-env-vars`). For a first smoke test without a DB, the container will start with SQLite in an empty `instance/` (you still need to run migrations / create schema — same as on PythonAnywhere).

## Local Docker test

```bash
docker build -t vericant-flask .
docker run --rm -p 8080:8080 -e SECRET_KEY=dev-secret -e PORT=8080 vericant-flask
# Open http://localhost:8080
```
</think>


<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
StrReplace