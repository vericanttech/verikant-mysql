"""Quick check: load .env, optional SSH tunnel, then SELECT 1 on MySQL.

Run from repo root:
  python scripts/test_mysql_connection.py
  python scripts/test_mysql_connection.py --verbose
"""
import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv, dotenv_values

load_dotenv(_root / ".env")

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import pymysql

from app import create_app
from app.extensions import db


def _mask_secret(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + ("*" * (len(value) - 2)) + value[-1]


def _secret_fingerprint(value: str) -> str:
    if not value:
        return "none"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _print_env_diagnostics() -> None:
    """Show where values come from without leaking secrets."""
    file_vals = dotenv_values(_root / ".env")
    keys = [
        "SSH_TUNNEL",
        "PA_SSH_USER",
        "PA_SSH_HOST",
        "PA_SSH_PASSWORD",
        "PA_MYSQL_BUILD_URL",
        "PA_MYSQL_USER",
        "PA_MYSQL_HOST",
        "PA_MYSQL_PORT",
        "PA_MYSQL_PASSWORD",
        "PA_MYSQL_DATABASE",
        "SQLALCHEMY_DATABASE_URI",
        "DATABASE_URL",
    ]

    print("--- Runtime env diagnostics ---")
    for key in keys:
        from_file = file_vals.get(key)
        from_env = os.environ.get(key)
        if "PASSWORD" in key:
            file_repr = (
                f"len={len(from_file)} mask={_mask_secret(from_file)} "
                f"sha12={_secret_fingerprint(from_file)}"
                if from_file is not None
                else "None"
            )
            env_repr = (
                f"len={len(from_env)} mask={_mask_secret(from_env)} "
                f"sha12={_secret_fingerprint(from_env)}"
                if from_env is not None
                else "None"
            )
        else:
            file_repr = repr(from_file)
            env_repr = repr(from_env)
        print(f"  {key}: file={file_repr} | env={env_repr}")
    print("--------------------------------")


def _print_connection_diagnostics() -> None:
    """Password-safe breakdown of the SQLAlchemy URL."""
    u = db.engine.url
    # Path is e.g. /vericant%24shop -> decode for readability
    db_name = unquote(u.database or "") or "(none)"
    print("--- Connection settings (no password shown) ---")
    print(f"  Driver:     {u.drivername}")
    print(f"  User:       {u.username}")
    print(f"  Host:       {u.host}")
    print(f"  Port:       {u.port}")
    print(f"  Database:   {db_name}")
    print(f"  Query:      {dict(u.query) if u.query else {}}")
    url_pw = u.password or ""
    env_pw = os.environ.get("PA_MYSQL_PASSWORD", "")
    print(
        "  URL pw fp:  "
        f"len={len(url_pw)} sha12={_secret_fingerprint(url_pw)} "
        f"mask={_mask_secret(url_pw)}"
    )
    print(
        "  ENV pw fp:  "
        f"len={len(env_pw)} sha12={_secret_fingerprint(env_pw)} "
        f"mask={_mask_secret(env_pw)}"
    )
    print("-----------------------------------------------")


def _explain_operational_error(exc: OperationalError) -> None:
    print("\n=== MySQL / connection error (details) ===")
    orig = getattr(exc, "orig", None)
    if orig is not None:
        print(f"  Underlying: {type(orig).__name__}: {orig}")
        args = getattr(orig, "args", None)
        if args:
            errno = args[0] if len(args) > 0 else None
            msg = args[1] if len(args) > 1 else None
            if errno is not None:
                print(f"  MySQL errno: {errno}")
            if msg is not None:
                print(f"  MySQL msg:   {msg}")
    else:
        print(f"  {exc}")

    s = str(exc).lower()
    if "1045" in s or "access denied" in s:
        print("\n  1045 / Access denied usually means:")
        print("    - Wrong MySQL password in SQLALCHEMY_DATABASE_URI (not your PA website password).")
        print("    - Password contains @ # % + etc. → URL-encode it (e.g. in Python: urllib.parse.quote_plus(pwd)).")
        print("    - Username must match the Databases tab (often your PA username).")
        print("    - After changing password on PA, save .env and run this script again (no spaces around =).")
    if "timed out" in s or "2003" in s:
        print("\n  Timeout / 2003: enable SSH tunnel (SSH_TUNNEL=1 + PA_SSH_PASSWORD) or use PA console.")

    print("==========================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test DB connectivity (MySQL + optional SSH tunnel).")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable SQLAlchemy engine INFO logs (still avoids printing your password).",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

    app = create_app()
    with app.app_context():
        _print_env_diagnostics()
        tunnel = "on" if app.config.get("PA_SSH_TUNNEL_ACTIVE") else "off"
        build = os.environ.get("PA_MYSQL_BUILD_URL", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        print(f"SSH tunnel (in app): {tunnel}")
        print(f"PA_MYSQL_BUILD_URL mode: {build}")
        print(f"DB URL (password hidden): {db.engine.url.render_as_string(hide_password=True)}")
        _print_connection_diagnostics()

        # Direct driver-level probe using the same effective runtime values.
        # This helps distinguish SQLAlchemy-layer issues from pure MySQL auth issues.
        try:
            raw_user = os.environ.get("PA_MYSQL_USER", "vericant")
            raw_password = os.environ.get("PA_MYSQL_PASSWORD", "")
            raw_db = os.environ.get("PA_MYSQL_DATABASE", "vericant$shop")
            with pymysql.connect(
                host=db.engine.url.host or "127.0.0.1",
                port=int(db.engine.url.port or 3306),
                user=raw_user,
                password=raw_password,
                database=raw_db,
                connect_timeout=8,
            ) as raw_conn:
                with raw_conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    print("RAW PyMySQL SELECT 1 =>", cur.fetchone(), "OK")
        except Exception as raw_exc:
            print("RAW PyMySQL probe FAILED:", repr(raw_exc))

        try:
            with db.engine.connect() as conn:
                one = conn.execute(text("SELECT 1")).scalar()
            print("SELECT 1 =>", one, "OK")
        except OperationalError as e:
            _explain_operational_error(e)
            raise SystemExit(1) from e


if __name__ == "__main__":
    main()
