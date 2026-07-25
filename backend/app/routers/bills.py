from __future__ import annotations

import logging
import os
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..config import get_settings
from ..db import get_db
from ..extraction import ExtractionError, extract_receipt

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bills"])


def _bill_or_404(db: Session, bill_id: int) -> models.Bill:
    bill = db.get(models.Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    return bill


def _item_or_404(db: Session, item_id: int) -> models.LineItem:
    item = db.get(models.LineItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    return item


def _event_or_404(db: Session, event_id: int) -> models.Event:
    event = services.load_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return event


def _reload(db: Session, bill_id: int) -> schemas.BillOut:
    db.expire_all()
    return services.serialize_bill(_bill_or_404(db, bill_id))


def _valid_participant_ids(db: Session, event_id: int, ids: list[int]) -> list[int]:
    """Reject any participant that is not on this event's roster, rather than
    silently dropping them — a wrong id is a bug in the caller, not a no-op."""
    if not ids:
        return []
    unique = list(dict.fromkeys(ids))
    rows = db.execute(
        select(models.EventParticipant.id).where(
            models.EventParticipant.event_id == event_id,
            models.EventParticipant.id.in_(unique),
        )
    ).scalars().all()
    missing = set(unique) - set(rows)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Not on this event's roster: {sorted(missing)}",
        )
    return unique


# ---------------------------------------------------------------------- bills


@router.post(
    "/events/{event_id}/bills",
    response_model=schemas.BillOut,
    status_code=status.HTTP_201_CREATED,
)
def create_bill(event_id: int, payload: schemas.BillCreate, db: Session = Depends(get_db)):
    event = _event_or_404(db, event_id)
    bill = models.Bill(
        event_id=event.id,
        label=(payload.label or services.next_bill_label(event)),
        merchant=payload.merchant,
        bill_date=payload.bill_date,
        position=len(event.bills),
        payer_id=services.default_payer_id(event),
        source_type="manual",
        extraction_status="manual",
    )
    db.add(bill)
    db.commit()
    return _reload(db, bill.id)


@router.post(
    "/events/{event_id}/bills/upload",
    response_model=schemas.BillOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_bill(
    event_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    settings = get_settings()
    event = _event_or_404(db, event_id)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than the {settings.max_upload_mb} MB limit.",
        )

    original = os.path.basename(file.filename or "receipt")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", original)[:120] or "receipt"

    stored_name = f"{uuid.uuid4().hex}_{safe}"
    stored_path = os.path.join(settings.upload_dir, stored_name)
    try:
        os.makedirs(settings.upload_dir, exist_ok=True)
        with open(stored_path, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not save the upload to {settings.upload_dir}: {exc.strerror}. "
                "Check that the uploads volume is mounted and writable."
            ),
        ) from exc

    bill = models.Bill(
        event_id=event.id,
        label=services.next_bill_label(event),
        position=len(event.bills),
        payer_id=services.default_payer_id(event),
        source_filename=original,
        source_path=stored_path,
        source_type="pdf" if safe.lower().endswith(".pdf") else "image",
        extraction_status="pending",
    )
    db.add(bill)
    db.flush()

    # Extraction failure must never lose the upload. The bill is committed
    # either way; the user falls back to manual entry.
    try:
        receipt = extract_receipt(data, original)
    except ExtractionError as exc:
        bill.extraction_status = "failed"
        bill.extraction_error = str(exc)
        db.commit()
        return _reload(db, bill.id)
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("Unexpected extraction failure")
        bill.extraction_status = "failed"
        bill.extraction_error = f"Unexpected extraction error: {exc}"
        db.commit()
        return _reload(db, bill.id)

    bill.merchant = receipt.merchant
    bill.bill_date = receipt.bill_date
    bill.tax_cents = receipt.tax_cents
    bill.tip_cents = receipt.tip_cents
    bill.fee_cents = receipt.fee_cents
    bill.discount_cents = receipt.discount_cents
    bill.extracted_total_cents = receipt.total_cents or None
    bill.extraction_status = "ok"
    if receipt.merchant:
        bill.label = f"{services.next_bill_label(event)} — {receipt.merchant}"[:120]

    for position, item in enumerate(receipt.items):
        db.add(
            models.LineItem(
                bill_id=bill.id,
                name=item.name,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                total_cents=item.total_cents,
                position=position,
            )
        )

    db.commit()
    return _reload(db, bill.id)


@router.get("/bills/{bill_id}/source")
def get_bill_source(bill_id: int, db: Session = Depends(get_db)):
    bill = _bill_or_404(db, bill_id)
    if not bill.source_path or not os.path.exists(bill.source_path):
        raise HTTPException(status_code=404, detail="No uploaded file for this bill.")
    return FileResponse(bill.source_path, filename=bill.source_filename or "receipt")


@router.patch("/bills/{bill_id}", response_model=schemas.BillOut)
def update_bill(bill_id: int, payload: schemas.BillUpdate, db: Session = Depends(get_db)):
    bill = _bill_or_404(db, bill_id)
    data = payload.model_dump(exclude_unset=True)

    if "payer_id" in data and data["payer_id"] is not None:
        _valid_participant_ids(db, bill.event_id, [data["payer_id"]])

    for field, value in data.items():
        if field == "label" and value is not None:
            value = value.strip() or bill.label
        setattr(bill, field, value)

    db.commit()
    return _reload(db, bill.id)


@router.delete("/bills/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bill(bill_id: int, db: Session = Depends(get_db)):
    bill = _bill_or_404(db, bill_id)
    path = bill.source_path
    db.delete(bill)
    db.commit()
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:  # pragma: no cover
            log.warning("Could not remove upload %s", path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------- items


@router.post(
    "/bills/{bill_id}/items",
    response_model=schemas.ItemOut,
    status_code=status.HTTP_201_CREATED,
)
def create_item(bill_id: int, payload: schemas.ItemIn, db: Session = Depends(get_db)):
    bill = _bill_or_404(db, bill_id)
    item = models.LineItem(
        bill_id=bill.id,
        name=payload.name.strip(),
        quantity=payload.quantity,
        unit_price_cents=payload.unit_price_cents,
        total_cents=payload.resolved_total(),
        position=len(bill.items),
    )
    db.add(item)
    db.flush()

    for pid in _valid_participant_ids(db, bill.event_id, payload.participant_ids or []):
        db.add(models.ItemAssignment(line_item_id=item.id, event_participant_id=pid))

    db.commit()
    db.refresh(item)
    return services.serialize_item(item)


@router.patch("/items/{item_id}", response_model=schemas.ItemOut)
def update_item(item_id: int, payload: schemas.ItemIn, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data:
        item.name = (data["name"] or "").strip()
    if "quantity" in data:
        item.quantity = data["quantity"]
    if "unit_price_cents" in data:
        item.unit_price_cents = data["unit_price_cents"]
    if "total_cents" in data and data["total_cents"] is not None:
        item.total_cents = data["total_cents"]
    elif {"quantity", "unit_price_cents"} & set(data):
        item.total_cents = item.unit_price_cents * item.quantity

    if "participant_ids" in data and data["participant_ids"] is not None:
        _replace_assignments(db, item, data["participant_ids"])

    db.commit()
    db.refresh(item)
    return services.serialize_item(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ assignment


def _replace_assignments(db: Session, item: models.LineItem, participant_ids: list[int]) -> None:
    valid = _valid_participant_ids(db, item.bill.event_id, participant_ids)
    for existing in list(item.assignments):
        db.delete(existing)
    db.flush()
    for pid in valid:
        db.add(models.ItemAssignment(line_item_id=item.id, event_participant_id=pid))
    db.flush()


@router.put("/items/{item_id}/assignments", response_model=schemas.ItemOut)
def set_assignments(item_id: int, payload: schemas.AssignmentsIn, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id)
    _replace_assignments(db, item, payload.participant_ids)
    db.commit()
    db.refresh(item)
    return services.serialize_item(item)


@router.post("/bills/{bill_id}/assign", response_model=schemas.BillOut)
def bulk_assign(bill_id: int, payload: schemas.BulkAssignIn, db: Session = Depends(get_db)):
    """Assign the same people to every item on a bill.

    This is the common path: most items are shared by everyone, and the user
    then adjusts the handful of exceptions.
    """
    bill = _bill_or_404(db, bill_id)
    valid = _valid_participant_ids(db, bill.event_id, payload.participant_ids)

    for item in bill.items:
        if payload.only_unassigned and item.assignments:
            continue
        _replace_assignments(db, item, valid)

    db.commit()
    return _reload(db, bill.id)
