"""receiver_day_reports: each receiver's analysed day (cycles, defrosts)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-20 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'receiver_day_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('receiver_id', sa.Uuid(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False, comment='Local (Europe/Warsaw) calendar day'),
        sa.Column('cooling_count', sa.Integer(), nullable=False),
        sa.Column('cooling_seconds', sa.Integer(), nullable=False),
        sa.Column('idle_count', sa.Integer(), nullable=False),
        sa.Column('idle_seconds', sa.Integer(), nullable=False),
        sa.Column('duty_percent', sa.Float(), nullable=True),
        sa.Column('defrost_count', sa.Integer(), nullable=False),
        sa.Column('covered_seconds', sa.Integer(), nullable=False),
        sa.Column('min_temp', sa.Float(), nullable=True),
        sa.Column('avg_temp', sa.Float(), nullable=True),
        sa.Column('max_temp', sa.Float(), nullable=True),
        sa.Column('defrosts', sa.JSON(), nullable=False),
        sa.Column('off_periods', sa.JSON(), nullable=False),
        sa.Column('runs', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['receiver_id'], ['receivers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('receiver_id', 'day', name='uq_receiver_day_reports_receiver_day'),
    )
    op.create_index('ix_receiver_day_reports_receiver_id', 'receiver_day_reports', ['receiver_id'])


def downgrade() -> None:
    op.drop_index('ix_receiver_day_reports_receiver_id', table_name='receiver_day_reports')
    op.drop_table('receiver_day_reports')
