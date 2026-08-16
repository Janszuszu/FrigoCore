"""service alarm dispatch — assignments, events, escalation policies, device tokens

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-16 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alarm gains en_route_at — existing rows get NULL, which is correct:
    # no alarm created before this migration ever went en route.
    with op.batch_alter_table('alarms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('en_route_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'escalation_policies',
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('object_id', sa.Uuid(), nullable=True, comment='NULL = global default policy'),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('escalation_policies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_escalation_policies_object_id'), ['object_id'], unique=False)

    op.create_table(
        'escalation_tiers',
        sa.Column('policy_id', sa.Uuid(), nullable=False),
        sa.Column('tier_order', sa.Integer(), nullable=False),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('target_type', sa.String(length=16), nullable=False),
        sa.Column('target_user_id', sa.Uuid(), nullable=True),
        sa.Column('target_role', sa.String(length=16), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['policy_id'], ['escalation_policies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_id', 'tier_order', name='uq_escalation_tier_order'),
    )
    with op.batch_alter_table('escalation_tiers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_escalation_tiers_policy_id'), ['policy_id'], unique=False)

    op.create_table(
        'alarm_assignments',
        sa.Column('alarm_id', sa.Uuid(), nullable=False),
        sa.Column('tier', sa.Integer(), nullable=False),
        sa.Column('target_user_id', sa.Uuid(), nullable=True),
        sa.Column('target_role', sa.String(length=16), nullable=True),
        sa.Column('outcome', sa.String(length=16), nullable=False),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['alarm_id'], ['alarms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('alarm_assignments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alarm_assignments_alarm_id'), ['alarm_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alarm_assignments_target_user_id'), ['target_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alarm_assignments_outcome'), ['outcome'], unique=False)
        batch_op.create_index(batch_op.f('ix_alarm_assignments_expires_at'), ['expires_at'], unique=False)

    # Exactly one PENDING (actionable) assignment per alarm at a time — this
    # is what makes escalation and concurrent accept/decline race-safe at the
    # database level, not just in application code. Partial unique index,
    # supported by both SQLite and PostgreSQL.
    op.create_index(
        'uq_alarm_assignments_one_pending',
        'alarm_assignments',
        ['alarm_id'],
        unique=True,
        sqlite_where=sa.text("outcome = 'pending'"),
        postgresql_where=sa.text("outcome = 'pending'"),
    )

    op.create_table(
        'alarm_events',
        sa.Column('alarm_id', sa.Uuid(), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), nullable=True),
        sa.Column('message', sa.String(length=1024), nullable=True),
        sa.Column('event_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['alarm_id'], ['alarms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('alarm_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alarm_events_alarm_id'), ['alarm_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alarm_events_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_alarm_events_created_at'), ['created_at'], unique=False)

    op.create_table(
        'device_tokens',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('fcm_token', sa.String(length=512), nullable=False),
        sa.Column('platform', sa.String(length=16), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fcm_token'),
    )
    with op.batch_alter_table('device_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_device_tokens_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_device_tokens_fcm_token'), ['fcm_token'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('device_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_device_tokens_fcm_token'))
        batch_op.drop_index(batch_op.f('ix_device_tokens_user_id'))
    op.drop_table('device_tokens')

    with op.batch_alter_table('alarm_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alarm_events_created_at'))
        batch_op.drop_index(batch_op.f('ix_alarm_events_event_type'))
        batch_op.drop_index(batch_op.f('ix_alarm_events_alarm_id'))
    op.drop_table('alarm_events')

    op.drop_index('uq_alarm_assignments_one_pending', table_name='alarm_assignments')
    with op.batch_alter_table('alarm_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alarm_assignments_expires_at'))
        batch_op.drop_index(batch_op.f('ix_alarm_assignments_outcome'))
        batch_op.drop_index(batch_op.f('ix_alarm_assignments_target_user_id'))
        batch_op.drop_index(batch_op.f('ix_alarm_assignments_alarm_id'))
    op.drop_table('alarm_assignments')

    with op.batch_alter_table('escalation_tiers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_escalation_tiers_policy_id'))
    op.drop_table('escalation_tiers')

    with op.batch_alter_table('escalation_policies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_escalation_policies_object_id'))
    op.drop_table('escalation_policies')

    with op.batch_alter_table('alarms', schema=None) as batch_op:
        batch_op.drop_column('en_route_at')
