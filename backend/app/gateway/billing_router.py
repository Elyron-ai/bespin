"""Billing API router for managing metered events, plans, and usage."""
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.gateway.models import (
    MeteredEventType,
    Plan,
    PlanCapability,
    PlanEventCap,
    TenantSubscription,
    UsageEvent,
    UsageRollupPeriod,
    GatewayTenant,
    GatewayUser,
    Capability,
)
from app.gateway.schemas import (
    MeteredEventTypeCreate,
    MeteredEventTypeUpdate,
    MeteredEventTypeResponse,
    PlanCreate,
    PlanUpdate,
    PlanResponse,
    PlanCapabilitiesUpdate,
    PlanEventCapsUpdate,
    TenantSubscriptionUpdate,
    TenantSubscriptionResponse,
    TenantSubscriptionWithPlanResponse,
    BillingUsageResponse,
    BillingUsageBreakdownItem,
    BillingCreditsInfo,
    BillingLedgerResponse,
    BillingLedgerItem,
)
from app.gateway.billing_period import (
    get_period_start,
    get_period_end,
    get_current_utc_datetime_iso,
)
from app.gateway.entitlements import (
    get_tenant_subscription,
    get_plan,
    get_plan_capabilities,
    update_tenant_subscription,
)
from app.gateway.metering import get_period_usage_summary

router = APIRouter(tags=["billing"])


# =============================================================================
# Platform Admin Authentication
# =============================================================================

def get_platform_admin_key() -> str | None:
    """Get the platform admin key from environment."""
    return os.environ.get("PLATFORM_ADMIN_KEY")


def verify_platform_admin(
    x_platform_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    """Verify the platform admin key.

    Uses 404 to avoid revealing the existence of admin endpoints.
    """
    admin_key = get_platform_admin_key()
    if not admin_key:
        # No admin key configured, admin endpoints disabled
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )

    if x_platform_admin_key != admin_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )


# =============================================================================
# Tenant Authentication (reused from main router)
# =============================================================================

import secrets


def get_tenant_context_for_billing(
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> tuple[str, str]:
    """Validate headers and return (tenant_id, user_id) for billing endpoints."""
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

    return x_tenant_id, x_user_id


# =============================================================================
# Platform Admin APIs - Metered Events
# =============================================================================

@router.get(
    "/v1/admin/metered-events",
    response_model=list[MeteredEventTypeResponse],
    dependencies=[Depends(verify_platform_admin)],
)
def list_metered_events(
    db: Session = Depends(get_db),
) -> list[MeteredEventTypeResponse]:
    """List all metered event types (admin only)."""
    events = db.query(MeteredEventType).order_by(MeteredEventType.event_key).all()
    return [
        MeteredEventTypeResponse(
            event_key=e.event_key,
            display_name=e.display_name,
            description=e.description,
            unit_name=e.unit_name,
            credits_per_unit=e.credits_per_unit,
            list_price_per_credit=e.list_price_per_credit,
            billable=bool(e.billable),
            active=bool(e.active),
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in events
    ]


@router.post(
    "/v1/admin/metered-events",
    response_model=MeteredEventTypeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_platform_admin)],
)
def create_metered_event(
    request: MeteredEventTypeCreate,
    db: Session = Depends(get_db),
) -> MeteredEventTypeResponse:
    """Create a metered event type (admin only)."""
    # Check if event_key already exists
    existing = db.query(MeteredEventType).filter(
        MeteredEventType.event_key == request.event_key
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Event type '{request.event_key}' already exists",
        )

    now_iso = get_current_utc_datetime_iso()
    event = MeteredEventType(
        event_key=request.event_key,
        display_name=request.display_name,
        description=request.description,
        unit_name=request.unit_name,
        credits_per_unit=request.credits_per_unit,
        list_price_per_credit=request.list_price_per_credit,
        billable=1 if request.billable else 0,
        active=1 if request.active else 0,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return MeteredEventTypeResponse(
        event_key=event.event_key,
        display_name=event.display_name,
        description=event.description,
        unit_name=event.unit_name,
        credits_per_unit=event.credits_per_unit,
        list_price_per_credit=event.list_price_per_credit,
        billable=bool(event.billable),
        active=bool(event.active),
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


@router.put(
    "/v1/admin/metered-events/{event_key}",
    response_model=MeteredEventTypeResponse,
    dependencies=[Depends(verify_platform_admin)],
)
def update_metered_event(
    event_key: str,
    request: MeteredEventTypeUpdate,
    db: Session = Depends(get_db),
) -> MeteredEventTypeResponse:
    """Update a metered event type (admin only)."""
    event = db.query(MeteredEventType).filter(
        MeteredEventType.event_key == event_key
    ).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event type '{event_key}' not found",
        )

    now_iso = get_current_utc_datetime_iso()

    if request.display_name is not None:
        event.display_name = request.display_name
    if request.description is not None:
        event.description = request.description
    if request.unit_name is not None:
        event.unit_name = request.unit_name
    if request.credits_per_unit is not None:
        event.credits_per_unit = request.credits_per_unit
    if request.list_price_per_credit is not None:
        event.list_price_per_credit = request.list_price_per_credit
    if request.billable is not None:
        event.billable = 1 if request.billable else 0
    if request.active is not None:
        event.active = 1 if request.active else 0

    event.updated_at = now_iso
    db.commit()
    db.refresh(event)

    return MeteredEventTypeResponse(
        event_key=event.event_key,
        display_name=event.display_name,
        description=event.description,
        unit_name=event.unit_name,
        credits_per_unit=event.credits_per_unit,
        list_price_per_credit=event.list_price_per_credit,
        billable=bool(event.billable),
        active=bool(event.active),
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


# =============================================================================
# Platform Admin APIs - Plans
# =============================================================================

@router.get(
    "/v1/admin/plans",
    response_model=list[PlanResponse],
    dependencies=[Depends(verify_platform_admin)],
)
def list_plans(
    db: Session = Depends(get_db),
) -> list[PlanResponse]:
    """List all plans (admin only)."""
    plans = db.query(Plan).order_by(Plan.plan_id).all()
    return [
        PlanResponse(
            plan_id=p.plan_id,
            name=p.name,
            included_credits=p.included_credits,
            overage_price_per_credit=p.overage_price_per_credit,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in plans
    ]


@router.post(
    "/v1/admin/plans",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_platform_admin)],
)
def create_plan(
    request: PlanCreate,
    db: Session = Depends(get_db),
) -> PlanResponse:
    """Create a plan (admin only)."""
    existing = db.query(Plan).filter(Plan.plan_id == request.plan_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plan '{request.plan_id}' already exists",
        )

    now_iso = get_current_utc_datetime_iso()
    plan = Plan(
        plan_id=request.plan_id,
        name=request.name,
        included_credits=request.included_credits,
        overage_price_per_credit=request.overage_price_per_credit,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return PlanResponse(
        plan_id=plan.plan_id,
        name=plan.name,
        included_credits=plan.included_credits,
        overage_price_per_credit=plan.overage_price_per_credit,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.put(
    "/v1/admin/plans/{plan_id}",
    response_model=PlanResponse,
    dependencies=[Depends(verify_platform_admin)],
)
def update_plan(
    plan_id: str,
    request: PlanUpdate,
    db: Session = Depends(get_db),
) -> PlanResponse:
    """Update a plan (admin only)."""
    plan = db.query(Plan).filter(Plan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' not found",
        )

    now_iso = get_current_utc_datetime_iso()

    if request.name is not None:
        plan.name = request.name
    if request.included_credits is not None:
        plan.included_credits = request.included_credits
    if request.overage_price_per_credit is not None:
        plan.overage_price_per_credit = request.overage_price_per_credit

    plan.updated_at = now_iso
    db.commit()
    db.refresh(plan)

    return PlanResponse(
        plan_id=plan.plan_id,
        name=plan.name,
        included_credits=plan.included_credits,
        overage_price_per_credit=plan.overage_price_per_credit,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.put(
    "/v1/admin/plans/{plan_id}/capabilities",
    response_model=list[str],
    dependencies=[Depends(verify_platform_admin)],
)
def update_plan_capabilities(
    plan_id: str,
    request: PlanCapabilitiesUpdate,
    db: Session = Depends(get_db),
) -> list[str]:
    """Update capabilities for a plan (admin only)."""
    plan = db.query(Plan).filter(Plan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' not found",
        )

    # Delete existing capabilities
    db.query(PlanCapability).filter(PlanCapability.plan_id == plan_id).delete()

    # Add new capabilities
    for cap_key in request.capabilities:
        # Verify capability exists
        cap = db.query(Capability).filter(Capability.capability_key == cap_key).first()
        if not cap:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Capability '{cap_key}' not found",
            )
        db.add(PlanCapability(plan_id=plan_id, capability_key=cap_key))

    db.commit()
    return request.capabilities


@router.put(
    "/v1/admin/plans/{plan_id}/caps",
    response_model=list[dict],
    dependencies=[Depends(verify_platform_admin)],
)
def update_plan_event_caps(
    plan_id: str,
    request: PlanEventCapsUpdate,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Update event caps for a plan (admin only)."""
    plan = db.query(Plan).filter(Plan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' not found",
        )

    # Delete existing caps for this plan
    db.query(PlanEventCap).filter(PlanEventCap.plan_id == plan_id).delete()

    # Add new caps
    result = []
    for cap in request.caps:
        # Verify event type exists
        event = db.query(MeteredEventType).filter(
            MeteredEventType.event_key == cap.event_key
        ).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Event type '{cap.event_key}' not found",
            )
        db.add(PlanEventCap(
            plan_id=plan_id,
            event_key=cap.event_key,
            period=cap.period,
            cap_raw_units=cap.cap_raw_units,
        ))
        result.append({
            "event_key": cap.event_key,
            "period": cap.period,
            "cap_raw_units": cap.cap_raw_units,
        })

    db.commit()
    return result


# =============================================================================
# Platform Admin APIs - Tenant Subscriptions
# =============================================================================

@router.put(
    "/v1/admin/tenants/{tenant_id}/subscription",
    response_model=TenantSubscriptionResponse,
    dependencies=[Depends(verify_platform_admin)],
)
def admin_update_tenant_subscription(
    tenant_id: str,
    request: TenantSubscriptionUpdate,
    db: Session = Depends(get_db),
) -> TenantSubscriptionResponse:
    """Update or create a tenant subscription (admin only)."""
    # Verify tenant exists
    tenant = db.query(GatewayTenant).filter(
        GatewayTenant.tenant_id == tenant_id
    ).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )

    # Verify plan exists
    plan = db.query(Plan).filter(Plan.plan_id == request.plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{request.plan_id}' not found",
        )

    subscription = update_tenant_subscription(
        db=db,
        tenant_id=tenant_id,
        plan_id=request.plan_id,
        status=request.status,
        period_start=request.period_start,
    )
    db.commit()
    db.refresh(subscription)

    return TenantSubscriptionResponse(
        tenant_id=subscription.tenant_id,
        plan_id=subscription.plan_id,
        status=subscription.status,
        period_start=subscription.period_start,
        period_end=subscription.period_end,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


# =============================================================================
# Tenant-facing Billing APIs
# =============================================================================

@router.get("/v1/billing/events", response_model=list[MeteredEventTypeResponse])
def get_billing_events(
    context: Annotated[tuple[str, str], Depends(get_tenant_context_for_billing)],
    db: Session = Depends(get_db),
) -> list[MeteredEventTypeResponse]:
    """Get active metered event types (read-only, tenant-facing)."""
    events = db.query(MeteredEventType).filter(
        MeteredEventType.active == 1
    ).order_by(MeteredEventType.event_key).all()

    return [
        MeteredEventTypeResponse(
            event_key=e.event_key,
            display_name=e.display_name,
            description=e.description,
            unit_name=e.unit_name,
            credits_per_unit=e.credits_per_unit,
            list_price_per_credit=e.list_price_per_credit,
            billable=bool(e.billable),
            active=bool(e.active),
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in events
    ]


@router.get("/v1/billing/plan", response_model=TenantSubscriptionWithPlanResponse)
def get_billing_plan(
    context: Annotated[tuple[str, str], Depends(get_tenant_context_for_billing)],
    db: Session = Depends(get_db),
) -> TenantSubscriptionWithPlanResponse:
    """Get tenant subscription with plan details."""
    tenant_id, _ = context

    subscription = get_tenant_subscription(db, tenant_id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for tenant",
        )

    plan = get_plan(db, subscription.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plan '{subscription.plan_id}' not found",
        )

    capabilities = get_plan_capabilities(db, subscription.plan_id)

    return TenantSubscriptionWithPlanResponse(
        tenant_id=subscription.tenant_id,
        plan_id=subscription.plan_id,
        status=subscription.status,
        period_start=subscription.period_start,
        period_end=subscription.period_end,
        plan=PlanResponse(
            plan_id=plan.plan_id,
            name=plan.name,
            included_credits=plan.included_credits,
            overage_price_per_credit=plan.overage_price_per_credit,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        ),
        capabilities=capabilities,
    )


@router.get("/v1/billing/usage", response_model=BillingUsageResponse)
def get_billing_usage(
    context: Annotated[tuple[str, str], Depends(get_tenant_context_for_billing)],
    db: Session = Depends(get_db),
    period_start: str | None = None,
) -> BillingUsageResponse:
    """Get billing usage for a period."""
    tenant_id, _ = context

    # Default to current period
    if period_start is None:
        period_start = get_period_start()

    period_end = get_period_end(period_start)

    # Get subscription and plan
    subscription = get_tenant_subscription(db, tenant_id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for tenant",
        )

    plan = get_plan(db, subscription.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plan '{subscription.plan_id}' not found",
        )

    # Get usage summary
    usage_summary = get_period_usage_summary(db, tenant_id, period_start)

    # Calculate credits info
    used_credits = usage_summary["total_credits"]
    remaining = max(0, plan.included_credits - used_credits)
    overage_credits = max(0, used_credits - plan.included_credits)
    estimated_overage_cost = overage_credits * plan.overage_price_per_credit

    credits_info = BillingCreditsInfo(
        included=plan.included_credits,
        used=used_credits,
        remaining=remaining,
        overage_credits=overage_credits,
        estimated_overage_cost=estimated_overage_cost,
        estimated_list_cost=usage_summary["total_list_cost_estimate"],
    )

    # Build breakdown
    breakdown = [
        BillingUsageBreakdownItem(
            event_key=item["event_key"],
            unit_name=item["unit_name"],
            raw_units=item["raw_units"],
            credits=item["credits"],
            list_cost_estimate=item["list_cost_estimate"],
        )
        for item in usage_summary["breakdown"]
    ]

    return BillingUsageResponse(
        period_start=period_start,
        period_end=period_end,
        plan=PlanResponse(
            plan_id=plan.plan_id,
            name=plan.name,
            included_credits=plan.included_credits,
            overage_price_per_credit=plan.overage_price_per_credit,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        ),
        credits=credits_info,
        breakdown=breakdown,
    )


@router.get("/v1/billing/ledger", response_model=BillingLedgerResponse)
def get_billing_ledger(
    context: Annotated[tuple[str, str], Depends(get_tenant_context_for_billing)],
    db: Session = Depends(get_db),
    period_start: str | None = None,
    limit: int = 200,
) -> BillingLedgerResponse:
    """Get billing ledger (usage events) for a period."""
    tenant_id, _ = context

    # Default to current period
    if period_start is None:
        period_start = get_period_start()

    period_end = get_period_end(period_start)

    # Enforce reasonable limit
    limit = min(max(1, limit), 1000)

    # Query usage events for the period
    # Filter by created_at within the period
    from datetime import datetime
    period_start_dt = datetime.strptime(period_start, "%Y-%m-%d")
    period_end_dt = datetime.strptime(period_end, "%Y-%m-%d")

    events = db.query(UsageEvent).filter(
        UsageEvent.tenant_id == tenant_id,
        UsageEvent.created_at >= period_start_dt,
        UsageEvent.created_at < period_end_dt,
    ).order_by(UsageEvent.created_at.desc()).limit(limit).all()

    items = [
        BillingLedgerItem(
            event_key=e.activity_type,
            raw_units=e.units,
            credits=e.credits or 0.0,
            list_cost_estimate=e.list_cost_estimate or 0.0,
            tool_name=e.tool_name,
            request_id=e.request_id,
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in events
    ]

    return BillingLedgerResponse(
        period_start=period_start,
        items=items,
    )
