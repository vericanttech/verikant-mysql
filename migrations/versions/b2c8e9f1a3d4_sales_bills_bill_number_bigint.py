"""sales_bills.bill_number BIGINT (large composite bill numbers)

Revision ID: b2c8e9f1a3d4
Revises: d7a347885e2c
Create Date: 2026-04-03

"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c8e9f1a3d4'
down_revision = 'd7a347885e2c'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'sales_bills',
        'bill_number',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        'sales_bills',
        'bill_number',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
