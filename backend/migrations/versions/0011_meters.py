"""meters (liczniki): kWh counter plus optional power, current and voltage

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-11 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'meters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('object_id', sa.Uuid(), nullable=False),
        sa.Column('energy_sensor_id', sa.Uuid(), nullable=True, comment='kWh counter'),
        sa.Column('power_sensor_id', sa.Uuid(), nullable=True),
        sa.Column('current_sensor_id', sa.Uuid(), nullable=True),
        sa.Column('voltage_sensor_id', sa.Uuid(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['energy_sensor_id'], ['sensors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['power_sensor_id'], ['sensors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['current_sensor_id'], ['sensors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['voltage_sensor_id'], ['sensors.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_meters_object_id', 'meters', ['object_id'])


def downgrade() -> None:
    op.drop_index('ix_meters_object_id', table_name='meters')
    op.drop_table('meters')
