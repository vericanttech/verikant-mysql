#!/usr/bin/env python3
"""Restore one shop and its complete dependency graph from a MySQL backup schema.

The restore is deliberately ID-remapping and transactional: existing production
rows are never overwritten, and any failure rolls the entire restore back.

Dry run (default)::

    python scripts/restore_shop_from_mysql_backup.py \
      --source-schema 'vericant$shop_backup_20260912' --shop-id 16

Apply::

    python scripts/restore_shop_from_mysql_backup.py \
      --source-schema 'vericant$shop_backup_20260912' --shop-id 16 --apply
"""
from __future__ import annotations

import argparse
from collections import Counter
from typing import Any, Callable

from sqlalchemy import MetaData, Table, and_, insert, select

from app import create_app
from app.extensions import db


DIRECT_TABLES = (
    "shop_phones",
    "categories",
    "products",
    "clients",
    "suppliers",
    "sales_bills",
    "stock_movements",
    "payment_transactions",
    "expenses",
    "supplier_bills",
    "notes",
    "loans",
    "boutique_transactions",
    "checks",
    "employee_salaries",
    "employee_loans",
    "employee_loan_payments",
    "vitrine_product_selections",
    "vitrine_visits",
)

USER_FIELDS = {
    "sales_bills": ("user_id",),
    "stock_movements": ("user_id",),
    "payment_transactions": ("user_id",),
    "expenses": ("user_id",),
    "supplier_bills": ("user_id",),
    "notes": ("user_id",),
    "loans": ("user_id",),
    "boutique_transactions": ("user_id",),
    "checks": ("user_id",),
    "employee_salaries": ("employee_id", "processed_by"),
    "employee_loans": ("employee_id", "approved_by"),
    "employee_loan_payments": ("processed_by",),
}


def _rows(conn, table: Table, clause=None) -> list[dict[str, Any]]:
    statement = select(table)
    if clause is not None:
        statement = statement.where(clause)
    return [dict(row._mapping) for row in conn.execute(statement)]


def _prepare_values(target: Table, row: dict[str, Any]) -> dict[str, Any]:
    values = {key: value for key, value in row.items() if key in target.c}
    for column in target.primary_key.columns:
        if column.autoincrement is True or column.name == "id":
            values.pop(column.name, None)
    return values


def _accounting_defaults(values: dict[str, Any]) -> None:
    total = float(values.get("total_amount") or 0)
    paid = float(values.get("paid_amount") or 0)
    values.setdefault("amount_ht", total)
    values.setdefault("discount_amount", 0)
    values.setdefault("vat_amount", 0)
    values.setdefault("vat_applied", False)
    values.setdefault("paid_amount", paid)
    values.setdefault("remaining_amount", max(total - paid, 0))


def _insert_rows(
    conn,
    target: Table,
    source_rows: list[dict[str, Any]],
    transform: Callable[[dict[str, Any]], None] | None = None,
) -> dict[int, int]:
    id_map: dict[int, int] = {}
    for source_row in source_rows:
        values = _prepare_values(target, source_row)
        if transform:
            transform(values)
        result = conn.execute(insert(target).values(**values))
        if "id" in source_row and "id" in target.c:
            id_map[int(source_row["id"])] = int(result.inserted_primary_key[0])
    return id_map


def _mapped(mapping: dict[int, int], value: Any, label: str, nullable=False):
    if value is None and nullable:
        return None
    try:
        return mapping[int(value)]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Unresolved {label}: {value!r}") from exc


def restore(source_schema: str, source_shop_id: int, apply: bool) -> None:
    app = create_app()
    with app.app_context():
        engine = db.engine
        target_schema = engine.url.database
        if engine.dialect.name != "mysql":
            raise RuntimeError("This utility requires the production MySQL connection.")
        if source_schema == target_schema:
            raise RuntimeError("Source and target schemas must be different.")

        source_md = MetaData()
        target_md = MetaData()
        names = ("shops", "users", "user_shops", "sales_details", *DIRECT_TABLES)
        source = {
            name: Table(name, source_md, autoload_with=engine, schema=source_schema)
            for name in names
        }
        target = {
            name: Table(name, target_md, autoload_with=engine, schema=target_schema)
            for name in names
        }

        with engine.connect() as conn:
            shop_rows = _rows(
                conn, source["shops"], source["shops"].c.id == source_shop_id
            )
            if len(shop_rows) != 1:
                raise RuntimeError(
                    f"Expected one source shop {source_shop_id}; found {len(shop_rows)}."
                )
            shop = shop_rows[0]

            duplicate = conn.execute(
                select(target["shops"].c.id).where(
                    target["shops"].c.name == shop["name"]
                )
            ).first()
            if duplicate:
                raise RuntimeError(
                    f"Target already has shop {shop['name']!r} (id {duplicate.id})."
                )

            rows: dict[str, list[dict[str, Any]]] = {}
            for name in DIRECT_TABLES:
                rows[name] = _rows(
                    conn, source[name], source[name].c.shop_id == source_shop_id
                )

            bill_ids = {int(row["id"]) for row in rows["sales_bills"]}
            rows["sales_details"] = (
                _rows(conn, source["sales_details"], source["sales_details"].c.bill_id.in_(bill_ids))
                if bill_ids
                else []
            )
            rows["user_shops"] = _rows(
                conn,
                source["user_shops"],
                source["user_shops"].c.shop_id == source_shop_id,
            )

            linked_user_ids = {int(row["user_id"]) for row in rows["user_shops"]}
            linked_user_ids.update(
                int(row["id"])
                for row in _rows(
                    conn,
                    source["users"],
                    source["users"].c.current_shop_id == source_shop_id,
                )
            )
            required_user_ids = set(linked_user_ids)
            for table_name, fields in USER_FIELDS.items():
                for row in rows[table_name]:
                    required_user_ids.update(
                        int(row[field]) for field in fields if row.get(field) is not None
                    )
            rows["users"] = (
                _rows(conn, source["users"], source["users"].c.id.in_(required_user_ids))
                if required_user_ids
                else []
            )
            found_user_ids = {int(row["id"]) for row in rows["users"]}
            if found_user_ids != required_user_ids:
                raise RuntimeError(
                    f"Missing source users: {sorted(required_user_ids - found_user_ids)}"
                )

            product_ids = {int(row["id"]) for row in rows["products"]}
            detail_product_ids = {int(row["product_id"]) for row in rows["sales_details"]}
            if not detail_product_ids.issubset(product_ids):
                raise RuntimeError(
                    "Sales details reference products outside this shop: "
                    f"{sorted(detail_product_ids - product_ids)}"
                )

            movement_refs = Counter(
                (row.get("reference_type") or "none").lower()
                for row in rows["stock_movements"]
            )
            print(f"Source shop: {shop['name']} (id {source_shop_id})")
            print(f"Target schema: {target_schema}")
            print(f"Users: {', '.join(row['name'] for row in rows['users'])}")
            for name in ("users", "user_shops", *DIRECT_TABLES, "sales_details"):
                print(f"  {name}: {len(rows[name])}")
            print(f"  stock reference types: {dict(movement_refs)}")

            if not apply:
                print("DRY RUN ONLY: no production rows were changed.")
                return

            # SQLAlchemy autobegins a read transaction above. End that snapshot
            # before starting the single atomic production-write transaction.
            conn.rollback()
            transaction = conn.begin()
            try:
                shop_values = _prepare_values(target["shops"], shop)
                shop_values.setdefault("country_code", "SN")
                shop_values.setdefault("currency_code", "XOF")
                shop_values.setdefault("currency", "FCFA")
                shop_values.setdefault("show_all_sales", True)
                result = conn.execute(insert(target["shops"]).values(**shop_values))
                new_shop_id = int(result.inserted_primary_key[0])

                user_map: dict[int, int] = {}
                for source_user in rows["users"]:
                    existing = conn.execute(
                        select(target["users"].c.id).where(
                            target["users"].c.name == source_user["name"]
                        )
                    ).first()
                    old_user_id = int(source_user["id"])
                    if existing:
                        if old_user_id in linked_user_ids:
                            raise RuntimeError(
                                f"Linked username already exists in target: {source_user['name']!r}"
                            )
                        user_map[old_user_id] = int(existing.id)
                        continue
                    values = _prepare_values(target["users"], source_user)
                    if old_user_id in linked_user_ids:
                        values["current_shop_id"] = new_shop_id
                    elif values.get("current_shop_id") == source_shop_id:
                        values["current_shop_id"] = new_shop_id
                    else:
                        values["current_shop_id"] = None
                    inserted = conn.execute(insert(target["users"]).values(**values))
                    user_map[old_user_id] = int(inserted.inserted_primary_key[0])

                for source_link in rows["user_shops"]:
                    values = _prepare_values(target["user_shops"], source_link)
                    values["shop_id"] = new_shop_id
                    values["user_id"] = _mapped(
                        user_map, source_link["user_id"], "user_shops.user_id"
                    )
                    conn.execute(insert(target["user_shops"]).values(**values))

                def shop_transform(values):
                    values["shop_id"] = new_shop_id

                _insert_rows(conn, target["shop_phones"], rows["shop_phones"], shop_transform)
                category_map = _insert_rows(
                    conn, target["categories"], rows["categories"], shop_transform
                )

                def product_transform(values):
                    values["shop_id"] = new_shop_id
                    values["category_id"] = _mapped(
                        category_map, values.get("category_id"), "products.category_id", True
                    )

                product_map = _insert_rows(
                    conn, target["products"], rows["products"], product_transform
                )
                client_map = _insert_rows(
                    conn, target["clients"], rows["clients"], shop_transform
                )
                supplier_map = _insert_rows(
                    conn, target["suppliers"], rows["suppliers"], shop_transform
                )

                def bill_transform(values):
                    values["shop_id"] = new_shop_id
                    values["client_id"] = _mapped(
                        client_map, values.get("client_id"), "sales_bills.client_id", True
                    )
                    values["user_id"] = _mapped(
                        user_map, values.get("user_id"), "sales_bills.user_id"
                    )
                    _accounting_defaults(values)

                bill_map = _insert_rows(
                    conn, target["sales_bills"], rows["sales_bills"], bill_transform
                )

                def detail_transform(values):
                    values["bill_id"] = _mapped(
                        bill_map, values.get("bill_id"), "sales_details.bill_id"
                    )
                    values["product_id"] = _mapped(
                        product_map, values.get("product_id"), "sales_details.product_id"
                    )

                _insert_rows(
                    conn, target["sales_details"], rows["sales_details"], detail_transform
                )

                def supplier_bill_transform(values):
                    values["shop_id"] = new_shop_id
                    values["supplier_id"] = _mapped(
                        supplier_map, values.get("supplier_id"), "supplier_bills.supplier_id"
                    )
                    values["user_id"] = _mapped(
                        user_map, values.get("user_id"), "supplier_bills.user_id"
                    )

                supplier_bill_map = _insert_rows(
                    conn,
                    target["supplier_bills"],
                    rows["supplier_bills"],
                    supplier_bill_transform,
                )

                def employee_loan_transform(values):
                    values["shop_id"] = new_shop_id
                    values["employee_id"] = _mapped(
                        user_map, values.get("employee_id"), "employee_loans.employee_id"
                    )
                    values["approved_by"] = _mapped(
                        user_map, values.get("approved_by"), "employee_loans.approved_by"
                    )

                employee_loan_map = _insert_rows(
                    conn,
                    target["employee_loans"],
                    rows["employee_loans"],
                    employee_loan_transform,
                )

                def user_shop_transform(table_name, *category_fields):
                    def transform(values):
                        values["shop_id"] = new_shop_id
                        for field in USER_FIELDS.get(table_name, ()):
                            values[field] = _mapped(
                                user_map, values.get(field), f"{table_name}.{field}"
                            )
                        for field in category_fields:
                            values[field] = _mapped(
                                category_map,
                                values.get(field),
                                f"{table_name}.{field}",
                                True,
                            )
                    return transform

                _insert_rows(
                    conn,
                    target["payment_transactions"],
                    rows["payment_transactions"],
                    lambda values: (
                        values.update(
                            shop_id=new_shop_id,
                            bill_id=_mapped(bill_map, values.get("bill_id"), "payment_transactions.bill_id"),
                            user_id=_mapped(user_map, values.get("user_id"), "payment_transactions.user_id"),
                        )
                    ),
                )
                _insert_rows(conn, target["expenses"], rows["expenses"], user_shop_transform("expenses", "category_id"))
                _insert_rows(conn, target["notes"], rows["notes"], user_shop_transform("notes"))
                _insert_rows(conn, target["loans"], rows["loans"], user_shop_transform("loans"))
                _insert_rows(conn, target["boutique_transactions"], rows["boutique_transactions"], user_shop_transform("boutique_transactions", "category_id"))
                _insert_rows(conn, target["checks"], rows["checks"], user_shop_transform("checks"))
                _insert_rows(conn, target["employee_salaries"], rows["employee_salaries"], user_shop_transform("employee_salaries"))

                def loan_payment_transform(values):
                    values["shop_id"] = new_shop_id
                    values["loan_id"] = _mapped(
                        employee_loan_map, values.get("loan_id"), "employee_loan_payments.loan_id"
                    )
                    values["processed_by"] = _mapped(
                        user_map, values.get("processed_by"), "employee_loan_payments.processed_by"
                    )

                _insert_rows(conn, target["employee_loan_payments"], rows["employee_loan_payments"], loan_payment_transform)

                def movement_transform(values):
                    values["shop_id"] = new_shop_id
                    values["product_id"] = _mapped(
                        product_map, values.get("product_id"), "stock_movements.product_id"
                    )
                    values["user_id"] = _mapped(
                        user_map, values.get("user_id"), "stock_movements.user_id"
                    )
                    old_reference = values.get("reference_id")
                    reference_type = (values.get("reference_type") or "").lower()
                    if old_reference is None:
                        return
                    if reference_type in {"sale", "bill"}:
                        values["reference_id"] = bill_map.get(int(old_reference))
                    elif reference_type in {"purchase", "supplier_bill"}:
                        values["reference_id"] = supplier_bill_map.get(int(old_reference))
                    else:
                        values["reference_id"] = None

                _insert_rows(conn, target["stock_movements"], rows["stock_movements"], movement_transform)

                def vitrine_selection_transform(values):
                    values["shop_id"] = new_shop_id
                    values["product_id"] = _mapped(
                        product_map, values.get("product_id"), "vitrine_product_selections.product_id"
                    )

                _insert_rows(conn, target["vitrine_product_selections"], rows["vitrine_product_selections"], vitrine_selection_transform)
                _insert_rows(conn, target["vitrine_visits"], rows["vitrine_visits"], shop_transform)

                transaction.commit()
            except Exception:
                transaction.rollback()
                raise

            print(f"RESTORE COMMITTED: new shop id {new_shop_id}")
            print(f"Restored linked users: {len(linked_user_ids)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-schema", required=True)
    parser.add_argument("--shop-id", type=int, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the restore. Without this flag the command is read-only.",
    )
    args = parser.parse_args()
    restore(args.source_schema, args.shop_id, args.apply)


if __name__ == "__main__":
    main()
