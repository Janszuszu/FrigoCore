"""drop receivers.setpoint — time left is counted to the cut-out instead

On a PEGO-style controller the setpoint is where cooling stops, so a
separate setpoint field only duplicated the cut-out (or contradicted it).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-10 21:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('receivers', schema=None) as batch_op:
        batch_op.drop_column('setpoint')


def downgrade() -> None:
    with op.batch_alter_table('receivers', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'setpoint', sa.Float(), nullable=True, comment='Temperature the chamber should hold, °C',
        ))
