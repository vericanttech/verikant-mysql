"""sales_bills VAT: amount_ht, vat_rate, vat_amount

Revision ID: c3d4e5f6a7b8
Revises: f1e2d3c4b5a6
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'f1e2d3c4b5a6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c['name'] for c in insp.get_columns('sales_bills')}

    if 'amount_ht' not in cols:
        op.add_column('sales_bills', sa.Column('amount_ht', sa.REAL(), nullable=True))
    if 'vat_rate' not in cols:
        op.add_column('sales_bills', sa.Column('vat_rate', sa.REAL(), nullable=True))
    if 'vat_amount' not in cols:
        op.add_column(
            'sales_bills',
            sa.Column('vat_amount', sa.REAL(), nullable=False, server_default='0'),
        )

    op.execute(
        "UPDATE sales_bills SET amount_ht = total_amount, vat_amount = 0 "
        "WHERE amount_ht IS NULL"
    )
    op.alter_column(
        'sales_bills',
        'amount_ht',
        existing_type=sa.REAL(),
        nullable=False,
    )


def downgrade():
    op.drop_column('sales_bills', 'vat_amount')
    op.drop_column('sales_bills', 'vat_rate')
    op.drop_column('sales_bills', 'amount_ht')
