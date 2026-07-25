"""Database models.

Money is stored as integer cents everywhere. Never floats — floating-point
arithmetic on currency drifts by fractions of a cent and compounds across the
line items of a bill.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Person(Base):
    """The reusable directory of names, so recurring people aren't retyped."""

    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    participants: Mapped[list[EventParticipant]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventParticipant.id",
    )
    bills: Mapped[list[Bill]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="Bill.position, Bill.id",
    )


class EventParticipant(Base):
    """This event's roster. Assignments and payers reference a participant, not
    a person, so the database itself prevents assigning an item to somebody who
    is not on the event."""

    __tablename__ = "event_participants"
    __table_args__ = (UniqueConstraint("event_id", "person_id", name="uq_event_person"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    event: Mapped[Event] = relationship(back_populates="participants")
    person: Mapped[Person] = relationship()


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bill_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    payer_id: Mapped[int | None] = mapped_column(
        ForeignKey("event_participants.id", ondelete="SET NULL"), nullable=True
    )

    tax_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tip_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fee_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    source_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    extraction_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual"
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_total_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped[Event] = relationship(back_populates="bills")
    payer: Mapped[EventParticipant | None] = relationship()
    items: Mapped[list[LineItem]] = relationship(
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="LineItem.position, LineItem.id",
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(
        ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    bill: Mapped[Bill] = relationship(back_populates="items")
    assignments: Mapped[list[ItemAssignment]] = relationship(
        back_populates="line_item",
        cascade="all, delete-orphan",
        order_by="ItemAssignment.id",
    )


class ItemAssignment(Base):
    __tablename__ = "item_assignments"
    __table_args__ = (
        UniqueConstraint("line_item_id", "event_participant_id", name="uq_item_participant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_item_id: Mapped[int] = mapped_column(
        ForeignKey("line_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_participant_id: Mapped[int] = mapped_column(
        ForeignKey("event_participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Always 1 in v1. Exists so "Alice counts as 2 shares" is possible later
    # without a migration.
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    line_item: Mapped[LineItem] = relationship(back_populates="assignments")
    participant: Mapped[EventParticipant] = relationship()
