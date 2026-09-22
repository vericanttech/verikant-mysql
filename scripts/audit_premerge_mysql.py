#!/usr/bin/env python3
"""Read-only per-shop comparison of pre-merge MySQL and current production.

Run from the repository root::

    python -m scripts.audit_premerge_mysql
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import MetaData, Table, select

from app import create_app
from app.extensions import db


SHOP_TABLES = (
    "shop_phones", "categories", "products", "clients", "sales_bills",
    "stock_movements", "payment_transactions", "expenses", "suppliers",
    "supplier_bills", "notes", "loans", "boutique_transactions", "checks",
    "employee_salaries", "employee_loans", "employee_loan_payments",
    "vitrine_product_selections", "vitrine_visits", "user_shops",
)


def row_dicts(conn, table, where=None):
    query = select(table)
    if where is not None:
        query = query.where(where)
    return [dict(row._mapping) for row in conn.execute(query)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-schema", default="vericant$shop_backup_20260912")
    parser.add_argument("--shop-id", type=int)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        engine = db.engine
        live_schema = engine.url.database
        if engine.dialect.name != "mysql" or args.source_schema == live_schema:
            raise RuntimeError("Expected two distinct MySQL schemas")
        names = ("shops", "users", "sales_details", *SHOP_TABLES)
        src_md, live_md = MetaData(), MetaData()
        src = {
            name: Table(name, src_md, autoload_with=engine, schema=args.source_schema)
            for name in names
        }
        live = {
            name: Table(name, live_md, autoload_with=engine, schema=live_schema)
            for name in names
        }
        with engine.connect() as conn:
            source_shops = row_dicts(conn, src["shops"])
            live_shops = row_dicts(conn, live["shops"])
            live_by_name = {shop["name"].casefold().strip(): shop for shop in live_shops}
            for source_shop in sorted(source_shops, key=lambda row: row["id"]):
                source_id = source_shop["id"]
                if args.shop_id is not None and source_id != args.shop_id:
                    continue
                live_shop = live_by_name.get(source_shop["name"].casefold().strip())
                live_id = live_shop["id"] if live_shop else None
                print(f"\nSHOP {source_id} {source_shop['name']!r} -> {live_id}")
                for name in SHOP_TABLES:
                    source_rows = row_dicts(conn, src[name], src[name].c.shop_id == source_id)
                    live_rows = (
                        row_dicts(conn, live[name], live[name].c.shop_id == live_id)
                        if live_id is not None else []
                    )
                    if not source_rows and not live_rows:
                        continue
                    if name == "user_shops":
                        source_keys = {row["user_id"] for row in source_rows}
                        live_keys = {row["user_id"] for row in live_rows}
                        overlap = len(source_keys & live_keys)
                        changed = 0
                    else:
                        source_by_id = {row["id"]: row for row in source_rows}
                        live_by_id = {row["id"]: row for row in live_rows}
                        source_keys = set(source_by_id)
                        live_keys = set(live_by_id)
                        overlap = len(source_keys & live_keys)
                        common_cols = set(src[name].c.keys()) & set(live[name].c.keys())
                        changed = sum(
                            any(
                                str(source_by_id[row_id][col]) != str(live_by_id[row_id][col])
                                for col in common_cols if col not in {"updated_at", "created_at"}
                            )
                            for row_id in source_keys & live_keys
                        )
                    print(
                        f"  {name}: backup={len(source_rows)} live={len(live_rows)} "
                        f"source_only_ids={len(source_keys-live_keys)} "
                        f"same_ids={overlap} different_same_ids={changed}"
                    )
                    if source_keys - live_keys:
                        print(f"    source_only_id_sample={sorted(source_keys-live_keys)[:12]}")
                    if name == "products" and changed:
                        for row_id in sorted(source_keys & live_keys):
                            src_row, live_row = source_by_id[row_id], live_by_id[row_id]
                            if src_row["name"] != live_row["name"]:
                                print(
                                    f"    product_id={row_id} backup_name={src_row['name']!r} "
                                    f"live_name={live_row['name']!r}"
                                )
                                break
                source_bill_ids = {
                    row["id"] for row in row_dicts(
                        conn, src["sales_bills"], src["sales_bills"].c.shop_id == source_id
                    )
                }
                live_bill_ids = {
                    row["id"] for row in row_dicts(
                        conn, live["sales_bills"], live["sales_bills"].c.shop_id == live_id
                    )
                } if live_id is not None else set()
                source_details = row_dicts(
                    conn, src["sales_details"], src["sales_details"].c.bill_id.in_(source_bill_ids)
                ) if source_bill_ids else []
                live_details = row_dicts(
                    conn, live["sales_details"], live["sales_details"].c.bill_id.in_(live_bill_ids)
                ) if live_bill_ids else []
                print(f"  sales_details: backup={len(source_details)} live={len(live_details)}")

            src_users = row_dicts(conn, src["users"])
            live_users = row_dicts(conn, live["users"])
            by_name = defaultdict(list)
            for user in live_users:
                by_name[user["name"].casefold().strip()].append(user)
            print("\nUSERS source_only_by_name:")
            for user in src_users:
                if user["name"].casefold().strip() not in by_name:
                    print(f"  {user['id']} {user['name']!r} shop={user['current_shop_id']}")


if __name__ == "__main__":
    main()
