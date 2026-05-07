from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import AccountType, ActivityType, CustomFieldType, DealStage, EmailDirection, EmailTrackingEventType, TaskRecurrence, TaskStatus, UserRole


# --- Auth ---

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserRead"


# --- User ---

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(max_length=255)
    password: str = Field(min_length=10, max_length=128)
    role: UserRole = UserRole.USER

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain an uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain a digit")
        return v


class UserRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain an uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain a digit")
        return v


class AuditLogRead(BaseModel):
    id: UUID
    event_type: str
    user_id: UUID | None = None
    target_user_id: UUID | None = None
    email: str | None = None
    ip_address: str | None = None
    detail: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAuditLogResponse(BaseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    per_page: int
    pages: int


# --- Tag ---

class TagCreate(BaseModel):
    name: str = Field(max_length=100)
    color: str = Field(default="#6366f1", max_length=7)


class TagRead(BaseModel):
    id: UUID
    name: str
    color: str

    model_config = {"from_attributes": True}


# --- Contact ---

class ContactCreate(BaseModel):
    first_name: str = Field(max_length=255)
    last_name: str = Field(max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    job_title: str | None = Field(None, max_length=255)
    company_id: UUID | None = None
    source: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=5000)
    tag_ids: list[UUID] = []


class ContactRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None
    company_id: UUID | None = None
    owner_id: UUID | None = None
    source: str | None = None
    notes: str | None = None
    tags: list[TagRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactUpdate(BaseModel):
    first_name: str | None = Field(None, max_length=255)
    last_name: str | None = Field(None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    job_title: str | None = Field(None, max_length=255)
    company_id: UUID | None = None
    source: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=5000)
    tag_ids: list[UUID] | None = None


# --- Company ---

class CompanyCreate(BaseModel):
    name: str = Field(max_length=255)
    domain: str | None = Field(None, max_length=255)
    industry: str | None = Field(None, max_length=255)
    size: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=1000)
    phone: str | None = Field(None, max_length=50)
    notes: str | None = Field(None, max_length=5000)
    tag_ids: list[UUID] = []


class CompanyRead(BaseModel):
    id: UUID
    name: str
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    address: str | None = None
    phone: str | None = None
    notes: str | None = None
    owner_id: UUID | None = None
    tags: list[TagRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    domain: str | None = Field(None, max_length=255)
    industry: str | None = Field(None, max_length=255)
    size: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=1000)
    phone: str | None = Field(None, max_length=50)
    notes: str | None = Field(None, max_length=5000)
    tag_ids: list[UUID] | None = None


# --- Deal ---

class BulkAction(BaseModel):
    action: str  # delete | add_tag | remove_tag | set_owner | set_stage | set_status
    ids: list[UUID] = Field(min_length=1, max_length=500)
    tag_id: UUID | None = None
    owner_id: UUID | None = None
    stage: DealStage | None = None
    status: TaskStatus | None = None


_STAGE_DEFAULT_PROBABILITY = {
    "lead": 10.0,
    "qualified": 25.0,
    "proposal": 50.0,
    "negotiation": 75.0,
    "closed_won": 100.0,
    "closed_lost": 0.0,
}


class DealCreate(BaseModel):
    title: str = Field(max_length=255)
    value: float = 0
    currency: str = Field(default="USD", max_length=10)
    stage: DealStage = DealStage.LEAD
    contact_id: UUID | None = None
    company_id: UUID | None = None
    expected_close_date: datetime | None = None
    notes: str | None = Field(None, max_length=5000)
    probability: float | None = Field(None, ge=0, le=100)
    tag_ids: list[UUID] = []


class DealRead(BaseModel):
    id: UUID
    title: str
    value: float
    currency: str
    stage: DealStage
    contact_id: UUID | None = None
    company_id: UUID | None = None
    owner_id: UUID | None = None
    expected_close_date: datetime | None = None
    notes: str | None = None
    probability: float | None = None
    tags: list[TagRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DealUpdate(BaseModel):
    title: str | None = Field(None, max_length=255)
    value: float | None = None
    currency: str | None = Field(None, max_length=10)
    stage: DealStage | None = None
    contact_id: UUID | None = None
    company_id: UUID | None = None
    owner_id: UUID | None = None
    expected_close_date: datetime | None = None
    notes: str | None = Field(None, max_length=5000)
    probability: float | None = Field(None, ge=0, le=100)
    tag_ids: list[UUID] | None = None


class DealStageUpdate(BaseModel):
    stage: DealStage


# --- Activity ---

class ActivityCreate(BaseModel):
    type: ActivityType
    subject: str = Field(max_length=255)
    description: str | None = Field(None, max_length=5000)
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    activity_date: datetime | None = None


class ActivityRead(BaseModel):
    id: UUID
    type: ActivityType
    subject: str
    description: str | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    created_by: UUID | None = None
    activity_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Task ---

class TaskCreate(BaseModel):
    title: str = Field(max_length=255)
    description: str | None = Field(None, max_length=5000)
    status: TaskStatus = TaskStatus.TODO
    due_date: datetime | None = None
    assigned_to: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    reminder_minutes_before: int | None = Field(None, ge=0)
    recurrence_rule: TaskRecurrence = TaskRecurrence.NONE
    parent_task_id: UUID | None = None


class TaskRead(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    status: TaskStatus
    due_date: datetime | None = None
    assigned_to: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    reminder_minutes_before: int | None = None
    recurrence_rule: TaskRecurrence = TaskRecurrence.NONE
    parent_task_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskUpdate(BaseModel):
    title: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=5000)
    status: TaskStatus | None = None
    due_date: datetime | None = None
    assigned_to: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    reminder_minutes_before: int | None = Field(None, ge=0)
    recurrence_rule: TaskRecurrence | None = None


# --- Custom Fields ---

class CustomFieldDefinitionCreate(BaseModel):
    name: str = Field(max_length=255)
    field_type: CustomFieldType
    entity_type: str = Field(max_length=50)  # "contact" or "company"
    options: str | None = Field(None, max_length=5000)
    is_required: bool = False


class CustomFieldDefinitionRead(BaseModel):
    id: UUID
    name: str
    field_type: CustomFieldType
    entity_type: str
    options: str | None = None
    is_required: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomFieldValueCreate(BaseModel):
    field_id: UUID
    contact_id: UUID | None = None
    company_id: UUID | None = None
    value: str = Field(max_length=10000)


class CustomFieldValueRead(BaseModel):
    id: UUID
    field_id: UUID
    contact_id: UUID | None = None
    company_id: UUID | None = None
    value: str | None = None

    model_config = {"from_attributes": True}


# --- Dashboard ---

class WeeklyDealCount(BaseModel):
    week: str
    count: int


class DashboardCharts(BaseModel):
    deals_over_time: list[WeeklyDealCount]
    revenue_by_stage: dict[str, float]
    contacts_by_source: dict[str, int]
    task_completion: dict[str, int]


class DashboardStats(BaseModel):
    total_contacts: int
    total_companies: int
    total_deals: int
    total_deal_value: float
    deals_by_stage: dict[str, int]
    recent_activities: list[ActivityRead]
    upcoming_tasks: list[TaskRead]
    charts: DashboardCharts


# --- Email / Gmail ---

class EmailMessageRead(BaseModel):
    id: UUID
    gmail_message_id: str
    gmail_thread_id: str | None = None
    direction: EmailDirection
    from_email: str
    to_emails: str  # JSON array
    cc_emails: str | None = None
    subject: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    snippet: str | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    synced_by: UUID | None = None
    has_tracking_pixel: bool = False
    email_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class EmailSendRequest(BaseModel):
    to: list[EmailStr]
    subject: str = Field(max_length=500)
    body_html: str = Field(max_length=500000)
    cc: list[EmailStr] | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    enable_tracking: bool = True


class EmailTrackingEventRead(BaseModel):
    id: UUID
    email_id: UUID
    event_type: EmailTrackingEventType
    url: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EmailTrackingStats(BaseModel):
    total_sent: int
    total_opened: int
    total_clicked: int
    open_rate: float
    click_rate: float


class EmailTemplateCreate(BaseModel):
    name: str = Field(max_length=255)
    subject: str = Field(max_length=500)
    body_html: str = Field(max_length=500000)


class EmailTemplateRead(BaseModel):
    id: UUID
    name: str
    subject: str
    body_html: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmailTemplateUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    subject: str | None = Field(None, max_length=500)
    body_html: str | None = Field(None, max_length=500000)


class GmailSyncStatus(BaseModel):
    is_configured: bool
    last_sync_at: datetime | None = None
    is_syncing: bool = False
    history_id: str | None = None


# --- Search ---

class SearchResults(BaseModel):
    contacts: list[ContactRead] = []
    companies: list[CompanyRead] = []
    deals: list[DealRead] = []
    tasks: list[TaskRead] = []


# --- Timeline ---

class TimelineItem(BaseModel):
    id: UUID
    type: str  # "activity", "email", "task"
    title: str
    description: str | None = None
    date: datetime
    metadata: dict = {}


class PaginatedTimelineResponse(BaseModel):
    items: list[TimelineItem]
    total: int
    page: int
    per_page: int
    pages: int


# --- Pagination ---

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    per_page: int
    pages: int


# --- Notifications ---

class NotificationRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    message: str | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None
    is_read: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class PaginatedNotificationResponse(BaseModel):
    items: list[NotificationRead]
    total: int
    page: int
    per_page: int
    pages: int
    unread_count: int


# --- API Keys ---

class APIKeyCreate(BaseModel):
    name: str = Field(max_length=255)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    scopes: list[str] | None = None


class APIKeyRead(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str] | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    rate_limit_per_minute: int | None = None
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}

    @field_validator("scopes", mode="before")
    @classmethod
    def parse_scopes_json(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v


class APIKeyCreated(BaseModel):
    id: UUID
    name: str
    key: str  # full key, shown only once
    key_prefix: str
    scopes: list[str] | None = None
    expires_at: datetime | None = None
    created_at: datetime


# --- Service Accounts ---

class ServiceAccountCreate(BaseModel):
    name: str = Field(max_length=255)
    description: str | None = Field(None, max_length=1000)


class ServiceAccountRead(BaseModel):
    id: UUID
    full_name: str
    email: str
    description: str | None = None
    account_type: AccountType
    is_active: bool
    created_at: datetime
    key_count: int = 0
    model_config = {"from_attributes": True}


class ServiceAccountUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=1000)
    is_active: bool | None = None


class ScopedAPIKeyCreate(BaseModel):
    name: str = Field(max_length=255)
    scopes: list[str]
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=1000)


# --- Bulk Operations ---

class BulkContactItem(BaseModel):
    first_name: str = Field(max_length=255)
    last_name: str = Field(max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    job_title: str | None = Field(None, max_length=255)
    company_name: str | None = None
    source: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=5000)


class BulkContactUpload(BaseModel):
    contacts: list[BulkContactItem] = Field(max_length=500)
    dedupe_on_email: bool = True
    default_source: str | None = "agent_import"


class BulkCompanyItem(BaseModel):
    name: str = Field(max_length=255)
    domain: str | None = Field(None, max_length=255)
    industry: str | None = Field(None, max_length=255)
    size: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=1000)
    phone: str | None = Field(None, max_length=50)
    notes: str | None = Field(None, max_length=5000)


class BulkCompanyUpload(BaseModel):
    companies: list[BulkCompanyItem] = Field(max_length=500)
    dedupe_on_domain: bool = True


class BulkDealItem(BaseModel):
    title: str = Field(max_length=255)
    value: float = 0
    currency: str = Field(default="USD", max_length=10)
    stage: DealStage = DealStage.LEAD
    contact_email: str | None = None
    company_name: str | None = None
    expected_close_date: datetime | None = None
    notes: str | None = Field(None, max_length=5000)


class BulkDealUpload(BaseModel):
    deals: list[BulkDealItem] = Field(max_length=500)


class BulkResultItem(BaseModel):
    index: int
    status: str  # "created", "skipped_duplicate", "error"
    id: UUID | None = None
    error: str | None = None


class BulkUploadResult(BaseModel):
    total: int
    created: int
    skipped: int
    errors: int
    results: list[BulkResultItem]


# --- Agent Research ---

class CompanyResearchResult(BaseModel):
    company: CompanyRead | None = None
    contacts: list[ContactRead] = []
    deals: list[DealRead] = []
    recent_activities: list[ActivityRead] = []


class ContactResearchResult(BaseModel):
    contact: ContactRead | None = None
    company: CompanyRead | None = None
    deals: list[DealRead] = []
    recent_activities: list[ActivityRead] = []


class AgentWhoAmI(BaseModel):
    service_account_id: UUID
    name: str
    email: str
    account_type: str
    scopes: list[str] | None = None
    rate_limit_per_minute: int | None = None


# --- Profile / Dossier ---

class ContactStats(BaseModel):
    total_deals: int = 0
    total_deal_value: float = 0.0
    open_deals: int = 0
    won_deals: int = 0
    total_activities: int = 0
    total_tasks: int = 0
    open_tasks: int = 0
    last_activity_date: datetime | None = None


class ContactProfile(BaseModel):
    contact: ContactRead
    company: CompanyRead | None = None
    deals: list[DealRead] = []
    tasks: list[TaskRead] = []
    custom_fields: list[CustomFieldValueRead] = []
    custom_field_definitions: list[CustomFieldDefinitionRead] = []
    stats: ContactStats
    model_config = {"from_attributes": True}


class CompanyStats(BaseModel):
    total_contacts: int = 0
    total_deals: int = 0
    total_deal_value: float = 0.0
    open_deals: int = 0
    won_deals: int = 0
    total_activities: int = 0
    last_activity_date: datetime | None = None


class CompanyProfile(BaseModel):
    company: CompanyRead
    contacts: list[ContactRead] = []
    deals: list[DealRead] = []
    custom_fields: list[CustomFieldValueRead] = []
    custom_field_definitions: list[CustomFieldDefinitionRead] = []
    stats: CompanyStats
    model_config = {"from_attributes": True}


class DealStats(BaseModel):
    total_activities: int = 0
    total_tasks: int = 0
    open_tasks: int = 0
    days_in_stage: int = 0
    days_open: int = 0
    last_activity_date: datetime | None = None


class DealProfile(BaseModel):
    deal: DealRead
    contact: ContactRead | None = None
    company: CompanyRead | None = None
    activities: list[ActivityRead] = []
    tasks: list[TaskRead] = []
    custom_fields: list[CustomFieldValueRead] = []
    custom_field_definitions: list[CustomFieldDefinitionRead] = []
    stats: DealStats
    model_config = {"from_attributes": True}
