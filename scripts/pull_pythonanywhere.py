#!/usr/bin/env python3
"""
Download a project tree from PythonAnywhere to this repo via the Files API.

Opposite of uploading static files: recursively lists and downloads files.

Usage (from repository root):

    python scripts/pull_pythonanywhere.py

Requirements: ``pip install requests``

Env / config:
    PA_API_TOKEN, PA_USERNAME, PA_REMOTE_PATH, PA_OUTPUT_DIR, PA_HOST
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ─── CONFIG (override with env vars) ───────────────────────────────────────────

API_TOKEN = os.getenv("PA_API_TOKEN", "YOUR_API_TOKEN_HERE")
USERNAME = os.getenv("PA_USERNAME", "vericant")

REMOTE_PATH = os.getenv("PA_REMOTE_PATH", f"/home/{USERNAME}/POS-Master")

# Default: sync into this git repo root (the folder that contains app/, wsgi.py, etc.).
OUTPUT_DIR = os.getenv("PA_OUTPUT_DIR", str(_REPO_ROOT))

HOST = os.getenv("PA_HOST", "www.pythonanywhere.com")

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "env", "node_modules", ".cache"}
SKIP_EXTS = {".pyc", ".pyo"}
SKIP_FILES = {".bash_history"}

BASE_URL = f"https://{HOST}/api/v0/user/{USERNAME}/"
HEADERS = {"Authorization": f"Token {API_TOKEN}"}

downloaded = 0
skipped = 0
errors = 0


def api_get(url: str, stream: bool = False) -> requests.Response:
    for attempt in range(2):
        resp = requests.get(url, headers=HEADERS, stream=stream, timeout=120)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            print(f"  Rate-limited; waiting {retry_after}s...")
            time.sleep(retry_after)
            continue
        return resp
    return resp


def list_remote(remote_path: str) -> dict:
    url = urljoin(BASE_URL, f"files/path{remote_path}")
    resp = api_get(url)

    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404:
        print(f"  Not found: {remote_path}")
        return {}
    resp.raise_for_status()
    return {}


def download_file(remote_path: str, local_path: Path) -> bool:
    url = urljoin(BASE_URL, f"files/path{remote_path}")
    resp = api_get(url, stream=True)

    if resp.status_code != 200:
        print(f"  Error {resp.status_code}: {remote_path}")
        return False

    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return True


def pull(remote_path: str, local_base: Path, relative: str = "") -> None:
    global downloaded, skipped, errors

    entries = list_remote(remote_path)
    if not entries:
        return

    for name, meta in entries.items():
        entry_remote = f"{remote_path.rstrip('/')}/{name}"
        entry_local = local_base / relative / name

        if meta["type"] == "directory":
            if name in SKIP_DIRS:
                print(f"  Skipping dir: {entry_remote}")
                skipped += 1
                continue
            print(f"  DIR  {entry_remote}/")
            pull(entry_remote, local_base, str(Path(relative) / name))

        elif meta["type"] == "file":
            if name in SKIP_FILES:
                skipped += 1
                continue
            if Path(name).suffix in SKIP_EXTS:
                skipped += 1
                continue

            print(f"  FILE {entry_remote}")
            ok = download_file(entry_remote, entry_local)
            if ok:
                downloaded += 1
            else:
                errors += 1


def main() -> None:
    global API_TOKEN, USERNAME, BASE_URL, HEADERS

    BASE_URL = f"https://{HOST}/api/v0/user/{USERNAME}/"
    HEADERS = {"Authorization": f"Token {API_TOKEN}"}

    if API_TOKEN == "YOUR_API_TOKEN_HERE":
        print("ERROR: Set PA_API_TOKEN (e.g. in .env or your shell).")
        sys.exit(1)

    output_root = Path(OUTPUT_DIR)
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"Pulling: {REMOTE_PATH}")
    print(f"Into   : {output_root.resolve()}")
    print(f"Host   : {HOST}")
    print("-" * 50)

    pull(REMOTE_PATH, output_root)

    print("-" * 50)
    print(f"Done: {downloaded} downloaded, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    main()
