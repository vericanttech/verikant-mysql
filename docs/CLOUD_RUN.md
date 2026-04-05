# Deploy this Flask app to Google Cloud Run

This project is a standard Flask factory app (`create_app` in `app/__init__.py`, WSGI `app` in `run.py`).

## What you get

- **`Dockerfile`** — runs **Gunicorn** on **`0.0.0.0:$PORT`** (required by Cloud Run).
- **`requirements-cloud.txt`** — same as `requirements.txt` plus **`psycopg2-binary`** for PostgreSQL.
- **`.dockerignore`** — excludes `.local/`, `.npm/`, venvs, and local DBs so builds stay small.

## Important: database

**Do not rely on the built-in SQLite fallback on Cloud Run.** The container filesystem is **ephemeral** — anything under `instance/` is lost when the revision is replaced or scaled.

Set a managed database and point the app at it (same as a typical MySQL/Postgres deployment):

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

Adjust secrets/env to your setup (`--set-secrets` vs `--set-env-vars`). A smoke test without `DATABASE_URL` may still boot using the optional SQLite fallback in an empty `instance/`, but that is not a durable or recommended setup for Cloud Run.

## Local Docker test

```bash
docker build -t vericant-flask .
docker run --rm -p 8080:8080 -e SECRET_KEY=dev-secret -e PORT=8080 vericant-flask
# Open http://localhost:8080
```
</think>


<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
StrReplace