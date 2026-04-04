# MySQL migration & PythonAnywhere deployment

This document summarizes work done to run the Verikant / POS Flask app on **MySQL** (PythonAnywhere), migrate data from **SQLite**, fix cross-database issues, and add tooling and deployment files.

---

## 1. Goals

- Use **MySQL** on PythonAnywhere instead of local SQLite for production.
- **Migrate** existing data from `instance/shop.db` to MySQL without losing rows (with known caveats below).
- Connect from a **local PC** via **SSH tunnel** when the DB is only reachable through PA.
- **Deploy** the app from GitHub to PythonAnywhere with a clear WSGI and environment setup.

---

## 2. Application & schema changes (high level)

| Area | Change |
|------|--------|
| **Database URL** | `app/__init__.py` builds the MySQL URL with `URL.create(...).render_as_string(hide_password=False)` so the password is not masked as `***` (fixes MySQL **1045** with SQLAlchemy). |
| **`sales_bills.bill_number`** | Switched from `Integer` to **`BigInteger`** — composite-style numbers (e.g. `260225008001`) exceed MySQL signed **INT** and caused duplicate key errors on `(shop_id, bill_number)`. Alembic revision `b2c8e9f1a3d4_sales_bills_bill_number_bigint.py`. |
| **Dashboard** | `app/routes/dashboard.py` — removed SQLite-only `func.datetime(...)`. **MySQL** does not support that; ordering uses `SalesBill.date.desc()`, etc., on string date columns (ISO-like strings sort chronologically). |
| **SSH tunnel** | `app/ssh_tunnel_db.py` — same URL/password handling when rewriting the host to `127.0.0.1` for local tunneling. |
| **Models** | Various **String** lengths and indexes adjusted for MySQL (earlier work): indexed columns use `String` instead of unbounded `Text` where required. |

---

## 3. SQLite → MySQL data migration (`scripts/migrate_sqlite_to_mysql.py`)

**Purpose:** Copy all application tables from a local SQLite file (default `instance/shop.db`) into the MySQL database configured in `.env`.

**Features:**

- Inserts in **foreign-key order**; disables `FOREIGN_KEY_CHECKS` during load; resets `AUTO_INCREMENT` where applicable.
- **User names:** MySQL unique index on `users.name` is **case-insensitive**; duplicate spellings (e.g. `Amadou` vs `amadou`) are disambiguated with a ` [id]` suffix on later rows.
- **Categories:** Same idea for unique `(shop_id, name)` when case-only duplicates exist in SQLite.
- **Batched inserts** (`--batch-size`, default 500) and `SET SESSION unique_checks=0` during load for speed over SSH.
- **`--truncate --yes`:** Deletes all app tables on MySQL before import (destructive).

**Run (examples):**

```bash
python scripts/migrate_sqlite_to_mysql.py --dry-run
python scripts/migrate_sqlite_to_mysql.py --truncate --yes
```

**Requires:** `PA_MYSQL_*` / `PA_MYSQL_BUILD_URL=1`, optional `SSH_TUNNEL=1` for local runs. Run `flask db upgrade` on MySQL **before** importing.

---

## 4. Verification & diagnostics

| File | Role |
|------|------|
| **`scripts/verify_migration_counts.py`** | Compares **row counts** per table between SQLite and MySQL. `--no-ssh` sets `SSH_TUNNEL=0` for that run. |
| **`scripts/test_mysql_connection.py`** | Diagnostics for MySQL connectivity, env/password fingerprinting (no full secrets printed). |

---

## 5. PythonAnywhere API helpers

| File | Role |
|------|------|
| **`scripts/pa_reload_webapp.py`** | `POST` to the PA API to **reload** the web app after deploy. Env: `PA_API_TOKEN`, `PA_DEPLOY_USERNAME`, `PA_WEBAPP_DOMAIN`, `PA_API_HOST`. |
| **`scripts/pa_upload_static_files.py`** | Uploads a local folder (default `app/static/uploads`) to PA via the **Files API**, file by file. Reads **`load_dotenv(.env)`**; supports `PA_API_TOKEN`, `PA_DEPLOY_USERNAME`, `PA_API_HOST`, `PA_UPLOAD_REMOTE_PREFIX`, `PA_UPLOAD_SOURCE`, `PA_UPLOAD_DELAY`. Requires `requests`. |

See [PythonAnywhere API help](https://help.pythonanywhere.com/pages/API/).

---

## 6. WSGI & entry points

| File | Role |
|------|------|
| **`wsgi.py`** (repo root) | Standard WSGI entry: adds project root to `sys.path`, `application = create_app()`. Used by Gunicorn/PA when the working directory is the project root. |
| **`deploy/pythonanywhere_var_www_wsgi.py`** | **Snippet to paste** into `/var/www/<username>_pythonanywhere_com_wsgi.py` on PythonAnywhere: sets `SSH_TUNNEL=0`, extends `sys.path`, imports `application` from `wsgi`, wraps with **ProxyFix** for HTTPS behind PA’s proxy. |

---

## 7. Environment variables

Loaded in **`app/__init__.py`** via `load_dotenv(project_root / '.env')`.

**MySQL (recommended on PA):**

- `PA_MYSQL_BUILD_URL=1`
- `PA_MYSQL_USER`, `PA_MYSQL_HOST`, `PA_MYSQL_PORT`, `PA_MYSQL_PASSWORD`, `PA_MYSQL_DATABASE` (e.g. `vericant$shop` — quote in `.env` if `$` is interpreted by the shell)

**App:**

- `SECRET_KEY`

**Local dev tunnel (not for PA web workers):**

- `SSH_TUNNEL=1`, `PA_SSH_USER`, `PA_SSH_HOST`, `PA_SSH_PASSWORD` or `PA_SSH_KEY_PATH`

**Optional (scripts / CI):**

- `PA_API_TOKEN`, `PA_DEPLOY_USERNAME`, `PA_WEBAPP_DOMAIN`, `PA_API_HOST`
- `PA_UPLOAD_REMOTE_PREFIX`, `PA_UPLOAD_SOURCE`, `PA_UPLOAD_DELAY`

Full template: **`.env.example`**.

---

## 8. Repository & packaging

- **`requirements.txt`** must be **UTF-8** (not UTF-16); otherwise `pip` fails on Linux/PA. Includes **`requests`** for upload/reload helpers.
- **`.gitignore`** excludes `.env`, `venv/`, `instance/`, `*.db`, **`app/static/uploads/`**, **`app/static/backups/`**, and stray local caches (`.cache/`, `.npm/`, etc.).
- **Remote:** [github.com/vericanttech/verikant-mysql](https://github.com/vericanttech/verikant-mysql) — clone on PA under e.g. `~/verikant-mysql`.

---

## 9. PythonAnywhere web app (checklist)

1. **Clone** repo, **venv** (`python3.10 -m venv venv`), `pip install -r requirements.txt`.
2. **Web** tab: **Source code** and **Working directory** = `/home/<user>/verikant-mysql`, **Virtualenv** = `.../verikant-mysql/venv`, **Python 3.10**.
3. Paste **`deploy/pythonanywhere_var_www_wsgi.py`** contents into **`/var/www/..._wsgi.py`** (adjust `PROJECT_ROOT` if path differs).
4. **Static files** mapping: URL `/static/` → `/home/<user>/verikant-mysql/app/static`.
5. **`.env`** on the server (or **Environment variables** in the Web tab) — no `SSH_TUNNEL` for production workers.
6. **`flask db upgrade`** once against MySQL.
7. **Reload** web app.

---

## 10. Security reminders

- **Rotate** any password or API token that was ever pasted into chat or committed by mistake.
- Never commit **`.env`** or **`app/static/uploads/`** (may contain shop/customer data).
- Treat **PA API tokens** like passwords; use env vars or CI secrets only.

---

## 11. Index of files added or central to this work

| Path | Description |
|------|-------------|
| `scripts/migrate_sqlite_to_mysql.py` | Bulk copy SQLite → MySQL with FK order, dedup names, batching. |
| `scripts/verify_migration_counts.py` | Compare table row counts SQLite vs MySQL. |
| `scripts/test_mysql_connection.py` | MySQL connection diagnostics. |
| `scripts/pa_reload_webapp.py` | Reload PA web app via API. |
| `scripts/pa_upload_static_files.py` | Upload local `uploads` tree via PA Files API (uses `.env`). |
| `wsgi.py` | WSGI `application` for hosting. |
| `deploy/pythonanywhere_var_www_wsgi.py` | Paste-ready `/var/www/...` WSGI snippet for PA. |
| `migrations/versions/b2c8e9f1a3d4_sales_bills_bill_number_bigint.py` | Alembic: `sales_bills.bill_number` → BIGINT. |
| `docs/MYSQL_AND_PYTHONANYWHERE.md` | This document. |

Related edits elsewhere: `app/__init__.py`, `app/ssh_tunnel_db.py`, `app/models.py`, `app/routes/dashboard.py`, `.env.example`, `.gitignore`, `requirements.txt`.

---

## 12. Operational notes

- **Performance:** App + MySQL on the same PythonAnywhere system is much faster than running the app on a PC with an SSH tunnel to MySQL.
- **SQLite** remains a valid local fallback when `PA_MYSQL_BUILD_URL` is not set; default SQLite path is `instance/shop.db`.

If you change schema again, add Alembic migrations and re-run **`flask db upgrade`** before re-importing data if needed.
