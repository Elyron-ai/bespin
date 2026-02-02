"""Entitlements module for capability checking and subscription management."""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.gateway.models import (
    TenantSubscription,
    Plan,
    PlanCapability,
    PlanEventCap,
    MeteredEventType,
)
from app.gateway.billing_period import (
    get_period_start,
    get_period_end,
    get_current_utc_datetime_iso,
)
from app.gateway.metering import (
    get_total_credits_used,
    get_event_usage_for_period,
    get_metered_event_type,
    calculate_credits_and_cost,
)


class EntitlementError(Exception):
    """Base exception for entitlement errors."""
    pass


class SubscriptionNotFoundError(EntitlementError):
    """Raised when a tenant has no subscription."""
    pass


class SubscriptionSuspendedError(EntitlementError):
    """Raised when a tenant's subscription is suspended."""
    pass


class CapabilityDeniedError(EntitlementError):
    """Raised when a tenant lacks a required capability."""
    pass


def get_tenant_subscription(
    db: Session,
    tenant_id: str,
) -> TenantSubscription | None:
    """Get a tenant's subscription.

    Args:
        db: Database session.
        tenant_id: The tenant ID.

    Returns:
        The TenantSubscription or None.
    """
    return db.query(TenantSubscription).filter(
        TenantSubscription.tenant_id == tenant_id
    ).first()


def get_plan(db: Session, plan_id: str) -> Plan | None:
    """Get a plan by ID.

    Args:
        db: Database session.
        plan_id: The plan ID.

    Returns:
        The Plan or None.
    """
    return db.query(Plan).filter(Plan.plan_id == plan_id).first()


def get_plan_capabilities(db: Session, plan_id: str) -> list[str]:
    """Get all capabilities for a plan.

    Args:
        db: Database session.
        plan_id: The plan ID.

    Returns:
        List of capability keys.
    """
    caps = db.query(PlanCapability).filter(
        PlanCapability.plan_id == plan_id
    ).all()
    return [c.capability_key for c in caps]


def get_plan_event_cap(
    db: Session,
    plan_id: str,
    event_key: str,
    period: str = "monthly",
) -> float | None:
    """Get the event cap for a plan (if any).

    Args:
        db: Database session.
        plan_id: The plan ID.
        event_key: The event type key.
        period: The period type ("monthly").

    Returns:
        The cap_raw_units or None if no cap.
    """
    cap = db.query(PlanEventCap).filter(
        PlanEventCap.plan_id == plan_id,
        PlanEventCap.event_key == event_key,
        PlanEventCap.period == period,
    ).first()
    return cap.cap_raw_units if cap else None


def check_entitlement(
    db: Session,
    tenant_id: str,
    capability_key: str,
) -> None:
    """Check if a tenant has a required capability.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        capability_key: The required capability key.

    Raises:
        HTTPException: 403 if subscription not found, suspended, or missing capability.
    """
    subscription = get_tenant_subscription(db, tenant_id)

    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "no_subscription",
                "message": "Tenant has no active subscription",
            },
        )

    if subscription.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "subscription_suspended",
                "message": "Tenant subscription is suspended",
                "status": subscription.status,
            },
        )

    # Check if plan has the required capability
    capabilities = get_plan_capabilities(db, subscription.plan_id)
    if capability_key not in capabilities:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "capability_denied",
                "message": f"Plan does not include capability: {capability_key}",
                "capability_key": capability_key,
                "plan_id": subscription.plan_id,
            },
        )


def check_quota(
    db: Session,
    tenant_id: str,
    event_key: str,
    requested_raw_units: float,
) -> dict:
    """Check if a tenant has enough quota for the requested usage.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        event_key: The event type key.
        requested_raw_units: Number of raw units requested.

    Returns:
        Dict with period_start, requested_credits for tracking.

    Raises:
        HTTPException: 429 if credits quota or per-event cap exceeded.
    """
    subscription = get_tenant_subscription(db, tenant_id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "no_subscription",
                "message": "Tenant has no active subscription",
            },
        )

    if subscription.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "subscription_suspended",
                "message": "Tenant subscription is suspended",
            },
        )

    plan = get_plan(db, subscription.plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "plan_not_found", "plan_id": subscription.plan_id},
        )

    period_start = get_period_start()

    # Get event type to calculate credits
    event_type = get_metered_event_type(db, event_key, active_only=True)
    if event_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unknown_event_type",
                "event_key": event_key,
            },
        )

    requested_credits, _ = calculate_credits_and_cost(event_type, requested_raw_units)

    # Check credits quota
    used_credits = get_total_credits_used(db, tenant_id, period_start)
    if used_credits + requested_credits > plan.included_credits:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "period_start": period_start,
                "event_key": event_key,
                "limit_credits": plan.included_credits,
                "used_credits": used_credits,
                "requested_credits": requested_credits,
                "cap_raw_units": None,
                "used_raw_units": None,
                "requested_raw_units": requested_raw_units,
            },
        )

    # Check per-event cap (if exists)
    cap = get_plan_event_cap(db, subscription.plan_id, event_key)
    if cap is not None:
        used_raw_units, _ = get_event_usage_for_period(db, tenant_id, period_start, event_key)
        if used_raw_units + requested_raw_units > cap:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "quota_exceeded",
                    "period_start": period_start,
                    "event_key": event_key,
                    "limit_credits": plan.included_credits,
                    "used_credits": used_credits,
                    "requested_credits": requested_credits,
                    "cap_raw_units": cap,
                    "used_raw_units": used_raw_units,
                    "requested_raw_units": requested_raw_units,
                },
            )

    return {
        "period_start": period_start,
        "requested_credits": requested_credits,
    }


def get_remaining_quota(
    db: Session,
    tenant_id: str,
    event_key: str,
) -> dict:
    """Get remaining quota for a tenant/event.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        event_key: The event type key.

    Returns:
        Dict with remaining_credits, remaining_raw_units (cap), allowed_raw_units.
    """
    subscription = get_tenant_subscription(db, tenant_id)
    if subscription is None or subscription.status != "active":
        return {
            "remaining_credits": 0,
            "remaining_raw_units_cap": None,
            "allowed_raw_units": 0,
        }

    plan = get_plan(db, subscription.plan_id)
    if plan is None:
        return {
            "remaining_credits": 0,
            "remaining_raw_units_cap": None,
            "allowed_raw_units": 0,
        }

    period_start = get_period_start()
    used_credits = get_total_credits_used(db, tenant_id, period_start)
    remaining_credits = max(0, plan.included_credits - used_credits)

    # Get event type to calculate max units from credits
    event_type = get_metered_event_type(db, event_key, active_only=True)
    if event_type is None or event_type.credits_per_unit <= 0:
        return {
            "remaining_credits": remaining_credits,
            "remaining_raw_units_cap": None,
            "allowed_raw_units": 0,
        }

    # Max units based on credits
    max_units_from_credits = remaining_credits / event_type.credits_per_unit

    # Check per-event cap
    cap = get_plan_event_cap(db, subscription.plan_id, event_key)
    remaining_cap = None
    if cap is not None:
        used_raw_units, _ = get_event_usage_for_period(db, tenant_id, period_start, event_key)
        remaining_cap = max(0, cap - used_raw_units)
        allowed_raw_units = min(max_units_from_credits, remaining_cap)
    else:
        allowed_raw_units = max_units_from_credits

    return {
        "remaining_credits": remaining_credits,
        "remaining_raw_units_cap": remaining_cap,
        "allowed_raw_units": int(allowed_raw_units),  # Floor for integer units
    }


def create_tenant_subscription(
    db: Session,
    tenant_id: str,
    plan_id: str = "starter",
    status: str = "active",
    period_start: str | None = None,
) -> TenantSubscription:
    """Create a subscription for a tenant.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        plan_id: The plan to assign (default: "starter").
        status: The subscription status (default: "active").
        period_start: Optional period start (default: current month).

    Returns:
        The created TenantSubscription.
    """
    if period_start is None:
        period_start = get_period_start()

    period_end = get_period_end(period_start)
    now_iso = get_current_utc_datetime_iso()

    subscription = TenantSubscription(
        tenant_id=tenant_id,
        plan_id=plan_id,
        status=status,
        period_start=period_start,
        period_end=period_end,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(subscription)
    return subscription


def update_tenant_subscription(
    db: Session,
    tenant_id: str,
    plan_id: str | None = None,
    status: str | None = None,
    period_start: str | None = None,
) -> TenantSubscription:
    """Update or create a tenant's subscription.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        plan_id: Optional new plan ID.
        status: Optional new status.
        period_start: Optional new period start.

    Returns:
        The updated or created TenantSubscription.
    """
    subscription = get_tenant_subscription(db, tenant_id)
    now_iso = get_current_utc_datetime_iso()

    if subscription is None:
        return create_tenant_subscription(
            db,
            tenant_id,
            plan_id=plan_id or "starter",
            status=status or "active",
            period_start=period_start,
        )

    if plan_id is not None:
        subscription.plan_id = plan_id
    if status is not None:
        subscription.status = status
    if period_start is not None:
        subscription.period_start = period_start
        subscription.period_end = get_period_end(period_start)

    subscription.updated_at = now_iso
    return subscription
