"""Dev Console for viewing database state."""
import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.gateway.models import (
    AuditLog,
    Brief,
    Conversation,
    GatewayTenant,
    GatewayUser,
    IdempotencyKey,
    KPIDefinition,
    KPIPoint,
    Message,
    NotificationOutbox,
    NotificationPref,
    UsageEvent,
    # Billing models
    MeteredEventType,
    Plan,
    PlanCapability,
    PlanEventCap,
    Capability,
    TenantSubscription,
    UsageRollupPeriod,
    # Core Business OS models
    Action,
    ActionReview,
    ActionExecution,
    Task,
    MeetingNote,
    Decision,
    MemoryFact,
    EvidenceLink,
    TimelineEvent,
)

router = APIRouter(prefix="/console", tags=["console"])

# Environment variables for console access
DEV_CONSOLE_ENABLED = os.getenv("DEV_CONSOLE_ENABLED", "0") == "1"
DEV_CONSOLE_KEY = os.getenv("DEV_CONSOLE_KEY", "dev-console-secret")

# Allowed tables for the table viewer
ALLOWED_TABLES = {
    "tenants": GatewayTenant,
    "users": GatewayUser,
    "kpi_definitions": KPIDefinition,
    "kpi_points": KPIPoint,
    "briefs": Brief,
    "audit_logs": AuditLog,
    "usage_events": UsageEvent,
    "idempotency_keys": IdempotencyKey,
    "notification_prefs": NotificationPref,
    "notification_outbox": NotificationOutbox,
    "conversations": Conversation,
    "messages": Message,
    # Billing tables
    "metered_event_types": MeteredEventType,
    "plans": Plan,
    "plan_capabilities": PlanCapability,
    "plan_event_caps": PlanEventCap,
    "capabilities": Capability,
    "tenant_subscriptions": TenantSubscription,
    "usage_rollups_period": UsageRollupPeriod,
    # Core Business OS tables
    "actions": Action,
    "action_reviews": ActionReview,
    "action_executions": ActionExecution,
    "tasks": Task,
    "meeting_notes": MeetingNote,
    "decisions": Decision,
    "memory_facts": MemoryFact,
    "evidence_links": EvidenceLink,
    "timeline_events": TimelineEvent,
}


def verify_console_access(key: str = Query(...)):
    """Verify console access is enabled and key is valid."""
    if not DEV_CONSOLE_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(key, DEV_CONSOLE_KEY):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return True


def mask_api_key(api_key: str) -> str:
    """Mask an API key, showing only first 4 and last 4 characters."""
    if len(api_key) <= 12:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"


def html_page(title: str, content: str) -> str:
    """Wrap content in a basic HTML page."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title} - Bespin Dev Console</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; margin-top: 30px; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        table {{ border-collapse: collapse; width: 100%; background: white; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 13px; }}
        th {{ background: #f0f0f0; font-weight: 600; }}
        tr:nth-child(even) {{ background: #fafafa; }}
        .card {{ background: white; padding: 15px; margin: 10px 0; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .stat {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #333; }}
        .stat-label {{ font-size: 12px; color: #666; }}
        .nav {{ margin-bottom: 20px; padding: 10px 0; border-bottom: 1px solid #ddd; }}
        .nav a {{ margin-right: 15px; }}
        pre {{ background: #f0f0f0; padding: 10px; overflow-x: auto; font-size: 12px; }}
        .truncate {{ max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    </style>
</head>
<body>
    <div class="nav">
        <a href="/console?key={DEV_CONSOLE_KEY}">Overview</a>
        <a href="/console/tenants?key={DEV_CONSOLE_KEY}">Tenants</a>
        <a href="/console/billing?key={DEV_CONSOLE_KEY}">Billing</a>
        <a href="/console/core-os?key={DEV_CONSOLE_KEY}">Core OS</a>
        <a href="/console/db/tenants?key={DEV_CONSOLE_KEY}">Tables</a>
        <a href="/console/db/download?key={DEV_CONSOLE_KEY}">Download DB</a>
    </div>
    <h1>{title}</h1>
    {content}
</body>
</html>"""


def format_value(val: Any) -> str:
    """Format a value for HTML display."""
    if val is None:
        return "<em>null</em>"
    if isinstance(val, str) and len(val) > 100:
        return f'<span class="truncate" title="{val[:500]}">{val[:100]}...</span>'
    return str(val)


@router.get("", response_class=HTMLResponse)
def console_overview(
    _: bool = Depends(verify_console_access),
    db: Session = Depends(get_db),
) -> str:
    """Dev console overview with counts."""
    counts = {
        "Tenants": db.query(func.count(GatewayTenant.tenant_id)).scalar() or 0,
        "Users": db.query(func.count(GatewayUser.user_id)).scalar() or 0,
        "KPI Definitions": db.query(func.count(KPIDefinition.kpi_id)).scalar() or 0,
        "KPI Points": db.query(func.count(KPIPoint.id)).scalar() or 0,
        "Briefs": db.query(func.count(Brief.brief_id)).scalar() or 0,
        "Audit Logs": db.query(func.count(AuditLog.id)).scalar() or 0,
        "Usage Events": db.query(func.count(UsageEvent.id)).scalar() or 0,
        "Idempotency Keys": db.query(func.count(IdempotencyKey.id)).scalar() or 0,
        "Notification Prefs": db.query(func.count()).select_from(NotificationPref).scalar() or 0,
        "Notification Outbox": db.query(func.count(NotificationOutbox.id)).scalar() or 0,
        "Conversations": db.query(func.count(Conversation.conversation_id)).scalar() or 0,
        "Messages": db.query(func.count(Message.message_id)).scalar() or 0,
        # Billing counts
        "Metered Events": db.query(func.count(MeteredEventType.event_key)).scalar() or 0,
        "Plans": db.query(func.count(Plan.plan_id)).scalar() or 0,
        "Subscriptions": db.query(func.count(TenantSubscription.tenant_id)).scalar() or 0,
        # Core Business OS counts
        "Actions": db.query(func.count(Action.action_id)).scalar() or 0,
        "Tasks": db.query(func.count(Task.task_id)).scalar() or 0,
        "Decisions": db.query(func.count(Decision.decision_id)).scalar() or 0,
        "Meeting Notes": db.query(func.count(MeetingNote.meeting_id)).scalar() or 0,
        "Memory Facts": db.query(func.count(MemoryFact.fact_id)).scalar() or 0,
        "Evidence Links": db.query(func.count(EvidenceLink.evidence_id)).scalar() or 0,
        "Timeline Events": db.query(func.count(TimelineEvent.event_id)).scalar() or 0,
    }

    stats_html = ""
    for label, value in counts.items():
        stats_html += f"""
        <div class="stat">
            <div class="stat-value">{value}</div>
            <div class="stat-label">{label}</div>
        </div>
        """

    tables_html = "<h2>Browse Tables</h2><ul>"
    for table_name in ALLOWED_TABLES.keys():
        tables_html += f'<li><a href="/console/db/{table_name}?key={DEV_CONSOLE_KEY}">{table_name}</a></li>'
    tables_html += "</ul>"

    content = f"""
    <div class="card">
        <h2>Database Statistics</h2>
        {stats_html}
    </div>
    {tables_html}
    """

    return html_page("Overview", content)


@router.get("/tenants", response_class=HTMLResponse)
def console_tenants(
    _: bool = Depends(verify_console_access),
    db: Session = Depends(get_db),
) -> str:
    """List all tenants."""
    tenants = db.query(GatewayTenant).order_by(GatewayTenant.created_at.desc()).all()

    rows_html = ""
    for t in tenants:
        rows_html += f"""
        <tr>
            <td><a href="/console/tenants/{t.tenant_id}?key={DEV_CONSOLE_KEY}">{t.tenant_id}</a></td>
            <td>{t.name}</td>
            <td>{t.region}</td>
            <td class="truncate">{mask_api_key(t.api_key)}</td>
            <td>{t.created_at}</td>
        </tr>
        """

    content = f"""
    <table>
        <tr>
            <th>Tenant ID</th>
            <th>Name</th>
            <th>Region</th>
            <th>API Key</th>
            <th>Created At</th>
        </tr>
        {rows_html}
    </table>
    """

    return html_page("Tenants", content)


@router.get("/tenants/{tenant_id}", response_class=HTMLResponse)
def console_tenant_detail(
    tenant_id: str,
    _: bool = Depends(verify_console_access),
    db: Session = Depends(get_db),
) -> str:
    """Show tenant detail: users, KPIs, briefs, outbox."""
    tenant = db.query(GatewayTenant).filter(GatewayTenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Users
    users = db.query(GatewayUser).filter(GatewayUser.tenant_id == tenant_id).all()
    users_html = "<table><tr><th>User ID</th><th>Email</th><th>Role</th><th>Created At</th></tr>"
    for u in users:
        users_html += f"<tr><td>{u.user_id}</td><td>{u.email}</td><td>{u.role}</td><td>{u.created_at}</td></tr>"
    users_html += "</table>"

    # KPIs
    kpis = db.query(KPIDefinition).filter(KPIDefinition.tenant_id == tenant_id).all()
    kpis_html = "<table><tr><th>KPI ID</th><th>Name</th><th>Unit</th><th>Description</th></tr>"
    for k in kpis:
        kpis_html += f"<tr><td>{k.kpi_id}</td><td>{k.name}</td><td>{k.unit or ''}</td><td>{k.description or ''}</td></tr>"
    kpis_html += "</table>"

    # Recent briefs
    briefs = db.query(Brief).filter(Brief.tenant_id == tenant_id).order_by(Brief.brief_date.desc()).limit(5).all()
    briefs_html = "<table><tr><th>Brief ID</th><th>Date</th><th>Window Days</th><th>Top N</th><th>Created At</th></tr>"
    for b in briefs:
        briefs_html += f"<tr><td>{b.brief_id}</td><td>{b.brief_date}</td><td>{b.window_days}</td><td>{b.top_n}</td><td>{b.created_at}</td></tr>"
    briefs_html += "</table>"

    # Recent outbox
    outbox = db.query(NotificationOutbox).filter(
        NotificationOutbox.tenant_id == tenant_id
    ).order_by(NotificationOutbox.created_at.desc()).limit(10).all()
    outbox_html = "<table><tr><th>ID</th><th>User ID</th><th>Type</th><th>Date</th><th>Status</th></tr>"
    for o in outbox:
        outbox_html += f"<tr><td>{o.id}</td><td>{o.user_id}</td><td>{o.notification_type}</td><td>{o.notif_date}</td><td>{o.status}</td></tr>"
    outbox_html += "</table>"

    # Subscription
    subscription = db.query(TenantSubscription).filter(
        TenantSubscription.tenant_id == tenant_id
    ).first()

    if subscription:
        sub_plan = db.query(Plan).filter(Plan.plan_id == subscription.plan_id).first()
        sub_html = f"""
        <div class="card">
            <h2>Subscription</h2>
            <p><strong>Plan:</strong> <a href="/console/billing/plans/{subscription.plan_id}?key={DEV_CONSOLE_KEY}">{subscription.plan_id}</a> ({sub_plan.name if sub_plan else 'Unknown'})</p>
            <p><strong>Status:</strong> {subscription.status}</p>
            <p><strong>Period:</strong> {subscription.period_start} to {subscription.period_end}</p>
            <p><strong>Included Credits:</strong> {sub_plan.included_credits if sub_plan else 'N/A'}</p>
        </div>
        """
    else:
        sub_html = """<div class="card"><h2>Subscription</h2><p>No subscription found.</p></div>"""

    # Usage rollups for this tenant
    rollups = db.query(UsageRollupPeriod).filter(
        UsageRollupPeriod.tenant_id == tenant_id
    ).order_by(UsageRollupPeriod.period_start.desc()).limit(20).all()

    rollups_html = """<table>
        <tr><th>Period Start</th><th>Event Key</th><th>Raw Units</th><th>Credits</th><th>Est. Cost</th></tr>"""
    for r in rollups:
        rollups_html += f"""<tr>
            <td>{r.period_start}</td>
            <td>{r.event_key}</td>
            <td>{r.raw_units:.2f}</td>
            <td>{r.credits:.2f}</td>
            <td>${r.list_cost_estimate:.4f}</td>
        </tr>"""
    rollups_html += "</table>"

    content = f"""
    <div class="card">
        <h2>Tenant Info</h2>
        <p><strong>ID:</strong> {tenant.tenant_id}</p>
        <p><strong>Name:</strong> {tenant.name}</p>
        <p><strong>Region:</strong> {tenant.region}</p>
        <p><strong>API Key:</strong> <code>{mask_api_key(tenant.api_key)}</code></p>
        <p><strong>Created:</strong> {tenant.created_at}</p>
    </div>

    {sub_html}

    <h2>Usage Rollups ({len(rollups)})</h2>
    {rollups_html}

    <h2>Users ({len(users)})</h2>
    {users_html}

    <h2>KPI Definitions ({len(kpis)})</h2>
    {kpis_html}

    <h2>Recent Briefs ({len(briefs)})</h2>
    {briefs_html}

    <h2>Recent Notifications ({len(outbox)})</h2>
    {outbox_html}
    """

    return html_page(f"Tenant: {tenant.name}", content)


@router.get("/billing", response_class=HTMLResponse)
def console_billing(
    _: bool = Depends(verify_console_access),
    db: Session = Depends(get_db),
) -> str:
    """Billing overview: metered events, plans, subscriptions."""
    # Metered event types
    events = db.query(MeteredEventType).order_by(MeteredEventType.event_key).all()
    events_html = """<table>
        <tr><th>Event Key</th><th>Display Name</th><th>Unit</th><th>Credits/Unit</th><th>Price/Credit</th><th>Billable</th><th>Active</th></tr>"""
    for e in events:
        events_html += f"""<tr>
            <td>{e.event_key}</td>
            <td>{e.display_name}</td>
            <td>{e.unit_name}</td>
            <td>{e.credits_per_unit}</td>
            <td>${e.list_price_per_credit}</td>
            <td>{'Yes' if e.billable else 'No'}</td>
            <td>{'Yes' if e.active else 'No'}</td>
        </tr>"""
    events_html += "</table>"

    # Plans
    plans = db.query(Plan).order_by(Plan.plan_id).all()
    plans_html = """<table>
        <tr><th>Plan ID</th><th>Name</th><th>Included Credits</th><th>Overage Price</th></tr>"""
    for p in plans:
        plans_html += f"""<tr>
            <td><a href="/console/billing/plans/{p.plan_id}?key={DEV_CONSOLE_KEY}">{p.plan_id}</a></td>
            <td>{p.name}</td>
            <td>{p.included_credits}</td>
            <td>${p.overage_price_per_credit}</td>
        </tr>"""
    plans_html += "</table>"

    # Subscriptions
    subscriptions = db.query(TenantSubscription).all()
    subs_html = """<table>
        <tr><th>Tenant ID</th><th>Plan</th><th>Status</th><th>Period Start</th><th>Period End</th></tr>"""
    for s in subscriptions:
        subs_html += f"""<tr>
            <td><a href="/console/tenants/{s.tenant_id}?key={DEV_CONSOLE_KEY}">{s.tenant_id[:8]}...</a></td>
            <td>{s.plan_id}</td>
            <td>{s.status}</td>
            <td>{s.period_start}</td>
            <td>{s.period_end}</td>
        </tr>"""
    subs_html += "</table>"

    # Usage rollups
    rollups = db.query(UsageRollupPeriod).order_by(
        UsageRollupPeriod.tenant_id,
        UsageRollupPeriod.period_start.desc()
    ).limit(50).all()
    rollups_html = """<table>
        <tr><th>Tenant ID</th><th>Period Start</th><th>Event Key</th><th>Raw Units</th><th>Credits</th><th>Est. Cost</th></tr>"""
    for r in rollups:
        rollups_html += f"""<tr>
            <td>{r.tenant_id[:8]}...</td>
            <td>{r.period_start}</td>
            <td>{r.event_key}</td>
            <td>{r.raw_units:.2f}</td>
            <td>{r.credits:.2f}</td>
            <td>${r.list_cost_estimate:.4f}</td>
        </tr>"""
    rollups_html += "</table>"

    content = f"""
    <div class="card">
        <h2>Metered Event Types ({len(events)})</h2>
        {events_html}
    </div>

    <div class="card">
        <h2>Plans ({len(plans)})</h2>
        {plans_html}
    </div>

    <div class="card">
        <h2>Tenant Subscriptions ({len(subscriptions)})</h2>
        {subs_html}
    </div>

    <div class="card">
        <h2>Usage Rollups (Recent 50)</h2>
        {rollups_html}
    </div>
    """

    return html_page("Billing Overview", content)


@router.get("/billing/plans/{plan_id}", response_class=HTMLResponse)
def console_plan_detail(
    plan_id: str,
    _: bool = Depends(verify_console_access),
    db: Session = Depends(get_db),
) -> str:
    """Plan detail: capabilities and event caps."""
    plan = db.query(Plan).filter(Plan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    # Capabilities
    caps = db.query(PlanCapability).filter(PlanCapability.plan_id == plan_id).all()
    caps_html = "<ul>"
    for c in caps:
        caps_html += f"<li>{c.capability_key}</li>"
    caps_html += "</ul>" if caps else "<p>No capabilities assigned.</p>"

    # Event caps
    event_caps = db.query(PlanEventCap).filter(PlanEventCap.plan_id == plan_id).all()
    event_caps_html = """<table>
        <tr><th>Event Key</th><th>Period</th><th>Cap (Raw Units)</th></tr>"""
    for ec in event_caps:
        event_caps_html += f"""<tr>
            <td>{ec.event_key}</td>
            <td>{ec.period}</td>
            <td>{ec.cap_raw_units}</td>
        </tr>"""
    event_caps_html += "</table>" if event_caps else "<p>No event caps.</p>"

    content = f"""
    <div class="card">
        <h2>Plan Info</h2>
        <p><strong>ID:</strong> {plan.plan_id}</p>
        <p><strong>Name:</strong> {plan.name}</p>
        <p><strong>Included Credits:</strong> {plan.included_credits}</p>
        <p><strong>Overage Price:</strong> ${plan.overage_price_per_credit}/credit</p>
    </div>

    <h2>Capabilities ({len(caps)})</h2>
    {caps_html}

    <h2>Event Caps ({len(event_caps)})</h2>
    {event_caps_html}
    """

    return html_page(f"Plan: {plan.name}", content)


@router.get("/db/{table}", response_class=HTMLResponse)
def console_table_viewer(
    table: str,
    _: bool = Depends(verify_console_access),
    db: Session = Depends(get_db),
    limit: int = Query(200, ge=1, le=1000),
) -> str:
    """View rows from a specific table."""
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not allowed")

    model = ALLOWED_TABLES[table]
    rows = db.query(model).limit(limit).all()

    if not rows:
        content = "<p>No rows found.</p>"
        return html_page(f"Table: {table}", content)

    # Get column names from the first row
    columns = [c.name for c in model.__table__.columns]

    header_html = "".join(f"<th>{col}</th>" for col in columns)
    rows_html = ""
    for row in rows:
        cells = "".join(f"<td>{format_value(getattr(row, col))}</td>" for col in columns)
        rows_html += f"<tr>{cells}</tr>"

    # Table navigation
    tables_nav = " | ".join(
        f'<a href="/console/db/{t}?key={DEV_CONSOLE_KEY}">{t}</a>'
        for t in ALLOWED_TABLES.keys()
    )

    content = f"""
    <p><strong>Tables:</strong> {tables_nav}</p>
    <p>Showing {len(rows)} rows (limit: {limit})</p>
    <table>
        <tr>{header_html}</tr>
        {rows_html}
    </table>
    """

    return html_page(f"Table: {table}", content)


@router.get("/core-os", response_class=HTMLResponse)
def console_core_os(
    _: bool = Depends(verify_console_access),
    db: Session = Depends(get_db),
) -> str:
    """Core Business OS overview: actions, tasks, decisions, memory, timeline."""
    # Actions
    actions = db.query(Action).order_by(Action.created_at.desc()).limit(20).all()
    actions_html = """<table>
        <tr><th>Action ID</th><th>Tenant</th><th>Title</th><th>Status</th><th>Type</th><th>Created At</th></tr>"""
    for a in actions:
        actions_html += f"""<tr>
            <td>{a.action_id[:8]}...</td>
            <td><a href="/console/tenants/{a.tenant_id}?key={DEV_CONSOLE_KEY}">{a.tenant_id[:8]}...</a></td>
            <td>{a.title[:50]}...</td>
            <td>{a.status}</td>
            <td>{a.action_type}</td>
            <td>{a.created_at}</td>
        </tr>"""
    actions_html += "</table>"

    # Tasks
    tasks = db.query(Task).order_by(Task.created_at.desc()).limit(20).all()
    tasks_html = """<table>
        <tr><th>Task ID</th><th>Tenant</th><th>Title</th><th>Status</th><th>Priority</th><th>Due Date</th></tr>"""
    for t in tasks:
        tasks_html += f"""<tr>
            <td>{t.task_id[:8]}...</td>
            <td>{t.tenant_id[:8]}...</td>
            <td>{t.title[:50]}...</td>
            <td>{t.status}</td>
            <td>{t.priority}</td>
            <td>{t.due_date or '-'}</td>
        </tr>"""
    tasks_html += "</table>"

    # Decisions
    decisions = db.query(Decision).order_by(Decision.created_at.desc()).limit(20).all()
    decisions_html = """<table>
        <tr><th>Decision ID</th><th>Tenant</th><th>Title</th><th>Status</th><th>Date</th></tr>"""
    for d in decisions:
        decisions_html += f"""<tr>
            <td>{d.decision_id[:8]}...</td>
            <td>{d.tenant_id[:8]}...</td>
            <td>{d.title[:50]}...</td>
            <td>{d.status}</td>
            <td>{d.decision_date}</td>
        </tr>"""
    decisions_html += "</table>"

    # Memory Facts
    facts = db.query(MemoryFact).order_by(MemoryFact.created_at.desc()).limit(20).all()
    facts_html = """<table>
        <tr><th>Fact ID</th><th>Tenant</th><th>Category</th><th>Key</th><th>Status</th></tr>"""
    for f in facts:
        facts_html += f"""<tr>
            <td>{f.fact_id[:8]}...</td>
            <td>{f.tenant_id[:8]}...</td>
            <td>{f.category}</td>
            <td>{f.fact_key[:30]}...</td>
            <td>{f.status}</td>
        </tr>"""
    facts_html += "</table>"

    # Timeline Events
    timeline = db.query(TimelineEvent).order_by(TimelineEvent.created_at.desc()).limit(30).all()
    timeline_html = """<table>
        <tr><th>Event ID</th><th>Tenant</th><th>Event Type</th><th>Entity</th><th>Summary</th><th>Created At</th></tr>"""
    for e in timeline:
        timeline_html += f"""<tr>
            <td>{e.event_id[:8]}...</td>
            <td>{e.tenant_id[:8]}...</td>
            <td>{e.event_type}</td>
            <td>{e.entity_type}/{e.entity_id[:8]}...</td>
            <td>{e.summary[:40]}...</td>
            <td>{e.created_at}</td>
        </tr>"""
    timeline_html += "</table>"

    content = f"""
    <div class="card">
        <h2>Recent Actions ({len(actions)})</h2>
        {actions_html}
    </div>

    <div class="card">
        <h2>Recent Tasks ({len(tasks)})</h2>
        {tasks_html}
    </div>

    <div class="card">
        <h2>Recent Decisions ({len(decisions)})</h2>
        {decisions_html}
    </div>

    <div class="card">
        <h2>Memory Facts ({len(facts)})</h2>
        {facts_html}
    </div>

    <div class="card">
        <h2>Timeline (Recent 30)</h2>
        {timeline_html}
    </div>
    """

    return html_page("Core Business OS", content)


@router.get("/db/download")
def console_download_db(
    _: bool = Depends(verify_console_access),
):
    """Download the SQLite database file."""
    db_path = "./test.db"
    if not os.path.exists(db_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database file not found")
    return FileResponse(
        path=db_path,
        filename="bespin.db",
        media_type="application/x-sqlite3",
    )
