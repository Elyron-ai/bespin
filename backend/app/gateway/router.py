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
from app.gateway.models import (
    AuditLog,
    GatewayTenant,
    GatewayUser,
    KPIDefinition,
    KPIPoint,
    UsageEvent,
)
from app.gateway.rbac import can_invoke_tools, can_read_kpis, can_write_kpis
from app.gateway.schemas import (
    KPICreate,
    KPILatestResponse,
    KPIPointsBulkRequest,
    KPIPointsBulkResponse,
    KPIResponse,
    TenantCreate,
    TenantResponse,
    ToolInvokeRequest,
    ToolInvokeResponse,
    UserCreate,
    UserResponse,
)
from app.gateway.tools import ToolContext, ToolNotFoundError, registry

router = APIRouter(prefix="/v1", tags=["gateway"])


@dataclass
class TenantContext:
    """Tenant context populated from request headers."""
    tenant_id: str
    user_id: str
    tenant: GatewayTenant
    user: GatewayUser


def get_basic_tenant_context(
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> TenantContext:
    """Validate headers and return tenant context (no idempotency key required).

    For use with endpoints that don't need idempotency.

    Returns:
        TenantContext with authenticated tenant and user.

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

    return TenantContext(
        tenant_id=x_tenant_id,
        user_id=x_user_id,
        tenant=tenant,
        user=user,
    )


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

    # Execute tool (with context for context-aware tools)
    tool_context = ToolContext(tenant_id=context.tenant_id, db=db)
    try:
        result = registry.invoke(request.tool_name, request.payload, context=tool_context)
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


# --- KPI Endpoints ---


@router.post("/kpis", response_model=KPIResponse, status_code=status.HTTP_201_CREATED)
def create_kpi(
    kpi_data: KPICreate,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> KPIResponse:
    """Create a new KPI definition.

    Requires admin role.
    """
    # Check RBAC: only admins can create KPIs
    if not can_write_kpis(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to create KPIs",
        )

    kpi = KPIDefinition(
        kpi_id=str(uuid.uuid4()),
        tenant_id=context.tenant_id,
        name=kpi_data.name,
        unit=kpi_data.unit,
        description=kpi_data.description,
    )
    db.add(kpi)
    db.commit()
    db.refresh(kpi)
    return KPIResponse.model_validate(kpi)


@router.post(
    "/kpis/{kpi_id}/points:bulk",
    response_model=KPIPointsBulkResponse,
    status_code=status.HTTP_200_OK,
)
def bulk_ingest_kpi_points(
    kpi_id: str,
    request: KPIPointsBulkRequest,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> KPIPointsBulkResponse:
    """Bulk ingest KPI data points.

    Requires admin role. Ignores duplicate (tenant_id, kpi_id, ts) entries.
    """
    # Check RBAC: only admins can ingest points
    if not can_write_kpis(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to ingest KPI points",
        )

    # Verify KPI exists and belongs to this tenant
    kpi = db.query(KPIDefinition).filter(
        KPIDefinition.kpi_id == kpi_id,
        KPIDefinition.tenant_id == context.tenant_id,
    ).first()
    if not kpi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"KPI '{kpi_id}' not found",
        )

    inserted = 0
    ignored = 0

    for point in request.points:
        # Check if point already exists
        existing = db.query(KPIPoint).filter(
            KPIPoint.tenant_id == context.tenant_id,
            KPIPoint.kpi_id == kpi_id,
            KPIPoint.ts == point.ts,
        ).first()

        if existing:
            ignored += 1
        else:
            kpi_point = KPIPoint(
                tenant_id=context.tenant_id,
                kpi_id=kpi_id,
                ts=point.ts,
                value=point.value,
            )
            db.add(kpi_point)
            inserted += 1

    db.commit()
    return KPIPointsBulkResponse(inserted=inserted, ignored=ignored)


@router.get("/kpis", response_model=list[KPIResponse])
def list_kpis(
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> list[KPIResponse]:
    """List all KPI definitions for the tenant.

    Requires member or admin role.
    """
    # Check RBAC: admin and member can read KPIs
    if not can_read_kpis(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to read KPIs",
        )

    kpis = db.query(KPIDefinition).filter(
        KPIDefinition.tenant_id == context.tenant_id
    ).all()
    return [KPIResponse.model_validate(kpi) for kpi in kpis]


@router.get("/kpis/{kpi_id}/latest", response_model=KPILatestResponse)
def get_kpi_latest(
    kpi_id: str,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> KPILatestResponse:
    """Get the latest data point for a KPI.

    Requires member or admin role.
    """
    # Check RBAC: admin and member can read KPIs
    if not can_read_kpis(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to read KPIs",
        )

    # Verify KPI exists and belongs to this tenant (for tenant isolation)
    kpi = db.query(KPIDefinition).filter(
        KPIDefinition.kpi_id == kpi_id,
        KPIDefinition.tenant_id == context.tenant_id,
    ).first()
    if not kpi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"KPI '{kpi_id}' not found",
        )

    # Get the latest point by ts
    latest_point = db.query(KPIPoint).filter(
        KPIPoint.tenant_id == context.tenant_id,
        KPIPoint.kpi_id == kpi_id,
    ).order_by(KPIPoint.ts.desc()).first()

    if not latest_point:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data points found for KPI '{kpi_id}'",
        )

    return KPILatestResponse(
        kpi_id=kpi_id,
        ts=latest_point.ts,
        value=latest_point.value,
    )
