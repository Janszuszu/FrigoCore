"""aggregates.cooling_capacity_kw — rated cooling capacity on the nameplate

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-11 09:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('aggregates', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'cooling_capacity_kw', sa.Float(), nullable=True, comment='Rated cooling capacity, kW',
        ))


def downgrade() -> None:
    with op.batch_alter_table('aggregates', schema=None) as batch_op:
        batch_op.drop_column('cooling_capacity_kw')
