"""Add idempotent mobile cashier operations.

Revision ID: r9s0t1u2v3w4
Revises: q8r9s0t1u2v3
"""
from alembic import op
import sqlalchemy as sa


revision = 'r9s0t1u2v3w4'
down_revision = 'q8r9s0t1u2v3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'mobile_cashier_operations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('client_operation_id', sa.String(length=64), nullable=False),
        sa.Column('operation_type', sa.String(length=32), nullable=False),
        sa.Column('response_payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'shop_id',
            'client_operation_id',
            name='uq_mobile_cashier_shop_client_operation',
        ),
    )
    op.create_index(
        'idx_mobile_cashier_operation_type',
        'mobile_cashier_operations',
        ['operation_type'],
    )
    op.create_index(
        'idx_mobile_cashier_operation_user',
        'mobile_cashier_operations',
        ['user_id'],
    )


def downgrade():
    op.drop_index(
        'idx_mobile_cashier_operation_user',
        table_name='mobile_cashier_operations',
    )
    op.drop_index(
        'idx_mobile_cashier_operation_type',
        table_name='mobile_cashier_operations',
    )
    op.drop_table('mobile_cashier_operations')
