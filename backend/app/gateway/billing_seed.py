"""Seed data for billing tables (metered events, plans, capabilities)."""
from sqlalchemy.orm import Session

from app.gateway.models import (
    MeteredEventType,
    Plan,
    PlanEventCap,
    Capability,
    PlanCapability,
)
from app.gateway.billing_period import get_current_utc_datetime_iso


# Default metered event types
DEFAULT_METERED_EVENTS = [
    {
        "event_key": "assistant_query",
        "display_name": "Assistant Query",
        "description": "Chat message to the assistant",
        "unit_name": "call",
        "credits_per_unit": 1.0,
        "list_price_per_credit": 0.02,
        "billable": 1,
        "active": 1,
    },
    {
        "event_key": "tool_invocation",
        "display_name": "Tool Invocation",
        "description": "Tool invoked via the API",
        "unit_name": "call",
        "credits_per_unit": 2.0,
        "list_price_per_credit": 0.02,
        "billable": 1,
        "active": 1,
    },
    {
        "event_key": "daily_brief_generated",
        "display_name": "Daily Brief Generated",
        "description": "Daily brief materialized for tenant",
        "unit_name": "brief",
        "credits_per_unit": 5.0,
        "list_price_per_credit": 0.02,
        "billable": 1,
        "active": 1,
    },
    {
        "event_key": "notification_enqueued",
        "display_name": "Notification Enqueued",
        "description": "Notification added to outbox",
        "unit_name": "notification",
        "credits_per_unit": 0.2,
        "list_price_per_credit": 0.02,
        "billable": 1,
        "active": 1,
    },
    {
        "event_key": "kpi_definition_created",
        "display_name": "KPI Definition Created",
        "description": "New KPI definition created",
        "unit_name": "kpi",
        "credits_per_unit": 0.5,
        "list_price_per_credit": 0.02,
        "billable": 1,
        "active": 1,
    },
    {
        "event_key": "kpi_points_ingested",
        "display_name": "KPI Points Ingested",
        "description": "KPI data points ingested",
        "unit_name": "row",
        "credits_per_unit": 0.001,
        "list_price_per_credit": 0.02,
        "billable": 1,
        "active": 1,
    },
]

# Default capabilities
DEFAULT_CAPABILITIES = [
    {"capability_key": "chat", "description": "Access to chat with assistant"},
    {"capability_key": "tools", "description": "Access to tool invocation API"},
    {"capability_key": "briefs", "description": "Access to daily briefs"},
    {"capability_key": "notifications", "description": "Access to notifications"},
    {"capability_key": "kpi_ingest", "description": "Access to create KPIs and ingest data"},
    {"capability_key": "kpi_read", "description": "Access to read KPI data"},
]

# Default plans
DEFAULT_PLANS = [
    {
        "plan_id": "starter",
        "name": "Starter",
        "included_credits": 500,
        "overage_price_per_credit": 0.02,
    },
    {
        "plan_id": "growth",
        "name": "Growth",
        "included_credits": 2000,
        "overage_price_per_credit": 0.015,
    },
    {
        "plan_id": "scale",
        "name": "Scale",
        "included_credits": 10000,
        "overage_price_per_credit": 0.01,
    },
]

# All capabilities
ALL_CAPABILITIES = ["chat", "tools", "briefs", "notifications", "kpi_ingest", "kpi_read"]

# Plan capabilities mapping
PLAN_CAPABILITIES = {
    "starter": ALL_CAPABILITIES,
    "growth": ALL_CAPABILITIES,
    "scale": ALL_CAPABILITIES,
}

# Optional event caps for starter plan
STARTER_EVENT_CAPS = [
    {"event_key": "daily_brief_generated", "period": "monthly", "cap_raw_units": 50},
    {"event_key": "tool_invocation", "period": "monthly", "cap_raw_units": 2000},
]


def seed_metered_events(db: Session) -> int:
    """Seed default metered event types if missing.

    Args:
        db: Database session.

    Returns:
        Number of events created.
    """
    now_iso = get_current_utc_datetime_iso()
    created = 0

    for event_data in DEFAULT_METERED_EVENTS:
        existing = db.query(MeteredEventType).filter(
            MeteredEventType.event_key == event_data["event_key"]
        ).first()

        if existing is None:
            event = MeteredEventType(
                event_key=event_data["event_key"],
                display_name=event_data["display_name"],
                description=event_data["description"],
                unit_name=event_data["unit_name"],
                credits_per_unit=event_data["credits_per_unit"],
                list_price_per_credit=event_data["list_price_per_credit"],
                billable=event_data["billable"],
                active=event_data["active"],
                created_at=now_iso,
                updated_at=now_iso,
            )
            db.add(event)
            created += 1

    return created


def seed_capabilities(db: Session) -> int:
    """Seed default capabilities if missing.

    Args:
        db: Database session.

    Returns:
        Number of capabilities created.
    """
    created = 0

    for cap_data in DEFAULT_CAPABILITIES:
        existing = db.query(Capability).filter(
            Capability.capability_key == cap_data["capability_key"]
        ).first()

        if existing is None:
            cap = Capability(
                capability_key=cap_data["capability_key"],
                description=cap_data["description"],
            )
            db.add(cap)
            created += 1

    return created


def seed_plans(db: Session) -> int:
    """Seed default plans if missing.

    Args:
        db: Database session.

    Returns:
        Number of plans created.
    """
    now_iso = get_current_utc_datetime_iso()
    created = 0

    for plan_data in DEFAULT_PLANS:
        existing = db.query(Plan).filter(
            Plan.plan_id == plan_data["plan_id"]
        ).first()

        if existing is None:
            plan = Plan(
                plan_id=plan_data["plan_id"],
                name=plan_data["name"],
                included_credits=plan_data["included_credits"],
                overage_price_per_credit=plan_data["overage_price_per_credit"],
                created_at=now_iso,
                updated_at=now_iso,
            )
            db.add(plan)
            created += 1

    return created


def seed_plan_capabilities(db: Session) -> int:
    """Seed plan capability mappings if missing.

    Args:
        db: Database session.

    Returns:
        Number of mappings created.
    """
    created = 0

    for plan_id, capabilities in PLAN_CAPABILITIES.items():
        for cap_key in capabilities:
            existing = db.query(PlanCapability).filter(
                PlanCapability.plan_id == plan_id,
                PlanCapability.capability_key == cap_key,
            ).first()

            if existing is None:
                mapping = PlanCapability(
                    plan_id=plan_id,
                    capability_key=cap_key,
                )
                db.add(mapping)
                created += 1

    return created


def seed_plan_event_caps(db: Session) -> int:
    """Seed event caps for starter plan if missing.

    Args:
        db: Database session.

    Returns:
        Number of caps created.
    """
    created = 0

    for cap_data in STARTER_EVENT_CAPS:
        existing = db.query(PlanEventCap).filter(
            PlanEventCap.plan_id == "starter",
            PlanEventCap.event_key == cap_data["event_key"],
            PlanEventCap.period == cap_data["period"],
        ).first()

        if existing is None:
            cap = PlanEventCap(
                plan_id="starter",
                event_key=cap_data["event_key"],
                period=cap_data["period"],
                cap_raw_units=cap_data["cap_raw_units"],
            )
            db.add(cap)
            created += 1

    return created


def seed_all_billing_data(db: Session) -> dict:
    """Seed all billing data (events, capabilities, plans, mappings).

    Args:
        db: Database session.

    Returns:
        Dict with counts of created items.
    """
    events = seed_metered_events(db)
    capabilities = seed_capabilities(db)
    plans = seed_plans(db)
    plan_caps = seed_plan_capabilities(db)
    event_caps = seed_plan_event_caps(db)

    db.commit()

    return {
        "metered_events": events,
        "capabilities": capabilities,
        "plans": plans,
        "plan_capabilities": plan_caps,
        "plan_event_caps": event_caps,
    }
