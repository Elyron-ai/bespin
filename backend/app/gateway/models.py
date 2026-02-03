"""Database models for the Tool Invocation Gateway."""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime, Float, Index, UniqueConstraint
from app.database import Base


def utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class GatewayTenant(Base):
    """Tenant model for multi-tenancy."""
    __tablename__ = "gateway_tenants"

    tenant_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    region = Column(String(50), nullable=False)
    api_key = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class GatewayUser(Base):
    """User model scoped to a tenant."""
    __tablename__ = "gateway_users"

    user_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # "admin" or "member"
    created_at = Column(DateTime, default=utc_now, nullable=False)


class AuditLog(Base):
    """Audit log for tracking all tool invocations."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False)
    action = Column(String(100), nullable=False)
    tool_name = Column(String(100), nullable=True)
    request_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class UsageEvent(Base):
    """Usage/metering events for billing and analytics."""
    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False)
    activity_type = Column(String(100), nullable=False)  # event_key
    units = Column(Float, nullable=False, default=1)  # raw_units
    credits = Column(Float, nullable=True, default=0.0)  # calculated credits
    list_cost_estimate = Column(Float, nullable=True, default=0.0)  # calculated cost
    tool_name = Column(String(100), nullable=True)
    request_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        # Index for billing ledger queries filtering by tenant and date range
        Index("ix_usage_events_tenant_created", "tenant_id", "created_at"),
    )


class IdempotencyKey(Base):
    """Idempotency keys to prevent duplicate processing."""
    __tablename__ = "idempotency_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False)
    endpoint = Column(String(100), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)  # SHA-256 hex
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "endpoint", "idempotency_key",
            name="uq_idempotency_tenant_endpoint_key"
        ),
        # Index for efficient lookups by tenant_id, endpoint, and idempotency_key
        Index("ix_idempotency_tenant_endpoint_key", "tenant_id", "endpoint", "idempotency_key"),
    )


class KPIDefinition(Base):
    """KPI definition scoped to a tenant."""
    __tablename__ = "kpi_definitions"

    kpi_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    name = Column(String(255), nullable=False)
    unit = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_kpi_definitions_tenant_name", "tenant_id", "name"),
    )


class KPIPoint(Base):
    """Time series data point for a KPI."""
    __tablename__ = "kpi_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False)
    kpi_id = Column(String(36), nullable=False)
    ts = Column(String(30), nullable=False)  # ISO 8601 datetime string
    value = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "kpi_id", "ts", name="uq_kpi_point_tenant_kpi_ts"),
        Index("ix_kpi_points_tenant_kpi_ts", "tenant_id", "kpi_id", "ts"),
    )


class Brief(Base):
    """Daily brief materialized for a tenant."""
    __tablename__ = "briefs"

    brief_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    brief_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    window_days = Column(Integer, nullable=False)
    top_n = Column(Integer, nullable=False)
    content_json = Column(Text, nullable=False)  # JSON string
    request_id = Column(String(36), nullable=False)  # UUID for audit/usage correlation
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "brief_date", name="uq_brief_tenant_date"),
        Index("ix_briefs_tenant_date", "tenant_id", "brief_date"),
    )


class NotificationPref(Base):
    """User notification preferences scoped to a tenant."""
    __tablename__ = "notification_prefs"

    tenant_id = Column(String(36), nullable=False, primary_key=True)
    user_id = Column(String(36), nullable=False, primary_key=True)
    daily_brief_enabled = Column(Integer, nullable=False, default=1)  # 0 or 1
    delivery_method = Column(String(50), nullable=False, default="in_app")
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class NotificationOutbox(Base):
    """Notification outbox for queued notifications."""
    __tablename__ = "notification_outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False)
    notification_type = Column(String(50), nullable=False)  # e.g. "daily_brief"
    notif_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    status = Column(String(20), nullable=False)  # "queued" | "acked"
    payload_json = Column(Text, nullable=False)  # JSON string
    request_id = Column(String(36), nullable=False)  # UUID correlation
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "notification_type", "notif_date",
            name="uq_notification_tenant_user_type_date"
        ),
        Index("ix_notification_outbox_tenant_user_date", "tenant_id", "user_id", "notif_date"),
    )


class Conversation(Base):
    """Conversation for the Cofounder chat."""
    __tablename__ = "conversations"

    conversation_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False)
    title = Column(String(255), nullable=True)
    created_at = Column(String(30), nullable=False)  # ISO 8601 datetime string

    __table_args__ = (
        Index("ix_conversations_tenant_user_created", "tenant_id", "user_id", "created_at"),
    )


class Message(Base):
    """Message within a conversation."""
    __tablename__ = "messages"

    message_id = Column(String(36), primary_key=True)
    conversation_id = Column(String(36), nullable=False)
    tenant_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False)
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=False)  # JSON string (e.g. cards)
    created_at = Column(String(30), nullable=False)  # ISO 8601 datetime string

    __table_args__ = (
        Index("ix_messages_tenant_conversation_created", "tenant_id", "conversation_id", "created_at"),
    )


class TenantLimit(Base):
    """Per-tenant daily quota limits for various activity types."""
    __tablename__ = "tenant_limits"

    tenant_id = Column(String(36), primary_key=True)
    assistant_query_daily_limit = Column(Integer, nullable=False, default=100)
    tool_invocation_daily_limit = Column(Integer, nullable=False, default=100)
    daily_brief_generated_daily_limit = Column(Integer, nullable=False, default=10)
    notification_enqueued_daily_limit = Column(Integer, nullable=False, default=500)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class UsageRollupDaily(Base):
    """Daily usage rollup for efficient quota checking."""
    __tablename__ = "usage_rollups_daily"

    tenant_id = Column(String(36), nullable=False, primary_key=True)
    rollup_date = Column(String(10), nullable=False, primary_key=True)  # YYYY-MM-DD
    activity_type = Column(String(100), nullable=False, primary_key=True)
    units = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_usage_rollups_tenant_date", "tenant_id", "rollup_date"),
    )


# =============================================================================
# Billing / Metering Models (Phase 0 Item #7)
# =============================================================================

class MeteredEventType(Base):
    """Catalog of metered event types with weights and pricing."""
    __tablename__ = "metered_event_types"

    event_key = Column(String(100), primary_key=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    unit_name = Column(String(50), nullable=False)  # e.g. "call", "row", "brief"
    credits_per_unit = Column(Float, nullable=False)  # weight
    list_price_per_credit = Column(Float, nullable=False)  # catalog sticker price
    billable = Column(Integer, nullable=False, default=1)  # 0 or 1
    active = Column(Integer, nullable=False, default=1)  # 0 or 1
    created_at = Column(String(30), nullable=False)  # ISO 8601
    updated_at = Column(String(30), nullable=False)  # ISO 8601


class Plan(Base):
    """Billing plan with included credits and overage pricing."""
    __tablename__ = "plans"

    plan_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    included_credits = Column(Integer, nullable=False)  # monthly included
    overage_price_per_credit = Column(Float, nullable=False)
    created_at = Column(String(30), nullable=False)  # ISO 8601
    updated_at = Column(String(30), nullable=False)  # ISO 8601


class PlanEventCap(Base):
    """Per-event raw unit caps for a plan (optional)."""
    __tablename__ = "plan_event_caps"

    plan_id = Column(String(100), nullable=False, primary_key=True)
    event_key = Column(String(100), nullable=False, primary_key=True)
    period = Column(String(20), nullable=False, primary_key=True)  # "monthly" for v1
    cap_raw_units = Column(Float, nullable=False)


class Capability(Base):
    """Feature capability that can be granted to plans."""
    __tablename__ = "capabilities"

    capability_key = Column(String(100), primary_key=True)
    description = Column(Text, nullable=True)


class PlanCapability(Base):
    """Mapping of capabilities to plans (entitlements)."""
    __tablename__ = "plan_capabilities"

    plan_id = Column(String(100), nullable=False, primary_key=True)
    capability_key = Column(String(100), nullable=False, primary_key=True)


class TenantSubscription(Base):
    """Tenant subscription to a plan with billing period."""
    __tablename__ = "tenant_subscriptions"

    tenant_id = Column(String(36), primary_key=True)
    plan_id = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)  # "active" | "suspended"
    period_start = Column(String(10), nullable=False)  # YYYY-MM-01
    period_end = Column(String(10), nullable=False)  # next YYYY-MM-01
    created_at = Column(String(30), nullable=False)  # ISO 8601
    updated_at = Column(String(30), nullable=False)  # ISO 8601


class UsageRollupPeriod(Base):
    """Monthly usage rollup with credits and cost estimates."""
    __tablename__ = "usage_rollups_period"

    tenant_id = Column(String(36), nullable=False, primary_key=True)
    period_start = Column(String(10), nullable=False, primary_key=True)  # YYYY-MM-01
    event_key = Column(String(100), nullable=False, primary_key=True)
    raw_units = Column(Float, nullable=False, default=0.0)
    credits = Column(Float, nullable=False, default=0.0)
    list_cost_estimate = Column(Float, nullable=False, default=0.0)
    updated_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        Index("ix_usage_rollups_period_tenant", "tenant_id", "period_start"),
    )


# =============================================================================
# Core Business OS Models
# =============================================================================

class Action(Base):
    """Action Center: recommended actions that can be approved/executed."""
    __tablename__ = "actions"

    action_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    created_by_user_id = Column(String(36), nullable=False)
    assigned_to_user_id = Column(String(36), nullable=True)
    source = Column(String(50), nullable=False)  # "user" | "agent" | "system"
    source_ref = Column(String(255), nullable=True)  # e.g. agent name or run id
    status = Column(String(50), nullable=False)  # "proposed" | "approved" | "rejected" | "executed" | "cancelled"
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    action_type = Column(String(100), nullable=False)  # e.g. "create_task", "update_record", "draft_content"
    payload_json = Column(Text, nullable=False)  # JSON string for execution payload
    created_at = Column(String(30), nullable=False)  # ISO 8601
    updated_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        Index("ix_actions_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_actions_tenant_creator_created", "tenant_id", "created_by_user_id", "created_at"),
        Index("ix_actions_tenant_assigned_status", "tenant_id", "assigned_to_user_id", "status"),
    )


class ActionReview(Base):
    """Review record for an action (approval/rejection)."""
    __tablename__ = "action_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False)
    action_id = Column(String(36), nullable=False)
    reviewer_user_id = Column(String(36), nullable=False)
    decision = Column(String(50), nullable=False)  # "approved" | "rejected"
    comment = Column(Text, nullable=True)
    created_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        # Only one review per action (v0 - exactly one decision)
        UniqueConstraint("tenant_id", "action_id", name="uq_action_review_tenant_action"),
        Index("ix_action_reviews_tenant_action_created", "tenant_id", "action_id", "created_at"),
    )


class ActionExecution(Base):
    """Execution record for an action."""
    __tablename__ = "action_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False)
    action_id = Column(String(36), nullable=False)
    executed_by_user_id = Column(String(36), nullable=False)
    execution_status = Column(String(50), nullable=False)  # "succeeded" | "failed" | "skipped"
    result_json = Column(Text, nullable=False)  # JSON string
    created_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        Index("ix_action_executions_tenant_action_created", "tenant_id", "action_id", "created_at"),
    )


class Task(Base):
    """Work OS: Tasks."""
    __tablename__ = "tasks"

    task_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    created_by_user_id = Column(String(36), nullable=False)
    assigned_to_user_id = Column(String(36), nullable=True)
    status = Column(String(50), nullable=False)  # "todo" | "doing" | "done"
    priority = Column(String(50), nullable=False)  # "low" | "medium" | "high"
    due_date = Column(String(10), nullable=True)  # YYYY-MM-DD
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    linked_entity_type = Column(String(100), nullable=True)  # e.g. "action", "decision", "kpi", "brief"
    linked_entity_id = Column(String(36), nullable=True)
    created_at = Column(String(30), nullable=False)  # ISO 8601
    updated_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        Index("ix_tasks_tenant_status_due", "tenant_id", "status", "due_date"),
        Index("ix_tasks_tenant_assigned_status", "tenant_id", "assigned_to_user_id", "status"),
    )


class MeetingNote(Base):
    """Work OS: Meeting notes."""
    __tablename__ = "meeting_notes"

    meeting_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    created_by_user_id = Column(String(36), nullable=False)
    meeting_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    title = Column(String(255), nullable=False)
    notes = Column(Text, nullable=False)  # markdown/text
    linked_entity_type = Column(String(100), nullable=True)
    linked_entity_id = Column(String(36), nullable=True)
    created_at = Column(String(30), nullable=False)  # ISO 8601
    updated_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        Index("ix_meeting_notes_tenant_date", "tenant_id", "meeting_date"),
    )


class Decision(Base):
    """Strategy OS: Decisions."""
    __tablename__ = "decisions"

    decision_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    created_by_user_id = Column(String(36), nullable=False)
    decision_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    title = Column(String(255), nullable=False)
    context = Column(Text, nullable=True)
    decision = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)
    status = Column(String(50), nullable=False)  # "active" | "superseded"
    superseded_by_decision_id = Column(String(36), nullable=True)
    created_at = Column(String(30), nullable=False)  # ISO 8601
    updated_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        Index("ix_decisions_tenant_date", "tenant_id", "decision_date"),
    )


class MemoryFact(Base):
    """Governed Memory: Facts about the business."""
    __tablename__ = "memory_facts"

    fact_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    created_by_user_id = Column(String(36), nullable=False)
    category = Column(String(100), nullable=False)  # "icp" | "positioning" | "pricing" | "goals" | "constraints" | "brand" | "other"
    fact_key = Column(String(255), nullable=False)  # short key e.g. "ICP.primary"
    fact_value = Column(Text, nullable=False)  # long text
    status = Column(String(50), nullable=False)  # "active" | "superseded"
    supersedes_fact_id = Column(String(36), nullable=True)
    created_at = Column(String(30), nullable=False)  # ISO 8601
    updated_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        UniqueConstraint("tenant_id", "fact_key", "status", name="uq_memory_fact_tenant_key_status"),
        Index("ix_memory_facts_tenant_category_status", "tenant_id", "category", "status"),
    )


class EvidenceLink(Base):
    """Evidence / Provenance links for actions, tasks, decisions, memory facts."""
    __tablename__ = "evidence_links"

    evidence_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    entity_type = Column(String(100), nullable=False)  # "action" | "task" | "decision" | "memory_fact"
    entity_id = Column(String(36), nullable=False)
    source_type = Column(String(100), nullable=False)  # "kpi" | "brief" | "note" | "decision" | "task" | "manual"
    source_ref_json = Column(Text, nullable=False)  # JSON with {table, id, field?, ts?} OR external ref
    snippet = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), nullable=False)
    created_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        Index("ix_evidence_links_tenant_entity", "tenant_id", "entity_type", "entity_id"),
    )


class TimelineEvent(Base):
    """Unified Timeline: User-facing 'what happened' stream."""
    __tablename__ = "timeline_events"

    event_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    actor_user_id = Column(String(36), nullable=False)  # who caused it (or "system")
    event_type = Column(String(100), nullable=False)  # e.g. "action_created", "task_completed"
    entity_type = Column(String(100), nullable=False)  # "action" | "task" | "decision" | "memory_fact" | "meeting"
    entity_id = Column(String(36), nullable=False)
    summary = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=False)  # JSON string
    created_at = Column(String(30), nullable=False)  # ISO 8601

    __table_args__ = (
        Index("ix_timeline_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_timeline_events_tenant_entity_created", "tenant_id", "entity_type", "entity_id", "created_at"),
    )
