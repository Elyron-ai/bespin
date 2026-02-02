"""Centralized metering module for usage tracking and billing.

This module provides the single source of truth for emitting usage events,
calculating credits, and updating period rollups.
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.gateway.models import (
    MeteredEventType,
    UsageEvent,
    UsageRollupPeriod,
)
from app.gateway.billing_period import get_period_start, get_current_utc_datetime_iso


class MeteringError(Exception):
    """Base exception for metering errors."""
    pass


class UnknownEventTypeError(MeteringError):
    """Raised when an unknown or inactive event type is used."""
    pass


def get_metered_event_type(
    db: Session,
    event_key: str,
    active_only: bool = True
) -> MeteredEventType | None:
    """Get a metered event type by key.

    Args:
        db: Database session.
        event_key: The event type key.
        active_only: If True, only return active event types.

    Returns:
        The MeteredEventType or None if not found.
    """
    query = db.query(MeteredEventType).filter(
        MeteredEventType.event_key == event_key
    )
    if active_only:
        query = query.filter(MeteredEventType.active == 1)
    return query.first()


def calculate_credits_and_cost(
    event_type: MeteredEventType,
    raw_units: float
) -> tuple[float, float]:
    """Calculate credits and estimated cost for usage.

    Args:
        event_type: The metered event type definition.
        raw_units: The number of raw units consumed.

    Returns:
        Tuple of (credits, list_cost_estimate).
    """
    credits = raw_units * event_type.credits_per_unit
    list_cost_estimate = credits * event_type.list_price_per_credit
    return credits, list_cost_estimate


def emit_usage(
    db: Session,
    tenant_id: str,
    user_id: str,
    event_key: str,
    raw_units: float,
    request_id: str,
    tool_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit a usage event and update period rollups.

    This is the SINGLE SOURCE OF TRUTH for recording metered usage.
    All usage must flow through this function.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        user_id: The user ID.
        event_key: The metered event type key (e.g., "assistant_query").
        raw_units: Number of raw units consumed.
        request_id: Unique request ID for correlation.
        tool_name: Optional tool name for tool invocations.
        metadata: Optional metadata (currently unused, for future use).

    Returns:
        Dict with credits, list_cost_estimate, event_key.

    Raises:
        UnknownEventTypeError: If the event_key is unknown or inactive.
    """
    # Load the metered event type
    event_type = get_metered_event_type(db, event_key, active_only=True)
    if event_type is None:
        raise UnknownEventTypeError(f"Unknown or inactive event type: {event_key}")

    # Calculate credits and cost
    credits, list_cost_estimate = calculate_credits_and_cost(event_type, raw_units)

    # Create usage event record
    usage_event = UsageEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        activity_type=event_key,
        units=raw_units,
        credits=credits,
        list_cost_estimate=list_cost_estimate,
        tool_name=tool_name,
        request_id=request_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(usage_event)

    # Update period rollup
    period_start = get_period_start()
    now_iso = get_current_utc_datetime_iso()

    rollup = db.query(UsageRollupPeriod).filter(
        UsageRollupPeriod.tenant_id == tenant_id,
        UsageRollupPeriod.period_start == period_start,
        UsageRollupPeriod.event_key == event_key,
    ).with_for_update().first()

    if rollup:
        rollup.raw_units += raw_units
        rollup.credits += credits
        rollup.list_cost_estimate += list_cost_estimate
        rollup.updated_at = now_iso
    else:
        rollup = UsageRollupPeriod(
            tenant_id=tenant_id,
            period_start=period_start,
            event_key=event_key,
            raw_units=raw_units,
            credits=credits,
            list_cost_estimate=list_cost_estimate,
            updated_at=now_iso,
        )
        db.add(rollup)
        db.flush()

    return {
        "event_key": event_key,
        "raw_units": raw_units,
        "credits": credits,
        "list_cost_estimate": list_cost_estimate,
    }


def get_period_usage_summary(
    db: Session,
    tenant_id: str,
    period_start: str,
) -> dict[str, Any]:
    """Get usage summary for a billing period.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        period_start: The billing period start (YYYY-MM-01).

    Returns:
        Dict with total_credits, total_list_cost_estimate, and breakdown by event.
    """
    rollups = db.query(UsageRollupPeriod).filter(
        UsageRollupPeriod.tenant_id == tenant_id,
        UsageRollupPeriod.period_start == period_start,
    ).all()

    # Batch fetch all event types to avoid N+1 query
    event_keys = [r.event_key for r in rollups]
    event_types = {}
    if event_keys:
        event_type_rows = db.query(MeteredEventType).filter(
            MeteredEventType.event_key.in_(event_keys)
        ).all()
        event_types = {et.event_key: et for et in event_type_rows}

    total_credits = 0.0
    total_list_cost_estimate = 0.0
    breakdown = []

    for rollup in rollups:
        total_credits += rollup.credits
        total_list_cost_estimate += rollup.list_cost_estimate

        # Get display info from pre-fetched event types
        event_type = event_types.get(rollup.event_key)

        breakdown.append({
            "event_key": rollup.event_key,
            "unit_name": event_type.unit_name if event_type else "unit",
            "raw_units": rollup.raw_units,
            "credits": rollup.credits,
            "list_cost_estimate": rollup.list_cost_estimate,
        })

    return {
        "total_credits": total_credits,
        "total_list_cost_estimate": total_list_cost_estimate,
        "breakdown": breakdown,
    }


def get_event_usage_for_period(
    db: Session,
    tenant_id: str,
    period_start: str,
    event_key: str,
) -> tuple[float, float]:
    """Get raw units and credits used for a specific event in a period.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        period_start: The billing period start (YYYY-MM-01).
        event_key: The event type key.

    Returns:
        Tuple of (raw_units, credits) used.
    """
    rollup = db.query(UsageRollupPeriod).filter(
        UsageRollupPeriod.tenant_id == tenant_id,
        UsageRollupPeriod.period_start == period_start,
        UsageRollupPeriod.event_key == event_key,
    ).first()

    if rollup:
        return rollup.raw_units, rollup.credits
    return 0.0, 0.0


def get_total_credits_used(
    db: Session,
    tenant_id: str,
    period_start: str,
) -> float:
    """Get total credits used in a billing period.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        period_start: The billing period start (YYYY-MM-01).

    Returns:
        Total credits used in the period.
    """
    rollups = db.query(UsageRollupPeriod).filter(
        UsageRollupPeriod.tenant_id == tenant_id,
        UsageRollupPeriod.period_start == period_start,
    ).all()

    return sum(r.credits for r in rollups)
