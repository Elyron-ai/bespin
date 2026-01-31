"""Brief generation logic for the Insight Materializer."""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.gateway.models import KPIDefinition, KPIPoint


def generate_daily_brief(
    db: Session,
    tenant_id: str,
    brief_date: str,
    window_days: int,
    top_n: int,
) -> dict[str, Any]:
    """Generate a daily brief for a tenant.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        brief_date: The date string in YYYY-MM-DD format.
        window_days: Number of days for the lookback window.
        top_n: Number of top KPIs to include in highlights.

    Returns:
        A dictionary containing the brief content.
    """
    # Get all KPI definitions for this tenant
    kpi_definitions = db.query(KPIDefinition).filter(
        KPIDefinition.tenant_id == tenant_id
    ).all()

    # Calculate the end of day boundary for brief_date
    end_ts = f"{brief_date}T23:59:59Z"

    # Track stats
    kpi_data = []
    kpis_up = 0
    kpis_down = 0
    kpis_flat = 0

    for kpi_def in kpi_definitions:
        # Find the latest KPI point with ts <= end_ts
        latest_point = db.query(KPIPoint).filter(
            KPIPoint.tenant_id == tenant_id,
            KPIPoint.kpi_id == kpi_def.kpi_id,
            KPIPoint.ts <= end_ts,
        ).order_by(KPIPoint.ts.desc()).first()

        if not latest_point:
            # No points for this KPI, skip it
            continue

        # Calculate window_start_ts = latest.ts - window_days days
        # Parse the latest timestamp
        latest_ts_str = latest_point.ts
        # Handle ISO 8601 format
        if latest_ts_str.endswith("Z"):
            latest_ts_str = latest_ts_str[:-1] + "+00:00"
        try:
            latest_dt = datetime.fromisoformat(latest_ts_str)
        except ValueError:
            # If we can't parse, skip this KPI
            continue

        window_start_dt = latest_dt - timedelta(days=window_days)
        window_start_ts = window_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Find the earliest point within the window
        start_point = db.query(KPIPoint).filter(
            KPIPoint.tenant_id == tenant_id,
            KPIPoint.kpi_id == kpi_def.kpi_id,
            KPIPoint.ts >= window_start_ts,
            KPIPoint.ts <= latest_point.ts,
        ).order_by(KPIPoint.ts.asc()).first()

        # If no start point found (shouldn't happen if latest exists), use latest
        if not start_point:
            start_point = latest_point

        # Compute deltas
        delta_abs = latest_point.value - start_point.value
        if start_point.value != 0:
            delta_pct = (delta_abs / start_point.value) * 100
        else:
            delta_pct = None

        # Update counters based on delta_abs
        if delta_abs > 0:
            kpis_up += 1
        elif delta_abs < 0:
            kpis_down += 1
        else:
            kpis_flat += 1

        kpi_data.append({
            "kpi_id": kpi_def.kpi_id,
            "name": kpi_def.name,
            "unit": kpi_def.unit,
            "latest": {"ts": latest_point.ts, "value": latest_point.value},
            "start": {"ts": start_point.ts, "value": start_point.value},
            "delta_abs": delta_abs,
            "delta_pct": delta_pct,
        })

    # Select highlights: top_n KPIs by ABS(delta_pct) descending
    # Treat None as 0 for ranking
    def sort_key(item: dict) -> float:
        pct = item["delta_pct"]
        return abs(pct) if pct is not None else 0.0

    sorted_kpis = sorted(kpi_data, key=sort_key, reverse=True)
    highlights = sorted_kpis[:top_n]

    # Generate alerts: KPIs where delta_pct is not null AND delta_pct <= -10.0
    alerts = []
    for kpi in kpi_data:
        if kpi["delta_pct"] is not None and kpi["delta_pct"] <= -10.0:
            alerts.append({
                "kpi_id": kpi["kpi_id"],
                "name": kpi["name"],
                "severity": "high",
                "reason": "delta_pct_below_threshold",
                "delta_pct": kpi["delta_pct"],
            })

    # Construct the content
    content = {
        "date": brief_date,
        "window_days": window_days,
        "top_n": top_n,
        "summary": {
            "kpis_considered": len(kpi_data),
            "kpis_up": kpis_up,
            "kpis_down": kpis_down,
            "kpis_flat": kpis_flat,
        },
        "highlights": highlights,
        "alerts": alerts,
    }

    return content
