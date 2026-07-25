"""Glue between the ORM and the pure splitting functions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import models, schemas
from .splitting import BillInput, ItemInput, compute_event


def load_event(db: Session, event_id: int) -> models.Event | None:
    stmt = (
        select(models.Event)
        .where(models.Event.id == event_id)
        .options(
            selectinload(models.Event.participants),
            selectinload(models.Event.bills)
            .selectinload(models.Bill.items)
            .selectinload(models.LineItem.assignments),
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def to_bill_inputs(event: models.Event) -> list[BillInput]:
    participant_ids = tuple(p.id for p in event.participants)
    return [
        BillInput(
            id=bill.id,
            label=bill.label,
            participant_ids=participant_ids,
            items=tuple(
                ItemInput(
                    id=item.id,
                    name=item.name,
                    total_cents=item.total_cents,
                    assignments={a.event_participant_id: a.weight for a in item.assignments},
                )
                for item in bill.items
            ),
            tax_cents=bill.tax_cents,
            tip_cents=bill.tip_cents,
            fee_cents=bill.fee_cents,
            discount_cents=bill.discount_cents,
            payer_id=bill.payer_id,
        )
        for bill in event.bills
    ]


def compute_totals(event: models.Event) -> schemas.EventTotalsOut:
    breakdown = compute_event(to_bill_inputs(event))

    return schemas.EventTotalsOut(
        grand_total_cents=breakdown.grand_total_cents,
        is_complete=breakdown.is_complete,
        totals_cents=breakdown.totals_cents,
        paid_cents=breakdown.paid_cents,
        net_cents=breakdown.net_cents,
        debts=[
            schemas.DebtOut(
                from_participant_id=d.from_participant_id,
                to_participant_id=d.to_participant_id,
                amount_cents=d.amount_cents,
            )
            for d in breakdown.debts
        ],
        bills=[
            schemas.BillBreakdownOut(
                bill_id=b.bill_id,
                label=b.label,
                items_total_cents=b.items_total_cents,
                grand_total_cents=b.grand_total_cents,
                payer_id=b.payer_id,
                is_complete=b.is_complete,
                unassigned_item_ids=b.unassigned_item_ids,
                shares=[
                    schemas.ShareOut(
                        participant_id=s.participant_id,
                        subtotal_cents=s.subtotal_cents,
                        tax_cents=s.tax_cents,
                        tip_cents=s.tip_cents,
                        fee_cents=s.fee_cents,
                        discount_cents=s.discount_cents,
                        total_cents=s.total_cents,
                    )
                    for s in sorted(b.shares.values(), key=lambda s: s.participant_id)
                ],
                item_shares=b.item_shares,
            )
            for b in breakdown.bills
        ],
    )


def serialize_item(item: models.LineItem) -> schemas.ItemOut:
    return schemas.ItemOut(
        id=item.id,
        name=item.name,
        quantity=item.quantity,
        unit_price_cents=item.unit_price_cents,
        total_cents=item.total_cents,
        position=item.position,
        participant_ids=sorted(a.event_participant_id for a in item.assignments),
    )


def serialize_bill(bill: models.Bill) -> schemas.BillOut:
    return schemas.BillOut(
        id=bill.id,
        label=bill.label,
        merchant=bill.merchant,
        bill_date=bill.bill_date,
        position=bill.position,
        payer_id=bill.payer_id,
        tax_cents=bill.tax_cents,
        tip_cents=bill.tip_cents,
        fee_cents=bill.fee_cents,
        discount_cents=bill.discount_cents,
        source_filename=bill.source_filename,
        source_type=bill.source_type,
        extraction_status=bill.extraction_status,
        extraction_error=bill.extraction_error,
        extracted_total_cents=bill.extracted_total_cents,
        items=[serialize_item(i) for i in bill.items],
    )


def serialize_participant(p: models.EventParticipant) -> schemas.ParticipantOut:
    return schemas.ParticipantOut(
        id=p.id,
        person_id=p.person_id,
        display_name=p.display_name,
        is_owner=bool(p.person and p.person.is_owner),
    )


def serialize_event(event: models.Event, include_totals: bool = True) -> schemas.EventOut:
    return schemas.EventOut(
        id=event.id,
        name=event.name,
        notes=event.notes,
        created_at=event.created_at,
        participants=[serialize_participant(p) for p in event.participants],
        bills=[serialize_bill(b) for b in event.bills],
        totals=compute_totals(event) if include_totals else None,
    )


def next_bill_label(event: models.Event) -> str:
    return f"Bill {len(event.bills) + 1}"


def default_payer_id(event: models.Event) -> int | None:
    """The owner, if they are on this event's roster — otherwise the first
    participant. Payer is always editable afterwards."""
    for p in event.participants:
        if p.person and p.person.is_owner:
            return p.id
    return event.participants[0].id if event.participants else None
