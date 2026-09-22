#!/usr/bin/env python3
"""One-time, guarded reconciliation of TOURE & FRÉRES pre-merge history.

Dry-run by default. Never updates an existing live row or stock balance.
The three older invoices with reused numbers receive deterministic new numbers;
the printed mapping should be retained with the deployment backup.
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
    "sales_details", "payment_transactions", "stock_movements", "loans",
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def fetch(conn, table, clause=None):
    query = select(table)
    if clause is not None:
        query = query.where(clause)
    return {int(row.id): dict(row._mapping) for row in conn.execute(query)}


def same(source, target, *fields):
    return all(str(source.get(field)) == str(target.get(field)) for field in fields)


def merge(source_schema, apply):
    shop_id = 13
    app = create_app()
    with app.app_context():
        engine = db.engine
        live_schema = engine.url.database
        require(engine.dialect.name == "mysql" and source_schema != live_schema,
                "Two distinct MySQL schemas are required")
        source_md, live_md = MetaData(), MetaData()
        src = {name: Table(name, source_md, autoload_with=engine, schema=source_schema)
               for name in NAMES}
        live = {name: Table(name, live_md, autoload_with=engine, schema=live_schema)
                for name in NAMES}

        with engine.connect() as conn:
            s = {name: fetch(conn, src[name], src[name].c.shop_id == shop_id)
                 for name in ("categories", "clients", "products", "sales_bills",
                              "payment_transactions", "stock_movements", "loans")}
            t = {name: fetch(conn, live[name], live[name].c.shop_id == shop_id)
                 for name in s}
            s["shops"] = fetch(conn, src["shops"], src["shops"].c.id == shop_id)
            t["shops"] = fetch(conn, live["shops"], live["shops"].c.id == shop_id)
            require(len(s["shops"]) == len(t["shops"]) == 1, "Shop must exist in both schemas")
            require(next(iter(s["shops"].values()))["name"] == "TOURE & FRÉRES" and
                    next(iter(t["shops"].values()))["name"] == "TOURE & FRÉRES",
                    "Unexpected shop identity")

            for name in ("categories", "clients"):
                require(s[name].keys() <= t[name].keys(), f"Missing {name} in live")
                for row_id in s[name]:
                    require(same(s[name][row_id], t[name][row_id], "created_at", "name"),
                            f"Ambiguous {name} id {row_id}")

            shared_products = {i for i in s["products"].keys() & t["products"].keys()
                               if same(s["products"][i], t["products"][i], "created_at")}
            new_products = [s["products"][i] for i in sorted(s["products"].keys() - shared_products)]
            for row in new_products:
                require(row["category_id"] is None or int(row["category_id"]) in t["categories"],
                        f"Product {row['id']} has no live category")

            shared_bills = {i for i in s["sales_bills"].keys() & t["sales_bills"].keys()
                            if same(s["sales_bills"][i], t["sales_bills"][i],
                                    "created_at", "bill_number")}
            new_bills = [s["sales_bills"][i] for i in sorted(s["sales_bills"].keys() - shared_bills)]
            live_numbers = {int(row["bill_number"]) for row in t["sales_bills"].values()}
            source_numbers = [int(row["bill_number"]) for row in s["sales_bills"].values()]
            require(len(source_numbers) == len(set(source_numbers)), "Duplicate source bill numbers")
            collisions = [row for row in new_bills if int(row["bill_number"]) in live_numbers]
            require(len(collisions) == 3, f"Expected exactly three number collisions, got {len(collisions)}")
            expected_numbers = {200426041001, 200426041002, 200426041003}
            require({int(row["bill_number"]) for row in collisions} == expected_numbers,
                    "Unexpected invoice-number collisions")
            renumber = {}
            for offset, row in enumerate(sorted(collisions, key=lambda item: int(item["bill_number"]))):
                original = int(row["bill_number"])
                replacement = original * 1000 + 901 + offset
                require(replacement not in live_numbers and replacement not in source_numbers,
                        f"Replacement bill number {replacement} is already used")
                renumber[int(row["id"])] = replacement
            for row in new_bills:
                require(row["client_id"] is None or int(row["client_id"]) in t["clients"],
                        f"Bill {row['id']} has no live client")

            source_bill_ids = set(s["sales_bills"])
            live_bill_ids = set(t["sales_bills"])
            sd = fetch(conn, src["sales_details"], src["sales_details"].c.bill_id.in_(source_bill_ids))
            td = fetch(conn, live["sales_details"], live["sales_details"].c.bill_id.in_(live_bill_ids))
            new_bill_ids = {int(row["id"]) for row in new_bills}
            new_details = [row for row in sd.values() if int(row["bill_id"]) in new_bill_ids]
            for row in sd.values():
                require(int(row["product_id"]) in s["products"],
                        f"Detail {row['id']} has unknown source product")
                if int(row["bill_id"]) in shared_bills:
                    target = td.get(int(row["id"]))
                    require(target is not None and same(row, target, "created_at", "bill_id", "product_id"),
                            f"Shared detail {row['id']} differs or is missing")

            shared_payments = {i for i in s["payment_transactions"].keys() & t["payment_transactions"].keys()
                               if same(s["payment_transactions"][i], t["payment_transactions"][i],
                                       "created_at", "bill_id") and
                               int(s["payment_transactions"][i]["bill_id"]) in shared_bills}
            new_payments = [s["payment_transactions"][i] for i in sorted(
                s["payment_transactions"].keys() - shared_payments)]
            shared_movements = {i for i in s["stock_movements"].keys() & t["stock_movements"].keys()
                                if same(s["stock_movements"][i], t["stock_movements"][i],
                                        "created_at", "product_id", "reference_type", "reference_id")}
            new_movements = [s["stock_movements"][i] for i in sorted(
                s["stock_movements"].keys() - shared_movements)]
            for row in new_movements:
                require(int(row["product_id"]) in s["products"],
                        f"Movement {row['id']} has unknown source product")
            for row in new_payments:
                require(int(row["bill_id"]) in s["sales_bills"],
                        f"Payment {row['id']} has unknown source bill")

            shared_loans = {i for i in s["loans"].keys() & t["loans"].keys()
                            if same(s["loans"][i], t["loans"][i], "created_at")}
            new_loans = [s["loans"][i] for i in sorted(s["loans"].keys() - shared_loans)]

            source_users = fetch(conn, src["users"])
            live_users = fetch(conn, live["users"])
            used_users = {int(row["user_id"]) for name in
                          ("sales_bills", "payment_transactions", "stock_movements", "loans")
                          for row in s[name].values()}
            for user_id in used_users:
                require(user_id in source_users and user_id in live_users and
                        source_users[user_id]["name"] == live_users[user_id]["name"],
                        f"User identity mismatch {user_id}")

            print("TOURE & FRÉRES planned additions:")
            print({"products": len(new_products), "bills": len(new_bills),
                   "details": len(new_details), "payments": len(new_payments),
                   "movements": len(new_movements), "loans": len(new_loans)})
            print("Product ID collisions:", len((s["products"].keys() & t["products"].keys()) - shared_products))
            print("Movement reference types:", dict(Counter(row.get("reference_type") for row in new_movements)))
            print("INVOICE NUMBER MAPPING (source bill ID, old number, new number):")
            for row in collisions:
                print(int(row["id"]), int(row["bill_number"]), renumber[int(row["id"])])
            print("Existing records and stock balances remain unchanged.")
            if not apply:
                print("DRY RUN ONLY")
                return

            conn.rollback()
            tx = conn.begin()
            try:
                product_map = {i: i for i in shared_products}
                for row in new_products:
                    result = conn.execute(insert(live["products"]).values(
                        **_prepare_values(live["products"], row)))
                    product_map[int(row["id"])] = int(result.inserted_primary_key[0])

                bill_map = {i: i for i in shared_bills}
                for row in new_bills:
                    values = _prepare_values(live["sales_bills"], row)
                    _accounting_defaults(values)
                    if int(row["id"]) in renumber:
                        values["bill_number"] = renumber[int(row["id"])]
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
                        values.get("reference_type") or "").lower() in {"sale", "bill"}:
                        values["reference_id"] = bill_map[int(values["reference_id"])]
                    conn.execute(insert(live["stock_movements"]).values(**values))
                for row in new_loans:
                    conn.execute(insert(live["loans"]).values(**_prepare_values(live["loans"], row)))
                tx.commit()
            except Exception:
                tx.rollback()
                raise
            print("MERGE COMMITTED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-schema", default="vericant$shop_backup_20260912")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    merge(args.source_schema, args.apply)


if __name__ == "__main__":
    main()
