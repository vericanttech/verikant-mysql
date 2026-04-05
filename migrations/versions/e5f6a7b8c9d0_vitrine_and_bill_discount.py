"""vitrine marketing fields + sales_bills discount

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    shop_cols = {c['name'] for c in insp.get_columns('shops')}
    if 'vitrine_slug' not in shop_cols:
        op.add_column('shops', sa.Column('vitrine_slug', sa.String(128), nullable=True))
    if 'vitrine_enabled' not in shop_cols:
        op.add_column(
            'shops',
            sa.Column('vitrine_enabled', sa.Boolean(), nullable=False, server_default='0'),
        )
    if 'vitrine_title' not in shop_cols:
        op.add_column('shops', sa.Column('vitrine_title', sa.Text(), nullable=True))
    if 'vitrine_body' not in shop_cols:
        op.add_column('shops', sa.Column('vitrine_body', sa.Text(), nullable=True))
    if 'vitrine_discount_percent' not in shop_cols:
        op.add_column('shops', sa.Column('vitrine_discount_percent', sa.REAL(), nullable=True))
    if 'vitrine_promo_end' not in shop_cols:
        op.add_column('shops', sa.Column('vitrine_promo_end', sa.String(32), nullable=True))

    try:
        op.create_unique_constraint('uq_shops_vitrine_slug', 'shops', ['vitrine_slug'])
    except Exception:
        pass

    bill_cols = {c['name'] for c in insp.get_columns('sales_bills')}
    if 'discount_rate' not in bill_cols:
        op.add_column('sales_bills', sa.Column('discount_rate', sa.REAL(), nullable=True))
    if 'discount_amount' not in bill_cols:
        op.add_column(
            'sales_bills',
            sa.Column('discount_amount', sa.REAL(), nullable=False, server_default='0'),
        )

    tables = insp.get_table_names()
    if 'vitrine_visits' not in tables:
        op.create_table(
            'vitrine_visits',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('shop_id', sa.Integer(), nullable=False),
            sa.Column('visitor_key', sa.String(64), nullable=False),
            sa.Column('created_at', sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
            sa.PrimaryKeyConstraint('id'),
        )
    # MySQL cannot index full TEXT without prefix; shop_id index is enough for analytics filters.
    insp = sa.inspect(conn)
    if 'vitrine_visits' in insp.get_table_names():
        idx_names = {i['name'] for i in insp.get_indexes('vitrine_visits')}
        if 'idx_vitrine_visit_shop' not in idx_names:
            op.create_index('idx_vitrine_visit_shop', 'vitrine_visits', ['shop_id'])


def downgrade():
    op.drop_table('vitrine_visits')
    try:
        op.drop_constraint('uq_shops_vitrine_slug', 'shops', type_='unique')
    except Exception:
        pass
    op.drop_column('sales_bills', 'discount_amount')
    op.drop_column('sales_bills', 'discount_rate')
    op.drop_column('shops', 'vitrine_promo_end')
    op.drop_column('shops', 'vitrine_discount_percent')
    op.drop_column('shops', 'vitrine_body')
    op.drop_column('shops', 'vitrine_title')
    op.drop_column('shops', 'vitrine_enabled')
    op.drop_column('shops', 'vitrine_slug')
