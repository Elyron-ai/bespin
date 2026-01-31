"""Dev Console for viewing database state."""
import os
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
}


def verify_console_access(key: str = Query(...)):
    """Verify console access is enabled and key is valid."""
    if not DEV_CONSOLE_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if key != DEV_CONSOLE_KEY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return True


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
            <td class="truncate">{t.api_key}</td>
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

    content = f"""
    <div class="card">
        <h2>Tenant Info</h2>
        <p><strong>ID:</strong> {tenant.tenant_id}</p>
        <p><strong>Name:</strong> {tenant.name}</p>
        <p><strong>Region:</strong> {tenant.region}</p>
        <p><strong>API Key:</strong> <code>{tenant.api_key}</code></p>
        <p><strong>Created:</strong> {tenant.created_at}</p>
    </div>

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
