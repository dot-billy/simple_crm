import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import log_mutation
from app.auth import get_current_user, require_scope
from app.database import get_db
from app.models import Activity, AuditEventType, Company, Contact, CustomFieldDefinition, CustomFieldValue, Deal, DealStage, Tag, Task, TaskStatus, User, UserRole, contact_tags
from app.schemas import BulkAction, ContactCreate, ContactProfile, ContactRead, ContactStats, ContactUpdate, CompanyRead, CustomFieldDefinitionRead, CustomFieldValueRead, DealRead, TaskRead

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


SORTABLE_COLUMNS = {
    "first_name": Contact.first_name,
    "last_name": Contact.last_name,
    "email": Contact.email,
    "job_title": Contact.job_title,
    "created_at": Contact.created_at,
}


def _apply_ownership_filter(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Contact.owner_id == user.id)
    return query


@router.get("", response_model=dict)
async def list_contacts(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    search: str = Query(""),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    tag_id: str = Query(""),
    source: str = Query(""),
    include_custom_fields: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:read")),
):
    query = select(Contact).options(selectinload(Contact.tags))
    query = _apply_ownership_filter(query, current_user)

    if search:
        query = query.where(
            (Contact.first_name.ilike(f"%{search}%"))
            | (Contact.last_name.ilike(f"%{search}%"))
            | (Contact.email.ilike(f"%{search}%"))
        )

    if tag_id:
        query = query.join(contact_tags).where(contact_tags.c.tag_id == tag_id)

    if source:
        query = query.where(Contact.source == source)

    # Custom field filters: ?cf_<field_id>=value matches CustomFieldValue.value
    cf_filters = {k[3:]: v for k, v in request.query_params.items() if k.startswith("cf_") and v}
    for field_id, val in cf_filters.items():
        try:
            fid = UUID(field_id)
        except ValueError:
            continue
        sub = (
            select(CustomFieldValue.contact_id)
            .where(CustomFieldValue.field_id == fid, CustomFieldValue.value.ilike(f"%{val}%"))
        )
        query = query.where(Contact.id.in_(sub))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    col = SORTABLE_COLUMNS.get(sort_by, Contact.created_at)
    order = col.asc().nullslast() if sort_dir == "asc" else col.desc().nullslast()
    query = query.order_by(order).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    items_data = [ContactRead.model_validate(c).model_dump(mode="json") for c in items]
    if include_custom_fields and items:
        ids = [c.id for c in items]
        cfvs = (await db.execute(select(CustomFieldValue).where(CustomFieldValue.contact_id.in_(ids)))).scalars().all()
        by_contact: dict = {}
        for v in cfvs:
            by_contact.setdefault(str(v.contact_id), []).append({
                "field_id": str(v.field_id), "value": v.value,
            })
        for d in items_data:
            d["custom_fields"] = by_contact.get(d["id"], [])

    return {
        "items": items_data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/sources", response_model=list[str])
async def list_contact_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:read")),
):
    query = select(Contact.source).where(Contact.source.isnot(None), Contact.source != "")
    query = _apply_ownership_filter(query, current_user)
    query = query.distinct().order_by(Contact.source)
    result = await db.execute(query)
    return [row[0] for row in result.all()]


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:read")),
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
    current_user: User = Depends(require_scope("contacts:write")),
):
    contact = Contact(
        **data.model_dump(exclude={"tag_ids"}),
        owner_id=current_user.id,
    )
    if data.tag_ids:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        contact.tags = list(tags)
    db.add(contact)
    await db.flush()
    log_mutation(db, event_type=AuditEventType.CONTACT_CREATED, user=current_user, entity_type="contact", entity_id=contact.id, after=contact)
    await db.commit()
    refreshed = await db.execute(select(Contact).options(selectinload(Contact.tags)).where(Contact.id == contact.id))
    return refreshed.scalar_one()


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:write")),
):
    query = select(Contact).options(selectinload(Contact.tags)).where(Contact.id == contact_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    before_snapshot = {c.name: getattr(contact, c.name) for c in contact.__table__.columns}

    update_data = data.model_dump(exclude_unset=True, exclude={"tag_ids"})
    for field, value in update_data.items():
        setattr(contact, field, value)

    if data.tag_ids is not None:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        contact.tags = list(tags)

    log_mutation(db, event_type=AuditEventType.CONTACT_UPDATED, user=current_user, entity_type="contact", entity_id=contact.id, before=before_snapshot, after=contact)
    await db.commit()
    refreshed = await db.execute(select(Contact).options(selectinload(Contact.tags)).where(Contact.id == contact.id))
    return refreshed.scalar_one()


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:write")),
):
    query = select(Contact).where(Contact.id == contact_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    before_snapshot = {c.name: getattr(contact, c.name) for c in contact.__table__.columns}
    contact_id_copy = contact.id
    await db.delete(contact)
    log_mutation(db, event_type=AuditEventType.CONTACT_DELETED, user=current_user, entity_type="contact", entity_id=contact_id_copy, before=before_snapshot)
    await db.commit()
    return {"ok": True}


@router.post("/bulk")
async def bulk_contacts(
    data: BulkAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:write")),
):
    query = select(Contact).options(selectinload(Contact.tags)).where(Contact.id.in_(data.ids))
    query = _apply_ownership_filter(query, current_user)
    contacts = (await db.execute(query)).scalars().all()
    affected = 0
    for c in contacts:
        before = {col.name: getattr(c, col.name) for col in c.__table__.columns}
        if data.action == "delete":
            cid = c.id
            await db.delete(c)
            log_mutation(db, event_type=AuditEventType.CONTACT_DELETED, user=current_user, entity_type="contact", entity_id=cid, before=before)
        elif data.action == "add_tag" and data.tag_id:
            tag = (await db.execute(select(Tag).where(Tag.id == data.tag_id))).scalar_one_or_none()
            if tag and tag not in c.tags:
                c.tags.append(tag)
                log_mutation(db, event_type=AuditEventType.CONTACT_UPDATED, user=current_user, entity_type="contact", entity_id=c.id, before=before, after=c)
        elif data.action == "remove_tag" and data.tag_id:
            c.tags = [t for t in c.tags if t.id != data.tag_id]
            log_mutation(db, event_type=AuditEventType.CONTACT_UPDATED, user=current_user, entity_type="contact", entity_id=c.id, before=before, after=c)
        elif data.action == "set_owner":
            c.owner_id = data.owner_id
            log_mutation(db, event_type=AuditEventType.CONTACT_UPDATED, user=current_user, entity_type="contact", entity_id=c.id, before=before, after=c)
        else:
            continue
        affected += 1
    await db.commit()
    return {"affected": affected}


@router.get("/{contact_id}/profile", response_model=ContactProfile)
async def get_contact_profile(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:read")),
):
    query = (
        select(Contact)
        .options(
            selectinload(Contact.tags),
            selectinload(Contact.company).selectinload(Company.tags),
            selectinload(Contact.deals).selectinload(Deal.tags),
            selectinload(Contact.tasks),
            selectinload(Contact.custom_field_values),
        )
        .where(Contact.id == contact_id)
    )
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Custom field definitions for contacts
    defs_result = await db.execute(
        select(CustomFieldDefinition).where(CustomFieldDefinition.entity_type == "contact").order_by(CustomFieldDefinition.name)
    )
    definitions = defs_result.scalars().all()

    # Compute stats
    closed_stages = {DealStage.CLOSED_WON, DealStage.CLOSED_LOST}
    deals = contact.deals or []
    tasks = contact.tasks or []

    # Last activity date
    last_act_q = select(func.max(Activity.activity_date)).where(Activity.contact_id == contact_id)
    last_activity_date = (await db.execute(last_act_q)).scalar()

    # Total activities count
    act_count_q = select(func.count()).select_from(Activity).where(Activity.contact_id == contact_id)
    total_activities = (await db.execute(act_count_q)).scalar() or 0

    stats = ContactStats(
        total_deals=len(deals),
        total_deal_value=sum(d.value or 0 for d in deals),
        open_deals=sum(1 for d in deals if d.stage not in closed_stages),
        won_deals=sum(1 for d in deals if d.stage == DealStage.CLOSED_WON),
        total_activities=total_activities,
        total_tasks=len(tasks),
        open_tasks=sum(1 for t in tasks if t.status != TaskStatus.DONE),
        last_activity_date=last_activity_date,
    )

    return ContactProfile(
        contact=ContactRead.model_validate(contact),
        company=CompanyRead.model_validate(contact.company) if contact.company else None,
        deals=[DealRead.model_validate(d) for d in deals],
        tasks=[TaskRead.model_validate(t) for t in tasks],
        custom_fields=[CustomFieldValueRead.model_validate(v) for v in (contact.custom_field_values or [])],
        custom_field_definitions=[CustomFieldDefinitionRead.model_validate(d) for d in definitions],
        stats=stats,
    )


@router.get("/export/csv")
async def export_contacts_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:read")),
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


def _sanitize_csv_value(val: str | None) -> str | None:
    if not val:
        return val
    return val.lstrip("=+-@")


@router.post("/import/csv")
async def import_contacts_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("contacts:write")),
):
    MAX_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_ROWS = 10000
    raw = await file.read(MAX_SIZE + 1)
    if len(raw) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")
    content = raw.decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    count = 0
    for row in reader:
        if count >= MAX_ROWS:
            break
        contact = Contact(
            first_name=_sanitize_csv_value(row.get("first_name", "")) or "",
            last_name=_sanitize_csv_value(row.get("last_name", "")) or "",
            email=_sanitize_csv_value(row.get("email")),
            phone=_sanitize_csv_value(row.get("phone")),
            job_title=_sanitize_csv_value(row.get("job_title")),
            source=_sanitize_csv_value(row.get("source")),
            notes=_sanitize_csv_value(row.get("notes")),
            owner_id=current_user.id,
        )
        db.add(contact)
        count += 1
    await db.commit()
    return {"imported": count}
