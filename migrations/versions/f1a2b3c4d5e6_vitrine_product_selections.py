"""vitrine_product_selections: curated products per shop

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if 'vitrine_product_selections' in insp.get_table_names():
        return
    op.create_table(
        'vitrine_product_selections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_promo', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'product_id', name='uq_vitrine_shop_product'),
    )
    op.create_index(
        'idx_vitrine_sel_shop_order',
        'vitrine_product_selections',
        ['shop_id', 'sort_order'],
    )


def downgrade():
    op.drop_table('vitrine_product_selections')
