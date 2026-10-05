"""Add account deletion request queue.

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
"""
from alembic import op
import sqlalchemy as sa


revision = 'q8r9s0t1u2v3'
down_revision = 'p7q8r9s0t1u2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'account_deletion_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('shop_id', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('contact', sa.String(length=255), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column(
            'language_code',
            sa.String(length=2),
            nullable=False,
            server_default='fr',
        ),
        sa.Column(
            'status',
            sa.String(length=24),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('processed_at', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_deletion_request_shop', 'account_deletion_requests', ['shop_id']
    )
    op.create_index(
        'idx_deletion_request_status', 'account_deletion_requests', ['status']
    )
    op.create_index(
        'idx_deletion_request_user', 'account_deletion_requests', ['user_id']
    )


def downgrade():
    op.drop_index('idx_deletion_request_user', table_name='account_deletion_requests')
    op.drop_index('idx_deletion_request_status', table_name='account_deletion_requests')
    op.drop_index('idx_deletion_request_shop', table_name='account_deletion_requests')
    op.drop_table('account_deletion_requests')
