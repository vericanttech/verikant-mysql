"""Preserve case-distinct legacy usernames and category names on MySQL.

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
"""
from alembic import op


revision = 'j1k2l3m4n5o6'
down_revision = 'i0j1k2l3m4n5'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != 'mysql':
        return
    op.execute(
        "ALTER TABLE users MODIFY name VARCHAR(255) "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL"
    )
    op.execute(
        "ALTER TABLE categories MODIFY name VARCHAR(255) "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL"
    )


def downgrade():
    # A case-insensitive downgrade can fail when legitimate legacy values differ
    # only by case, so leave the safe binary collation in place.
    pass
