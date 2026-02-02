"""Pydantic schemas for the Tool Invocation Gateway API."""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, Field


# Tenant schemas
class TenantCreate(BaseModel):
    """Request schema for creating a tenant."""
    name: str = Field(..., min_length=1, max_length=255)
    region: str = Field(..., min_length=1, max_length=50)
    admin_email: EmailStr = Field(..., description="Email for the bootstrap admin user")


class BootstrapAdmin(BaseModel):
    """Bootstrap admin user created with tenant."""
    user_id: str
    email: str
    role: str


class TenantResponse(BaseModel):
    """Response schema for tenant creation."""
    tenant_id: str
    name: str
    region: str
    api_key: str
    created_at: datetime
    admin: BootstrapAdmin

    class Config:
        from_attributes = True


# User schemas
class UserCreate(BaseModel):
    """Request schema for creating a user."""
    tenant_id: str = Field(..., min_length=36, max_length=36)
    email: EmailStr
    role: str = Field(..., pattern="^(admin|member)$")


class UserResponse(BaseModel):
    """Response schema for user creation."""
    user_id: str
    tenant_id: str
    email: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# Tool invocation schemas
class ToolInvokeRequest(BaseModel):
    """Request schema for tool invocation."""
    tool_name: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeResponse(BaseModel):
    """Response schema for tool invocation."""
    request_id: str
    result: dict[str, Any]


# Error schemas
class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: str | None = None


# KPI schemas
class KPICreate(BaseModel):
    """Request schema for creating a KPI definition."""
    name: str = Field(..., min_length=1, max_length=255)
    unit: str | None = Field(None, max_length=50)
    description: str | None = None


class KPIResponse(BaseModel):
    """Response schema for KPI definition."""
    kpi_id: str
    name: str
    unit: str | None
    description: str | None

    class Config:
        from_attributes = True


class KPIPoint(BaseModel):
    """A single KPI data point."""
    ts: str = Field(..., description="ISO 8601 datetime string")
    value: float


class KPIPointsBulkRequest(BaseModel):
    """Request schema for bulk ingesting KPI points."""
    points: list[KPIPoint] = Field(..., min_length=1)


class KPIPointsBulkResponse(BaseModel):
    """Response schema for bulk point ingestion."""
    inserted: int
    ignored: int


class KPILatestResponse(BaseModel):
    """Response schema for latest KPI point."""
    kpi_id: str
    ts: str
    value: float


# Brief schemas
class BriefMaterializeRequest(BaseModel):
    """Request schema for materializing a daily brief."""
    date: str | None = Field(None, description="YYYY-MM-DD, defaults to today UTC")
    window_days: int = Field(7, ge=1, le=365)
    top_n: int = Field(3, ge=1, le=100)


class BriefPointInfo(BaseModel):
    """Point info within brief highlights."""
    ts: str
    value: float


class BriefHighlight(BaseModel):
    """A KPI highlight in the brief."""
    kpi_id: str
    name: str
    unit: str | None
    latest: BriefPointInfo
    start: BriefPointInfo
    delta_abs: float
    delta_pct: float | None


class BriefAlert(BaseModel):
    """An alert in the brief."""
    kpi_id: str
    name: str
    severity: str
    reason: str
    delta_pct: float


class BriefSummary(BaseModel):
    """Summary section of the brief."""
    kpis_considered: int
    kpis_up: int
    kpis_down: int
    kpis_flat: int


class BriefContent(BaseModel):
    """Content of a daily brief."""
    date: str
    window_days: int
    top_n: int
    summary: BriefSummary
    highlights: list[BriefHighlight]
    alerts: list[BriefAlert]


class BriefResponse(BaseModel):
    """Response schema for brief operations."""
    brief_id: str
    request_id: str
    content: BriefContent


# Notification schemas
class NotificationPrefRequest(BaseModel):
    """Request schema for updating notification preferences."""
    daily_brief_enabled: bool = True
    delivery_method: str = Field("in_app", pattern="^in_app$")


class NotificationPrefResponse(BaseModel):
    """Response schema for notification preferences."""
    daily_brief_enabled: bool
    delivery_method: str


class NotificationOutboxItem(BaseModel):
    """A single notification in the outbox."""
    id: int
    notification_type: str
    date: str
    status: str
    request_id: str
    payload: dict[str, Any]


class NotificationOutboxResponse(BaseModel):
    """Response schema for notification outbox listing."""
    items: list[NotificationOutboxItem]


class DailyBriefRunnerRequest(BaseModel):
    """Request schema for the daily brief runner."""
    date: str | None = Field(None, description="YYYY-MM-DD, defaults to today UTC")
    window_days: int = Field(7, ge=1, le=365)
    top_n: int = Field(3, ge=1, le=100)


class DailyBriefRunnerResponse(BaseModel):
    """Response schema for the daily brief runner."""
    date: str
    brief_id: str
    brief_created: bool
    notifications_inserted: int
    notifications_ignored: int
    notifications_suppressed_due_to_quota: int = 0


# Conversation schemas
class ConversationCreate(BaseModel):
    """Request schema for creating a conversation."""
    title: str | None = None


class ConversationResponse(BaseModel):
    """Response schema for a conversation."""
    conversation_id: str
    title: str | None
    created_at: str

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    """Response schema for listing conversations."""
    items: list[ConversationResponse]


class MessageResponse(BaseModel):
    """Response schema for a message."""
    message_id: str
    role: str
    content: str
    cards: list[dict[str, Any]]
    created_at: str


class ConversationDetailResponse(BaseModel):
    """Response schema for conversation detail with messages."""
    conversation_id: str
    title: str | None
    created_at: str
    messages: list[MessageResponse]


# Chat schemas
class ChatRequest(BaseModel):
    """Request schema for cofounder chat."""
    conversation_id: str | None = None
    message: str = Field(..., min_length=1, max_length=4000)
    date: str | None = Field(None, description="YYYY-MM-DD for date-specific queries")


class ChatAssistantMessage(BaseModel):
    """Assistant message in chat response."""
    message_id: str
    content: str
    cards: list[dict[str, Any]]


class ChatResponse(BaseModel):
    """Response schema for cofounder chat."""
    request_id: str
    conversation_id: str
    assistant_message: ChatAssistantMessage


# Tenant Limits schemas
class TenantLimitsResponse(BaseModel):
    """Response schema for tenant limits."""
    tenant_id: str
    assistant_query_daily_limit: int
    tool_invocation_daily_limit: int
    daily_brief_generated_daily_limit: int
    notification_enqueued_daily_limit: int


class TenantLimitsUpdateRequest(BaseModel):
    """Request schema for updating tenant limits."""
    assistant_query_daily_limit: int = Field(..., ge=0)
    tool_invocation_daily_limit: int = Field(..., ge=0)
    daily_brief_generated_daily_limit: int = Field(..., ge=0)
    notification_enqueued_daily_limit: int = Field(..., ge=0)


# Usage schemas
class UsageItem(BaseModel):
    """A single usage item in the daily usage response."""
    activity_type: str
    units: int


class DailyUsageResponse(BaseModel):
    """Response schema for daily usage summary."""
    date: str
    limits: TenantLimitsResponse
    usage: list[UsageItem]


# =============================================================================
# Billing Schemas (Phase 0 Item #7)
# =============================================================================

# Metered Event Type schemas
class MeteredEventTypeCreate(BaseModel):
    """Request schema for creating/updating a metered event type."""
    event_key: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    unit_name: str = Field(..., min_length=1, max_length=50)
    credits_per_unit: float = Field(..., ge=0)
    list_price_per_credit: float = Field(..., ge=0)
    billable: bool = True
    active: bool = True


class MeteredEventTypeUpdate(BaseModel):
    """Request schema for updating a metered event type."""
    display_name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    unit_name: str | None = Field(None, min_length=1, max_length=50)
    credits_per_unit: float | None = Field(None, ge=0)
    list_price_per_credit: float | None = Field(None, ge=0)
    billable: bool | None = None
    active: bool | None = None


class MeteredEventTypeResponse(BaseModel):
    """Response schema for a metered event type."""
    event_key: str
    display_name: str
    description: str | None
    unit_name: str
    credits_per_unit: float
    list_price_per_credit: float
    billable: bool
    active: bool
    created_at: str
    updated_at: str


# Plan schemas
class PlanCreate(BaseModel):
    """Request schema for creating a plan."""
    plan_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    included_credits: int = Field(..., ge=0)
    overage_price_per_credit: float = Field(..., ge=0)


class PlanUpdate(BaseModel):
    """Request schema for updating a plan."""
    name: str | None = Field(None, min_length=1, max_length=255)
    included_credits: int | None = Field(None, ge=0)
    overage_price_per_credit: float | None = Field(None, ge=0)


class PlanResponse(BaseModel):
    """Response schema for a plan."""
    plan_id: str
    name: str
    included_credits: int
    overage_price_per_credit: float
    created_at: str
    updated_at: str


class PlanCapabilitiesUpdate(BaseModel):
    """Request schema for updating plan capabilities."""
    capabilities: list[str]


class PlanEventCapItem(BaseModel):
    """A single event cap item."""
    event_key: str
    period: str = "monthly"
    cap_raw_units: float = Field(..., ge=0)


class PlanEventCapsUpdate(BaseModel):
    """Request schema for updating plan event caps."""
    caps: list[PlanEventCapItem]


# Tenant Subscription schemas
class TenantSubscriptionUpdate(BaseModel):
    """Request schema for updating tenant subscription."""
    plan_id: str = Field(..., min_length=1, max_length=100)
    status: str = Field("active", pattern="^(active|suspended)$")
    period_start: str | None = Field(None, description="YYYY-MM-01, defaults to current month")


class TenantSubscriptionResponse(BaseModel):
    """Response schema for tenant subscription."""
    tenant_id: str
    plan_id: str
    status: str
    period_start: str
    period_end: str
    created_at: str
    updated_at: str


class TenantSubscriptionWithPlanResponse(BaseModel):
    """Response schema for tenant subscription with plan details."""
    tenant_id: str
    plan_id: str
    status: str
    period_start: str
    period_end: str
    plan: PlanResponse
    capabilities: list[str]


# Billing Usage schemas
class BillingUsageBreakdownItem(BaseModel):
    """A single usage breakdown item in the billing usage response."""
    event_key: str
    unit_name: str
    raw_units: float
    credits: float
    list_cost_estimate: float


class BillingCreditsInfo(BaseModel):
    """Credits information in the billing usage response."""
    included: int
    used: float
    remaining: float
    overage_credits: float
    estimated_overage_cost: float
    estimated_list_cost: float


class BillingUsageResponse(BaseModel):
    """Response schema for billing usage."""
    period_start: str
    period_end: str
    plan: PlanResponse
    credits: BillingCreditsInfo
    breakdown: list[BillingUsageBreakdownItem]


class BillingLedgerItem(BaseModel):
    """A single ledger item in the billing ledger response."""
    event_key: str
    raw_units: float
    credits: float
    list_cost_estimate: float
    tool_name: str | None
    request_id: str
    created_at: str


class BillingLedgerResponse(BaseModel):
    """Response schema for billing ledger."""
    period_start: str
    items: list[BillingLedgerItem]
