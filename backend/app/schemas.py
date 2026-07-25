"""Request/response schemas.

All money crosses the wire as integer cents (fields ending in ``_cents``).
Formatting to "$1,234.56" happens in the UI. This keeps floats out of the
transport layer entirely.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_CENTS = 1_000_000_000  # $10,000,000 — a sanity ceiling, not a business rule


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- people


class PersonOut(ORMModel):
    id: int
    name: str
    is_owner: bool


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_owner: bool = False

    @field_validator("name")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v


# --------------------------------------------------------------- event participants


class ParticipantOut(ORMModel):
    id: int
    person_id: int
    display_name: str
    is_owner: bool = False


class ParticipantCreate(BaseModel):
    """Either name a new person or attach an existing one from the directory."""

    name: str | None = Field(default=None, max_length=120)
    person_id: int | None = None

    @field_validator("name")
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class ParticipantUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


# ----------------------------------------------------------------------- line items


class ItemIn(BaseModel):
    name: str = Field(default="", max_length=300)
    quantity: int = Field(default=1, ge=1, le=10_000)
    unit_price_cents: int = Field(default=0, ge=-MAX_CENTS, le=MAX_CENTS)
    total_cents: int | None = Field(default=None, ge=-MAX_CENTS, le=MAX_CENTS)
    participant_ids: list[int] | None = None

    def resolved_total(self) -> int:
        if self.total_cents is not None:
            return self.total_cents
        return self.unit_price_cents * self.quantity


class ItemOut(ORMModel):
    id: int
    name: str
    quantity: int
    unit_price_cents: int
    total_cents: int
    position: int
    participant_ids: list[int] = []


class AssignmentsIn(BaseModel):
    participant_ids: list[int] = Field(default_factory=list)


class BulkAssignIn(BaseModel):
    participant_ids: list[int] = Field(default_factory=list)
    only_unassigned: bool = False


# --------------------------------------------------------------------------- bills


class BillCreate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    merchant: str | None = Field(default=None, max_length=200)
    bill_date: dt.date | None = None


class BillUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    merchant: str | None = Field(default=None, max_length=200)
    bill_date: dt.date | None = None
    payer_id: int | None = None
    tax_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)
    tip_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)
    fee_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)
    discount_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)


class BillOut(ORMModel):
    id: int
    label: str
    merchant: str | None
    bill_date: dt.date | None
    position: int
    payer_id: int | None
    tax_cents: int
    tip_cents: int
    fee_cents: int
    discount_cents: int
    source_filename: str | None
    source_type: str
    extraction_status: str
    extraction_error: str | None
    extracted_total_cents: int | None
    items: list[ItemOut] = []


# ------------------------------------------------------------------------ breakdown


class ShareOut(BaseModel):
    participant_id: int
    subtotal_cents: int
    tax_cents: int
    tip_cents: int
    fee_cents: int
    discount_cents: int
    total_cents: int


class BillBreakdownOut(BaseModel):
    bill_id: int
    label: str
    items_total_cents: int
    grand_total_cents: int
    payer_id: int | None
    is_complete: bool
    unassigned_item_ids: list[int]
    shares: list[ShareOut]
    item_shares: dict[int, dict[int, int]]


class DebtOut(BaseModel):
    from_participant_id: int
    to_participant_id: int
    amount_cents: int


class EventTotalsOut(BaseModel):
    grand_total_cents: int
    is_complete: bool
    totals_cents: dict[int, int]
    paid_cents: dict[int, int]
    net_cents: dict[int, int]
    debts: list[DebtOut]
    bills: list[BillBreakdownOut]


# --------------------------------------------------------------------------- events


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v


class EventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None


class EventSummaryOut(ORMModel):
    id: int
    name: str
    created_at: dt.datetime
    bill_count: int = 0
    participant_count: int = 0
    grand_total_cents: int = 0


class EventOut(ORMModel):
    id: int
    name: str
    notes: str | None
    created_at: dt.datetime
    participants: list[ParticipantOut] = []
    bills: list[BillOut] = []
    totals: EventTotalsOut | None = None


class ConfigOut(BaseModel):
    extraction_enabled: bool
    max_upload_mb: int
    currency: str
