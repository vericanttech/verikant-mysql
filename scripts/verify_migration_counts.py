"""Compare row counts: local SQLite vs configured MySQL (same tables as migrate script).

Run from project root (MySQL .env + optional SSH tunnel like the app):
  python scripts/verify_migration_counts.py
  python scripts/verify_migration_counts.py --sqlite path/to/shop.db
  python scripts/verify_migration_counts.py --no-ssh   # if MySQL is reachable without tunnel
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import text

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv(_root / ".env")

from app import create_app
from app.extensions import db

TABLES = [
    "shops",
    "shop_phones",
    "users",
    "user_shops",
    "categories",
    "products",
    "clients",
    "sales_bills",
    "sales_details",
    "stock_movements",
    "payment_transactions",
    "expenses",
    "suppliers",
    "supplier_bills",
    "notes",
    "loans",
    "boutique_transactions",
    "checks",
    "employee_salaries",
    "employee_loans",
    "employee_loan_payments",
]


def _sqlite_count(conn: sqlite3.Connection, table: str) -> int | None:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    if not cur.fetchone():
        return None
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=_root / "instance" / "shop.db",
    )
    parser.add_argument(
        "--no-ssh",
        action="store_true",
        help="Set SSH_TUNNEL=0 for this run (MySQL host/port must be reachable directly).",
    )
    args = parser.parse_args()

    if args.no_ssh:
        os.environ["SSH_TUNNEL"] = "0"

    if not args.sqlite.is_file():
        raise SystemExit(f"SQLite file not found: {args.sqlite}")

    app = create_app()
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("mysql"):
        raise SystemExit("App is not configured for MySQL (expected mysql+... URI).")

    sq = sqlite3.connect(str(args.sqlite))
    mismatches = []
    total_sqlite = 0
    total_mysql = 0

    with app.app_context():
        print(f"SQLite: {args.sqlite.resolve()}")
        print(f"MySQL:  (from app config)\n")
        print(f"{'table':<28} {'sqlite':>10} {'mysql':>10} {'ok':>5}")
        print("-" * 56)
        for t in TABLES:
            sc = _sqlite_count(sq, t)
            if sc is None:
                print(f"{t:<28} {'(missing)':>10} {'-':>10} {'n/a':>5}")
                continue
            mc = db.session.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
            total_sqlite += sc
            total_mysql += int(mc)
            ok = sc == mc
            flag = "yes" if ok else "NO"
            print(f"{t:<28} {sc:>10} {mc:>10} {flag:>5}")
            if not ok:
                mismatches.append((t, sc, mc))

    print("-" * 56)
    print(f"{'TOTAL':<28} {total_sqlite:>10} {total_mysql:>10} {'yes' if not mismatches else 'NO':>5}")

    if mismatches:
        print("\nMismatch detail:")
        for t, sc, mc in mismatches:
            print(f"  {t}: sqlite={sc} mysql={mc} (diff {mc - sc:+d})")
        raise SystemExit(1)
    print("\nAll compared tables match.")


if __name__ == "__main__":
    main()
