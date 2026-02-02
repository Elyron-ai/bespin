"""API router for the Tool Invocation Gateway."""
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.gateway.briefs import generate_daily_brief
from app.gateway.idempotency import (
    IdempotencyConflictError,
    check_idempotency,
    store_idempotency,
)
from app.gateway.models import (
    AuditLog,
    Brief,
    Conversation,
    GatewayTenant,
    GatewayUser,
    KPIDefinition,
    KPIPoint,
    Message,
    NotificationOutbox,
    NotificationPref,
    TenantLimit,
    UsageEvent,
    UsageRollupDaily,
)
from app.gateway.quota import (
    check_quota,
    create_default_limits,
    get_remaining_quota,
    get_today_date_utc,
    get_usage,
    increment_usage,
    ACTIVITY_LIMIT_FIELD,
    DEFAULT_LIMITS,
)
from app.gateway.entitlements import (
    check_entitlement,
    check_quota as check_billing_quota,
    create_tenant_subscription,
    get_remaining_quota as get_remaining_billing_quota,
)
from app.gateway.metering import emit_usage
from app.gateway.rbac import (
    can_invoke_tools,
    can_materialize_briefs,
    can_read_briefs,
    can_read_kpis,
    can_run_jobs,
    can_use_cofounder_chat,
    can_write_kpis,
)
from app.gateway.schemas import (
    BootstrapAdmin,
    BriefMaterializeRequest,
    BriefResponse,
    ChatAssistantMessage,
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    DailyBriefRunnerRequest,
    DailyBriefRunnerResponse,
    DailyUsageResponse,
    KPICreate,
    KPILatestResponse,
    KPIPointsBulkRequest,
    KPIPointsBulkResponse,
    KPIResponse,
    MessageResponse,
    NotificationOutboxItem,
    NotificationOutboxResponse,
    NotificationPrefRequest,
    NotificationPrefResponse,
    TenantCreate,
    TenantLimitsResponse,
    TenantLimitsUpdateRequest,
    TenantResponse,
    ToolInvokeRequest,
    ToolInvokeResponse,
    UsageItem,
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


def _validate_and_authenticate(
    db: Session,
    x_tenant_id: str | None,
    x_user_id: str | None,
    x_api_key: str | None,
) -> TenantContext:
    """Common validation and authentication logic for tenant context.

    Args:
        db: Database session.
        x_tenant_id: Tenant ID from header.
        x_user_id: User ID from header.
        x_api_key: API key from header.

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
    # Use constant-time comparison to prevent timing attacks
    if not tenant or not secrets.compare_digest(tenant.api_key, x_api_key):
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
    return _validate_and_authenticate(db, x_tenant_id, x_user_id, x_api_key)


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(32)


# --- Tenant Endpoints ---


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db),
) -> TenantResponse:
    """Create a new tenant with a bootstrap admin user.

    This endpoint is open (no auth) for MVP purposes.
    Creates a tenant and an initial admin user for bootstrapping.
    """
    tenant_id = str(uuid.uuid4())
    admin_user_id = str(uuid.uuid4())

    # Create tenant
    tenant = GatewayTenant(
        tenant_id=tenant_id,
        name=tenant_data.name,
        region=tenant_data.region,
        api_key=generate_api_key(),
    )
    db.add(tenant)

    # Create bootstrap admin user
    admin_user = GatewayUser(
        user_id=admin_user_id,
        tenant_id=tenant_id,
        email=tenant_data.admin_email,
        role="admin",
    )
    db.add(admin_user)

    # Create default tenant limits
    create_default_limits(db, tenant_id)

    # Create default subscription (starter plan)
    create_tenant_subscription(db, tenant_id, plan_id="starter", status="active")

    db.commit()
    db.refresh(tenant)
    db.refresh(admin_user)

    return TenantResponse(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        region=tenant.region,
        api_key=tenant.api_key,
        created_at=tenant.created_at,
        admin=BootstrapAdmin(
            user_id=admin_user.user_id,
            email=admin_user.email,
            role=admin_user.role,
        ),
    )


# --- User Endpoints ---


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> UserResponse:
    """Create a new user under a tenant.

    Requires admin role. Users can only be created within the authenticated tenant.
    """
    # Check RBAC: only admins can create users
    if context.user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to create users",
        )

    # Security: Users can only create users within their own tenant
    if user_data.tenant_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create users for a different tenant",
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
    # Validate idempotency key first (before auth to fail fast)
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: Idempotency-Key",
        )

    # Use common authentication logic
    context = _validate_and_authenticate(db, x_tenant_id, x_user_id, x_api_key)
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

    # Check entitlement (capability)
    check_entitlement(db, context.tenant_id, "tools")

    # Check idempotency BEFORE quota (replays must not consume quota)
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
            # Idempotent replay - return cached response without consuming quota
            return ToolInvokeResponse(**cached_response)
    except IdempotencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    # Check billing quota (credits + caps) - after idempotency check
    check_billing_quota(db, context.tenant_id, "tool_invocation", requested_raw_units=1)

    # Also check legacy daily quota for backward compatibility
    today = get_today_date_utc()
    check_quota(db, context.tenant_id, today, "tool_invocation", requested_units=1)

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

    # Emit usage via centralized metering (calculates credits + updates period rollup)
    emit_usage(
        db=db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        event_key="tool_invocation",
        raw_units=1,
        request_id=request_id,
        tool_name=request.tool_name,
    )

    # Increment legacy daily usage rollup for backward compatibility
    increment_usage(db, context.tenant_id, today, "tool_invocation", units=1)

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

    # Check entitlement (capability)
    check_entitlement(db, context.tenant_id, "kpi_ingest")

    # Check billing quota before creating
    check_billing_quota(db, context.tenant_id, "kpi_definition_created", requested_raw_units=1)

    request_id = str(uuid.uuid4())

    kpi = KPIDefinition(
        kpi_id=str(uuid.uuid4()),
        tenant_id=context.tenant_id,
        name=kpi_data.name,
        unit=kpi_data.unit,
        description=kpi_data.description,
    )
    db.add(kpi)

    # Emit usage via centralized metering
    emit_usage(
        db=db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        event_key="kpi_definition_created",
        raw_units=1,
        request_id=request_id,
    )

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

    # Check entitlement (capability)
    check_entitlement(db, context.tenant_id, "kpi_ingest")

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

    # Batch fetch existing timestamps to avoid N+1 queries
    incoming_timestamps = [point.ts for point in request.points]
    existing_points = db.query(KPIPoint.ts).filter(
        KPIPoint.tenant_id == context.tenant_id,
        KPIPoint.kpi_id == kpi_id,
        KPIPoint.ts.in_(incoming_timestamps),
    ).all()
    existing_timestamps = {p.ts for p in existing_points}

    # Calculate how many will be inserted (for quota check)
    expected_inserts = sum(1 for p in request.points if p.ts not in existing_timestamps)

    # Check billing quota for expected inserts
    if expected_inserts > 0:
        check_billing_quota(db, context.tenant_id, "kpi_points_ingested", requested_raw_units=expected_inserts)

    inserted = 0
    ignored = 0

    for point in request.points:
        if point.ts in existing_timestamps:
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

    # Emit usage for actual inserted count
    if inserted > 0:
        request_id = str(uuid.uuid4())
        emit_usage(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            event_key="kpi_points_ingested",
            raw_units=inserted,
            request_id=request_id,
        )

    db.commit()
    return KPIPointsBulkResponse(inserted=inserted, ignored=ignored)


@router.get("/kpis", response_model=list[KPIResponse])
def list_kpis(
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> list[KPIResponse]:
    """List KPI definitions for the tenant with pagination.

    Requires member or admin role.

    Args:
        limit: Maximum number of KPIs to return (default 100, max 500).
        offset: Number of KPIs to skip (default 0).
    """
    # Check RBAC: admin and member can read KPIs
    if not can_read_kpis(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to read KPIs",
        )

    # Check entitlement (capability)
    check_entitlement(db, context.tenant_id, "kpi_read")

    # Enforce reasonable limits
    limit = min(max(1, limit), 500)
    offset = max(0, offset)

    kpis = db.query(KPIDefinition).filter(
        KPIDefinition.tenant_id == context.tenant_id
    ).order_by(KPIDefinition.created_at.desc()).offset(offset).limit(limit).all()
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

    # Check entitlement (capability)
    check_entitlement(db, context.tenant_id, "kpi_read")

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


# --- Brief Endpoints ---


@router.post("/briefs/materialize", response_model=BriefResponse, status_code=status.HTTP_200_OK)
def materialize_brief(
    request: BriefMaterializeRequest,
    context_and_key: Annotated[tuple[TenantContext, str], Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> BriefResponse:
    """Materialize a daily brief for the tenant.

    Requires admin role. Supports idempotent retries via Idempotency-Key header.
    """
    context, idempotency_key = context_and_key
    endpoint = "/v1/briefs/materialize"

    # Check RBAC: only admins can materialize briefs
    if not can_materialize_briefs(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to materialize briefs",
        )

    # Check entitlement (capability)
    check_entitlement(db, context.tenant_id, "briefs")

    # Determine brief_date (default to today UTC if not provided)
    brief_date = request.date
    if brief_date is None:
        brief_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Normalize request body for idempotency check
    request_body = {
        "date": brief_date,
        "window_days": request.window_days,
        "top_n": request.top_n,
    }

    # Check idempotency BEFORE quota (replays must not consume quota)
    try:
        cached_response = check_idempotency(
            db=db,
            tenant_id=context.tenant_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_body=request_body,
        )
        if cached_response is not None:
            return BriefResponse(**cached_response)
    except IdempotencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    # Check if brief already exists for this tenant + date
    existing_brief = db.query(Brief).filter(
        Brief.tenant_id == context.tenant_id,
        Brief.brief_date == brief_date,
    ).first()

    if existing_brief:
        # Brief exists, return it and store idempotency record (no quota consumed)
        content = json.loads(existing_brief.content_json)
        response = BriefResponse(
            brief_id=existing_brief.brief_id,
            request_id=existing_brief.request_id,
            content=content,
        )
        # Store idempotency record (so future calls with same key return same response)
        store_idempotency(
            db=db,
            tenant_id=context.tenant_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_body=request_body,
            response=response.model_dump(),
        )
        return response

    # Brief will be newly created - check billing quota
    check_billing_quota(db, context.tenant_id, "daily_brief_generated", requested_raw_units=1)

    # Also check legacy daily quota for backward compatibility
    today = get_today_date_utc()
    check_quota(db, context.tenant_id, today, "daily_brief_generated", requested_units=1)

    # Generate brief content
    content = generate_daily_brief(
        db=db,
        tenant_id=context.tenant_id,
        brief_date=brief_date,
        window_days=request.window_days,
        top_n=request.top_n,
    )

    # Generate IDs
    brief_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    # Create brief record
    brief = Brief(
        brief_id=brief_id,
        tenant_id=context.tenant_id,
        brief_date=brief_date,
        window_days=request.window_days,
        top_n=request.top_n,
        content_json=json.dumps(content),
        request_id=request_id,
    )
    db.add(brief)

    # Write audit log
    audit_log = AuditLog(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="briefs.materialize",
        tool_name="daily_brief",
        request_id=request_id,
    )
    db.add(audit_log)

    # Emit usage via centralized metering
    emit_usage(
        db=db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        event_key="daily_brief_generated",
        raw_units=1,
        request_id=request_id,
        tool_name="daily_brief",
    )

    # Increment legacy daily usage rollup for backward compatibility
    increment_usage(db, context.tenant_id, today, "daily_brief_generated", units=1)

    db.commit()

    # Build response
    response = BriefResponse(
        brief_id=brief_id,
        request_id=request_id,
        content=content,
    )

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


@router.get("/briefs/latest", response_model=BriefResponse)
def get_latest_brief(
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> BriefResponse:
    """Get the most recent brief for the tenant.

    Requires member or admin role.
    """
    # Check RBAC: admin and member can read briefs
    if not can_read_briefs(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to read briefs",
        )

    # Get the latest brief by brief_date
    latest_brief = db.query(Brief).filter(
        Brief.tenant_id == context.tenant_id
    ).order_by(Brief.brief_date.desc()).first()

    if not latest_brief:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No briefs found for this tenant",
        )

    content = json.loads(latest_brief.content_json)
    return BriefResponse(
        brief_id=latest_brief.brief_id,
        request_id=latest_brief.request_id,
        content=content,
    )


@router.get("/briefs/{date}", response_model=BriefResponse)
def get_brief_by_date(
    date: str,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> BriefResponse:
    """Get a brief by date.

    Requires member or admin role.
    """
    # Check RBAC: admin and member can read briefs
    if not can_read_briefs(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to read briefs",
        )

    # Fetch brief by tenant_id and date
    brief = db.query(Brief).filter(
        Brief.tenant_id == context.tenant_id,
        Brief.brief_date == date,
    ).first()

    if not brief:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brief for date '{date}' not found",
        )

    content = json.loads(brief.content_json)
    return BriefResponse(
        brief_id=brief.brief_id,
        request_id=brief.request_id,
        content=content,
    )


# --- Notification Endpoints ---


@router.get("/notifications/prefs", response_model=NotificationPrefResponse)
def get_notification_prefs(
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> NotificationPrefResponse:
    """Get notification preferences for the current user.

    Returns defaults if no preferences have been saved.
    """
    pref = db.query(NotificationPref).filter(
        NotificationPref.tenant_id == context.tenant_id,
        NotificationPref.user_id == context.user_id,
    ).first()

    if pref:
        return NotificationPrefResponse(
            daily_brief_enabled=bool(pref.daily_brief_enabled),
            delivery_method=pref.delivery_method,
        )

    # Return defaults if no prefs exist
    return NotificationPrefResponse(
        daily_brief_enabled=True,
        delivery_method="in_app",
    )


@router.put("/notifications/prefs", response_model=NotificationPrefResponse)
def update_notification_prefs(
    request: NotificationPrefRequest,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> NotificationPrefResponse:
    """Update notification preferences for the current user."""
    pref = db.query(NotificationPref).filter(
        NotificationPref.tenant_id == context.tenant_id,
        NotificationPref.user_id == context.user_id,
    ).first()

    now = datetime.now(timezone.utc)

    if pref:
        pref.daily_brief_enabled = 1 if request.daily_brief_enabled else 0
        pref.delivery_method = request.delivery_method
        pref.updated_at = now
    else:
        pref = NotificationPref(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            daily_brief_enabled=1 if request.daily_brief_enabled else 0,
            delivery_method=request.delivery_method,
            created_at=now,
            updated_at=now,
        )
        db.add(pref)

    db.commit()
    db.refresh(pref)

    return NotificationPrefResponse(
        daily_brief_enabled=bool(pref.daily_brief_enabled),
        delivery_method=pref.delivery_method,
    )


@router.get("/notifications/outbox", response_model=NotificationOutboxResponse)
def list_notifications(
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
    date: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> NotificationOutboxResponse:
    """List notifications for the current user.

    Optional filters: date (YYYY-MM-DD), status (queued|acked), limit.
    """
    query = db.query(NotificationOutbox).filter(
        NotificationOutbox.tenant_id == context.tenant_id,
        NotificationOutbox.user_id == context.user_id,
    )

    if date:
        query = query.filter(NotificationOutbox.notif_date == date)
    if status:
        query = query.filter(NotificationOutbox.status == status)

    notifications = query.order_by(NotificationOutbox.created_at.desc()).limit(limit).all()

    items = []
    for notif in notifications:
        items.append(NotificationOutboxItem(
            id=notif.id,
            notification_type=notif.notification_type,
            date=notif.notif_date,
            status=notif.status,
            request_id=notif.request_id,
            payload=json.loads(notif.payload_json),
        ))

    return NotificationOutboxResponse(items=items)


@router.post("/notifications/{notification_id}/ack")
def ack_notification(
    notification_id: int,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> NotificationOutboxItem:
    """Acknowledge a notification.

    Only the owner of the notification can acknowledge it.
    """
    # Filter by tenant_id and user_id in the query to prevent IDOR attacks
    # and avoid leaking existence of notifications belonging to other users
    notif = db.query(NotificationOutbox).filter(
        NotificationOutbox.id == notification_id,
        NotificationOutbox.tenant_id == context.tenant_id,
        NotificationOutbox.user_id == context.user_id,
    ).first()

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found",
        )

    notif.status = "acked"
    db.commit()
    db.refresh(notif)

    return NotificationOutboxItem(
        id=notif.id,
        notification_type=notif.notification_type,
        date=notif.notif_date,
        status=notif.status,
        request_id=notif.request_id,
        payload=json.loads(notif.payload_json),
    )


# --- Job Runner Endpoints ---


@router.post("/jobs/daily-brief", response_model=DailyBriefRunnerResponse)
def run_daily_brief_job(
    request: DailyBriefRunnerRequest,
    context_and_key: Annotated[tuple[TenantContext, str], Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> DailyBriefRunnerResponse:
    """Run the daily brief job: materialize brief and enqueue notifications.

    Requires admin role. Idempotent via Idempotency-Key header.
    """
    context, idempotency_key = context_and_key
    endpoint = "/v1/jobs/daily-brief"

    # Check RBAC: only admins can run jobs
    if not can_run_jobs(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to run jobs",
        )

    # Check entitlements (briefs and notifications)
    check_entitlement(db, context.tenant_id, "briefs")
    check_entitlement(db, context.tenant_id, "notifications")

    # Determine brief_date (default to today UTC if not provided)
    brief_date = request.date
    if brief_date is None:
        brief_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Normalize request body for idempotency check
    request_body = {
        "date": brief_date,
        "window_days": request.window_days,
        "top_n": request.top_n,
    }

    # Check idempotency BEFORE quota (replays must not consume quota)
    try:
        cached_response = check_idempotency(
            db=db,
            tenant_id=context.tenant_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_body=request_body,
        )
        if cached_response is not None:
            return DailyBriefRunnerResponse(**cached_response)
    except IdempotencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    # Get today's date for legacy quota checking
    today = get_today_date_utc()

    # Ensure brief exists for this date
    brief_created = False
    existing_brief = db.query(Brief).filter(
        Brief.tenant_id == context.tenant_id,
        Brief.brief_date == brief_date,
    ).first()

    if existing_brief:
        brief_id = existing_brief.brief_id
        brief_content = json.loads(existing_brief.content_json)
    else:
        # Brief will be newly created - check billing quota
        check_billing_quota(db, context.tenant_id, "daily_brief_generated", requested_raw_units=1)

        # Also check legacy daily quota for backward compatibility
        check_quota(db, context.tenant_id, today, "daily_brief_generated", requested_units=1)

        # Create the brief using the same generator as /v1/briefs/materialize
        brief_content = generate_daily_brief(
            db=db,
            tenant_id=context.tenant_id,
            brief_date=brief_date,
            window_days=request.window_days,
            top_n=request.top_n,
        )

        brief_id = str(uuid.uuid4())
        brief_request_id = str(uuid.uuid4())

        brief = Brief(
            brief_id=brief_id,
            tenant_id=context.tenant_id,
            brief_date=brief_date,
            window_days=request.window_days,
            top_n=request.top_n,
            content_json=json.dumps(brief_content),
            request_id=brief_request_id,
        )
        db.add(brief)

        # Write audit log for brief creation
        audit_log = AuditLog(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            action="briefs.materialize",
            tool_name="daily_brief",
            request_id=brief_request_id,
        )
        db.add(audit_log)

        # Emit usage via centralized metering
        emit_usage(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            event_key="daily_brief_generated",
            raw_units=1,
            request_id=brief_request_id,
            tool_name="daily_brief",
        )

        # Increment legacy daily usage rollup for backward compatibility
        increment_usage(db, context.tenant_id, today, "daily_brief_generated", units=1)

        brief_created = True

    # Enqueue notifications for opted-in users
    # Find all users in this tenant with daily_brief_enabled=1 and delivery_method="in_app"
    opted_in_prefs = db.query(NotificationPref).filter(
        NotificationPref.tenant_id == context.tenant_id,
        NotificationPref.daily_brief_enabled == 1,
        NotificationPref.delivery_method == "in_app",
    ).all()

    # Also include users without explicit prefs (defaults: enabled=true, method=in_app)
    # Get user_ids that have explicit prefs
    explicit_user_ids = {p.user_id for p in opted_in_prefs}

    # Get all users in this tenant
    all_users = db.query(GatewayUser).filter(
        GatewayUser.tenant_id == context.tenant_id,
    ).all()

    # Users with default prefs (no explicit row)
    default_enabled_users = [u for u in all_users if u.user_id not in explicit_user_ids]

    # Also include users who explicitly opted out
    opted_out_prefs = db.query(NotificationPref).filter(
        NotificationPref.tenant_id == context.tenant_id,
        NotificationPref.daily_brief_enabled == 0,
    ).all()
    opted_out_user_ids = {p.user_id for p in opted_out_prefs}

    # Final list of users to notify: explicit opt-in + default (minus explicit opt-out)
    users_to_notify = [p.user_id for p in opted_in_prefs]
    users_to_notify.extend([u.user_id for u in default_enabled_users if u.user_id not in opted_out_user_ids])

    # Generate a single request_id for this runner execution
    runner_request_id = str(uuid.uuid4())

    # Prepare notification payload
    notification_payload = {
        "title": "Daily Brief",
        "date": brief_date,
        "summary": brief_content.get("summary", {}),
        "highlights": brief_content.get("highlights", []),
    }
    payload_json = json.dumps(notification_payload)

    # Batch fetch existing notifications to avoid N+1 queries
    existing_notifications = db.query(NotificationOutbox.user_id).filter(
        NotificationOutbox.tenant_id == context.tenant_id,
        NotificationOutbox.user_id.in_(users_to_notify),
        NotificationOutbox.notification_type == "daily_brief",
        NotificationOutbox.notif_date == brief_date,
    ).all()
    existing_user_ids = {n.user_id for n in existing_notifications}

    # Determine how many new notifications we can insert based on quota
    users_needing_notification = [uid for uid in users_to_notify if uid not in existing_user_ids]

    # Get billing remaining quota for notifications
    billing_remaining = get_remaining_billing_quota(db, context.tenant_id, "notification_enqueued")
    allowed_notifications = billing_remaining.get("allowed_raw_units", 0)

    # Also check legacy daily quota
    legacy_remaining_quota = get_remaining_quota(db, context.tenant_id, today, "notification_enqueued")
    legacy_remaining_quota = max(0, legacy_remaining_quota)

    # Use the minimum of both quotas
    effective_remaining = min(allowed_notifications, legacy_remaining_quota)

    notifications_inserted = 0
    notifications_ignored = len(existing_user_ids)
    notifications_suppressed_due_to_quota = 0

    for user_id in users_needing_notification:
        if effective_remaining <= 0:
            # Quota exhausted, suppress remaining notifications
            notifications_suppressed_due_to_quota += 1
            continue

        notif = NotificationOutbox(
            tenant_id=context.tenant_id,
            user_id=user_id,
            notification_type="daily_brief",
            notif_date=brief_date,
            status="queued",
            payload_json=payload_json,
            request_id=runner_request_id,
        )
        db.add(notif)
        notifications_inserted += 1
        effective_remaining -= 1

        # Emit usage via centralized metering
        emit_usage(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            event_key="notification_enqueued",
            raw_units=1,
            request_id=runner_request_id,
            tool_name="daily_brief",
        )

        # Increment legacy daily usage rollup
        increment_usage(db, context.tenant_id, today, "notification_enqueued", units=1)

    # Write a single audit log for the enqueue action
    if notifications_inserted > 0 or notifications_ignored > 0 or notifications_suppressed_due_to_quota > 0:
        audit_log = AuditLog(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            action="notifications.enqueue",
            tool_name="daily_brief",
            request_id=runner_request_id,
        )
        db.add(audit_log)

    db.commit()

    # Build response
    response = DailyBriefRunnerResponse(
        date=brief_date,
        brief_id=brief_id,
        brief_created=brief_created,
        notifications_inserted=notifications_inserted,
        notifications_ignored=notifications_ignored,
        notifications_suppressed_due_to_quota=notifications_suppressed_due_to_quota,
    )

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


# --- Conversation Endpoints ---


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    request: ConversationCreate,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """Create a new conversation.

    Requires admin or member role with chat permission.
    """
    if not can_use_cofounder_chat(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to use chat",
        )

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    conversation = Conversation(
        conversation_id=str(uuid.uuid4()),
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        title=request.title,
        created_at=now,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return ConversationResponse(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        created_at=conversation.created_at,
    )


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> ConversationListResponse:
    """List conversations for the current user with pagination.

    Only returns conversations owned by this user within this tenant.

    Args:
        limit: Maximum number of conversations to return (default 50, max 200).
        offset: Number of conversations to skip (default 0).
    """
    if not can_use_cofounder_chat(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to use chat",
        )

    # Enforce reasonable limits
    limit = min(max(1, limit), 200)
    offset = max(0, offset)

    conversations = db.query(Conversation).filter(
        Conversation.tenant_id == context.tenant_id,
        Conversation.user_id == context.user_id,
    ).order_by(Conversation.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        ConversationResponse(
            conversation_id=c.conversation_id,
            title=c.title,
            created_at=c.created_at,
        )
        for c in conversations
    ]
    return ConversationListResponse(items=items)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: str,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    """Get a conversation with its messages.

    Only the owner can view their conversation.
    """
    if not can_use_cofounder_chat(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to use chat",
        )

    # Fetch conversation with tenant and user isolation
    conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.tenant_id == context.tenant_id,
        Conversation.user_id == context.user_id,
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Fetch messages for this conversation
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.tenant_id == context.tenant_id,
    ).order_by(Message.created_at.asc()).all()

    message_responses = [
        MessageResponse(
            message_id=m.message_id,
            role=m.role,
            content=m.content,
            cards=json.loads(m.metadata_json),
            created_at=m.created_at,
        )
        for m in messages
    ]

    return ConversationDetailResponse(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        created_at=conversation.created_at,
        messages=message_responses,
    )


# --- Cofounder Chat Endpoint ---


def _compute_kpi_summary(db: Session, tenant_id: str, kpi_id: str, window_days: int = 7) -> dict:
    """Compute KPI summary (reusing logic from tools.py)."""
    from datetime import timedelta

    kpi = db.query(KPIDefinition).filter(
        KPIDefinition.kpi_id == kpi_id,
        KPIDefinition.tenant_id == tenant_id,
    ).first()
    if not kpi:
        return {"error": f"KPI '{kpi_id}' not found"}

    latest_point = db.query(KPIPoint).filter(
        KPIPoint.tenant_id == tenant_id,
        KPIPoint.kpi_id == kpi_id,
    ).order_by(KPIPoint.ts.desc()).first()

    if not latest_point:
        return {"error": f"No data points found for KPI '{kpi_id}'"}

    latest_ts = datetime.fromisoformat(latest_point.ts.replace("Z", "+00:00"))
    window_start = latest_ts - timedelta(days=window_days)
    window_start_str = window_start.isoformat().replace("+00:00", "Z")

    start_point = db.query(KPIPoint).filter(
        KPIPoint.tenant_id == tenant_id,
        KPIPoint.kpi_id == kpi_id,
        KPIPoint.ts >= window_start_str,
        KPIPoint.ts <= latest_point.ts,
    ).order_by(KPIPoint.ts.asc()).first()

    if not start_point:
        start_point = latest_point

    delta_abs = latest_point.value - start_point.value
    if start_point.value == 0:
        delta_pct = None
    else:
        delta_pct = (delta_abs / start_point.value) * 100

    return {
        "kpi_id": kpi_id,
        "name": kpi.name,
        "unit": kpi.unit,
        "latest": {"ts": latest_point.ts, "value": latest_point.value},
        "start": {"ts": start_point.ts, "value": start_point.value},
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
    }


def _route_intent(
    message: str,
    tenant_id: str,
    user_id: str,
    date: str | None,
    db: Session,
) -> tuple[str, list[dict]]:
    """Route message intent and generate deterministic response.

    Returns tuple of (content, cards).
    """
    message_lower = message.lower()

    # Intent: help
    if "help" in message_lower:
        content = (
            "Available commands:\n"
            "- 'today's brief' or 'brief' - Get your latest daily brief\n"
            "- 'kpis' - List all KPIs with latest values\n"
            "- 'kpi:<name>' - Get detailed summary for a specific KPI\n"
            "- 'outbox' or 'notifications' - View queued notifications\n"
            "- 'help' - Show this help message"
        )
        return content, []

    # Intent: brief / today
    if "brief" in message_lower or "today" in message_lower:
        if date:
            brief = db.query(Brief).filter(
                Brief.tenant_id == tenant_id,
                Brief.brief_date == date,
            ).first()
        else:
            brief = db.query(Brief).filter(
                Brief.tenant_id == tenant_id,
            ).order_by(Brief.brief_date.desc()).first()

        if not brief:
            content = (
                "No brief found. To generate a brief, an admin should run:\n"
                "POST /v1/jobs/daily-brief or POST /v1/briefs/materialize"
            )
            return content, []

        brief_content = json.loads(brief.content_json)
        content = f"Here's your brief for {brief.brief_date}:"
        cards = [{
            "type": "brief",
            "date": brief.brief_date,
            "brief_id": brief.brief_id,
            "summary": brief_content.get("summary", {}),
            "highlights": brief_content.get("highlights", []),
        }]
        return content, cards

    # Intent: outbox / notifications
    if "outbox" in message_lower or "notification" in message_lower:
        notifications = db.query(NotificationOutbox).filter(
            NotificationOutbox.tenant_id == tenant_id,
            NotificationOutbox.user_id == user_id,
        ).order_by(NotificationOutbox.created_at.desc()).limit(10).all()

        if not notifications:
            content = "No notifications in your outbox."
            return content, []

        content = f"Found {len(notifications)} notification(s) in your outbox:"
        cards = []
        for notif in notifications:
            payload = json.loads(notif.payload_json)
            cards.append({
                "type": "notification",
                "id": notif.id,
                "date": notif.notif_date,
                "title": payload.get("title", notif.notification_type),
                "status": notif.status,
            })
        return content, cards

    # Intent: kpi:<name> (specific KPI summary)
    import re
    from sqlalchemy import func
    kpi_name_match = re.search(r"kpi:(\S+)", message_lower)
    if kpi_name_match:
        kpi_name = kpi_name_match.group(1)
        # Find KPI by name using case-insensitive database query (more efficient)
        matching_kpi = db.query(KPIDefinition).filter(
            KPIDefinition.tenant_id == tenant_id,
            func.lower(KPIDefinition.name) == kpi_name.lower(),
        ).first()

        if not matching_kpi:
            content = f"KPI '{kpi_name}' not found."
            return content, []

        summary = _compute_kpi_summary(db, tenant_id, matching_kpi.kpi_id, window_days=7)
        if "error" in summary:
            content = summary["error"]
            return content, []

        content = f"Summary for KPI '{matching_kpi.name}':"
        cards = [{
            "type": "kpi_summary",
            **summary,
        }]
        return content, cards

    # Intent: kpis (list all)
    if "kpi" in message_lower:
        kpis = db.query(KPIDefinition).filter(
            KPIDefinition.tenant_id == tenant_id,
        ).all()

        if not kpis:
            content = "No KPIs defined for your tenant."
            return content, []

        # Batch fetch all latest points to avoid N+1 queries
        # Using a subquery to get max ts per kpi_id
        kpi_ids = [kpi.kpi_id for kpi in kpis]
        all_points = db.query(KPIPoint).filter(
            KPIPoint.tenant_id == tenant_id,
            KPIPoint.kpi_id.in_(kpi_ids),
        ).order_by(KPIPoint.kpi_id, KPIPoint.ts.desc()).all()

        # Group by kpi_id and take the first (latest) for each
        latest_by_kpi: dict[str, KPIPoint] = {}
        for point in all_points:
            if point.kpi_id not in latest_by_kpi:
                latest_by_kpi[point.kpi_id] = point

        content = f"Found {len(kpis)} KPI(s):"
        cards = []
        for kpi in kpis:
            latest_point = latest_by_kpi.get(kpi.kpi_id)
            card = {
                "type": "kpi",
                "kpi_id": kpi.kpi_id,
                "name": kpi.name,
                "unit": kpi.unit,
                "latest": None,
            }
            if latest_point:
                card["latest"] = {"ts": latest_point.ts, "value": latest_point.value}
            cards.append(card)
        return content, cards

    # Fallback
    content = "Try: 'today's brief', 'kpis', 'outbox', or 'help'"
    return content, []


@router.post("/cofounder/chat", response_model=ChatResponse)
def cofounder_chat(
    request: ChatRequest,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Send a message to the Cofounder AI assistant.

    The assistant responds with deterministic, data-driven responses
    based on your briefs, KPIs, and notifications.
    """
    if not can_use_cofounder_chat(context.user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to use chat",
        )

    # Check entitlement (capability)
    check_entitlement(db, context.tenant_id, "chat")

    # Check billing quota before making any state changes
    check_billing_quota(db, context.tenant_id, "assistant_query", requested_raw_units=1)

    # Also check legacy daily quota for backward compatibility
    today = get_today_date_utc()
    check_quota(db, context.tenant_id, today, "assistant_query", requested_units=1)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    request_id = str(uuid.uuid4())

    # Handle conversation: create new or use existing
    if request.conversation_id:
        conversation = db.query(Conversation).filter(
            Conversation.conversation_id == request.conversation_id,
            Conversation.tenant_id == context.tenant_id,
            Conversation.user_id == context.user_id,
        ).first()
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
    else:
        # Create new conversation with title from first message
        title = request.message[:40] if len(request.message) > 40 else request.message
        conversation = Conversation(
            conversation_id=str(uuid.uuid4()),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            title=title,
            created_at=now,
        )
        db.add(conversation)

    # Persist user message
    user_message = Message(
        message_id=str(uuid.uuid4()),
        conversation_id=conversation.conversation_id,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        role="user",
        content=request.message,
        metadata_json="[]",
        created_at=now,
    )
    db.add(user_message)

    # Generate assistant response (deterministic intent routing)
    assistant_content, assistant_cards = _route_intent(
        message=request.message,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        date=request.date,
        db=db,
    )

    # Persist assistant message
    assistant_message_id = str(uuid.uuid4())
    assistant_message = Message(
        message_id=assistant_message_id,
        conversation_id=conversation.conversation_id,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        role="assistant",
        content=assistant_content,
        metadata_json=json.dumps(assistant_cards),
        created_at=now,
    )
    db.add(assistant_message)

    # Write audit log
    audit_log = AuditLog(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="cofounder.chat",
        tool_name="chat",
        request_id=request_id,
    )
    db.add(audit_log)

    # Emit usage via centralized metering
    emit_usage(
        db=db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        event_key="assistant_query",
        raw_units=1,
        request_id=request_id,
        tool_name="chat",
    )

    # Increment legacy daily usage rollup for backward compatibility
    increment_usage(db, context.tenant_id, today, "assistant_query", units=1)

    db.commit()

    return ChatResponse(
        request_id=request_id,
        conversation_id=conversation.conversation_id,
        assistant_message=ChatAssistantMessage(
            message_id=assistant_message_id,
            content=assistant_content,
            cards=assistant_cards,
        ),
    )


# --- Tenant Limits Endpoints ---


@router.get("/limits", response_model=TenantLimitsResponse)
def get_limits(
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> TenantLimitsResponse:
    """Get the current tenant's daily limits.

    Accessible by all authenticated users (admin and member).
    """
    tenant_limit = db.query(TenantLimit).filter(
        TenantLimit.tenant_id == context.tenant_id
    ).first()

    if tenant_limit:
        return TenantLimitsResponse(
            tenant_id=context.tenant_id,
            assistant_query_daily_limit=tenant_limit.assistant_query_daily_limit,
            tool_invocation_daily_limit=tenant_limit.tool_invocation_daily_limit,
            daily_brief_generated_daily_limit=tenant_limit.daily_brief_generated_daily_limit,
            notification_enqueued_daily_limit=tenant_limit.notification_enqueued_daily_limit,
        )

    # Return defaults if no tenant_limits row exists
    return TenantLimitsResponse(
        tenant_id=context.tenant_id,
        assistant_query_daily_limit=DEFAULT_LIMITS["assistant_query_daily_limit"],
        tool_invocation_daily_limit=DEFAULT_LIMITS["tool_invocation_daily_limit"],
        daily_brief_generated_daily_limit=DEFAULT_LIMITS["daily_brief_generated_daily_limit"],
        notification_enqueued_daily_limit=DEFAULT_LIMITS["notification_enqueued_daily_limit"],
    )


@router.put("/limits", response_model=TenantLimitsResponse)
def update_limits(
    request: TenantLimitsUpdateRequest,
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
) -> TenantLimitsResponse:
    """Update the current tenant's daily limits.

    Requires admin role.
    """
    # Check RBAC: only admins can update limits
    if context.user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized to update limits",
        )

    tenant_limit = db.query(TenantLimit).filter(
        TenantLimit.tenant_id == context.tenant_id
    ).first()

    now = datetime.now(timezone.utc)

    if tenant_limit:
        tenant_limit.assistant_query_daily_limit = request.assistant_query_daily_limit
        tenant_limit.tool_invocation_daily_limit = request.tool_invocation_daily_limit
        tenant_limit.daily_brief_generated_daily_limit = request.daily_brief_generated_daily_limit
        tenant_limit.notification_enqueued_daily_limit = request.notification_enqueued_daily_limit
        tenant_limit.updated_at = now
    else:
        tenant_limit = TenantLimit(
            tenant_id=context.tenant_id,
            assistant_query_daily_limit=request.assistant_query_daily_limit,
            tool_invocation_daily_limit=request.tool_invocation_daily_limit,
            daily_brief_generated_daily_limit=request.daily_brief_generated_daily_limit,
            notification_enqueued_daily_limit=request.notification_enqueued_daily_limit,
            created_at=now,
            updated_at=now,
        )
        db.add(tenant_limit)

    db.commit()
    db.refresh(tenant_limit)

    return TenantLimitsResponse(
        tenant_id=context.tenant_id,
        assistant_query_daily_limit=tenant_limit.assistant_query_daily_limit,
        tool_invocation_daily_limit=tenant_limit.tool_invocation_daily_limit,
        daily_brief_generated_daily_limit=tenant_limit.daily_brief_generated_daily_limit,
        notification_enqueued_daily_limit=tenant_limit.notification_enqueued_daily_limit,
    )


# --- Usage Endpoints ---


@router.get("/usage/daily", response_model=DailyUsageResponse)
def get_daily_usage(
    context: Annotated[TenantContext, Depends(get_basic_tenant_context)],
    db: Session = Depends(get_db),
    date: str | None = None,
) -> DailyUsageResponse:
    """Get daily usage summary for the tenant.

    Accessible by all authenticated users (admin and member).

    Args:
        date: Optional date in YYYY-MM-DD format. Defaults to today UTC.
    """
    # Default to today if date not provided
    if date is None:
        date = get_today_date_utc()

    # Get tenant limits
    tenant_limit = db.query(TenantLimit).filter(
        TenantLimit.tenant_id == context.tenant_id
    ).first()

    if tenant_limit:
        limits = TenantLimitsResponse(
            tenant_id=context.tenant_id,
            assistant_query_daily_limit=tenant_limit.assistant_query_daily_limit,
            tool_invocation_daily_limit=tenant_limit.tool_invocation_daily_limit,
            daily_brief_generated_daily_limit=tenant_limit.daily_brief_generated_daily_limit,
            notification_enqueued_daily_limit=tenant_limit.notification_enqueued_daily_limit,
        )
    else:
        limits = TenantLimitsResponse(
            tenant_id=context.tenant_id,
            assistant_query_daily_limit=DEFAULT_LIMITS["assistant_query_daily_limit"],
            tool_invocation_daily_limit=DEFAULT_LIMITS["tool_invocation_daily_limit"],
            daily_brief_generated_daily_limit=DEFAULT_LIMITS["daily_brief_generated_daily_limit"],
            notification_enqueued_daily_limit=DEFAULT_LIMITS["notification_enqueued_daily_limit"],
        )

    # Get usage for each activity type
    activity_types = ["assistant_query", "tool_invocation", "daily_brief_generated", "notification_enqueued"]
    usage = []
    for activity_type in activity_types:
        units = get_usage(db, context.tenant_id, date, activity_type)
        usage.append(UsageItem(activity_type=activity_type, units=units))

    return DailyUsageResponse(
        date=date,
        limits=limits,
        usage=usage,
    )
