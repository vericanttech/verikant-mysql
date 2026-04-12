"""shops show_all_sales listing mode

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-04-12

"""
from alembic import op
import sqlalchemy as sa

revision = 'i0j1k2l3m4n5'
down_revision = 'h9i0j1k2l3m4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c['name'] for c in insp.get_columns('shops')}

    if 'show_all_sales' not in cols:
        op.add_column(
            'shops',
            sa.Column('show_all_sales', sa.Boolean(), nullable=False, server_default='1'),
        )


def downgrade():
    op.drop_column('shops', 'show_all_sales')
