import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import Contact, Tag, User, UserRole
from app.schemas import ContactCreate, ContactRead, ContactUpdate

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


def _apply_ownership_filter(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Contact.owner_id == user.id)
    return query


@router.get("", response_model=dict)
async def list_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Contact).options(selectinload(Contact.tags))
    query = _apply_ownership_filter(query, current_user)

    if search:
        query = query.where(
            (Contact.first_name.ilike(f"%{search}%"))
            | (Contact.last_name.ilike(f"%{search}%"))
            | (Contact.email.ilike(f"%{search}%"))
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Contact.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [ContactRead.model_validate(c) for c in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Contact).options(selectinload(Contact.tags)).where(Contact.id == contact_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.post("", response_model=ContactRead)
async def create_contact(
    data: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = Contact(
        **data.model_dump(exclude={"tag_ids"}),
        owner_id=current_user.id,
    )
    if data.tag_ids:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        contact.tags = list(tags)
    db.add(contact)
    await db.commit()
    await db.refresh(contact, ["tags"])
    return contact


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Contact).options(selectinload(Contact.tags)).where(Contact.id == contact_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    update_data = data.model_dump(exclude_unset=True, exclude={"tag_ids"})
    for field, value in update_data.items():
        setattr(contact, field, value)

    if data.tag_ids is not None:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        contact.tags = list(tags)

    await db.commit()
    await db.refresh(contact, ["tags"])
    return contact


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Contact).where(Contact.id == contact_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()
    return {"ok": True}


@router.get("/export/csv")
async def export_contacts_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Contact)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query.order_by(Contact.created_at.desc()))
    contacts = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["first_name", "last_name", "email", "phone", "job_title", "source", "notes"])
    for c in contacts:
        writer.writerow([c.first_name, c.last_name, c.email, c.phone, c.job_title, c.source, c.notes])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.post("/import/csv")
async def import_contacts_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    count = 0
    for row in reader:
        contact = Contact(
            first_name=row.get("first_name", ""),
            last_name=row.get("last_name", ""),
            email=row.get("email"),
            phone=row.get("phone"),
            job_title=row.get("job_title"),
            source=row.get("source"),
            notes=row.get("notes"),
            owner_id=current_user.id,
        )
        db.add(contact)
        count += 1
    await db.commit()
    return {"imported": count}
