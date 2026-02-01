"""Quota enforcement module for tenant usage limits."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.gateway.models import TenantLimit, UsageRollupDaily

# Valid activity types that have quotas
ActivityType = Literal[
    "assistant_query",
    "tool_invocation",
    "daily_brief_generated",
    "notification_enqueued",
]

# Mapping of activity_type to limit field name
ACTIVITY_LIMIT_FIELD: dict[str, str] = {
    "assistant_query": "assistant_query_daily_limit",
    "tool_invocation": "tool_invocation_daily_limit",
    "daily_brief_generated": "daily_brief_generated_daily_limit",
    "notification_enqueued": "notification_enqueued_daily_limit",
}

# Default limits for new tenants
DEFAULT_LIMITS = {
    "assistant_query_daily_limit": 100,
    "tool_invocation_daily_limit": 100,
    "daily_brief_generated_daily_limit": 10,
    "notification_enqueued_daily_limit": 500,
}


def get_today_date_utc() -> str:
    """Get today's date in UTC as YYYY-MM-DD string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_usage(
    db: Session,
    tenant_id: str,
    date: str,
    activity_type: str,
) -> int:
    """Get current usage for a tenant/date/activity_type combination.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        date: The date in YYYY-MM-DD format.
        activity_type: The activity type.

    Returns:
        The current usage units (0 if no rollup exists).
    """
    rollup = db.query(UsageRollupDaily).filter(
        UsageRollupDaily.tenant_id == tenant_id,
        UsageRollupDaily.rollup_date == date,
        UsageRollupDaily.activity_type == activity_type,
    ).first()

    return rollup.units if rollup else 0


def get_limit(
    db: Session,
    tenant_id: str,
    activity_type: str,
) -> int:
    """Get the limit for a tenant/activity_type combination.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        activity_type: The activity type.

    Returns:
        The limit for this activity type.

    Raises:
        ValueError: If the activity type is unknown.
    """
    if activity_type not in ACTIVITY_LIMIT_FIELD:
        raise ValueError(f"Unknown activity type: {activity_type}")

    tenant_limit = db.query(TenantLimit).filter(
        TenantLimit.tenant_id == tenant_id
    ).first()

    if not tenant_limit:
        # Return default limit if no tenant_limits row exists
        return DEFAULT_LIMITS.get(ACTIVITY_LIMIT_FIELD[activity_type], 0)

    field_name = ACTIVITY_LIMIT_FIELD[activity_type]
    return getattr(tenant_limit, field_name)


def get_remaining_quota(
    db: Session,
    tenant_id: str,
    date: str,
    activity_type: str,
) -> int:
    """Get the remaining quota for a tenant/date/activity_type.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        date: The date in YYYY-MM-DD format.
        activity_type: The activity type.

    Returns:
        The remaining units available (can be negative if over limit).
    """
    limit = get_limit(db, tenant_id, activity_type)
    usage = get_usage(db, tenant_id, date, activity_type)
    return limit - usage


def check_quota(
    db: Session,
    tenant_id: str,
    date: str,
    activity_type: str,
    requested_units: int = 1,
) -> None:
    """Check if a tenant has enough quota for the requested activity.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        date: The date in YYYY-MM-DD format.
        activity_type: The activity type.
        requested_units: Number of units requested.

    Raises:
        HTTPException: 429 status if quota would be exceeded.
    """
    limit = get_limit(db, tenant_id, activity_type)
    current = get_usage(db, tenant_id, date, activity_type)

    if current + requested_units > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "activity_type": activity_type,
                "limit": limit,
                "current": current,
                "requested": requested_units,
            },
        )


def increment_usage(
    db: Session,
    tenant_id: str,
    date: str,
    activity_type: str,
    units: int = 1,
) -> None:
    """Increment usage rollup for a tenant/date/activity_type.

    Creates a new rollup row if one doesn't exist.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        date: The date in YYYY-MM-DD format.
        activity_type: The activity type.
        units: Number of units to increment by.
    """
    # Use with_for_update() to properly handle concurrent updates
    rollup = db.query(UsageRollupDaily).filter(
        UsageRollupDaily.tenant_id == tenant_id,
        UsageRollupDaily.rollup_date == date,
        UsageRollupDaily.activity_type == activity_type,
    ).with_for_update().first()

    if rollup:
        rollup.units += units
        rollup.updated_at = datetime.now(timezone.utc)
    else:
        rollup = UsageRollupDaily(
            tenant_id=tenant_id,
            rollup_date=date,
            activity_type=activity_type,
            units=units,
        )
        db.add(rollup)
        # Flush to make the new row visible to subsequent queries in the same transaction
        db.flush()


def create_default_limits(
    db: Session,
    tenant_id: str,
) -> TenantLimit:
    """Create default tenant limits for a new tenant.

    Args:
        db: Database session.
        tenant_id: The tenant ID.

    Returns:
        The created TenantLimit object.
    """
    tenant_limit = TenantLimit(
        tenant_id=tenant_id,
        assistant_query_daily_limit=DEFAULT_LIMITS["assistant_query_daily_limit"],
        tool_invocation_daily_limit=DEFAULT_LIMITS["tool_invocation_daily_limit"],
        daily_brief_generated_daily_limit=DEFAULT_LIMITS["daily_brief_generated_daily_limit"],
        notification_enqueued_daily_limit=DEFAULT_LIMITS["notification_enqueued_daily_limit"],
    )
    db.add(tenant_limit)
    return tenant_limit
