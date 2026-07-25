import datetime as dt
import re
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import excel, models, schemas, services
from ..db import get_db
from .people import find_or_create_person

router = APIRouter(prefix="/api/events", tags=["events"])


def event_or_404(db: Session, event_id: int) -> models.Event:
    event = services.load_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return event


@router.get("", response_model=list[schemas.EventSummaryOut])
def list_events(db: Session = Depends(get_db)):
    events = db.execute(
        select(models.Event).order_by(models.Event.created_at.desc(), models.Event.id.desc())
    ).scalars().all()

    out: list[schemas.EventSummaryOut] = []
    for e in events:
        full = services.load_event(db, e.id)
        totals = services.compute_totals(full)
        out.append(
            schemas.EventSummaryOut(
                id=full.id,
                name=full.name,
                created_at=full.created_at,
                bill_count=len(full.bills),
                participant_count=len(full.participants),
                grand_total_cents=totals.grand_total_cents,
            )
        )
    return out


@router.post("", response_model=schemas.EventOut, status_code=status.HTTP_201_CREATED)
def create_event(payload: schemas.EventCreate, db: Session = Depends(get_db)):
    event = models.Event(name=payload.name, notes=payload.notes)
    db.add(event)
    db.flush()

    # The owner is on every event's roster by default — they are the one using
    # the app, and the default payer.
    owner = db.execute(
        select(models.Person).where(models.Person.is_owner.is_(True))
    ).scalars().first()
    if owner is not None:
        db.add(
            models.EventParticipant(
                event_id=event.id, person_id=owner.id, display_name=owner.name
            )
        )

    db.commit()
    return services.serialize_event(event_or_404(db, event.id))


@router.get("/{event_id}", response_model=schemas.EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    return services.serialize_event(event_or_404(db, event_id))


@router.patch("/{event_id}", response_model=schemas.EventOut)
def update_event(event_id: int, payload: schemas.EventUpdate, db: Session = Depends(get_db)):
    event = event_or_404(db, event_id)
    if payload.name is not None:
        event.name = payload.name.strip() or event.name
    if payload.notes is not None:
        event.notes = payload.notes
    db.commit()
    return services.serialize_event(event_or_404(db, event_id))


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = event_or_404(db, event_id)
    db.delete(event)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{event_id}/totals", response_model=schemas.EventTotalsOut)
def get_totals(event_id: int, db: Session = Depends(get_db)):
    return services.compute_totals(event_or_404(db, event_id))


# --------------------------------------------------------------------- roster


@router.post(
    "/{event_id}/participants",
    response_model=schemas.ParticipantOut,
    status_code=status.HTTP_201_CREATED,
)
def add_participant(
    event_id: int, payload: schemas.ParticipantCreate, db: Session = Depends(get_db)
):
    event = event_or_404(db, event_id)

    if payload.person_id is not None:
        person = db.get(models.Person, payload.person_id)
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found.")
    elif payload.name:
        person = find_or_create_person(db, payload.name)
    else:
        raise HTTPException(status_code=422, detail="Provide a name or a person_id.")

    if any(p.person_id == person.id for p in event.participants):
        raise HTTPException(
            status_code=409, detail=f"{person.name} is already on this event."
        )

    participant = models.EventParticipant(
        event_id=event.id, person_id=person.id, display_name=person.name
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return services.serialize_participant(participant)


@router.patch(
    "/{event_id}/participants/{participant_id}", response_model=schemas.ParticipantOut
)
def rename_participant(
    event_id: int,
    participant_id: int,
    payload: schemas.ParticipantUpdate,
    db: Session = Depends(get_db),
):
    participant = db.get(models.EventParticipant, participant_id)
    if participant is None or participant.event_id != event_id:
        raise HTTPException(status_code=404, detail="Participant not found on this event.")
    participant.display_name = payload.display_name.strip()
    db.commit()
    db.refresh(participant)
    return services.serialize_participant(participant)


@router.delete(
    "/{event_id}/participants/{participant_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_participant(event_id: int, participant_id: int, db: Session = Depends(get_db)):
    participant = db.get(models.EventParticipant, participant_id)
    if participant is None or participant.event_id != event_id:
        raise HTTPException(status_code=404, detail="Participant not found on this event.")

    # Removing someone who still has items assigned would silently change every
    # total on the event. Block it and say what needs to happen instead.
    assigned = db.execute(
        select(func.count())
        .select_from(models.ItemAssignment)
        .where(models.ItemAssignment.event_participant_id == participant_id)
    ).scalar_one()
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{participant.display_name} is assigned to {assigned} "
                f"item{'s' if assigned != 1 else ''}. Reassign those items first."
            ),
        )

    paying = db.execute(
        select(func.count())
        .select_from(models.Bill)
        .where(models.Bill.payer_id == participant_id)
    ).scalar_one()
    if paying:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{participant.display_name} is the payer on {paying} "
                f"bill{'s' if paying != 1 else ''}. Change the payer first."
            ),
        )

    db.delete(participant)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------- export


@router.get("/{event_id}/export.xlsx")
def export_event(event_id: int, db: Session = Depends(get_db)):
    event = event_or_404(db, event_id)
    totals = services.compute_totals(event)
    payload = excel.build_workbook(event, totals)

    slug = re.sub(r"[^A-Za-z0-9]+", "-", event.name).strip("-").lower() or "event"
    filename = f"{slug}-{dt.date.today().strftime('%m-%d-%Y')}.xlsx"
    quoted = urllib.parse.quote(filename)

    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quoted}"
        },
    )
