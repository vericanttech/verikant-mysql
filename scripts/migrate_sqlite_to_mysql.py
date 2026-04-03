"""Copy all rows from local SQLite (e.g. instance/shop.db) into the configured MySQL DB.

Requires .env to point the app at MySQL (PA_MYSQL_BUILD_URL=1 + PA_MYSQL_*), and
optional SSH_TUNNEL=1 for PythonAnywhere from your PC.

Run from project root:
  python scripts/migrate_sqlite_to_mysql.py --sqlite instance/shop.db
  python scripts/migrate_sqlite_to_mysql.py --dry-run
  python scripts/migrate_sqlite_to_mysql.py --truncate --yes
  python scripts/migrate_sqlite_to_mysql.py --truncate --yes --batch-size 1000

--truncate deletes all rows from app tables on MySQL (in FK-safe order) before import.

Performance: rows are sent in batches (``--batch-size``, default 500) using a single
round-trip per batch. Over an SSH tunnel this matters far more than on localhost.
MySQL ``unique_checks=0`` is set for the load phase only (safe here because SQLite
data already satisfied uniqueness).

MySQL vs SQLite (handled here or in schema — run ``flask db upgrade`` before import):
  * users.name UNIQUE is case-insensitive on MySQL; duplicate spellings are disambiguated.
  * categories (shop_id, name) same for case-insensitive uniqueness.
  * sales_bills.bill_number must be BIGINT on MySQL (large composite numbers); see migration
    b2c8e9f1a3d4.
  * Other INTEGER columns are IDs, quantities, or stock — within signed 32-bit range in practice.
  * supplier_bills.bill_number is Text (no INT overflow).
  * stock_movements.reference_id stores bill *id*, not display bill_number.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import BigInteger, Boolean, Float, Integer, Numeric, insert, text
from sqlalchemy.exc import IntegrityError

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv(_root / ".env")

from app import create_app
from app.extensions import db
from app.models import (
    BoutiqueTransaction,
    Category,
    Check,
    Client,
    EmployeeLoan,
    EmployeeLoanPayment,
    EmployeeSalary,
    Expense,
    Loan,
    Note,
    PaymentTransaction,
    Product,
    SalesBill,
    SalesDetail,
    Shop,
    ShopPhone,
    StockMovement,
    Supplier,
    SupplierBill,
    User,
    UserShop,
)

# Parents before children (same schema as Flask-SQLAlchemy models).
TABLE_ORDER = [
    Shop,
    ShopPhone,
    User,
    UserShop,
    Category,
    Product,
    Client,
    SalesBill,
    SalesDetail,
    StockMovement,
    PaymentTransaction,
    Expense,
    Supplier,
    SupplierBill,
    Note,
    Loan,
    BoutiqueTransaction,
    Check,
    EmployeeSalary,
    EmployeeLoan,
    EmployeeLoanPayment,
]


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _coerce(column, value):
    if value is None:
        return None
    if isinstance(value, (bytes, memoryview)):
        value = bytes(value).decode("utf-8", errors="replace")
    t = column.type
    if isinstance(t, Boolean):
        if isinstance(value, (int, float)):
            return bool(int(value))
        s = str(value).strip().lower()
        if s in ("0", "false", "no", ""):
            return False
        if s in ("1", "true", "yes"):
            return True
        return bool(value)
    if isinstance(t, (Integer, BigInteger)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if isinstance(t, (Float, Numeric)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def _row_dict(sqlite_row: sqlite3.Row, col_names: list[str]) -> dict:
    return {col_names[i]: sqlite_row[i] for i in range(len(col_names))}


def _build_insert_dict(model, row_dict: dict) -> dict | None:
    table = model.__table__
    out = {}
    for key, raw in row_dict.items():
        if key not in table.columns:
            continue
        col = table.columns[key]
        out[key] = _coerce(col, raw)
    return out if out else None


def _destination_is_mysql(uri: str) -> bool:
    return uri.startswith("mysql")


def _norm_key(s: str) -> str:
    """Match MySQL unique checks on typical utf8mb4_unicode_ci (case-insensitive)."""
    return s.casefold().strip()


def _user_names_for_mysql(conn: sqlite3.Connection) -> dict[int, str]:
    """
    MySQL has UNIQUE(users.name). SQLite may contain duplicate names, including
    same word with different casing (e.g. Amadou vs amadou) — MySQL still rejects
    both. Map each user id to a distinct name (lowest id keeps original string).
    """
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        ("users",),
    )
    if not cur.fetchone():
        return {}
    rows = conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    by_norm: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in rows:
        uid = int(r["id"])
        raw = str(r["name"])
        by_norm[_norm_key(raw)].append((uid, raw))
    out: dict[int, str] = {}
    for _norm, items in by_norm.items():
        items.sort(key=lambda t: t[0])
        if len(items) == 1:
            out[items[0][0]] = items[0][1]
            continue
        for i, (uid, raw) in enumerate(items):
            if i == 0:
                out[uid] = raw
            else:
                suffix = f" [{uid}]"
                base = raw[: max(0, 255 - len(suffix))]
                out[uid] = base + suffix
    return out


def _category_names_for_mysql(conn: sqlite3.Connection) -> dict[int, str]:
    """UNIQUE(shop_id, name) on categories — disambiguate duplicate pairs in SQLite."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        ("categories",),
    )
    if not cur.fetchone():
        return {}
    rows = conn.execute(
        "SELECT id, shop_id, name FROM categories ORDER BY id"
    ).fetchall()
    # Unique is (shop_id, name) with case-insensitive name in MySQL
    by_key: dict[tuple[int, str], list[tuple[int, str]]] = defaultdict(list)
    for r in rows:
        cid = int(r["id"])
        sid = int(r["shop_id"])
        nm = str(r["name"])
        by_key[(sid, _norm_key(nm))].append((cid, nm))
    out: dict[int, str] = {}
    for _key, items in by_key.items():
        items.sort(key=lambda t: t[0])
        if len(items) == 1:
            out[items[0][0]] = items[0][1]
            continue
        for i, (cid, raw) in enumerate(items):
            if i == 0:
                out[cid] = raw
            else:
                suffix = f" [{cid}]"
                base = raw[: max(0, 255 - len(suffix))]
                out[cid] = base + suffix
    return out


def _assert_mysql_empty(session) -> None:
    n = session.execute(text("SELECT COUNT(*) FROM shops")).scalar()
    if n:
        raise SystemExit(
            "MySQL already has rows in `shops`. Use --truncate --yes to clear app "
            "tables first, or import into an empty database."
        )


def _truncate_mysql(session) -> None:
    session.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    for model in reversed(TABLE_ORDER):
        name = model.__table__.name
        session.execute(text(f"DELETE FROM `{name}`"))
    session.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    session.commit()


def _reset_auto_increment(session) -> None:
    for model in TABLE_ORDER:
        table = model.__table__
        if "id" not in table.columns:
            continue
        pk_cols = list(table.primary_key.columns)
        if len(pk_cols) != 1 or pk_cols[0].name != "id":
            continue
        name = table.name
        max_id = session.execute(text(f"SELECT MAX(id) FROM `{name}`")).scalar()
        if max_id is None:
            continue
        next_id = int(max_id) + 1
        session.execute(text(f"ALTER TABLE `{name}` AUTO_INCREMENT = :n"), {"n": next_id})
    session.commit()


def _flush_insert_batch(session, table, batch: list, dry_run: bool) -> None:
    if dry_run or not batch:
        return
    session.execute(insert(table), batch)
    batch.clear()


def migrate(
    sqlite_path: Path,
    dry_run: bool,
    truncate: bool,
    batch_size: int = 500,
) -> None:
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite file not found: {sqlite_path}")

    app = create_app()
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not _destination_is_mysql(uri):
        raise SystemExit(
            "App DATABASE_URL / MySQL env is not set to MySQL. "
            "Set PA_MYSQL_BUILD_URL=1 and PA_MYSQL_* (or SQLALCHEMY_DATABASE_URI=mysql+...)."
        )

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    user_names = _user_names_for_mysql(conn)
    category_names = _category_names_for_mysql(conn)

    with app.app_context():
        if truncate and not dry_run:
            _truncate_mysql(db.session)
        elif not dry_run:
            _assert_mysql_empty(db.session)

        db.session.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        if not dry_run:
            db.session.execute(text("SET SESSION unique_checks=0"))
            db.session.commit()

        total = 0
        try:
            for model in TABLE_ORDER:
                name = model.__table__.name
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (name,),
                )
                if not cur.fetchone():
                    print(f"  skip {name} (not in SQLite)")
                    continue

                cols = _sqlite_columns(conn, name)
                rows = conn.execute(f"SELECT * FROM {name}").fetchall()
                inserted = 0
                batch: list[dict] = []
                bs = max(1, int(batch_size))
                table = model.__table__
                for row in rows:
                    d = _row_dict(row, cols)
                    insert_dict = _build_insert_dict(model, d)
                    if not insert_dict:
                        continue
                    if model is User and "id" in insert_dict:
                        uid = int(insert_dict["id"])
                        if uid in user_names:
                            insert_dict["name"] = user_names[uid]
                    if model is Category and "id" in insert_dict:
                        cid = int(insert_dict["id"])
                        if cid in category_names:
                            insert_dict["name"] = category_names[cid]
                    if dry_run:
                        inserted += 1
                        continue
                    batch.append(insert_dict)
                    if len(batch) >= bs:
                        _flush_insert_batch(db.session, table, batch, dry_run=False)
                    inserted += 1
                if not dry_run:
                    _flush_insert_batch(db.session, table, batch, dry_run=False)
                total += inserted
                action = "would copy" if dry_run else "copied"
                print(f"  {action} {inserted} row(s) -> {name}")
                if not dry_run:
                    db.session.commit()
        finally:
            if not dry_run:
                db.session.execute(text("SET SESSION unique_checks=1"))
            db.session.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            if not dry_run:
                db.session.commit()

        if dry_run:
            print(f"Dry run complete. {total} rows would be imported.")
            return

        _reset_auto_increment(db.session)
        print(f"Done. Imported {total} rows total.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate instance/shop.db to MySQL.")
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=_root / "instance" / "shop.db",
        help="Path to SQLite file (default: instance/shop.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows per table without writing to MySQL.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete all app data on MySQL before import (requires --yes).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive --truncate.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        metavar="N",
        help="MySQL insert batch size (default: 500). Larger = fewer network round trips.",
    )
    args = parser.parse_args()

    if args.truncate and not args.yes:
        raise SystemExit("--truncate requires --yes (this deletes all app tables on MySQL).")

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")

    try:
        migrate(args.sqlite, args.dry_run, args.truncate, args.batch_size)
    except IntegrityError as e:
        raise SystemExit(f"MySQL rejected a row (duplicate or FK): {e}") from e


if __name__ == "__main__":
    main()
