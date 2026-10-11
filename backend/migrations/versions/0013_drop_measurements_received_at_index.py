"""measurements: drop the received_at-only index

Every query reads one sensor (or a few) over a time range, which the
(sensor_id, received_at) index serves. The time-only index was not just
unused but harmful: rows are stored in time order, so Postgres judged it
cheap and scanned every sensor's readings in the window (346 ms) instead of
the composite index (47 ms) for a 24 h chart — measured on prod 2026-10-11.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-11 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            'ix_measurements_received_at', table_name='measurements',
            postgresql_concurrently=True, if_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            'ix_measurements_received_at', 'measurements', ['received_at'],
            postgresql_concurrently=True, if_not_exists=True,
        )
