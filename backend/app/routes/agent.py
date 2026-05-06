import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_scope
from app.database import get_db
from app.models import (
    Activity,
    AuditEventType,
    AuditLog,
    Company,
    Contact,
    Deal,
    User,
)
from app.schemas import (
    ActivityRead,
    AgentWhoAmI,
    BulkCompanyItem,
    BulkCompanyUpload,
    BulkContactItem,
    BulkContactUpload,
    BulkDealItem,
    BulkDealUpload,
    BulkResultItem,
    BulkUploadResult,
    CompanyRead,
    CompanyResearchResult,
    ContactRead,
    ContactResearchResult,
    DealRead,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger(__name__)


async def _write_audit(
    db: AsyncSession,
    event_type: AuditEventType,
    *,
    ip_address: str | None = None,
    user_id=None,
    detail: str | None = None,
    api_key_id=None,
) -> None:
    try:
        entry = AuditLog(
            event_type=event_type,
            user_id=user_id,
            ip_address=ip_address,
            detail=detail,
            api_key_id=api_key_id,
        )
        db.add(entry)
        await db.commit()
    except Exception:
        logger.exception("Failed to write audit log")


# --- Whoami ---


@router.get("/whoami", response_model=AgentWhoAmI)
async def whoami(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    api_key = getattr(request.state, "api_key", None)
    scopes = None
    rate_limit = None
    if api_key:
        scopes = json.loads(api_key.scopes) if api_key.scopes else None
        rate_limit = api_key.rate_limit_per_minute
    return AgentWhoAmI(
        service_account_id=current_user.id,
        name=current_user.full_name,
        email=current_user.email,
        account_type=current_user.account_type.value,
        scopes=scopes,
        rate_limit_per_minute=rate_limit,
    )


# --- Bulk Upload: Contacts ---


@router.post("/bulk/contacts", response_model=BulkUploadResult)
async def bulk_upload_contacts(
    data: BulkContactUpload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("agent:bulk_upload")),
):
    api_key = getattr(request.state, "api_key", None)
    api_key_id = api_key.id if api_key else None
    results: list[BulkResultItem] = []
    created = 0
    skipped = 0
    errors = 0

    # Pre-fetch existing emails for dedup
    existing_emails: set[str] = set()
    if data.dedupe_on_email:
        emails_in_batch = [c.email.lower() for c in data.contacts if c.email]
        if emails_in_batch:
            result = await db.execute(
                select(Contact.email).where(Contact.email.in_(emails_in_batch))
            )
            existing_emails = {row[0].lower() for row in result.all() if row[0]}

    # Pre-resolve company names
    company_names = {c.company_name for c in data.contacts if c.company_name}
    company_map: dict[str, UUID] = {}
    if company_names:
        for name in company_names:
            result = await db.execute(
                select(Company).where(Company.name.ilike(name)).limit(1)
            )
            company = result.scalar_one_or_none()
            if company:
                company_map[name.lower()] = company.id

    for i, item in enumerate(data.contacts):
        try:
            # Dedup check
            if data.dedupe_on_email and item.email and item.email.lower() in existing_emails:
                results.append(BulkResultItem(index=i, status="skipped_duplicate"))
                skipped += 1
                continue

            source = item.source or data.default_source
            company_id = None
            if item.company_name:
                company_id = company_map.get(item.company_name.lower())

            contact = Contact(
                first_name=item.first_name,
                last_name=item.last_name,
                email=item.email,
                phone=item.phone,
                job_title=item.job_title,
                company_id=company_id,
                owner_id=current_user.id,
                source=source,
                notes=item.notes,
            )
            db.add(contact)
            await db.flush()

            results.append(BulkResultItem(index=i, status="created", id=contact.id))
            created += 1

            # Track email for in-batch dedup
            if item.email:
                existing_emails.add(item.email.lower())

        except Exception as e:
            results.append(BulkResultItem(index=i, status="error", error=str(e)))
            errors += 1

    await db.commit()

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.BULK_IMPORT,
        ip_address=ip,
        user_id=current_user.id,
        api_key_id=api_key_id,
        detail=f"Bulk contact import: {created} created, {skipped} skipped, {errors} errors (total: {len(data.contacts)})",
    )

    return BulkUploadResult(
        total=len(data.contacts),
        created=created,
        skipped=skipped,
        errors=errors,
        results=results,
    )


# --- Bulk Upload: Companies ---


@router.post("/bulk/companies", response_model=BulkUploadResult)
async def bulk_upload_companies(
    data: BulkCompanyUpload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("agent:bulk_upload")),
):
    api_key = getattr(request.state, "api_key", None)
    api_key_id = api_key.id if api_key else None
    results: list[BulkResultItem] = []
    created = 0
    skipped = 0
    errors = 0

    # Pre-fetch existing domains for dedup
    existing_domains: set[str] = set()
    if data.dedupe_on_domain:
        domains_in_batch = [c.domain.lower() for c in data.companies if c.domain]
        if domains_in_batch:
            result = await db.execute(
                select(Company.domain).where(Company.domain.in_(domains_in_batch))
            )
            existing_domains = {row[0].lower() for row in result.all() if row[0]}

    for i, item in enumerate(data.companies):
        try:
            if data.dedupe_on_domain and item.domain and item.domain.lower() in existing_domains:
                results.append(BulkResultItem(index=i, status="skipped_duplicate"))
                skipped += 1
                continue

            company = Company(
                name=item.name,
                domain=item.domain,
                industry=item.industry,
                size=item.size,
                address=item.address,
                phone=item.phone,
                notes=item.notes,
                owner_id=current_user.id,
            )
            db.add(company)
            await db.flush()

            results.append(BulkResultItem(index=i, status="created", id=company.id))
            created += 1

            if item.domain:
                existing_domains.add(item.domain.lower())

        except Exception as e:
            results.append(BulkResultItem(index=i, status="error", error=str(e)))
            errors += 1

    await db.commit()

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.BULK_IMPORT,
        ip_address=ip,
        user_id=current_user.id,
        api_key_id=api_key_id,
        detail=f"Bulk company import: {created} created, {skipped} skipped, {errors} errors (total: {len(data.companies)})",
    )

    return BulkUploadResult(
        total=len(data.companies),
        created=created,
        skipped=skipped,
        errors=errors,
        results=results,
    )


# --- Bulk Upload: Deals ---


@router.post("/bulk/deals", response_model=BulkUploadResult)
async def bulk_upload_deals(
    data: BulkDealUpload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("agent:bulk_upload")),
):
    api_key = getattr(request.state, "api_key", None)
    api_key_id = api_key.id if api_key else None
    results: list[BulkResultItem] = []
    created = 0
    skipped = 0
    errors = 0

    for i, item in enumerate(data.deals):
        try:
            contact_id = None
            company_id = None

            # Resolve contact by email
            if item.contact_email:
                result = await db.execute(
                    select(Contact).where(Contact.email.ilike(item.contact_email)).limit(1)
                )
                contact = result.scalar_one_or_none()
                if contact:
                    contact_id = contact.id

            # Resolve company by name
            if item.company_name:
                result = await db.execute(
                    select(Company).where(Company.name.ilike(item.company_name)).limit(1)
                )
                company = result.scalar_one_or_none()
                if company:
                    company_id = company.id

            deal = Deal(
                title=item.title,
                value=item.value,
                currency=item.currency,
                stage=item.stage,
                contact_id=contact_id,
                company_id=company_id,
                owner_id=current_user.id,
                expected_close_date=item.expected_close_date,
                notes=item.notes,
            )
            db.add(deal)
            await db.flush()

            results.append(BulkResultItem(index=i, status="created", id=deal.id))
            created += 1

        except Exception as e:
            results.append(BulkResultItem(index=i, status="error", error=str(e)))
            errors += 1

    await db.commit()

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.BULK_IMPORT,
        ip_address=ip,
        user_id=current_user.id,
        api_key_id=api_key_id,
        detail=f"Bulk deal import: {created} created, {errors} errors (total: {len(data.deals)})",
    )

    return BulkUploadResult(
        total=len(data.deals),
        created=created,
        skipped=skipped,
        errors=errors,
        results=results,
    )


# --- Research Endpoints ---


@router.get("/research/company", response_model=CompanyResearchResult)
async def research_company(
    q: str = Query(min_length=1, description="Company name or domain"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("agent:research")),
):
    api_key = getattr(request.state, "api_key", None)
    api_key_id = api_key.id if api_key else None

    # Search by name or domain
    result = await db.execute(
        select(Company)
        .options(selectinload(Company.tags))
        .where(
            or_(
                Company.name.ilike(f"%{q}%"),
                Company.domain.ilike(f"%{q}%"),
            )
        )
        .limit(1)
    )
    company = result.scalar_one_or_none()

    if not company:
        ip = request.client.host if request.client else "unknown"
        await _write_audit(
            db,
            AuditEventType.AGENT_RESEARCH,
            ip_address=ip,
            user_id=current_user.id,
            api_key_id=api_key_id,
            detail=f"Company research: '{q}' - not found",
        )
        return CompanyResearchResult()

    # Load related data
    contacts_result = await db.execute(
        select(Contact)
        .options(selectinload(Contact.tags))
        .where(Contact.company_id == company.id)
        .order_by(Contact.created_at.desc())
        .limit(50)
    )
    contacts = contacts_result.scalars().all()

    deals_result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.tags))
        .where(Deal.company_id == company.id)
        .order_by(Deal.created_at.desc())
        .limit(20)
    )
    deals = deals_result.scalars().all()

    activities_result = await db.execute(
        select(Activity)
        .where(Activity.contact_id.in_([c.id for c in contacts]) if contacts else Activity.id == None)
        .order_by(Activity.created_at.desc())
        .limit(20)
    )
    activities = activities_result.scalars().all()

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.AGENT_RESEARCH,
        ip_address=ip,
        user_id=current_user.id,
        api_key_id=api_key_id,
        detail=f"Company research: '{q}' - found '{company.name}'",
    )

    return CompanyResearchResult(
        company=company,
        contacts=contacts,
        deals=deals,
        recent_activities=activities,
    )


@router.get("/research/contact", response_model=ContactResearchResult)
async def research_contact(
    q: str = Query(min_length=1, description="Contact email or name"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("agent:research")),
):
    api_key = getattr(request.state, "api_key", None)
    api_key_id = api_key.id if api_key else None

    # Search by email first, then name
    result = await db.execute(
        select(Contact)
        .options(selectinload(Contact.tags))
        .where(
            or_(
                Contact.email.ilike(f"%{q}%"),
                Contact.first_name.ilike(f"%{q}%"),
                Contact.last_name.ilike(f"%{q}%"),
            )
        )
        .limit(1)
    )
    contact = result.scalar_one_or_none()

    if not contact:
        ip = request.client.host if request.client else "unknown"
        await _write_audit(
            db,
            AuditEventType.AGENT_RESEARCH,
            ip_address=ip,
            user_id=current_user.id,
            api_key_id=api_key_id,
            detail=f"Contact research: '{q}' - not found",
        )
        return ContactResearchResult()

    # Load company
    company = None
    if contact.company_id:
        company_result = await db.execute(
            select(Company)
            .options(selectinload(Company.tags))
            .where(Company.id == contact.company_id)
        )
        company = company_result.scalar_one_or_none()

    # Load deals
    deals_result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.tags))
        .where(Deal.contact_id == contact.id)
        .order_by(Deal.created_at.desc())
        .limit(20)
    )
    deals = deals_result.scalars().all()

    # Load activities
    activities_result = await db.execute(
        select(Activity)
        .where(Activity.contact_id == contact.id)
        .order_by(Activity.created_at.desc())
        .limit(20)
    )
    activities = activities_result.scalars().all()

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.AGENT_RESEARCH,
        ip_address=ip,
        user_id=current_user.id,
        api_key_id=api_key_id,
        detail=f"Contact research: '{q}' - found '{contact.first_name} {contact.last_name}'",
    )

    return ContactResearchResult(
        contact=contact,
        company=company,
        deals=deals,
        recent_activities=activities,
    )
