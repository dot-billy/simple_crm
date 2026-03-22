from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models import ActivityType, CustomFieldType, DealStage, EmailDirection, EmailTrackingEventType, TaskStatus, UserRole


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
    full_name: str
    password: str
    role: UserRole = UserRole.USER


class UserRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


# --- Tag ---

class TagCreate(BaseModel):
    name: str
    color: str = "#6366f1"


class TagRead(BaseModel):
    id: UUID
    name: str
    color: str

    model_config = {"from_attributes": True}


# --- Contact ---

class ContactCreate(BaseModel):
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None
    company_id: UUID | None = None
    source: str | None = None
    notes: str | None = None
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
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None
    company_id: UUID | None = None
    source: str | None = None
    notes: str | None = None
    tag_ids: list[UUID] | None = None


# --- Company ---

class CompanyCreate(BaseModel):
    name: str
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    address: str | None = None
    phone: str | None = None
    notes: str | None = None
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
    tags: list[TagRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    address: str | None = None
    phone: str | None = None
    notes: str | None = None
    tag_ids: list[UUID] | None = None


# --- Deal ---

class DealCreate(BaseModel):
    title: str
    value: float = 0
    currency: str = "USD"
    stage: DealStage = DealStage.LEAD
    contact_id: UUID | None = None
    company_id: UUID | None = None
    expected_close_date: datetime | None = None
    notes: str | None = None
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
    tags: list[TagRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DealUpdate(BaseModel):
    title: str | None = None
    value: float | None = None
    currency: str | None = None
    stage: DealStage | None = None
    contact_id: UUID | None = None
    company_id: UUID | None = None
    expected_close_date: datetime | None = None
    notes: str | None = None
    tag_ids: list[UUID] | None = None


# --- Activity ---

class ActivityCreate(BaseModel):
    type: ActivityType
    subject: str
    description: str | None = None
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
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    due_date: datetime | None = None
    assigned_to: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None


class TaskRead(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    status: TaskStatus
    due_date: datetime | None = None
    assigned_to: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    due_date: datetime | None = None
    assigned_to: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None


# --- Custom Fields ---

class CustomFieldDefinitionCreate(BaseModel):
    name: str
    field_type: CustomFieldType
    entity_type: str  # "contact" or "company"
    options: str | None = None
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
    value: str


class CustomFieldValueRead(BaseModel):
    id: UUID
    field_id: UUID
    contact_id: UUID | None = None
    company_id: UUID | None = None
    value: str | None = None

    model_config = {"from_attributes": True}


# --- Dashboard ---

class DashboardStats(BaseModel):
    total_contacts: int
    total_companies: int
    total_deals: int
    total_deal_value: float
    deals_by_stage: dict[str, int]
    recent_activities: list[ActivityRead]
    upcoming_tasks: list[TaskRead]


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
    to: list[str]
    subject: str
    body_html: str
    cc: list[str] | None = None
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
    name: str
    subject: str
    body_html: str


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
    name: str | None = None
    subject: str | None = None
    body_html: str | None = None


class GmailSyncStatus(BaseModel):
    is_configured: bool
    last_sync_at: datetime | None = None
    is_syncing: bool = False
    history_id: str | None = None


# --- Pagination ---

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    per_page: int
    pages: int
