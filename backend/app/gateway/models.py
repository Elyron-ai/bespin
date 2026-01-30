"""Database models for the Tool Invocation Gateway."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Float, Index, UniqueConstraint
from app.database import Base


class GatewayTenant(Base):
    """Tenant model for multi-tenancy."""
    __tablename__ = "gateway_tenants"

    tenant_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    region = Column(String(50), nullable=False)
    api_key = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GatewayUser(Base):
    """User model scoped to a tenant."""
    __tablename__ = "gateway_users"

    user_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # "admin" or "member"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    """Audit log for tracking all tool invocations."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False)
    action = Column(String(100), nullable=False)
    tool_name = Column(String(100), nullable=True)
    request_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class IdempotencyKey(Base):
    """Idempotency keys to prevent duplicate processing."""
    __tablename__ = "idempotency_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(36), nullable=False)
    endpoint = Column(String(100), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)  # SHA-256 hex
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "endpoint", "idempotency_key",
            name="uq_idempotency_tenant_endpoint_key"
        ),
    )


class KPIDefinition(Base):
    """KPI definition scoped to a tenant."""
    __tablename__ = "kpi_definitions"

    kpi_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False)
    name = Column(String(255), nullable=False)
    unit = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "kpi_id", "ts", name="uq_kpi_point_tenant_kpi_ts"),
        Index("ix_kpi_points_tenant_kpi_ts", "tenant_id", "kpi_id", "ts"),
    )
