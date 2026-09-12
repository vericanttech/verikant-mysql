"""Allow exact legacy category names that MySQL compares as equivalent.

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
"""
from alembic import op


revision = 'k2l3m4n5o6p7'
down_revision = 'j1k2l3m4n5o6'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != 'mysql':
        return
    op.drop_index('idx_category_shop_name', table_name='categories')
    op.create_index(
        'idx_category_shop_name',
        'categories',
        ['shop_id', 'name'],
        unique=False,
    )


def downgrade():
    if op.get_bind().dialect.name != 'mysql':
        return
    op.drop_index('idx_category_shop_name', table_name='categories')
    op.create_index(
        'idx_category_shop_name',
        'categories',
        ['shop_id', 'name'],
        unique=True,
    )
