import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import log_mutation
from app.auth import get_current_user, require_role, require_scope
from app.database import get_db
from app.models import Activity, AuditEventType, Company, Contact, CustomFieldDefinition, CustomFieldValue, Deal, DealStage, Tag, User, UserRole, company_tags
from app.schemas import BulkAction, CompanyCreate, CompanyProfile, CompanyRead, CompanyStats, CompanyUpdate, ContactRead, CustomFieldDefinitionRead, CustomFieldValueRead, DealRead

router = APIRouter(prefix="/api/companies", tags=["companies"])


SORTABLE_COLUMNS = {
    "name": Company.name,
    "domain": Company.domain,
    "industry": Company.industry,
    "created_at": Company.created_at,
}


def _apply_ownership_filter(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Company.owner_id == user.id)
    return query


@router.get("", response_model=dict)
async def list_companies(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    search: str = Query(""),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    tag_id: str = Query(""),
    industry: str = Query(""),
    include_custom_fields: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("companies:read")),
):
    query = select(Company).options(selectinload(Company.tags))
    query = _apply_ownership_filter(query, current_user)
    if search:
        query = query.where(
            (Company.name.ilike(f"%{search}%")) | (Company.domain.ilike(f"%{search}%"))
        )
    if tag_id:
        query = query.join(company_tags).where(company_tags.c.tag_id == tag_id)
    if industry:
        query = query.where(Company.industry == industry)
    cf_filters = {k[3:]: v for k, v in request.query_params.items() if k.startswith("cf_") and v}
    for field_id, val in cf_filters.items():
        try:
            fid = UUID(field_id)
        except ValueError:
            continue
        sub = (
            select(CustomFieldValue.company_id)
            .where(CustomFieldValue.field_id == fid, CustomFieldValue.value.ilike(f"%{val}%"))
        )
        query = query.where(Company.id.in_(sub))
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    col = SORTABLE_COLUMNS.get(sort_by, Company.created_at)
    order = col.asc().nullslast() if sort_dir == "asc" else col.desc().nullslast()
    query = query.order_by(order).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()
    items_data = [CompanyRead.model_validate(c).model_dump(mode="json") for c in items]
    if include_custom_fields and items:
        ids = [c.id for c in items]
        cfvs = (await db.execute(select(CustomFieldValue).where(CustomFieldValue.company_id.in_(ids)))).scalars().all()
        by_company: dict = {}
        for v in cfvs:
            by_company.setdefault(str(v.company_id), []).append({
                "field_id": str(v.field_id), "value": v.value,
            })
        for d in items_data:
            d["custom_fields"] = by_company.get(d["id"], [])
    return {
        "items": items_data,
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/industries", response_model=list[str])
async def list_company_industries(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("companies:read")),
):
    query = select(Company.industry).where(Company.industry.isnot(None), Company.industry != "")
    query = _apply_ownership_filter(query, current_user)
    query = query.distinct().order_by(Company.industry)
    result = await db.execute(query)
    return [row[0] for row in result.all()]


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(company_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("companies:read"))):
    query = select(Company).options(selectinload(Company.tags)).where(Company.id == company_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.post("", response_model=CompanyRead)
async def create_company(data: CompanyCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("companies:write"))):
    company = Company(**data.model_dump(exclude={"tag_ids"}), owner_id=current_user.id)
    if data.tag_ids:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        company.tags = list(tags)
    db.add(company)
    await db.flush()
    log_mutation(db, event_type=AuditEventType.COMPANY_CREATED, user=current_user, entity_type="company", entity_id=company.id, after=company)
    await db.commit()
    refreshed = await db.execute(select(Company).options(selectinload(Company.tags)).where(Company.id == company.id))
    return refreshed.scalar_one()


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(company_id: UUID, data: CompanyUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("companies:write"))):
    query = select(Company).options(selectinload(Company.tags)).where(Company.id == company_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    before_snapshot = {c.name: getattr(company, c.name) for c in company.__table__.columns}
    for field, value in data.model_dump(exclude_unset=True, exclude={"tag_ids"}).items():
        setattr(company, field, value)
    if data.tag_ids is not None:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        company.tags = list(tags)
    log_mutation(db, event_type=AuditEventType.COMPANY_UPDATED, user=current_user, entity_type="company", entity_id=company.id, before=before_snapshot, after=company)
    await db.commit()
    refreshed = await db.execute(select(Company).options(selectinload(Company.tags)).where(Company.id == company.id))
    return refreshed.scalar_one()


@router.delete("/{company_id}")
async def delete_company(company_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("companies:write"))):
    query = select(Company).where(Company.id == company_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    before_snapshot = {c.name: getattr(company, c.name) for c in company.__table__.columns}
    company_id_copy = company.id
    await db.delete(company)
    log_mutation(db, event_type=AuditEventType.COMPANY_DELETED, user=current_user, entity_type="company", entity_id=company_id_copy, before=before_snapshot)
    await db.commit()
    return {"ok": True}


@router.post("/bulk")
async def bulk_companies(
    data: BulkAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("companies:write")),
):
    query = select(Company).options(selectinload(Company.tags)).where(Company.id.in_(data.ids))
    query = _apply_ownership_filter(query, current_user)
    companies = (await db.execute(query)).scalars().all()
    affected = 0
    for c in companies:
        before = {col.name: getattr(c, col.name) for col in c.__table__.columns}
        if data.action == "delete":
            cid = c.id
            await db.delete(c)
            log_mutation(db, event_type=AuditEventType.COMPANY_DELETED, user=current_user, entity_type="company", entity_id=cid, before=before)
        elif data.action == "add_tag" and data.tag_id:
            tag = (await db.execute(select(Tag).where(Tag.id == data.tag_id))).scalar_one_or_none()
            if tag and tag not in c.tags:
                c.tags.append(tag)
                log_mutation(db, event_type=AuditEventType.COMPANY_UPDATED, user=current_user, entity_type="company", entity_id=c.id, before=before, after=c)
        elif data.action == "remove_tag" and data.tag_id:
            c.tags = [t for t in c.tags if t.id != data.tag_id]
            log_mutation(db, event_type=AuditEventType.COMPANY_UPDATED, user=current_user, entity_type="company", entity_id=c.id, before=before, after=c)
        else:
            continue
        affected += 1
    await db.commit()
    return {"affected": affected}


@router.get("/{company_id}/profile", response_model=CompanyProfile)
async def get_company_profile(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("companies:read")),
):
    query = (
        select(Company)
        .options(
            selectinload(Company.tags),
            selectinload(Company.contacts).selectinload(Contact.tags),
            selectinload(Company.deals).selectinload(Deal.tags),
            selectinload(Company.custom_field_values),
        )
        .where(Company.id == company_id)
    )
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Custom field definitions for companies
    defs_result = await db.execute(
        select(CustomFieldDefinition).where(CustomFieldDefinition.entity_type == "company").order_by(CustomFieldDefinition.name)
    )
    definitions = defs_result.scalars().all()

    # Compute stats
    closed_stages = {DealStage.CLOSED_WON, DealStage.CLOSED_LOST}
    deals = company.deals or []
    contacts = company.contacts or []
    contact_ids = [c.id for c in contacts]

    # Activity stats across all company contacts
    total_activities = 0
    last_activity_date = None
    if contact_ids:
        act_count_q = select(func.count()).select_from(Activity).where(Activity.contact_id.in_(contact_ids))
        total_activities = (await db.execute(act_count_q)).scalar() or 0
        last_act_q = select(func.max(Activity.activity_date)).where(Activity.contact_id.in_(contact_ids))
        last_activity_date = (await db.execute(last_act_q)).scalar()

    stats = CompanyStats(
        total_contacts=len(contacts),
        total_deals=len(deals),
        total_deal_value=sum(d.value or 0 for d in deals),
        open_deals=sum(1 for d in deals if d.stage not in closed_stages),
        won_deals=sum(1 for d in deals if d.stage == DealStage.CLOSED_WON),
        total_activities=total_activities,
        last_activity_date=last_activity_date,
    )

    return CompanyProfile(
        company=CompanyRead.model_validate(company),
        contacts=[ContactRead.model_validate(c) for c in contacts],
        deals=[DealRead.model_validate(d) for d in deals],
        custom_fields=[CustomFieldValueRead.model_validate(v) for v in (company.custom_field_values or [])],
        custom_field_definitions=[CustomFieldDefinitionRead.model_validate(d) for d in definitions],
        stats=stats,
    )


def _sanitize_csv_value(val: str | None) -> str | None:
    if not val:
        return val
    return val.lstrip("=+-@")


@router.post("/import/csv")
async def import_companies_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
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
        name = _sanitize_csv_value(row.get("name", "")) or ""
        if not name:
            continue
        company = Company(
            name=name,
            domain=_sanitize_csv_value(row.get("domain")),
            industry=_sanitize_csv_value(row.get("industry")),
            size=_sanitize_csv_value(row.get("size")),
            address=_sanitize_csv_value(row.get("address")),
            phone=_sanitize_csv_value(row.get("phone")),
            notes=_sanitize_csv_value(row.get("notes")),
            owner_id=current_user.id,
        )
        db.add(company)
        count += 1
    await db.commit()
    return {"imported": count}
