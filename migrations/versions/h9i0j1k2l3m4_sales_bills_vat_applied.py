"""sales_bills vat_applied flag

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-04-12

"""
from alembic import op
import sqlalchemy as sa

revision = 'h9i0j1k2l3m4'
down_revision = 'g8h9i0j1k2l3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c['name'] for c in insp.get_columns('sales_bills')}

    if 'vat_applied' not in cols:
        op.add_column(
            'sales_bills',
            sa.Column('vat_applied', sa.Boolean(), nullable=False, server_default='0'),
        )

    op.execute(
        'UPDATE sales_bills SET vat_applied = 1 WHERE vat_rate IS NOT NULL'
    )


def downgrade():
    op.drop_column('sales_bills', 'vat_applied')
