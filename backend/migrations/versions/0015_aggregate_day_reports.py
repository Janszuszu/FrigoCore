"""aggregate_day_reports: each aggregate's day read from its power draw

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-20 13:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'aggregate_day_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('aggregate_id', sa.Uuid(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False, comment='Local (Europe/Warsaw) calendar day'),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('running_seconds', sa.Integer(), nullable=False),
        sa.Column('idle_seconds', sa.Integer(), nullable=False),
        sa.Column('starts', sa.Integer(), nullable=False),
        sa.Column('avg_run_seconds', sa.Integer(), nullable=True),
        sa.Column('max_run_seconds', sa.Integer(), nullable=True),
        sa.Column('avg_idle_seconds', sa.Integer(), nullable=True),
        sa.Column('duty_percent', sa.Float(), nullable=True),
        sa.Column('covered_seconds', sa.Integer(), nullable=False),
        sa.Column('energy_kwh', sa.Float(), nullable=True),
        sa.Column('avg_running_value', sa.Float(), nullable=True, comment='W or A while running'),
        sa.Column('avg_start_peak', sa.Float(), nullable=True),
        sa.Column('threshold', sa.Float(), nullable=True),
        sa.Column('runs', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['aggregate_id'], ['aggregates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('aggregate_id', 'day', name='uq_aggregate_day_reports_aggregate_day'),
    )
    op.create_index('ix_aggregate_day_reports_aggregate_id', 'aggregate_day_reports', ['aggregate_id'])


def downgrade() -> None:
    op.drop_index('ix_aggregate_day_reports_aggregate_id', table_name='aggregate_day_reports')
    op.drop_table('aggregate_day_reports')
