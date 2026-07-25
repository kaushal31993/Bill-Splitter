"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "event_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.UniqueConstraint("event_id", "person_id", name="uq_event_person"),
    )
    op.create_index("ix_event_participants_event_id", "event_participants", ["event_id"])

    op.create_table(
        "bills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("merchant", sa.String(200), nullable=True),
        sa.Column("bill_date", sa.Date(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "payer_id",
            sa.Integer(),
            sa.ForeignKey("event_participants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tax_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tip_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fee_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_filename", sa.String(300), nullable=True),
        sa.Column("source_path", sa.String(500), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("extraction_status", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("extracted_total_cents", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_bills_event_id", "bills", ["event_id"])

    op.create_table(
        "line_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "bill_id", sa.Integer(), sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_line_items_bill_id", "line_items", ["bill_id"])

    op.create_table(
        "item_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "line_item_id",
            sa.Integer(),
            sa.ForeignKey("line_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_participant_id",
            sa.Integer(),
            sa.ForeignKey("event_participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("line_item_id", "event_participant_id", name="uq_item_participant"),
    )
    op.create_index("ix_item_assignments_line_item_id", "item_assignments", ["line_item_id"])
    op.create_index(
        "ix_item_assignments_event_participant_id", "item_assignments", ["event_participant_id"]
    )


def downgrade() -> None:
    op.drop_table("item_assignments")
    op.drop_table("line_items")
    op.drop_table("bills")
    op.drop_table("event_participants")
    op.drop_table("events")
    op.drop_table("people")
