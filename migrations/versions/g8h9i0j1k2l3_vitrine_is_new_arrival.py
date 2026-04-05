"""vitrine_product_selections: is_new_arrival badge

Revision ID: g8h9i0j1k2l3
Revises: f1a2b3c4d5e6
Create Date: 2026-04-05

"""
from alembic import op
import sqlalchemy as sa

revision = 'g8h9i0j1k2l3'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if 'vitrine_product_selections' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('vitrine_product_selections')}
    if 'is_new_arrival' not in cols:
        op.add_column(
            'vitrine_product_selections',
            sa.Column('is_new_arrival', sa.Boolean(), nullable=False, server_default='0'),
        )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if 'vitrine_product_selections' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('vitrine_product_selections')}
    if 'is_new_arrival' in cols:
        op.drop_column('vitrine_product_selections', 'is_new_arrival')
