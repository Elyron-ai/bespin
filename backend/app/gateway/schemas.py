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
