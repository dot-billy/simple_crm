import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import app.catalyst_intake as catalyst_intake
from app.catalyst_intake import (
    CATALYST_INTAKE_SUBJECT,
    build_slack_payload,
    is_catalyst_intake_activity,
    notify_catalyst_intake_slack,
)


class CatalystIntakeTests(unittest.TestCase):
    def test_is_catalyst_intake_activity_matches_only_exact_subject(self):
        self.assertTrue(is_catalyst_intake_activity(SimpleNamespace(subject=CATALYST_INTAKE_SUBJECT)))
        self.assertFalse(is_catalyst_intake_activity(SimpleNamespace(subject="Catalyst managed intake request ")))
        self.assertFalse(is_catalyst_intake_activity(SimpleNamespace(subject="Managed intake request")))
        self.assertFalse(is_catalyst_intake_activity(SimpleNamespace(subject=None)))

    def test_build_slack_payload_includes_intake_details_and_deal_link(self):
        activity = SimpleNamespace(
            description="\n".join(
                [
                    "Selected path: Managed service",
                    "Key person: Avery Stone <avery@example.com>",
                    "Company: Acme Networks",
                    "Expected nodes/sites: 75 nodes / 4 sites",
                    "Timeline: Next month",
                    "Notes: Needs CISO review before rollout",
                ]
            )
        )
        deal = SimpleNamespace(id="deal-123")
        contact = SimpleNamespace(first_name="Fallback", last_name="Person", email="fallback@example.com")
        company = SimpleNamespace(name="Fallback Company")

        payload = build_slack_payload(activity, deal, contact, company, "https://crm.example.com/")

        self.assertEqual(["text"], list(payload.keys()))
        self.assertTrue(payload["text"].startswith("*New Catalyst managed intake*"))
        self.assertIn("Selected path: Managed service", payload["text"])
        self.assertIn("Company: Acme Networks", payload["text"])
        self.assertIn("Key person: Avery Stone <avery@example.com>", payload["text"])
        self.assertIn("Expected nodes/sites: 75 nodes / 4 sites", payload["text"])
        self.assertIn("Timeline: Next month", payload["text"])
        self.assertIn("Notes: Needs CISO review before rollout", payload["text"])
        self.assertIn("CRM deal: https://crm.example.com/deals/deal-123", payload["text"])

    def test_build_slack_payload_uses_contact_and_company_fallbacks(self):
        activity = SimpleNamespace(
            description="\n".join(
                [
                    "Selected path: Guided setup",
                    "Expected nodes/sites: 12 nodes / 2 sites",
                    "Timeline: This quarter",
                    "Notes: Prefers phased deployment",
                ]
            )
        )
        deal = SimpleNamespace(id="deal-456")
        contact = SimpleNamespace(first_name="Jamie", last_name="Mills", email="jamie@example.com")
        company = SimpleNamespace(name="Fallback Co")

        payload = build_slack_payload(activity, deal, contact, company, "")

        self.assertIn("Company: Fallback Co", payload["text"])
        self.assertIn("Key person: Jamie Mills <jamie@example.com>", payload["text"])
        self.assertIn("CRM deal: /deals/deal-456", payload["text"])


class CatalystIntakeSlackTests(unittest.IsolatedAsyncioTestCase):
    async def test_notify_catalyst_intake_slack_noops_when_webhook_url_empty(self):
        post_json = AsyncMock()

        await notify_catalyst_intake_slack(
            "",
            SimpleNamespace(description="Selected path: Managed service"),
            SimpleNamespace(id="deal-123"),
            None,
            None,
            "https://crm.example.com",
            post_json=post_json,
        )

        post_json.assert_not_awaited()

    async def test_notify_catalyst_intake_slack_swallows_delivery_failures(self):
        post_json = AsyncMock(side_effect=RuntimeError("slack is unavailable"))

        with self.assertLogs("app.catalyst_intake", level="ERROR") as logs:
            await notify_catalyst_intake_slack(
                "https://hooks.slack.test/services/test",
                SimpleNamespace(description="Selected path: Managed service"),
                SimpleNamespace(id="deal-123"),
                None,
                None,
                "https://crm.example.com",
                post_json=post_json,
            )

        post_json.assert_awaited_once()
        self.assertIn("Failed to deliver Catalyst intake Slack notification", logs.output[0])

    async def test_notify_catalyst_intake_slack_logs_sanitized_delivery_failure(self):
        fake_webhook_url = "https://hooks.slack.test/services/T000/B000/secret-token"
        submitted_company = "Acme Networks"
        submitted_email = "avery@example.com"
        submitted_notes = "Needs CISO review before rollout"
        post_json = AsyncMock(
            side_effect=RuntimeError(
                f"post failed to {fake_webhook_url} for {submitted_company} {submitted_email}: {submitted_notes}"
            )
        )

        with self.assertLogs("app.catalyst_intake", level="ERROR") as logs:
            await notify_catalyst_intake_slack(
                fake_webhook_url,
                SimpleNamespace(
                    description="\n".join(
                        [
                            "Company: Acme Networks",
                            "Key person: Avery Stone <avery@example.com>",
                            "Notes: Needs CISO review before rollout",
                        ]
                    )
                ),
                SimpleNamespace(id="deal-123"),
                SimpleNamespace(first_name="Avery", last_name="Stone", email=submitted_email),
                SimpleNamespace(name=submitted_company),
                "https://crm.example.com",
                post_json=post_json,
            )

        log_output = "\n".join(logs.output)
        self.assertIn("Failed to deliver Catalyst intake Slack notification", log_output)
        self.assertNotIn(fake_webhook_url, log_output)
        self.assertNotIn(submitted_company, log_output)
        self.assertNotIn(submitted_email, log_output)
        self.assertNotIn(submitted_notes, log_output)
        self.assertNotIn("post failed", log_output)

    async def test_post_slack_json_suppresses_transport_logs_that_include_webhook_url(self):
        fake_webhook_url = "https://hooks.slack.test/services/T000/B000/secret-token"
        real_async_client = httpx.AsyncClient

        def handle_request(request):
            return httpx.Response(200, request=request)

        def async_client_factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handle_request)
            return real_async_client(*args, **kwargs)

        with patch.object(catalyst_intake.httpx, "AsyncClient", side_effect=async_client_factory):
            with self.assertNoLogs("httpx", level="INFO"):
                with self.assertNoLogs("httpcore", level="INFO"):
                    await catalyst_intake._post_slack_json(fake_webhook_url, {"text": "hello"})


class CatalystIntakeSchedulingTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("SECRET_KEY", "unit-test-secret-key")

    def _activities_module(self):
        return importlib.import_module("app.routes.activities")

    def test_schedule_catalyst_intake_notification_captures_values_for_background_delivery(self):
        activities = self._activities_module()
        schedule_notification = getattr(activities, "_schedule_catalyst_intake_notification", None)
        self.assertIsNotNone(schedule_notification, "activities route should expose a private scheduling helper")
        background_tasks = _RecordingBackgroundTasks()
        company = SimpleNamespace(name="Acme Networks")
        contact = SimpleNamespace(first_name="Avery", last_name="Stone", email="avery@example.com")
        deal = SimpleNamespace(id="deal-123", company=company)
        activity = SimpleNamespace(
            subject=CATALYST_INTAKE_SUBJECT,
            deal_id="deal-123",
            description="\n".join(
                [
                    "Company: Acme Networks",
                    "Key person: Avery Stone <avery@example.com>",
                    "Notes: Needs CISO review before rollout",
                ]
            ),
            deal=deal,
            contact=contact,
        )

        scheduled = schedule_notification(
            background_tasks,
            activity,
            slack_webhook_url="https://hooks.slack.test/services/test",
            crm_frontend_base_url="https://crm.example.com",
        )

        self.assertTrue(scheduled)
        self.assertEqual(1, len(background_tasks.calls))
        scheduled_func, scheduled_args, scheduled_kwargs = background_tasks.calls[0]
        self.assertIs(scheduled_func, activities.notify_catalyst_intake_slack)
        self.assertEqual((), scheduled_args)
        self.assertEqual("https://hooks.slack.test/services/test", scheduled_kwargs["webhook_url"])
        self.assertEqual("https://crm.example.com", scheduled_kwargs["crm_frontend_base_url"])
        self.assertIsNot(activity, scheduled_kwargs["activity"])
        self.assertIsNot(deal, scheduled_kwargs["deal"])
        self.assertIsNot(contact, scheduled_kwargs["contact"])
        self.assertIsNot(company, scheduled_kwargs["company"])

        activity.description = "Company: Mutated Company"
        deal.id = "mutated-deal"
        contact.email = "mutated@example.com"
        company.name = "Mutated Company"

        payload = build_slack_payload(
            scheduled_kwargs["activity"],
            scheduled_kwargs["deal"],
            scheduled_kwargs["contact"],
            scheduled_kwargs["company"],
            scheduled_kwargs["crm_frontend_base_url"],
        )
        self.assertIn("Company: Acme Networks", payload["text"])
        self.assertIn("Key person: Avery Stone <avery@example.com>", payload["text"])
        self.assertIn("Notes: Needs CISO review before rollout", payload["text"])
        self.assertIn("CRM deal: https://crm.example.com/deals/deal-123", payload["text"])

    def test_schedule_catalyst_intake_notification_skips_non_intake_or_missing_deal(self):
        activities = self._activities_module()
        schedule_notification = getattr(activities, "_schedule_catalyst_intake_notification", None)
        self.assertIsNotNone(schedule_notification, "activities route should expose a private scheduling helper")

        for activity in [
            SimpleNamespace(subject="Regular call", deal_id="deal-123", deal=SimpleNamespace(id="deal-123")),
            SimpleNamespace(subject=CATALYST_INTAKE_SUBJECT, deal_id=None, deal=None),
        ]:
            background_tasks = _RecordingBackgroundTasks()

            scheduled = schedule_notification(
                background_tasks,
                activity,
                slack_webhook_url="https://hooks.slack.test/services/test",
                crm_frontend_base_url="https://crm.example.com",
            )

            self.assertFalse(scheduled)
            self.assertEqual([], background_tasks.calls)


class _RecordingBackgroundTasks:
    def __init__(self):
        self.calls = []

    def add_task(self, func, *args, **kwargs):
        self.calls.append((func, args, kwargs))


if __name__ == "__main__":
    unittest.main()
