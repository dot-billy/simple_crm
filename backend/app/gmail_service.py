import base64
import hashlib
import hmac
import json
import logging
import re
import urllib.parse
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Contact,
    EmailDirection,
    EmailMessage,
    EmailTrackingEvent,
    EmailTrackingEventType,
    GmailSyncState,
)

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def sign_tracking_url(email_id: str, url_b64: str = "") -> str:
    """Generate an HMAC signature for a tracking URL."""
    msg = f"{email_id}:{url_b64}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:16]


def verify_tracking_signature(email_id: str, url_b64: str, sig: str) -> bool:
    """Verify an HMAC signature for a tracking URL."""
    expected = sign_tracking_url(email_id, url_b64)
    return hmac.compare_digest(expected, sig)


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _get_gmail_service(user_email: str):
    """Build a Gmail API service impersonating the given user via domain-wide delegation."""
    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE not configured")
    credentials = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
        subject=user_email,
    )
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _extract_email_address(header_value: str) -> str:
    """Extract email from 'Name <email@example.com>' format."""
    match = re.search(r"<([^>]+)>", header_value)
    return match.group(1).lower() if match else header_value.strip().lower()


def _extract_all_emails(header_value: str) -> list[str]:
    """Extract all email addresses from a comma-separated header."""
    if not header_value:
        return []
    parts = header_value.split(",")
    return [_extract_email_address(p) for p in parts if p.strip()]


def _get_header(headers: list[dict], name: str) -> str:
    """Get a specific header value from Gmail message headers."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body(payload: dict) -> tuple[str, str]:
    """Extract text and HTML body from Gmail message payload."""
    text_body = ""
    html_body = ""

    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        text_body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        html_body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif payload.get("parts"):
        for part in payload["parts"]:
            t, h = _decode_body(part)
            if t and not text_body:
                text_body = t
            if h and not html_body:
                html_body = h

    return text_body, html_body


def inject_tracking_pixel(html_body: str, email_id: str) -> str:
    """Inject a 1x1 tracking pixel into the email HTML body."""
    sig = sign_tracking_url(email_id)
    pixel_url = f"{settings.APP_BASE_URL}/api/email/track/open/{email_id}?sig={sig}"
    pixel_tag = f'<img src="{pixel_url}" width="1" height="1" style="display:none" alt="" />'

    if "</body>" in html_body.lower():
        return html_body.replace("</body>", f"{pixel_tag}</body>")
    return html_body + pixel_tag


def rewrite_links_for_tracking(html_body: str, email_id: str) -> str:
    """Rewrite <a href> links to go through our click tracker."""
    soup = BeautifulSoup(html_body, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        original_url = a_tag["href"]
        if original_url.startswith("mailto:") or original_url.startswith("#"):
            continue
        encoded = base64.urlsafe_b64encode(original_url.encode()).decode()
        sig = sign_tracking_url(email_id, encoded)
        a_tag["href"] = f"{settings.APP_BASE_URL}/api/email/track/click/{email_id}?url={encoded}&sig={sig}"
    return str(soup)


async def match_contact_by_email(db: AsyncSession, email_addr: str) -> uuid.UUID | None:
    """Find a CRM contact matching an email address."""
    result = await db.execute(
        select(Contact).where(Contact.email == email_addr.lower())
    )
    contact = result.scalar_one_or_none()
    return contact.id if contact else None


async def auto_create_contact_from_email(
    db: AsyncSession, email_addr: str, display_name: str = ""
) -> uuid.UUID | None:
    """Auto-create a contact from an inbound email if they don't exist."""
    existing = await match_contact_by_email(db, email_addr)
    if existing:
        return existing

    parts = display_name.split(" ", 1) if display_name else [email_addr.split("@")[0], ""]
    first_name = parts[0] or email_addr.split("@")[0]
    last_name = parts[1] if len(parts) > 1 else ""

    contact = Contact(
        first_name=first_name,
        last_name=last_name,
        email=email_addr.lower(),
        source="gmail_auto",
    )
    db.add(contact)
    await db.flush()
    return contact.id


async def sync_user_gmail(db: AsyncSession, user_email: str, user_id: uuid.UUID) -> int:
    """
    Sync Gmail messages for a user. Uses history-based incremental sync
    after the initial full sync.
    Returns the number of new messages synced.
    """
    service = _get_gmail_service(user_email)

    # Get or create sync state with row-level lock to prevent races
    result = await db.execute(
        select(GmailSyncState)
        .where(GmailSyncState.user_id == user_id)
        .with_for_update(skip_locked=True)
    )
    sync_state = result.scalar_one_or_none()
    if not sync_state:
        sync_state = GmailSyncState(user_id=user_id)
        db.add(sync_state)
        await db.flush()
        # Re-select with lock
        result = await db.execute(
            select(GmailSyncState)
            .where(GmailSyncState.user_id == user_id)
            .with_for_update(skip_locked=True)
        )
        sync_state = result.scalar_one_or_none()
        if not sync_state:
            logger.info("Sync lock contention for %s, skipping", user_email)
            return 0

    if sync_state.is_syncing:
        logger.info("Sync already in progress for %s", user_email)
        return 0

    sync_state.is_syncing = True
    await db.commit()

    synced_count = 0

    try:
        if sync_state.history_id:
            # Incremental sync using history
            synced_count = await _incremental_sync(db, service, sync_state, user_email, user_id)
        else:
            # Initial full sync - last 30 days
            synced_count = await _initial_sync(db, service, sync_state, user_email, user_id)

        sync_state.last_sync_at = datetime.now(timezone.utc)
        sync_state.is_syncing = False
        await db.commit()

    except Exception as e:
        logger.error("Gmail sync failed for %s: %s", user_email, e)
        sync_state.is_syncing = False
        await db.commit()
        raise

    return synced_count


async def _initial_sync(
    db: AsyncSession, service, sync_state: GmailSyncState,
    user_email: str, user_id: uuid.UUID,
) -> int:
    """Full sync: fetch recent messages from Gmail."""
    count = 0
    page_token = None

    for _ in range(10):  # max 10 pages (~1000 messages)
        kwargs = {
            "userId": "me",
            "maxResults": 100,
            "q": "newer_than:30d",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        results = service.users().messages().list(**kwargs).execute()
        messages = results.get("messages", [])

        for msg_ref in messages:
            new = await _process_message(db, service, msg_ref["id"], user_email, user_id)
            if new:
                count += 1

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    # Get the latest history ID
    profile = service.users().getProfile(userId="me").execute()
    sync_state.history_id = profile.get("historyId")

    return count


async def _incremental_sync(
    db: AsyncSession, service, sync_state: GmailSyncState,
    user_email: str, user_id: uuid.UUID,
) -> int:
    """Incremental sync using Gmail history API."""
    count = 0
    page_token = None

    try:
        for _ in range(10):
            kwargs = {
                "userId": "me",
                "startHistoryId": sync_state.history_id,
                "historyTypes": ["messageAdded"],
            }
            if page_token:
                kwargs["pageToken"] = page_token

            results = service.users().history().list(**kwargs).execute()
            histories = results.get("history", [])

            for history in histories:
                for msg_added in history.get("messagesAdded", []):
                    msg_id = msg_added["message"]["id"]
                    new = await _process_message(db, service, msg_id, user_email, user_id)
                    if new:
                        count += 1

            page_token = results.get("nextPageToken")
            if not page_token:
                break

        sync_state.history_id = results.get("historyId", sync_state.history_id)

    except Exception as e:
        if "historyId" in str(e).lower():
            # History expired, do full re-sync
            logger.warning("History expired for %s, doing full re-sync", user_email)
            sync_state.history_id = None
            return await _initial_sync(db, service, sync_state, user_email, user_id)
        raise

    return count


async def _process_message(
    db: AsyncSession, service, msg_id: str, user_email: str, user_id: uuid.UUID
) -> bool:
    """Fetch and store a single Gmail message. Returns True if new."""
    # Check if already stored
    existing = await db.execute(
        select(EmailMessage).where(EmailMessage.gmail_message_id == msg_id)
    )
    if existing.scalar_one_or_none():
        return False

    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers = msg.get("payload", {}).get("headers", [])
    from_header = _get_header(headers, "From")
    to_header = _get_header(headers, "To")
    cc_header = _get_header(headers, "Cc")
    subject = _get_header(headers, "Subject")
    date_header = _get_header(headers, "Date")

    from_email = _extract_email_address(from_header)
    to_emails = _extract_all_emails(to_header)
    cc_emails = _extract_all_emails(cc_header)

    # Determine direction
    direction = EmailDirection.OUTBOUND if from_email == user_email.lower() else EmailDirection.INBOUND

    # Parse date
    internal_date = msg.get("internalDate")
    email_date = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc) if internal_date else datetime.now(timezone.utc)

    # Decode body
    text_body, html_body = _decode_body(msg.get("payload", {}))

    # Match to contact
    match_email = from_email if direction == EmailDirection.INBOUND else (to_emails[0] if to_emails else "")
    contact_id = await match_contact_by_email(db, match_email)

    # Auto-create contact for inbound from unknown senders
    if not contact_id and direction == EmailDirection.INBOUND:
        display_name = from_header.split("<")[0].strip().strip('"') if "<" in from_header else ""
        contact_id = await auto_create_contact_from_email(db, from_email, display_name)

    email = EmailMessage(
        gmail_message_id=msg_id,
        gmail_thread_id=msg.get("threadId"),
        direction=direction,
        from_email=from_email,
        to_emails=json.dumps(to_emails),
        cc_emails=json.dumps(cc_emails) if cc_emails else None,
        subject=subject,
        body_text=text_body,
        body_html=html_body,
        snippet=msg.get("snippet", ""),
        contact_id=contact_id,
        synced_by=user_id,
        email_date=email_date,
    )
    db.add(email)
    await db.flush()

    return True


async def send_email(
    db: AsyncSession,
    user_email: str,
    user_id: uuid.UUID,
    to: list[str],
    subject: str,
    body_html: str,
    cc: list[str] | None = None,
    contact_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    enable_tracking: bool = True,
) -> EmailMessage:
    """Send an email via Gmail API with optional tracking."""
    # Validate email addresses to prevent header injection
    for addr in to:
        if not _EMAIL_RE.match(addr) or '\n' in addr or '\r' in addr:
            raise ValueError(f"Invalid email address: {addr}")
    if cc:
        for addr in cc:
            if not _EMAIL_RE.match(addr) or '\n' in addr or '\r' in addr:
                raise ValueError(f"Invalid email address: {addr}")
    # Strip newlines from subject to prevent header injection
    subject = subject.replace("\n", "").replace("\r", "")

    email_id = uuid.uuid4()

    # Inject tracking
    tracked_html = body_html
    if enable_tracking:
        tracked_html = inject_tracking_pixel(tracked_html, str(email_id))
        tracked_html = rewrite_links_for_tracking(tracked_html, str(email_id))

    # Build MIME message
    mime = MIMEMultipart("alternative")
    mime["From"] = user_email
    mime["To"] = ", ".join(to)
    if cc:
        mime["Cc"] = ", ".join(cc)
    mime["Subject"] = subject

    # Plain text fallback
    soup = BeautifulSoup(tracked_html, "html.parser")
    plain_text = soup.get_text(separator="\n")
    mime.attach(MIMEText(plain_text, "plain"))
    mime.attach(MIMEText(tracked_html, "html"))

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

    # Send via Gmail API
    service = _get_gmail_service(user_email)
    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()

    # Auto-match contact if not provided
    if not contact_id and to:
        contact_id = await match_contact_by_email(db, to[0])

    # Store in DB
    email_msg = EmailMessage(
        id=email_id,
        gmail_message_id=sent["id"],
        gmail_thread_id=sent.get("threadId"),
        direction=EmailDirection.OUTBOUND,
        from_email=user_email,
        to_emails=json.dumps(to),
        cc_emails=json.dumps(cc) if cc else None,
        subject=subject,
        body_text=plain_text,
        body_html=body_html,
        contact_id=contact_id,
        deal_id=deal_id,
        synced_by=user_id,
        has_tracking_pixel=enable_tracking,
        email_date=datetime.now(timezone.utc),
    )
    db.add(email_msg)

    # Record sent event
    tracking_event = EmailTrackingEvent(
        email_id=email_id,
        event_type=EmailTrackingEventType.SENT,
    )
    db.add(tracking_event)

    await db.commit()
    await db.refresh(email_msg)

    return email_msg
