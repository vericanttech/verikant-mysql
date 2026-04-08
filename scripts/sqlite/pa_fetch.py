"""Download the production SQLite DB from PythonAnywhere via the Files API.

Uses PA_API_TOKEN (Account → API token). Skips re-download if the local file exists
and was written less than CACHE_MAX_AGE_SEC ago (default 1 hour), unless force=True.

Env (see .env):
  PA_API_TOKEN      — required for download
  PA_USERNAME       — PythonAnywhere account name for the Files API (optional if PA_MYSQL_USER is set)
  PA_MYSQL_USER     — reused as username when PA_USERNAME is unset (same account on PA)
  PA_HOST           — www.pythonanywhere.com (EU: eu.pythonanywhere.com)
  PA_REMOTE_SQLITE_PATH — full path to .db on the server (optional; see defaults below)
  PA_REMOTE_PATH    — project root on PA (default /home/<user>/POS-Master); used if
                      PA_REMOTE_SQLITE_PATH is unset: <PA_REMOTE_PATH>/instance/shop.db

Local output: scripts/sqlite/shop_from_pa.db (next to this package).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_SQLITE_DIR = Path(__file__).resolve().parent
_DEFAULT_LOCAL = _SCRIPTS_SQLITE_DIR / "shop_from_pa.db"

CACHE_MAX_AGE_SEC = int(os.getenv("PA_SQLITE_CACHE_SEC", "3600"))


def _pa_username() -> str:
    """PythonAnywhere account name: PA_USERNAME, else PA_MYSQL_USER (same as DB user on PA)."""
    u = (os.getenv("PA_USERNAME") or "").strip()
    if u:
        return u
    return (os.getenv("PA_MYSQL_USER") or "").strip()


def _remote_sqlite_path() -> str:
    explicit = (os.getenv("PA_REMOTE_SQLITE_PATH") or "").strip()
    if explicit:
        return explicit
    user = _pa_username() or "vericant"
    base = (os.getenv("PA_REMOTE_PATH") or "").strip()
    if not base:
        base = f"/home/{user}/POS-Master"
    base = base.rstrip("/")
    return f"{base}/instance/shop.db"


def _api_get(url: str, headers: dict, stream: bool = False) -> requests.Response:
    for attempt in range(2):
        resp = requests.get(url, headers=headers, stream=stream, timeout=120)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            print(f"  Rate-limited; waiting {retry_after}s...")
            time.sleep(retry_after)
            continue
        return resp
    return resp


def fetch_pythonanywhere_sqlite(
    *,
    local_path: Path | None = None,
    force: bool = False,
    cache_max_age_sec: int | None = None,
) -> Path:
    """
    Ensure ``local_path`` (default: scripts/sqlite/shop_from_pa.db) exists and is fresh.

    Returns the path to the local SQLite file.
    """
    token = (os.getenv("PA_API_TOKEN") or "").strip()
    username = _pa_username()
    host = (os.getenv("PA_HOST") or "www.pythonanywhere.com").strip()

    if not token:
        print("ERROR: Set PA_API_TOKEN in .env (PythonAnywhere → Account → API token).", file=sys.stderr)
        sys.exit(1)
    if not username:
        print(
            "ERROR: Set PA_USERNAME or PA_MYSQL_USER (PythonAnywhere account name).",
            file=sys.stderr,
        )
        sys.exit(1)

    out = local_path or _DEFAULT_LOCAL
    out.parent.mkdir(parents=True, exist_ok=True)

    max_age = cache_max_age_sec if cache_max_age_sec is not None else CACHE_MAX_AGE_SEC
    if out.is_file() and not force:
        age = time.time() - out.stat().st_mtime
        if age < max_age:
            print(
                f"Using cached SQLite ({age / 60:.1f} min old, < {max_age / 60:.0f} min): {out}"
            )
            return out.resolve()

    remote = _remote_sqlite_path()
    base_url = f"https://{host}/api/v0/user/{username}/"
    headers = {"Authorization": f"Token {token}"}
    url = urljoin(base_url, f"files/path{remote}")

    print(f"Downloading SQLite from PythonAnywhere…")
    print(f"  Remote: {remote}")
    print(f"  Local : {out.resolve()}")

    resp = _api_get(url, headers, stream=True)
    if resp.status_code != 200:
        print(f"ERROR: HTTP {resp.status_code} for {url}", file=sys.stderr)
        if resp.status_code == 404:
            print(
                "  Check PA_REMOTE_SQLITE_PATH or PA_REMOTE_PATH + instance/shop.db",
                file=sys.stderr,
            )
        sys.exit(1)

    tmp = out.with_suffix(out.suffix + ".tmp")
    try:
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        tmp.replace(out)
    except Exception:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise

    print(f"  Saved {out.stat().st_size} bytes.")
    return out.resolve()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Download shop.db from PythonAnywhere.")
    p.add_argument("--force", action="store_true", help="Ignore 1h cache and re-download.")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Local file path (default: {_DEFAULT_LOCAL})",
    )
    args = p.parse_args()
    fetch_pythonanywhere_sqlite(local_path=args.output, force=args.force)
