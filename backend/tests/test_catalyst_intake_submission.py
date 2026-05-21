import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key")

from app.models import APIKeyScope, CatalystIntakeStatus
from app.catalyst_intake_processor import (
    CATALYST_INTAKE_TAG,
    KEY_PERSON_TAG,
    claim_next_submission,
    process_claimed_submission,
)
from app.routes.catalyst_intake import accept_catalyst_intake
from app.schemas import CatalystIntakeAccepted, CatalystIntakeCreate


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.refreshed = []

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True

    async def refresh(self, value):
        self.refreshed.append(value)


class FakeRepository:
    def __init__(self, *, fail_on_activity=False):
        self.fail_on_activity = fail_on_activity
        self.created_companies = []
        self.created_contacts = []
        self.created_deals = []
        self.created_activities = []
        self.updated_company_tags = []
        self.updated_contact_tags = []
        self.updated_deal_tags = []
        self.catalyst_tag = SimpleNamespace(id=uuid4(), name=CATALYST_INTAKE_TAG, color="#0EA5E9")
        self.key_person_tag = SimpleNamespace(id=uuid4(), name=KEY_PERSON_TAG, color="#14B8A6")
        self.company = None
        self.contact = None
        self.open_deals = []

    async def ensure_tag(self, name, color):
        if name == CATALYST_INTAKE_TAG:
            return self.catalyst_tag
        if name == KEY_PERSON_TAG:
            return self.key_person_tag
        raise AssertionError(f"unexpected tag {name}")

    async def find_company(self, company_name):
        return self.company

    async def create_company(self, company_name, catalyst_tag):
        self.company = SimpleNamespace(id=uuid4(), name=company_name, tags=[catalyst_tag])
        self.created_companies.append(self.company)
        return self.company

    async def update_company_tags(self, company, tag_ids):
        self.updated_company_tags.append((company.id, tag_ids))
        return company

    async def find_contact_by_email(self, email):
        return self.contact

    async def create_contact(self, intake, company, tags):
        self.contact = SimpleNamespace(id=uuid4(), email=intake.email, company_id=company.id, tags=tags)
        self.created_contacts.append(self.contact)
        return self.contact

    async def update_contact(self, contact, *, company_id=None, tag_ids=None):
        self.updated_contact_tags.append((contact.id, company_id, tag_ids))
        if company_id is not None:
            contact.company_id = company_id
        return contact

    async def fetch_open_deals(self):
        return self.open_deals

    async def create_deal(self, title, note, company, contact, catalyst_tag):
        deal = SimpleNamespace(
            id=uuid4(),
            title=title,
            stage="lead",
            company_id=company.id,
            contact_id=contact.id,
            notes=note,
            tags=[catalyst_tag],
        )
        self.open_deals.append(deal)
        self.created_deals.append(deal)
        return deal

    async def update_deal_tags(self, deal, tag_ids):
        self.updated_deal_tags.append((deal.id, tag_ids))
        return deal

    async def create_activity(self, note, contact, deal, created_by):
        if self.fail_on_activity:
            raise RuntimeError("failed for ada@example.com / Example Co / Needs an isolated database.")
        activity = SimpleNamespace(id=uuid4(), description=note, contact=contact, deal=deal)
        self.created_activities.append(activity)
        return activity


class CatalystIntakeSubmissionTests(unittest.IsolatedAsyncioTestCase):
    def test_api_key_scope_includes_catalyst_intake_write(self):
        self.assertEqual(APIKeyScope.CATALYST_INTAKE_WRITE.value, "catalyst_intake:write")

    def test_route_source_requires_catalyst_intake_write_scope(self):
        with open("app/routes/catalyst_intake.py", encoding="utf-8") as source_file:
            source = source_file.read()

        self.assertIn('APIRouter(prefix="/api/catalyst-intake"', source)
        self.assertIn('status_code=status.HTTP_202_ACCEPTED', source)
        self.assertIn('require_scope("catalyst_intake:write")', source)

    async def test_accept_catalyst_intake_persists_pending_submission(self):
        db = FakeSession()
        user = SimpleNamespace(id=uuid4())
        payload = CatalystIntakeCreate(
            path="dedicated-managed",
            name="Ada Lovelace",
            email="ADA@Example.COM",
            company="Example Co",
            expected_nodes_sites="25 nodes / 4 sites",
            timeline="30-60-days",
            notes="Needs an isolated database.",
        )

        response = await accept_catalyst_intake(payload, db=db, current_user=user)

        self.assertIsInstance(response, CatalystIntakeAccepted)
        self.assertEqual("accepted", response.status)
        self.assertEqual(1, len(db.added))
        submission = db.added[0]
        self.assertEqual(CatalystIntakeStatus.PENDING, submission.status)
        self.assertEqual(user.id, submission.created_by)
        self.assertEqual("dedicated-managed", submission.path)
        self.assertEqual("Ada Lovelace", submission.name)
        self.assertEqual("ada@example.com", submission.email)
        self.assertEqual("Example Co", submission.company)
        self.assertEqual("25 nodes / 4 sites", submission.expected_nodes_sites)
        self.assertEqual("30-60-days", submission.timeline)
        self.assertEqual("Needs an isolated database.", submission.notes)
        self.assertTrue(db.committed)
        self.assertEqual([submission], db.refreshed)

    def test_claim_next_submission_uses_skip_locked_row_claiming(self):
        with open("app/catalyst_intake_processor.py", encoding="utf-8") as source_file:
            source = source_file.read()

        self.assertIn("with_for_update(skip_locked=True)", source)
        self.assertIn("CatalystIntakeStatus.PENDING", source)
        self.assertIn("CatalystIntakeStatus.PROCESSING", source)
        self.assertIn("CatalystIntakeStatus.FAILED", source)
        self.assertIn("attempts", source)

    async def test_process_claimed_submission_creates_crm_records_and_marks_processed(self):
        db = FakeSession()
        repo = FakeRepository()
        submission = self._submission()
        submission.status = CatalystIntakeStatus.PROCESSING
        submission.attempts = 1

        processed = await process_claimed_submission(
            db,
            submission,
            repository=repo,
            slack_webhook_url="",
            crm_frontend_base_url="https://simple-crm.example.test",
        )

        self.assertTrue(processed)
        self.assertEqual(CatalystIntakeStatus.PROCESSED, submission.status)
        self.assertIsNone(submission.last_error)
        self.assertIsNotNone(submission.processed_at)
        self.assertEqual(repo.created_companies[0].id, submission.company_id)
        self.assertEqual(repo.created_contacts[0].id, submission.contact_id)
        self.assertEqual(repo.created_deals[0].id, submission.deal_id)
        self.assertEqual(repo.created_activities[0].id, submission.activity_id)
        self.assertIn("Selected path: Dedicated Managed", repo.created_activities[0].description)
        self.assertTrue(db.committed)

    async def test_process_claimed_submission_marks_failed_with_sanitized_error(self):
        db = FakeSession()
        repo = FakeRepository(fail_on_activity=True)
        submission = self._submission()
        submission.status = CatalystIntakeStatus.PROCESSING
        submission.attempts = 1

        processed = await process_claimed_submission(
            db,
            submission,
            repository=repo,
            slack_webhook_url="",
            crm_frontend_base_url="https://simple-crm.example.test",
        )

        self.assertFalse(processed)
        self.assertEqual(CatalystIntakeStatus.FAILED, submission.status)
        self.assertEqual("RuntimeError", submission.last_error)
        self.assertNotIn("ada@example.com", submission.last_error)
        self.assertNotIn("Example Co", submission.last_error)
        self.assertNotIn("isolated database", submission.last_error)
        self.assertTrue(db.committed)

    def _submission(self):
        return SimpleNamespace(
            id=uuid4(),
            path="dedicated-managed",
            name="Ada Lovelace",
            email="ada@example.com",
            company="Example Co",
            expected_nodes_sites="25 nodes / 4 sites",
            timeline="30-60-days",
            notes="Needs an isolated database.",
            created_by=uuid4(),
            company_id=None,
            contact_id=None,
            deal_id=None,
            activity_id=None,
            status=CatalystIntakeStatus.PENDING,
            last_error=None,
            processed_at=None,
        )


class FakeSessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class CatalystIntakeWorkerTests(unittest.IsolatedAsyncioTestCase):
    def test_docker_compose_defines_dedicated_catalyst_intake_worker(self):
        with open("../docker-compose.yml", encoding="utf-8") as source_file:
            source = source_file.read()

        self.assertIn("catalyst-intake-worker:", source)
        self.assertIn("python -m app.catalyst_intake_worker", source)
        self.assertIn("CATALYST_INTAKE_WORKER_POLL_SECONDS", source)

    def test_worker_ensures_schema_before_polling(self):
        with open("app/catalyst_intake_worker.py", encoding="utf-8") as source_file:
            source = source_file.read()

        self.assertIn("ensure_schema", source)
        self.assertIn("Base.metadata.create_all", source)

    async def test_run_once_processes_one_submission_from_session_factory(self):
        from app import catalyst_intake_worker

        db = FakeSession()
        session_factory = lambda: FakeSessionContext(db)
        process_next = AsyncMock(return_value=True)

        with patch.object(catalyst_intake_worker, "process_next_submission", process_next):
            processed = await catalyst_intake_worker.run_once(
                session_factory=session_factory,
                slack_webhook_url="https://hooks.slack.test/services/test",
                crm_frontend_base_url="https://simple-crm.example.test",
            )

        self.assertTrue(processed)
        process_next.assert_awaited_once_with(
            db,
            slack_webhook_url="https://hooks.slack.test/services/test",
            crm_frontend_base_url="https://simple-crm.example.test",
        )
