import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx


CATALYST_INTAKE_SUBJECT = "Catalyst managed intake request"

logger = logging.getLogger(__name__)

SlackPayload = dict[str, str]
PostSlackJson = Callable[[str, SlackPayload], Awaitable[None]]


def is_catalyst_intake_activity(activity: Any) -> bool:
    return getattr(activity, "subject", None) == CATALYST_INTAKE_SUBJECT


def build_slack_payload(activity: Any, deal: Any, contact: Any, company: Any, crm_frontend_base_url: str) -> SlackPayload:
    fields = _parse_description_fields(getattr(activity, "description", None))
    deal_link = _build_deal_link(getattr(deal, "id", ""), crm_frontend_base_url)

    text_lines = [
        "*New Catalyst managed intake*",
        f"Selected path: {_display_value(fields.get('Selected path'))}",
        f"Company: {_display_value(fields.get('Company') or _company_name(company))}",
        f"Key person: {_display_value(fields.get('Key person') or _contact_name(contact))}",
        f"Expected nodes/sites: {_display_value(fields.get('Expected nodes/sites'))}",
        f"Timeline: {_display_value(fields.get('Timeline'))}",
        f"Notes: {_display_value(fields.get('Notes'))}",
        f"CRM deal: {deal_link}",
    ]
    return {"text": "\n".join(text_lines)}


async def notify_catalyst_intake_slack(
    webhook_url: str,
    activity: Any,
    deal: Any,
    contact: Any,
    company: Any,
    crm_frontend_base_url: str,
    post_json: PostSlackJson | None = None,
) -> None:
    webhook_url = (webhook_url or "").strip()
    if not webhook_url:
        return

    if post_json is None:
        post_json = _post_slack_json

    payload = build_slack_payload(activity, deal, contact, company, crm_frontend_base_url)
    try:
        await post_json(webhook_url, payload)
    except Exception as exc:
        status_code = _delivery_failure_status_code(exc)
        if status_code is None:
            logger.error(
                "Failed to deliver Catalyst intake Slack notification (error_type=%s)",
                type(exc).__name__,
            )
        else:
            logger.error(
                "Failed to deliver Catalyst intake Slack notification (error_type=%s, status_code=%s)",
                type(exc).__name__,
                status_code,
            )


async def _post_slack_json(webhook_url: str, payload: SlackPayload) -> None:
    _suppress_slack_transport_info_logs()
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()


def _suppress_slack_transport_info_logs() -> None:
    # httpx/httpcore INFO request logs include full URLs; Slack webhook URLs are secrets.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _delivery_failure_status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _parse_description_fields(description: str | None) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in (description or "").splitlines():
        label, separator, value = line.partition(":")
        if separator:
            fields[label.strip()] = value.strip()
    return fields


def _build_deal_link(deal_id: Any, crm_frontend_base_url: str) -> str:
    path = f"/deals/{deal_id}"
    base_url = (crm_frontend_base_url or "").rstrip("/")
    if not base_url:
        return path
    return f"{base_url}{path}"


def _company_name(company: Any) -> str:
    return getattr(company, "name", "") or ""


def _contact_name(contact: Any) -> str:
    if contact is None:
        return ""

    first_name = getattr(contact, "first_name", "") or ""
    last_name = getattr(contact, "last_name", "") or ""
    email = getattr(contact, "email", "") or ""
    name = " ".join(part for part in [first_name, last_name] if part)
    if name and email:
        return f"{name} <{email}>"
    return name or email


def _escape_slack_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _display_value(value: str | None) -> str:
    if not value:
        return "Not provided"
    return _escape_slack_text(value)
