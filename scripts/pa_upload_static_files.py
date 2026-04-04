"""Upload a local folder to PythonAnywhere using the Files API (file-by-file).

Docs: https://help.pythonanywhere.com/pages/API/

Requires:
  pip install requests

Loads project root ``.env`` (same as the Flask app). Set:

  PA_API_TOKEN          — Account → API token (never commit)
  PA_DEPLOY_USERNAME    — e.g. vericant
  PA_API_HOST           — optional, default www.pythonanywhere.com
  PA_UPLOAD_REMOTE_PREFIX — optional, remote absolute path prefix
  PA_UPLOAD_SOURCE      — optional, local folder (relative to project root)
  PA_UPLOAD_DELAY       — optional, seconds between requests (default 1.6)

Example:
  python scripts/pa_upload_static_files.py
  python scripts/pa_upload_static_files.py --source app/static/uploads --dry-run

Rate limit: ~40 requests/minute — pauses between uploads.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    raise SystemExit(1)

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def _default_upload_source() -> Path:
    raw = os.environ.get("PA_UPLOAD_SOURCE", "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (_root / p)
    return _root / "app" / "static" / "uploads"


def _build_url(host: str, username: str, remote_file_path: str) -> str:
    """POST target for one file. remote_file_path is absolute e.g. /home/user/.../file.jpg"""
    from urllib.parse import quote

    base = f"https://{host.rstrip('/')}/api/v0/user/{username}/files/path"
    # Encode path; keep slashes so PA receives a normal path
    return base + quote(remote_file_path, safe="/")


def upload_one(
    session: requests.Session,
    token: str,
    url: str,
    local_path: Path,
) -> tuple[bool, str]:
    headers = {"Authorization": f"Token {token}"}
    try:
        with open(local_path, "rb") as f:
            files = {"content": (local_path.name, f)}
            r = session.post(url, headers=headers, files=files, timeout=120)
    except OSError as e:
        return False, str(e)
    if r.status_code in (200, 201):
        return True, r.text[:200] if r.text else "ok"
    return False, f"HTTP {r.status_code}: {r.text[:500]}"


def main() -> int:
    load_dotenv(_root / ".env")

    default_remote = os.environ.get(
        "PA_UPLOAD_REMOTE_PREFIX",
        "/home/vericant/verikant-mysql/app/static/uploads",
    ).strip()
    default_host = os.environ.get("PA_API_HOST", "www.pythonanywhere.com").strip()
    default_user = os.environ.get("PA_DEPLOY_USERNAME", "").strip()
    default_token = os.environ.get("PA_API_TOKEN", "").strip()
    try:
        default_delay = float(os.environ.get("PA_UPLOAD_DELAY", "1.6"))
    except ValueError:
        default_delay = 1.6

    p = argparse.ArgumentParser(description="Upload folder to PythonAnywhere via Files API.")
    p.add_argument(
        "--source",
        type=Path,
        default=_default_upload_source(),
        help="Local directory (default: PA_UPLOAD_SOURCE or app/static/uploads)",
    )
    p.add_argument(
        "--remote-prefix",
        default=default_remote,
        help="Absolute path on PA (default: PA_UPLOAD_REMOTE_PREFIX or .../uploads)",
    )
    p.add_argument(
        "--host",
        default=default_host,
        help="www.pythonanywhere.com or eu.pythonanywhere.com (default: PA_API_HOST)",
    )
    p.add_argument(
        "--username",
        default=default_user,
        help="PA username (default: PA_DEPLOY_USERNAME)",
    )
    p.add_argument(
        "--token",
        default=default_token,
        help="API token (default: PA_API_TOKEN from .env)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=default_delay,
        help="Seconds between requests (default: PA_UPLOAD_DELAY or 1.6)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print paths only, do not upload",
    )
    args = p.parse_args()

    token = args.token
    username = args.username
    if not token or not username:
        print(
            "Set PA_API_TOKEN and PA_DEPLOY_USERNAME in .env (or pass --token / --username).",
            file=sys.stderr,
        )
        return 1

    src: Path = args.source.resolve()
    if not src.is_dir():
        print(f"Source is not a directory: {src}", file=sys.stderr)
        return 1

    prefix = args.remote_prefix.rstrip("/")

    files: list[tuple[Path, str]] = []
    for dirpath, _dirnames, filenames in os.walk(src):
        for name in filenames:
            local = Path(dirpath) / name
            rel = local.relative_to(src).as_posix()
            remote_abs = f"{prefix}/{rel}"
            files.append((local, remote_abs))

    if not files:
        print("No files found to upload.")
        return 0

    print(f"Found {len(files)} file(s). Remote prefix: {prefix}/")
    session = requests.Session()

    ok_n = 0
    for i, (local_path, remote_abs) in enumerate(files, 1):
        url = _build_url(args.host, username, remote_abs)
        print(f"[{i}/{len(files)}] {local_path.name} -> {remote_abs}")
        if args.dry_run:
            continue
        ok, msg = upload_one(session, token, url, local_path)
        if ok:
            ok_n += 1
        else:
            print(f"  FAILED: {msg}", file=sys.stderr)
        if i < len(files) and args.delay > 0:
            time.sleep(args.delay)

    if args.dry_run:
        print("Dry run only.")
        return 0

    print(f"Done. Uploaded {ok_n}/{len(files)} successfully.")
    return 0 if ok_n == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
