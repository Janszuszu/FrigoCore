"""receivers (odbiorniki): chamber + evaporator sensor and working temperatures

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-10 20:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'receivers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('object_id', sa.Uuid(), nullable=False),
        sa.Column('chamber_sensor_id', sa.Uuid(), nullable=True,
                  comment='Air temperature inside the chamber'),
        sa.Column('evaporator_sensor_id', sa.Uuid(), nullable=True,
                  comment="Evaporator coil temperature; without it defrost can't be told apart"),
        sa.Column('setpoint', sa.Float(), nullable=True, comment='Temperature the chamber should hold, °C'),
        sa.Column('cut_in', sa.Float(), nullable=True, comment='Chamber temperature at which cooling starts, °C'),
        sa.Column('cut_out', sa.Float(), nullable=True, comment='Chamber temperature at which cooling stops, °C'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chamber_sensor_id'], ['sensors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['evaporator_sensor_id'], ['sensors.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_receivers_object_id', 'receivers', ['object_id'])


def downgrade() -> None:
    op.drop_index('ix_receivers_object_id', table_name='receivers')
    op.drop_table('receivers')
