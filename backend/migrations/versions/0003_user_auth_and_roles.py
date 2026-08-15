"""user auth and roles

Revision ID: a1b2c3d4e5f6
Revises: 9e288d43a755
Create Date: 2026-08-15 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9e288d43a755'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_objects',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('object_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'object_id'),
    )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_object_id'))
        batch_op.drop_column('object_id')


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('object_id', sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_object_id'), ['object_id'], unique=False)

    op.drop_table('user_objects')
