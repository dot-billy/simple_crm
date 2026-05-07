import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

import enum


# --- Enums ---

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


class DealStage(str, enum.Enum):
    LEAD = "lead"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class ActivityType(str, enum.Enum):
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    NOTE = "note"
    OTHER = "other"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskRecurrence(str, enum.Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class EmailDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EmailTrackingEventType(str, enum.Enum):
    SENT = "sent"
    OPENED = "opened"
    CLICKED = "clicked"


class CustomFieldType(str, enum.Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    SELECT = "select"


class AccountType(str, enum.Enum):
    HUMAN = "human"
    SERVICE = "service"


class APIKeyScope(str, enum.Enum):
    CONTACTS_READ = "contacts:read"
    CONTACTS_WRITE = "contacts:write"
    COMPANIES_READ = "companies:read"
    COMPANIES_WRITE = "companies:write"
    DEALS_READ = "deals:read"
    DEALS_WRITE = "deals:write"
    ACTIVITIES_READ = "activities:read"
    ACTIVITIES_WRITE = "activities:write"
    TASKS_READ = "tasks:read"
    TASKS_WRITE = "tasks:write"
    TAGS_READ = "tags:read"
    TAGS_WRITE = "tags:write"
    SEARCH_READ = "search:read"
    DASHBOARD_READ = "dashboard:read"
    EMAIL_READ = "email:read"
    EMAIL_WRITE = "email:write"
    NOTIFICATIONS_READ = "notifications:read"
    NOTIFICATIONS_WRITE = "notifications:write"
    CUSTOM_FIELDS_READ = "custom_fields:read"
    CUSTOM_FIELDS_WRITE = "custom_fields:write"
    AUDIT_READ = "audit:read"
    AGENT_BULK_UPLOAD = "agent:bulk_upload"
    AGENT_RESEARCH = "agent:research"
    ALL = "*"


# --- Association tables ---

contact_tags = Table(
    "contact_tags",
    Base.metadata,
    Column("contact_id", UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

company_tags = Table(
    "company_tags",
    Base.metadata,
    Column("company_id", UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

deal_tags = Table(
    "deal_tags",
    Base.metadata,
    Column("deal_id", UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


# --- Models ---

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.USER)
    account_type = Column(SAEnum(AccountType), nullable=False, default=AccountType.HUMAN)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contacts = relationship("Contact", back_populates="owner")
    deals = relationship("Deal", back_populates="owner")
    tasks = relationship("Task", back_populates="assigned_to_user", foreign_keys="Task.assigned_to")
    activities = relationship("Activity", back_populates="created_by_user")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    email = Column(String(255), index=True)
    phone = Column(String(50))
    job_title = Column(String(255))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="contacts")
    owner = relationship("User", back_populates="contacts")
    tags = relationship("Tag", secondary=contact_tags, back_populates="contacts")
    activities = relationship("Activity", back_populates="contact")
    deals = relationship("Deal", back_populates="contact")
    tasks = relationship("Task", back_populates="contact")
    custom_field_values = relationship("CustomFieldValue", back_populates="contact")


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    domain = Column(String(255))
    industry = Column(String(255))
    size = Column(String(50))
    address = Column(Text)
    phone = Column(String(50))
    notes = Column(Text)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contacts = relationship("Contact", back_populates="company")
    owner = relationship("User")
    tags = relationship("Tag", secondary=company_tags, back_populates="companies")
    deals = relationship("Deal", back_populates="company")
    custom_field_values = relationship("CustomFieldValue", back_populates="company")


class Deal(Base):
    __tablename__ = "deals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    value = Column(Float, default=0)
    currency = Column(String(10), default="USD")
    stage = Column(SAEnum(DealStage), nullable=False, default=DealStage.LEAD)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expected_close_date = Column(DateTime(timezone=True))
    notes = Column(Text)
    probability = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contact = relationship("Contact", back_populates="deals")
    company = relationship("Company", back_populates="deals")
    owner = relationship("User", back_populates="deals")
    tags = relationship("Tag", secondary=deal_tags, back_populates="deals")
    activities = relationship("Activity", back_populates="deal")
    tasks = relationship("Task", back_populates="deal")
    custom_field_values = relationship("CustomFieldValue", back_populates="deal")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(SAEnum(ActivityType), nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activity_date = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    contact = relationship("Contact", back_populates="activities")
    deal = relationship("Deal", back_populates="activities")
    created_by_user = relationship("User", back_populates="activities")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(SAEnum(TaskStatus), nullable=False, default=TaskStatus.TODO)
    due_date = Column(DateTime(timezone=True))
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), nullable=True)
    reminder_minutes_before = Column(Integer, nullable=True)
    recurrence_rule = Column(SAEnum(TaskRecurrence), nullable=False, default=TaskRecurrence.NONE)
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    assigned_to_user = relationship("User", back_populates="tasks")
    contact = relationship("Contact", back_populates="tasks")
    deal = relationship("Deal", back_populates="tasks")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False, index=True)
    color = Column(String(7), default="#6366f1")

    contacts = relationship("Contact", secondary=contact_tags, back_populates="tags")
    companies = relationship("Company", secondary=company_tags, back_populates="tags")
    deals = relationship("Deal", secondary=deal_tags, back_populates="tags")


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gmail_message_id = Column(String(255), unique=True, nullable=False, index=True)
    gmail_thread_id = Column(String(255), index=True)
    direction = Column(SAEnum(EmailDirection), nullable=False)
    from_email = Column(String(255), nullable=False)
    to_emails = Column(Text, nullable=False)  # JSON array
    cc_emails = Column(Text)  # JSON array
    subject = Column(String(500))
    body_text = Column(Text)
    body_html = Column(Text)
    snippet = Column(Text)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), nullable=True)
    synced_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    has_tracking_pixel = Column(Boolean, default=False)
    email_date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    contact = relationship("Contact")
    deal = relationship("Deal")
    synced_by_user = relationship("User")
    tracking_events = relationship("EmailTrackingEvent", back_populates="email", cascade="all, delete-orphan")


class EmailTrackingEvent(Base):
    __tablename__ = "email_tracking_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(UUID(as_uuid=True), ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(SAEnum(EmailTrackingEventType), nullable=False)
    url = Column(Text)  # for click events
    ip_address = Column(String(45))
    user_agent = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    email = relationship("EmailMessage", back_populates="tracking_events")


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    creator = relationship("User")


class GmailSyncState(Base):
    __tablename__ = "gmail_sync_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    history_id = Column(String(50))  # Gmail history ID for incremental sync
    last_sync_at = Column(DateTime(timezone=True))
    is_syncing = Column(Boolean, default=False)

    user = relationship("User")


class CustomFieldDefinition(Base):
    __tablename__ = "custom_field_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    field_type = Column(SAEnum(CustomFieldType), nullable=False)
    entity_type = Column(String(50), nullable=False)  # "contact", "company", "deal"
    options = Column(Text)  # JSON array for select options
    is_required = Column(Boolean, default=False)
    validation_rule = Column(Text, nullable=True)  # JSON: {regex, min, max}
    default_value = Column(Text, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    field_id = Column(UUID(as_uuid=True), ForeignKey("custom_field_definitions.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True)
    value = Column(Text)

    field = relationship("CustomFieldDefinition")
    contact = relationship("Contact", back_populates="custom_field_values")
    company = relationship("Company", back_populates="custom_field_values")
    deal = relationship("Deal", back_populates="custom_field_values")


# --- Audit ---

class AuditEventType(str, enum.Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    PASSWORD_CHANGED = "password_changed"
    SERVICE_ACCOUNT_CREATED = "service_account_created"
    SERVICE_ACCOUNT_UPDATED = "service_account_updated"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    BULK_IMPORT = "bulk_import"
    AGENT_RESEARCH = "agent_research"
    CONTACT_CREATED = "contact_created"
    CONTACT_UPDATED = "contact_updated"
    CONTACT_DELETED = "contact_deleted"
    COMPANY_CREATED = "company_created"
    COMPANY_UPDATED = "company_updated"
    COMPANY_DELETED = "company_deleted"
    DEAL_CREATED = "deal_created"
    DEAL_UPDATED = "deal_updated"
    DEAL_DELETED = "deal_deleted"
    DEAL_STAGE_CHANGED = "deal_stage_changed"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    ACTIVITY_CREATED = "activity_created"
    ACTIVITY_DELETED = "activity_deleted"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(SAEnum(AuditEventType), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    detail = Column(Text, nullable=True)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    entity_type = Column(String(50), nullable=True, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    before_state = Column(Text, nullable=True)
    after_state = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# --- Saved Views ---

class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)  # contact / company / deal / task
    name = Column(String(255), nullable=False)
    filters = Column(Text, nullable=False)  # JSON string of filter state
    is_shared = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")


# --- Notifications ---

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    entity_type = Column(String(50), nullable=True)  # "deal", "task", "contact"
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User")


# --- API Keys ---

class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    key_prefix = Column(String(8), nullable=False, index=True)
    key_hash = Column(String(255), nullable=False)
    scopes = Column(Text, nullable=True)  # JSON array of scope strings; NULL = full access
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    rate_limit_per_minute = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
