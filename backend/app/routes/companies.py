import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Company, Tag, User, UserRole
from app.schemas import CompanyCreate, CompanyRead, CompanyUpdate

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _apply_ownership_filter(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Company.owner_id == user.id)
    return query


@router.get("", response_model=dict)
async def list_companies(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Company).options(selectinload(Company.tags))
    query = _apply_ownership_filter(query, current_user)
    if search:
        query = query.where(
            (Company.name.ilike(f"%{search}%")) | (Company.domain.ilike(f"%{search}%"))
        )
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = query.order_by(Company.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()
    return {
        "items": [CompanyRead.model_validate(c) for c in items],
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(company_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Company).options(selectinload(Company.tags)).where(Company.id == company_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.post("", response_model=CompanyRead)
async def create_company(data: CompanyCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    company = Company(**data.model_dump(exclude={"tag_ids"}), owner_id=current_user.id)
    if data.tag_ids:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        company.tags = list(tags)
    db.add(company)
    await db.commit()
    await db.refresh(company, ["tags"])
    return company


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(company_id: UUID, data: CompanyUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Company).options(selectinload(Company.tags)).where(Company.id == company_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    for field, value in data.model_dump(exclude_unset=True, exclude={"tag_ids"}).items():
        setattr(company, field, value)
    if data.tag_ids is not None:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        company.tags = list(tags)
    await db.commit()
    await db.refresh(company, ["tags"])
    return company


@router.delete("/{company_id}")
async def delete_company(company_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Company).where(Company.id == company_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    await db.delete(company)
    await db.commit()
    return {"ok": True}


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
