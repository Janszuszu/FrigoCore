"""aggregates (agregaty): nameplate data and a group of the object's sensors

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-11 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'aggregates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('object_id', sa.Uuid(), nullable=False),
        sa.Column('compressor_model', sa.String(length=256), nullable=True),
        sa.Column('refrigerant', sa.String(length=64), nullable=True,
                  comment='Refrigerant designation, e.g. R404A'),
        sa.Column('refrigerant_charge_kg', sa.Float(), nullable=True),
        sa.Column('installed_on', sa.Date(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_aggregates_object_id', 'aggregates', ['object_id'])
    op.create_table(
        'aggregate_sensors',
        sa.Column('aggregate_id', sa.Uuid(), nullable=False),
        sa.Column('sensor_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['aggregate_id'], ['aggregates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sensor_id'], ['sensors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('aggregate_id', 'sensor_id'),
    )
    op.create_index('ix_aggregate_sensors_sensor_id', 'aggregate_sensors', ['sensor_id'])


def downgrade() -> None:
    op.drop_index('ix_aggregate_sensors_sensor_id', table_name='aggregate_sensors')
    op.drop_table('aggregate_sensors')
    op.drop_index('ix_aggregates_object_id', table_name='aggregates')
    op.drop_table('aggregates')
