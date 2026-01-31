"""Pydantic schemas for the Tool Invocation Gateway API."""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, Field


# Tenant schemas
class TenantCreate(BaseModel):
    """Request schema for creating a tenant."""
    name: str = Field(..., min_length=1, max_length=255)
    region: str = Field(..., min_length=1, max_length=50)


class TenantResponse(BaseModel):
    """Response schema for tenant creation."""
    tenant_id: str
    name: str
    region: str
    api_key: str
    created_at: datetime

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
