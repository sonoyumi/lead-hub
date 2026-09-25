"""Initial schema: managers, leads, lead_events

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

LEAD_STATUS = sa.Enum("new", "in_progress", "won", "lost", name="leadstatus", native_enum=False, length=20)


def upgrade() -> None:
    op.create_table(
        "managers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("telegram_chat_id", sa.String(32), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("status", LEAD_STATUS, nullable=False),
        sa.Column("manager_id", sa.Integer(), sa.ForeignKey("managers.id"), nullable=True),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_leads_status_created", "leads", ["status", "created_at"])
    op.create_index("ix_leads_phone", "leads", ["phone"])
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_table(
        "lead_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lead_events_lead_id", "lead_events", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_events_lead_id", table_name="lead_events")
    op.drop_table("lead_events")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_index("ix_leads_phone", table_name="leads")
    op.drop_index("ix_leads_status_created", table_name="leads")
    op.drop_table("leads")
    op.drop_table("managers")
