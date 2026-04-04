"""products.image_path optional thumbnail

Revision ID: f1e2d3c4b5a6
Revises: b2c8e9f1a3d4
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = 'f1e2d3c4b5a6'
down_revision = 'b2c8e9f1a3d4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'products',
        sa.Column('image_path', sa.String(length=512), nullable=True),
    )


def downgrade():
    op.drop_column('products', 'image_path')
