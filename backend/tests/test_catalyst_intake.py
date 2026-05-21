import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


if __name__ == "__main__":
    unittest.main()
