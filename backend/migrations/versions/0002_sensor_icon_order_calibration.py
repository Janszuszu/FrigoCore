"""sensor icon, display order and calibration

Revision ID: 9e288d43a755
Revises: 0f603005f247
Create Date: 2026-08-09 11:04:57.553989
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9e288d43a755'
down_revision: Union[str, None] = '0f603005f247'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default is required, not cosmetic: these columns are NOT NULL and
    # existing installations already hold sensor rows, which have no value to
    # put in them otherwise.
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'icon', sa.String(length=32), nullable=False,
            server_default='thermometer',
            comment="Sensor icon identifier, e.g. 'evaporator', 'condenser', 'fan'",
        ))
        batch_op.add_column(sa.Column(
            'display_order', sa.Integer(), nullable=False, server_default='0',
            comment='Position on the client Dashboard within the object (ascending)',
        ))
        batch_op.add_column(sa.Column(
            'calibration_offset', sa.Float(), nullable=False, server_default='0',
            comment='Degrees added to each raw reading, e.g. -0.5',
        ))

    # Backfill display_order per object in the order sensors were listed
    # before this column existed (alphabetically by name), so upgrading does
    # not visibly reshuffle anyone's dashboard.
    sensors = sa.table(
        'sensors',
        sa.column('id', sa.Uuid()),
        sa.column('name', sa.String()),
        sa.column('object_id', sa.Uuid()),
        sa.column('display_order', sa.Integer()),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(sensors.c.id, sensors.c.object_id).order_by(
            sensors.c.object_id, sensors.c.name
        )
    ).fetchall()
    position_by_object: dict[object, int] = {}
    for sensor_id, object_id in rows:
        position = position_by_object.get(object_id, 0)
        position_by_object[object_id] = position + 1
        bind.execute(
            sensors.update()
            .where(sensors.c.id == sensor_id)
            .values(display_order=position)
        )


def downgrade() -> None:
    with op.batch_alter_table('sensors', schema=None) as batch_op:
        batch_op.drop_column('calibration_offset')
        batch_op.drop_column('display_order')
        batch_op.drop_column('icon')
