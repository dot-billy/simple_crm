from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role, require_scope
from app.database import get_db
from app.models import Company, Contact, CustomFieldDefinition, CustomFieldValue, User, UserRole
from app.schemas import (
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionRead,
    CustomFieldValueCreate,
    CustomFieldValueRead,
)

router = APIRouter(prefix="/api/custom-fields", tags=["custom_fields"])


async def _check_entity_ownership(db: AsyncSession, user: User, contact_id: UUID | None, company_id: UUID | None):
    """For USER role, verify ownership of referenced contact/company."""
    if user.role != UserRole.USER:
        return
    if contact_id:
        result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.owner_id == user.id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Not allowed")
    if company_id:
        result = await db.execute(select(Company).where(Company.id == company_id, Company.owner_id == user.id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Not allowed")


@router.get("/definitions", response_model=list[CustomFieldDefinitionRead])
async def list_definitions(
    entity_type: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("custom_fields:read")),
):
    query = select(CustomFieldDefinition)
    if entity_type:
        query = query.where(CustomFieldDefinition.entity_type == entity_type)
    result = await db.execute(query.order_by(CustomFieldDefinition.name))
    return result.scalars().all()


@router.post("/definitions", response_model=CustomFieldDefinitionRead)
async def create_definition(
    data: CustomFieldDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    defn = CustomFieldDefinition(**data.model_dump())
    db.add(defn)
    await db.commit()
    await db.refresh(defn)
    return defn


@router.delete("/definitions/{defn_id}")
async def delete_definition(
    defn_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(select(CustomFieldDefinition).where(CustomFieldDefinition.id == defn_id))
    defn = result.scalar_one_or_none()
    if not defn:
        raise HTTPException(status_code=404, detail="Definition not found")
    await db.delete(defn)
    await db.commit()
    return {"ok": True}


@router.get("/values", response_model=list[CustomFieldValueRead])
async def list_values(
    contact_id: UUID | None = Query(None),
    company_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("custom_fields:read")),
):
    await _check_entity_ownership(db, current_user, contact_id, company_id)
    query = select(CustomFieldValue)
    if contact_id:
        query = query.where(CustomFieldValue.contact_id == contact_id)
    if company_id:
        query = query.where(CustomFieldValue.company_id == company_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/values", response_model=CustomFieldValueRead)
async def set_value(
    data: CustomFieldValueCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("custom_fields:write")),
):
    await _check_entity_ownership(db, current_user, data.contact_id, data.company_id)
    # Upsert
    query = select(CustomFieldValue).where(CustomFieldValue.field_id == data.field_id)
    if data.contact_id:
        query = query.where(CustomFieldValue.contact_id == data.contact_id)
    if data.company_id:
        query = query.where(CustomFieldValue.company_id == data.company_id)
    result = await db.execute(query)
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = data.value
        await db.commit()
        await db.refresh(existing)
        return existing
    cfv = CustomFieldValue(**data.model_dump())
    db.add(cfv)
    await db.commit()
    await db.refresh(cfv)
    return cfv
