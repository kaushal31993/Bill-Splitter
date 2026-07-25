from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/api/people", tags=["people"])


def find_or_create_person(db: Session, name: str) -> models.Person:
    """Reuse an existing directory entry when the name matches, so the fifth
    event with the same people does not create five duplicate Person rows."""
    existing = db.execute(
        select(models.Person).where(
            func.lower(models.Person.name) == name.lower(),
            models.Person.archived.is_(False),
        )
    ).scalars().first()
    if existing:
        return existing
    person = models.Person(name=name)
    db.add(person)
    db.flush()
    return person


@router.get("", response_model=list[schemas.PersonOut])
def list_people(db: Session = Depends(get_db)):
    return db.execute(
        select(models.Person)
        .where(models.Person.archived.is_(False))
        .order_by(models.Person.is_owner.desc(), models.Person.name)
    ).scalars().all()


@router.post("", response_model=schemas.PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(payload: schemas.PersonCreate, db: Session = Depends(get_db)):
    person = find_or_create_person(db, payload.name)
    if payload.is_owner:
        # Exactly one owner. Promoting a new one demotes the old.
        db.execute(
            select(models.Person).where(models.Person.is_owner.is_(True))
        )
        for other in db.execute(
            select(models.Person).where(models.Person.is_owner.is_(True))
        ).scalars():
            other.is_owner = False
        person.is_owner = True
    db.commit()
    db.refresh(person)
    return person


@router.get("/owner", response_model=schemas.PersonOut)
def get_owner(db: Session = Depends(get_db)):
    owner = db.execute(
        select(models.Person).where(models.Person.is_owner.is_(True))
    ).scalars().first()
    if owner is None:
        raise HTTPException(status_code=404, detail="No owner set yet.")
    return owner
