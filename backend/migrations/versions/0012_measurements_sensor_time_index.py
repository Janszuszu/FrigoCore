"""measurements: index (sensor_id, received_at) for per-sensor time ranges

Charts, receiver stopwatches and meter consumption all read one sensor over
a time window. With only separate sensor_id and received_at indexes,
Postgres walked every reading in the window for all sensors and filtered
(343k of 360k rows thrown away for a 24 h chart on 2026-10-11). The
composite index replaces the single-column sensor_id one.

Built CONCURRENTLY so MQTT ingestion keeps writing during the build on a
large table; IF [NOT] EXISTS lets an index created by hand beforehand pass.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-11 11:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            'ix_measurements_sensor_id_received_at', 'measurements', ['sensor_id', 'received_at'],
            postgresql_concurrently=True, if_not_exists=True,
        )
        op.drop_index(
            'ix_measurements_sensor_id', table_name='measurements',
            postgresql_concurrently=True, if_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            'ix_measurements_sensor_id', 'measurements', ['sensor_id'],
            postgresql_concurrently=True, if_not_exists=True,
        )
        op.drop_index(
            'ix_measurements_sensor_id_received_at', table_name='measurements',
            postgresql_concurrently=True, if_exists=True,
        )
