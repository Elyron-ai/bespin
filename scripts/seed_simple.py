#!/usr/bin/env python3
"""Simple test data seeding with clear credentials."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.database import Base, SessionLocal, engine
from app.gateway.models import GatewayTenant, GatewayUser, KPIDefinition, KPIPoint, Brief
from datetime import datetime, timezone, timedelta
import json
import uuid

def seed_database():
    """Create test data with simple hardcoded credentials."""

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Clear existing test data
        db.query(GatewayTenant).filter_by(tenant_id="demo").delete()
        db.commit()

        # Create tenant with simple API key
        tenant = GatewayTenant(
            tenant_id="demo",
            name="Demo Tenant",
            region="us-east-1",
            api_key="demo-api-key-12345",
        )
        db.add(tenant)
        db.flush()

        # Create admin user
        admin = GatewayUser(
            user_id="demo-admin",
            tenant_id="demo",
            email="admin@demo.com",
            role="admin",
        )
        db.add(admin)

        # Create member user
        member = GatewayUser(
            user_id="demo-member",
            tenant_id="demo",
            email="member@demo.com",
            role="member",
        )
        db.add(member)
        db.flush()

        # Create KPIs
        kpis = [
            KPIDefinition(
                kpi_id="mrr",
                tenant_id="demo",
                name="Monthly Recurring Revenue",
                unit="USD",
                description="Total MRR from all customers",
            ),
            KPIDefinition(
                kpi_id="churn",
                tenant_id="demo",
                name="Monthly Churn Rate",
                unit="percent",
                description="Percentage of customers lost monthly",
            ),
            KPIDefinition(
                kpi_id="customers",
                tenant_id="demo",
                name="Total Customers",
                unit="count",
                description="Total number of active customers",
            ),
        ]
        db.add_all(kpis)
        db.flush()

        # Add KPI data points
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        kpi_points = [
            KPIPoint(tenant_id="demo", kpi_id="mrr", value=150000.0, ts=today.isoformat()),
            KPIPoint(tenant_id="demo", kpi_id="churn", value=2.5, ts=today.isoformat()),
            KPIPoint(tenant_id="demo", kpi_id="customers", value=500, ts=today.isoformat()),
            KPIPoint(tenant_id="demo", kpi_id="mrr", value=148000.0, ts=(today - timedelta(days=1)).isoformat()),
            KPIPoint(tenant_id="demo", kpi_id="churn", value=2.8, ts=(today - timedelta(days=1)).isoformat()),
            KPIPoint(tenant_id="demo", kpi_id="customers", value=490, ts=(today - timedelta(days=1)).isoformat()),
        ]
        db.add_all(kpi_points)
        db.flush()

        # Create daily brief
        brief_content = {
            "summary": "Strong day with MRR growth of $2k",
            "highlights": [
                "MRR increased by $2,000 (1.35%) to $150,000",
                "Churn improved to 2.5% from 2.8%",
                "Customer base grew by 10 net new customers",
            ],
            "kpis_summary": {
                "mrr": {"value": 150000, "change": 2000, "change_pct": 1.35},
                "churn": {"value": 2.5, "change": -0.3, "change_pct": -10.7},
                "customers": {"value": 500, "change": 10, "change_pct": 2.0},
            },
        }

        brief = Brief(
            brief_id=str(uuid.uuid4()),
            tenant_id="demo",
            brief_date=today.date().isoformat(),
            window_days=1,
            top_n=5,
            content_json=json.dumps(brief_content),
            request_id=str(uuid.uuid4()),
        )
        db.add(brief)
        db.commit()

        print("\n" + "="*70)
        print("✓ TEST DATA CREATED SUCCESSFULLY")
        print("="*70)
        print("\nUse these credentials in the Playground UI at http://localhost:8000/ui\n")
        print("Tenant ID:  demo")
        print("API Key:    demo-api-key-12345")
        print("User ID:    demo-admin  (or demo-member)")
        print("\n" + "="*70 + "\n")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
