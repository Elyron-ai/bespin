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
    activity_type = Column(String(100), nullable=False)
    units = Column(Integer, nullable=False, default=1)
    tool_name = Column(String(100), nullable=True)
    request_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


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
