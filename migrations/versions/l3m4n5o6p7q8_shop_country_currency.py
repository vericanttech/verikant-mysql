"""Add controlled shop country and currency codes.

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa


revision = "l3m4n5o6p7q8"
down_revision = "k2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    columns = {column["name"] for column in sa.inspect(conn).get_columns("shops")}
    if "country_code" not in columns:
        op.add_column(
            "shops",
            sa.Column("country_code", sa.String(length=2), nullable=False, server_default="SN"),
        )
    if "currency_code" not in columns:
        op.add_column(
            "shops",
            sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="XOF"),
        )

    # Preserve recognizable existing settings while assigning safe defaults to
    # all legacy Senegal shops.
    op.execute(
        "UPDATE shops SET country_code = 'GN', currency_code = 'GNF', currency = 'GNF' "
        "WHERE UPPER(TRIM(currency)) = 'GNF'"
    )
    op.execute(
        "UPDATE shops SET country_code = 'SL', currency_code = 'SLE', currency = 'Le' "
        "WHERE UPPER(TRIM(currency)) IN ('SLE', 'SLL', 'LE')"
    )
    op.execute(
        "UPDATE shops SET country_code = 'SN', currency_code = 'XOF', currency = 'FCFA' "
        "WHERE currency_code = 'XOF'"
    )


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("shops")}
    if "currency_code" in columns:
        op.drop_column("shops", "currency_code")
    if "country_code" in columns:
        op.drop_column("shops", "country_code")
