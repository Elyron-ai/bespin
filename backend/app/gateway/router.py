"""API router for the Tool Invocation Gateway."""
import secrets
import uuid
from typing import Annotated

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.gateway.idempotency import (
    IdempotencyConflictError,
    check_idempotency,
    store_idempotency,
)
from app.gateway.models import AuditLog, GatewayTenant, GatewayUser, UsageEvent
from app.gateway.rbac import can_invoke_tools
from app.gateway.schemas import (
    TenantCreate,
    TenantResponse,
    ToolInvokeRequest,
    ToolInvokeResponse,
    UserCreate,
    UserResponse,
)
from app.gateway.tools import ToolNotFoundError, registry

router = APIRouter(prefix="/v1", tags=["gateway"])


@dataclass
class TenantContext:
    """Tenant context populated from request headers."""
    tenant_id: str
    user_id: str
    tenant: GatewayTenant
    user: GatewayUser


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(32)


# --- Tenant Endpoints ---


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db),
) -> TenantResponse:
    """Create a new tenant.

    This endpoint is open (no auth) for MVP purposes.
    """
    tenant = GatewayTenant(
        tenant_id=str(uuid.uuid4()),
        name=tenant_data.name,
        region=tenant_data.region,
        api_key=generate_api_key(),
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return TenantResponse.model_validate(tenant)


# --- User Endpoints ---


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Create a new user under a tenant."""
    # Verify tenant exists
    tenant = db.query(GatewayTenant).filter(
        GatewayTenant.tenant_id == user_data.tenant_id
    ).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{user_data.tenant_id}' not found",
        )

    user = GatewayUser(
        user_id=str(uuid.uuid4()),
        tenant_id=user_data.tenant_id,
        email=user_data.email,
        role=user_data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


# --- Tool Invocation Endpoint ---


def get_tenant_context(
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> tuple[TenantContext, str]:
    """Validate headers and return tenant context with idempotency key.

    Returns:
        A tuple of (TenantContext, idempotency_key).

    Raises:
        HTTPException: On missing headers, auth failure, or authorization failure.
    """
    # Validate required headers are present
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: X-Tenant-ID",
        )
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: X-User-ID",
        )
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: X-API-Key",
        )
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: Idempotency-Key",
        )

    # Authenticate: verify tenant exists and API key matches
    tenant = db.query(GatewayTenant).filter(
        GatewayTenant.tenant_id == x_tenant_id
    ).first()
    if not tenant or tenant.api_key != x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant ID or API key",
        )

    # Authorize: verify user exists and belongs to tenant
    user = db.query(GatewayUser).filter(
        GatewayUser.user_id == x_user_id
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found",
        )
    if user.tenant_id != x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this tenant",
        )

    context = TenantContext(
        tenant_id=x_tenant_id,
        user_id=x_user_id,
        tenant=tenant,
        user=user,
    )
    return context, idempotency_key


@router.post("/tools/invoke", response_model=ToolInvokeResponse)
def invoke_tool(
    request: ToolInvokeRequest,
    context_and_key: Annotated[tuple[TenantContext, str], Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ToolInvokeResponse:
    """Invoke a tool with full tenant context, RBAC, idempotency, and auditing."""
    context, idempotency_key = context_and_key
    endpoint = "/v1/tools/invoke"

    # Check RBAC: only admins can invoke tools
    if not can_invoke_tools(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to invoke tools",
        )

    # Check idempotency
    request_body = request.model_dump()
    try:
        cached_response = check_idempotency(
            db=db,
            tenant_id=context.tenant_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_body=request_body,
        )
        if cached_response is not None:
            return ToolInvokeResponse(**cached_response)
    except IdempotencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    # Execute tool
    try:
        result = registry.invoke(request.tool_name, request.payload)
    except ToolNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    # Generate request ID for this invocation
    request_id = str(uuid.uuid4())

    # Write audit log
    audit_log = AuditLog(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="tools.invoke",
        tool_name=request.tool_name,
        request_id=request_id,
    )
    db.add(audit_log)

    # Write usage event
    usage_event = UsageEvent(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        activity_type="tool_invocation",
        units=1,
        tool_name=request.tool_name,
        request_id=request_id,
    )
    db.add(usage_event)
    db.commit()

    # Build response
    response = ToolInvokeResponse(request_id=request_id, result=result)

    # Store idempotency record
    store_idempotency(
        db=db,
        tenant_id=context.tenant_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_body=request_body,
        response=response.model_dump(),
    )

    return response
