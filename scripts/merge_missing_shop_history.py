#!/usr/bin/env python3
"""Merge source-only product and sales history into an existing MySQL shop.

This deliberately does not overwrite shared rows or adjust live stock balances.
It refuses ambiguous identities and invoice-number collisions. Dry run is default.
"""

from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import MetaData, Table, insert, select

from app import create_app
from app.extensions import db
from scripts.restore_shop_from_mysql_backup import _accounting_defaults, _prepare_values


NAMES = (
    "shops", "users", "categories", "clients", "products", "sales_bills",
    "sales_details", "payment_transactions", "stock_movements",
)


def rows(conn, table, clause=None):
    statement = select(table)
    if clause is not None:
        statement = statement.where(clause)
    return [dict(row._mapping) for row in conn.execute(statement)]


def index(values):
    return {int(row["id"]): row for row in values}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def same_identity(source_row, live_row, label, fields=("created_at",)):
    for field in fields:
        if str(source_row.get(field)) != str(live_row.get(field)):
            raise RuntimeError(
                f"{label} id {source_row['id']} has different {field}; "
                "manual reconciliation required"
            )


def merge(source_schema, shop_id, apply):
    app = create_app()
    with app.app_context():
        engine = db.engine
        live_schema = engine.url.database
        require(engine.dialect.name == "mysql", "Expected MySQL")
        require(source_schema != live_schema, "Source and live schemas are identical")
        src_md, live_md = MetaData(), MetaData()
        src = {n: Table(n, src_md, autoload_with=engine, schema=source_schema) for n in NAMES}
        live = {n: Table(n, live_md, autoload_with=engine, schema=live_schema) for n in NAMES}

        with engine.connect() as conn:
            source_shop = rows(conn, src["shops"], src["shops"].c.id == shop_id)
            target_shop = rows(conn, live["shops"], live["shops"].c.id == shop_id)
            require(len(source_shop) == len(target_shop) == 1, "Shop ID must exist in both schemas")
            require(source_shop[0]["name"] == target_shop[0]["name"], "Shop name mismatch")

            source = {}
            target = {}
            for name in ("categories", "clients", "products", "sales_bills",
                         "payment_transactions", "stock_movements"):
                source[name] = index(rows(conn, src[name], src[name].c.shop_id == shop_id))
                target[name] = index(rows(conn, live[name], live[name].c.shop_id == shop_id))

            source_bill_ids = set(source["sales_bills"])
            target_bill_ids = set(target["sales_bills"])
            source_details = rows(
                conn, src["sales_details"], src["sales_details"].c.bill_id.in_(source_bill_ids)
            ) if source_bill_ids else []
            target_details = rows(
                conn, live["sales_details"], live["sales_details"].c.bill_id.in_(target_bill_ids)
            ) if target_bill_ids else []
            target_detail_by_id = index(target_details)

            # Every previously shared foreign-key row must still be the same
            # historical entity. Values may legitimately have changed in live.
            for name in ("categories", "clients", "products"):
                for row_id in source[name].keys() & target[name].keys():
                    same_identity(source[name][row_id], target[name][row_id], name)

            # Existing parent rows must cover all source dependencies. This
            # utility does not silently restore deleted categories or clients.
            for name in ("categories", "clients"):
                missing = source[name].keys() - target[name].keys()
                require(not missing, f"Missing {name} in live: {sorted(missing)[:12]}")

            target_names = {str(row["name"]).strip().casefold() for row in target["products"].values()}
            new_products = [source["products"][i] for i in sorted(source["products"].keys() - target["products"].keys())]
            for row in new_products:
                require(str(row["name"]).strip().casefold() not in target_names,
                        f"Product may already exist under another ID: {row['name']!r}")
                require(row["category_id"] is None or int(row["category_id"]) in target["categories"],
                        f"Product {row['id']} has missing category")

            target_bill_numbers = {int(row["bill_number"]) for row in target["sales_bills"].values()}
            shared_bill_ids = {
                i for i in source["sales_bills"].keys() & target["sales_bills"].keys()
                if source["sales_bills"][i]["created_at"] == target["sales_bills"][i]["created_at"]
                and source["sales_bills"][i]["bill_number"] == target["sales_bills"][i]["bill_number"]
            }
            new_bills = [source["sales_bills"][i] for i in sorted(source["sales_bills"].keys() - shared_bill_ids)]
            for row in new_bills:
                require(int(row["bill_number"]) not in target_bill_numbers,
                        f"Bill number {row['bill_number']} already exists under another ID")
                require(row["client_id"] is None or int(row["client_id"]) in target["clients"],
                        f"Bill {row['id']} has missing client")

            source_users = index(rows(conn, src["users"]))
            target_users = index(rows(conn, live["users"]))
            used_users = set()
            for name in ("sales_bills", "payment_transactions", "stock_movements"):
                used_users.update(int(row["user_id"]) for row in source[name].values())
            for user_id in used_users:
                require(user_id in source_users and user_id in target_users,
                        f"Missing user {user_id}")
                require(source_users[user_id]["name"] == target_users[user_id]["name"],
                        f"User identity mismatch for {user_id}")

            new_bill_ids = {int(row["id"]) for row in new_bills}
            new_details = [row for row in source_details if int(row["bill_id"]) in new_bill_ids]
            for row in source_details:
                if int(row["bill_id"]) not in new_bill_ids:
                    existing = target_detail_by_id.get(int(row["id"]))
                    require(existing is not None, f"Shared bill {row['bill_id']} is missing detail {row['id']}")
                    same_identity(row, existing, "sales_details", ("created_at", "bill_id", "product_id"))
                require(int(row["product_id"]) in source["products"],
                        f"Detail {row['id']} references unknown product")

            shared_payment_ids = {
                i for i in source["payment_transactions"].keys() & target["payment_transactions"].keys()
                if source["payment_transactions"][i]["created_at"] == target["payment_transactions"][i]["created_at"]
                and source["payment_transactions"][i]["bill_id"] == target["payment_transactions"][i]["bill_id"]
                and source["payment_transactions"][i]["bill_id"] in shared_bill_ids
            }
            new_payments = [source["payment_transactions"][i] for i in sorted(
                source["payment_transactions"].keys() - shared_payment_ids
            )]
            shared_movement_ids = {
                i for i in source["stock_movements"].keys() & target["stock_movements"].keys()
                if source["stock_movements"][i]["created_at"] == target["stock_movements"][i]["created_at"]
                and source["stock_movements"][i]["product_id"] == target["stock_movements"][i]["product_id"]
                and source["stock_movements"][i]["reference_type"] == target["stock_movements"][i]["reference_type"]
                and source["stock_movements"][i]["reference_id"] == target["stock_movements"][i]["reference_id"]
            }
            new_movements = [source["stock_movements"][i] for i in sorted(
                source["stock_movements"].keys() - shared_movement_ids
            )]
            for row in new_payments:
                require(int(row["bill_id"]) in source["sales_bills"],
                        f"Payment {row['id']} references unknown bill")
            for row in new_movements:
                require(int(row["product_id"]) in source["products"],
                        f"Movement {row['id']} references unknown product")
                # Legacy movement references are not FK-constrained. Some old
                # rows use references outside this shop's bill ID set; keep
                # those raw values rather than inventing a different link.

            print(f"Shop {shop_id}: {source_shop[0]['name']}")
            print("Missing:", {"products": len(new_products), "sales_bills": len(new_bills),
                               "sales_details": len(new_details), "payments": len(new_payments),
                               "stock_movements": len(new_movements)})
            print("Same-ID invoice collisions remapped:", len(
                (source["sales_bills"].keys() & target["sales_bills"].keys()) - shared_bill_ids
            ))
            print("Movement reference types:", dict(Counter(row.get("reference_type") for row in new_movements)))
            print("Existing product stock balances and other shared rows will not be changed.")
            if not apply:
                print("DRY RUN ONLY: no production rows were changed.")
                return

            conn.rollback()
            tx = conn.begin()
            try:
                product_map = {i: i for i in source["products"].keys() & target["products"].keys()}
                for row in new_products:
                    result = conn.execute(insert(live["products"]).values(**_prepare_values(live["products"], row)))
                    product_map[int(row["id"])] = int(result.inserted_primary_key[0])

                bill_map = {i: i for i in shared_bill_ids}
                for row in new_bills:
                    values = _prepare_values(live["sales_bills"], row)
                    _accounting_defaults(values)
                    result = conn.execute(insert(live["sales_bills"]).values(**values))
                    bill_map[int(row["id"])] = int(result.inserted_primary_key[0])

                for row in new_details:
                    values = _prepare_values(live["sales_details"], row)
                    values["bill_id"] = bill_map[int(row["bill_id"])]
                    values["product_id"] = product_map[int(row["product_id"])]
                    conn.execute(insert(live["sales_details"]).values(**values))

                for row in new_payments:
                    values = _prepare_values(live["payment_transactions"], row)
                    values["bill_id"] = bill_map[int(row["bill_id"])]
                    conn.execute(insert(live["payment_transactions"]).values(**values))

                for row in new_movements:
                    values = _prepare_values(live["stock_movements"], row)
                    values["product_id"] = product_map[int(row["product_id"])]
                    if values.get("reference_id") is not None and int(values["reference_id"]) in bill_map and (
                        values.get("reference_type") or ""
                    ).lower() in {"sale", "bill"}:
                        values["reference_id"] = bill_map[int(values["reference_id"])]
                    conn.execute(insert(live["stock_movements"]).values(**values))
                tx.commit()
            except Exception:
                tx.rollback()
                raise
            print("MERGE COMMITTED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-schema", default="vericant$shop_backup_20260912")
    parser.add_argument("--shop-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    merge(args.source_schema, args.shop_id, args.apply)


if __name__ == "__main__":
    main()
