"""receiver_day_reports: the chamber door's openings and open time

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-26 13:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('receiver_day_reports') as batch:
        batch.add_column(sa.Column('door_open_count', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('door_open_seconds', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('receiver_day_reports') as batch:
        batch.drop_column('door_open_seconds')
        batch.drop_column('door_open_count')
