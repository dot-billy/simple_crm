from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalyst_intake import notify_catalyst_intake_slack
from app.models import (
    Activity,
    ActivityType,
    CatalystIntakeStatus,
    CatalystIntakeSubmission,
    Company,
    Contact,
    Deal,
    DealStage,
    Tag,
)

CATALYST_INTAKE_TAG = "catalyst-managed-intake"
KEY_PERSON_TAG = "key-person"
CATALYST_NOTE_MARKER = "Catalyst managed intake"
DEAL_TITLE_LIMIT = 255
MAX_ATTEMPTS = 5
LOCK_TIMEOUT_MINUTES = 15


@dataclass(frozen=True)
class IntakePayload:
    path: str
    name: str
    email: str
    company: str
    expected_nodes_sites: str
    timeline: str
    notes: str


class IntakeRepository(Protocol):
    async def ensure_tag(self, name: str, color: str) -> Any: ...
    async def find_company(self, company_name: str) -> Any | None: ...
    async def create_company(self, company_name: str, catalyst_tag: Any) -> Any: ...
    async def update_company_tags(self, company: Any, tag_ids: list[Any]) -> Any: ...
    async def find_contact_by_email(self, email: str) -> Any | None: ...
    async def create_contact(self, intake: IntakePayload, company: Any, tags: list[Any]) -> Any: ...
    async def update_contact(self, contact: Any, *, company_id: Any | None = None, tag_ids: list[Any] | None = None) -> Any: ...
    async def fetch_open_deals(self) -> list[Any]: ...
    async def create_deal(self, title: str, note: str, company: Any, contact: Any, catalyst_tag: Any) -> Any: ...
    async def update_deal_tags(self, deal: Any, tag_ids: list[Any]) -> Any: ...
    async def create_activity(self, note: str, contact: Any, deal: Any, created_by: Any) -> Any: ...


class SqlAlchemyIntakeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_tag(self, name: str, color: str) -> Tag:
        tag = (await self.db.execute(select(Tag).where(Tag.name == name))).scalar_one_or_none()
        if tag:
            return tag
        tag = Tag(name=name, color=color)
        self.db.add(tag)
        await self.db.flush()
        return tag

    async def find_company(self, company_name: str) -> Company | None:
        normalized_name = _normalize_for_match(company_name)
        result = await self.db.execute(
            select(Company)
            .options(selectinload(Company.tags))
            .where(Company.name.ilike(f"%{company_name}%"))
        )
        return next((company for company in result.scalars().all() if _normalize_for_match(company.name) == normalized_name), None)

    async def create_company(self, company_name: str, catalyst_tag: Tag) -> Company:
        company = Company(name=company_name, notes="Catalyst managed intake lead.", tags=[catalyst_tag])
        self.db.add(company)
        await self.db.flush()
        return company

    async def update_company_tags(self, company: Company, tag_ids: list[Any]) -> Company:
        company.tags = await self._tags_by_ids(tag_ids)
        await self.db.flush()
        return company

    async def find_contact_by_email(self, email: str) -> Contact | None:
        return (
            await self.db.execute(
                select(Contact)
                .options(selectinload(Contact.tags))
                .where(func.lower(Contact.email) == email.lower())
            )
        ).scalar_one_or_none()

    async def create_contact(self, intake: IntakePayload, company: Company, tags: list[Tag]) -> Contact:
        first_name, *last_name_parts = intake.name.split()
        contact = Contact(
            first_name=first_name,
            last_name=" ".join(last_name_parts) or "-",
            email=intake.email,
            company_id=company.id,
            source="catalyst-managed-intake",
            tags=tags,
        )
        self.db.add(contact)
        await self.db.flush()
        return contact

    async def update_contact(
        self,
        contact: Contact,
        *,
        company_id: Any | None = None,
        tag_ids: list[Any] | None = None,
    ) -> Contact:
        if company_id is not None:
            contact.company_id = company_id
        if tag_ids is not None:
            contact.tags = await self._tags_by_ids(tag_ids)
        await self.db.flush()
        return contact

    async def fetch_open_deals(self) -> list[Deal]:
        result = await self.db.execute(
            select(Deal)
            .options(selectinload(Deal.tags))
            .where(Deal.stage.notin_([DealStage.CLOSED_WON, DealStage.CLOSED_LOST]))
        )
        return list(result.scalars().all())

    async def create_deal(self, title: str, note: str, company: Company, contact: Contact, catalyst_tag: Tag) -> Deal:
        deal = Deal(
            title=title,
            stage=DealStage.LEAD,
            company_id=company.id,
            contact_id=contact.id,
            notes=note,
            tags=[catalyst_tag],
        )
        self.db.add(deal)
        await self.db.flush()
        return deal

    async def update_deal_tags(self, deal: Deal, tag_ids: list[Any]) -> Deal:
        deal.tags = await self._tags_by_ids(tag_ids)
        await self.db.flush()
        return deal

    async def create_activity(self, note: str, contact: Contact, deal: Deal, created_by: Any) -> Activity:
        activity = Activity(
            type=ActivityType.NOTE,
            subject="Catalyst managed intake request",
            description=note,
            contact_id=contact.id,
            deal_id=deal.id,
            created_by=created_by,
        )
        self.db.add(activity)
        await self.db.flush()
        return activity

    async def _tags_by_ids(self, tag_ids: list[Any]) -> list[Tag]:
        if not tag_ids:
            return []
        return list((await self.db.execute(select(Tag).where(Tag.id.in_(tag_ids)))).scalars().all())


async def claim_next_submission(
    db: AsyncSession,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    lock_timeout_minutes: int = LOCK_TIMEOUT_MINUTES,
) -> CatalystIntakeSubmission | None:
    now = _utcnow()
    stale_before = now - timedelta(minutes=lock_timeout_minutes)
    result = await db.execute(
        select(CatalystIntakeSubmission)
        .where(
            or_(
                CatalystIntakeSubmission.status == CatalystIntakeStatus.PENDING,
                and_(
                    CatalystIntakeSubmission.status.in_(
                        [CatalystIntakeStatus.PROCESSING, CatalystIntakeStatus.FAILED]
                    ),
                    CatalystIntakeSubmission.attempts < max_attempts,
                    or_(
                        CatalystIntakeSubmission.locked_at.is_(None),
                        CatalystIntakeSubmission.locked_at < stale_before,
                    ),
                ),
            )
        )
        .order_by(CatalystIntakeSubmission.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        return None
    submission.status = CatalystIntakeStatus.PROCESSING
    submission.attempts = (submission.attempts or 0) + 1
    submission.locked_at = now
    await db.commit()
    await db.refresh(submission)
    return submission


async def process_claimed_submission(
    db: AsyncSession,
    submission: CatalystIntakeSubmission,
    *,
    repository: IntakeRepository | None = None,
    slack_webhook_url: str,
    crm_frontend_base_url: str,
) -> bool:
    repository = repository or SqlAlchemyIntakeRepository(db)
    try:
        intake = _payload_from_submission(submission)
        catalyst_tag = await repository.ensure_tag(CATALYST_INTAKE_TAG, "#0EA5E9")
        key_person_tag = await repository.ensure_tag(KEY_PERSON_TAG, "#14B8A6")

        company = await _ensure_company(repository, intake, catalyst_tag)
        contact = await _ensure_contact(repository, intake, company, catalyst_tag, key_person_tag)
        note = build_activity_description(intake)
        deal = await _ensure_deal(repository, intake, note, company, contact, catalyst_tag)
        activity = await repository.create_activity(note, contact, deal, submission.created_by)

        submission.company_id = company.id
        submission.contact_id = contact.id
        submission.deal_id = deal.id
        submission.activity_id = activity.id
        submission.status = CatalystIntakeStatus.PROCESSED
        submission.processed_at = _utcnow()
        submission.last_error = None
        await db.commit()

        await notify_catalyst_intake_slack(
            slack_webhook_url,
            activity,
            deal,
            contact,
            company,
            crm_frontend_base_url,
        )
        return True
    except Exception as exc:
        if hasattr(db, "rollback"):
            await db.rollback()
        submission.status = CatalystIntakeStatus.FAILED
        submission.last_error = sanitize_processing_error(exc)
        if hasattr(db, "add"):
            db.add(submission)
        await db.commit()
        return False


async def process_next_submission(
    db: AsyncSession,
    *,
    slack_webhook_url: str,
    crm_frontend_base_url: str,
) -> bool:
    submission = await claim_next_submission(db)
    if submission is None:
        return False
    return await process_claimed_submission(
        db,
        submission,
        slack_webhook_url=slack_webhook_url,
        crm_frontend_base_url=crm_frontend_base_url,
    )


def sanitize_processing_error(exc: Exception) -> str:
    return type(exc).__name__


def build_activity_description(intake: IntakePayload) -> str:
    return "\n".join(
        [
            "Catalyst managed intake submission",
            f"Selected path: {_path_label(intake.path)}",
            f"Key person: {intake.name} <{intake.email}>",
            f"Company: {intake.company}",
            f"Expected nodes/sites: {intake.expected_nodes_sites}",
            f"Timeline: {_timeline_label(intake.timeline)}",
            f"Notes: {intake.notes or 'None provided'}",
        ]
    )


async def _ensure_company(repository: IntakeRepository, intake: IntakePayload, catalyst_tag: Any) -> Any:
    company = await repository.find_company(intake.company)
    if company is None:
        return await repository.create_company(intake.company, catalyst_tag)
    if not _has_tag(company, CATALYST_INTAKE_TAG):
        return await repository.update_company_tags(company, _tag_ids(company, [catalyst_tag.id]))
    return company


async def _ensure_contact(
    repository: IntakeRepository,
    intake: IntakePayload,
    company: Any,
    catalyst_tag: Any,
    key_person_tag: Any,
) -> Any:
    contact = await repository.find_contact_by_email(intake.email)
    if contact is None:
        return await repository.create_contact(intake, company, [catalyst_tag, key_person_tag])
    patch: dict[str, Any] = {}
    if getattr(contact, "company_id", None) is None:
        patch["company_id"] = company.id
    if not _has_tag(contact, CATALYST_INTAKE_TAG) or not _has_tag(contact, KEY_PERSON_TAG):
        patch["tag_ids"] = _tag_ids(contact, [catalyst_tag.id, key_person_tag.id])
    if patch:
        return await repository.update_contact(contact, **patch)
    return contact


async def _ensure_deal(
    repository: IntakeRepository,
    intake: IntakePayload,
    note: str,
    company: Any,
    contact: Any,
    catalyst_tag: Any,
) -> Any:
    deal = _choose_open_deal(await repository.fetch_open_deals(), company, contact)
    if deal is None:
        return await repository.create_deal(_build_deal_title(company.name), note, company, contact, catalyst_tag)
    if not _has_tag(deal, CATALYST_INTAKE_TAG):
        return await repository.update_deal_tags(deal, _tag_ids(deal, [catalyst_tag.id]))
    return deal


def _choose_open_deal(deals: list[Any], company: Any, contact: Any) -> Any | None:
    open_deals = [deal for deal in deals if _is_open_deal(deal)]
    exact_matches = [
        deal for deal in open_deals if getattr(deal, "company_id", None) == company.id and getattr(deal, "contact_id", None) == contact.id
    ]
    exact_catalyst = next((deal for deal in exact_matches if _has_catalyst_marker(deal, company.name)), None)
    if exact_catalyst:
        return exact_catalyst

    company_catalyst = next(
        (
            deal
            for deal in open_deals
            if getattr(deal, "company_id", None) == company.id and _has_catalyst_marker(deal, company.name)
        ),
        None,
    )
    if company_catalyst:
        return company_catalyst

    if getattr(contact, "company_id", None) in {None, company.id}:
        return next(
            (
                deal
                for deal in open_deals
                if getattr(deal, "company_id", None) is None
                and getattr(deal, "contact_id", None) == contact.id
                and _has_catalyst_marker(deal, company.name)
            ),
            None,
        )
    return None


def _payload_from_submission(submission: CatalystIntakeSubmission) -> IntakePayload:
    return IntakePayload(
        path=submission.path,
        name=submission.name,
        email=submission.email,
        company=submission.company,
        expected_nodes_sites=submission.expected_nodes_sites,
        timeline=submission.timeline,
        notes=submission.notes or "",
    )


def _is_open_deal(deal: Any) -> bool:
    stage = getattr(deal, "stage", "")
    stage_value = getattr(stage, "value", stage)
    return stage_value not in {DealStage.CLOSED_WON.value, DealStage.CLOSED_LOST.value}


def _has_catalyst_marker(deal: Any, company_name: str) -> bool:
    return (
        _has_tag(deal, CATALYST_INTAKE_TAG)
        or CATALYST_NOTE_MARKER in (getattr(deal, "notes", None) or "")
        or _normalize_for_match(getattr(deal, "title", "")) == _normalize_for_match(_build_deal_title(company_name))
    )


def _has_tag(entity: Any, tag_name: str) -> bool:
    return any(getattr(tag, "name", None) == tag_name for tag in (getattr(entity, "tags", None) or []))


def _tag_ids(entity: Any, extra_ids: list[Any]) -> list[Any]:
    existing_ids = [tag.id for tag in (getattr(entity, "tags", None) or [])]
    return list(dict.fromkeys([*existing_ids, *extra_ids]))


def _build_deal_title(company_name: str) -> str:
    return f"Catalyst - {company_name}"[:DEAL_TITLE_LIMIT]


def _normalize_for_match(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _path_label(path: str) -> str:
    return {
        "shared-hosted": "Shared Hosted",
        "dedicated-managed": "Dedicated Managed",
        "enterprise-msp": "Enterprise / MSP",
    }.get(path, path)


def _timeline_label(timeline: str) -> str:
    return {
        "as-soon-as-possible": "As soon as possible",
        "30-60-days": "30-60 days",
        "this-quarter": "This quarter",
        "planning-ahead": "Planning ahead",
    }.get(timeline, timeline)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
