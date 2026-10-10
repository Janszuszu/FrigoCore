"""sensor kind (temperature, current, voltage, power, energy)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-10 14:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every sensor that exists today measures temperature, so the server
    # default backfills existing rows correctly.
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'kind', sa.String(length=16), nullable=False,
            server_default='temperature',
            comment='Measured quantity: temperature, current, voltage, power, energy',
        ))


def downgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.drop_column('kind')
