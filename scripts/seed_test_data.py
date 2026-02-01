#!/usr/bin/env python3
"""Seed test data for Playground UI testing."""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.database import Base, SessionLocal, engine
from app.gateway.models import (
    GatewayTenant,
    GatewayUser,
    KPIDefinition,
    KPIPoint,
    Brief,
)
from datetime import datetime, timedelta
import json
import secrets

def seed_database():
    """Create test data in the database."""

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # Check if test tenant already exists
        existing = db.query(GatewayTenant).filter_by(name="Test Tenant").first()
        if existing:
            print(f"Test tenant already exists!")
            print_credentials(existing, db)
            return

        # Create a test tenant
        tenant = GatewayTenant(
            tenant_id="test-tenant-001",
            name="Test Tenant",
            region="us-east-1",
            api_key=secrets.token_urlsafe(32),
        )
        db.add(tenant)
        db.flush()

        # Create admin user
        admin = GatewayUser(
            user_id="test-admin-001",
            tenant_id=tenant.tenant_id,
            email="admin@test.com",
            role="admin",
        )
        db.add(admin)
        db.flush()

        # Create member user
        member = GatewayUser(
            user_id="test-member-001",
            tenant_id=tenant.tenant_id,
            email="member@test.com",
            role="member",
        )
        db.add(member)
        db.flush()

        # Create some KPI definitions
        kpis = [
            KPIDefinition(
                kpi_id="mrr",
                tenant_id=tenant.tenant_id,
                name="Monthly Recurring Revenue",
                unit="USD",
                description="Total MRR from all customers",
            ),
            KPIDefinition(
                kpi_id="churn",
                tenant_id=tenant.tenant_id,
                name="Monthly Churn Rate",
                unit="percent",
                description="Percentage of customers lost monthly",
            ),
            KPIDefinition(
                kpi_id="customers",
                tenant_id=tenant.tenant_id,
                name="Total Customers",
                unit="count",
                description="Total number of active customers",
            ),
        ]
        db.add_all(kpis)
        db.flush()

        # Add some data points
        from datetime import timezone
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        kpi_points = [
            KPIPoint(
                tenant_id=tenant.tenant_id,
                kpi_id="mrr",
                value=150000.0,
                ts=today.isoformat(),
            ),
            KPIPoint(
                tenant_id=tenant.tenant_id,
                kpi_id="churn",
                value=2.5,
                ts=today.isoformat(),
            ),
            KPIPoint(
                tenant_id=tenant.tenant_id,
                kpi_id="customers",
                value=500,
                ts=today.isoformat(),
            ),
            # Yesterday's data
            KPIPoint(
                tenant_id=tenant.tenant_id,
                kpi_id="mrr",
                value=148000.0,
                ts=(today - timedelta(days=1)).isoformat(),
            ),
            KPIPoint(
                tenant_id=tenant.tenant_id,
                kpi_id="churn",
                value=2.8,
                ts=(today - timedelta(days=1)).isoformat(),
            ),
            KPIPoint(
                tenant_id=tenant.tenant_id,
                kpi_id="customers",
                value=490,
                ts=(today - timedelta(days=1)).isoformat(),
            ),
        ]
        db.add_all(kpi_points)
        db.flush()

        # Create a daily brief
        brief_content = {
            "summary": "Strong day with MRR growth of $2k",
            "highlights": [
                "MRR increased by $2,000 (1.35%) to $150,000",
                "Churn improved to 2.5% from 2.8%",
                "Customer base grew by 10 net new customers",
            ],
            "kpis_summary": {
                "mrr": {
                    "value": 150000,
                    "change": 2000,
                    "change_pct": 1.35,
                },
                "churn": {
                    "value": 2.5,
                    "change": -0.3,
                    "change_pct": -10.7,
                },
                "customers": {
                    "value": 500,
                    "change": 10,
                    "change_pct": 2.0,
                },
            },
        }

        import uuid
        brief = Brief(
            brief_id=str(uuid.uuid4()),
            tenant_id=tenant.tenant_id,
            brief_date=today.date().isoformat(),
            window_days=1,
            top_n=5,
            content_json=json.dumps(brief_content),
            request_id=str(uuid.uuid4()),
        )
        db.add(brief)

        db.commit()

        print_credentials(tenant, db)

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        sys.exit(1)
    finally:
        db.close()

def print_credentials(tenant, db):
    """Print credentials to use in Playground UI."""
    admin = db.query(GatewayUser).filter_by(
        tenant_id=tenant.tenant_id,
        role="admin"
    ).first()

    member = db.query(GatewayUser).filter_by(
        tenant_id=tenant.tenant_id,
        role="member"
    ).first()

    print("\n" + "="*60)
    print("✓ Test data created successfully!")
    print("="*60)
    print("\nUse these credentials in the Playground UI at /ui:\n")

    print("ADMIN ACCOUNT:")
    print(f"  Tenant ID: {tenant.tenant_id}")
    print(f"  API Key:   {tenant.api_key}")
    print(f"  User ID:   {admin.user_id if admin else 'N/A'}")

    print("\nMEMBER ACCOUNT:")
    print(f"  Tenant ID: {tenant.tenant_id}")
    print(f"  API Key:   {tenant.api_key}")
    print(f"  User ID:   {member.user_id if member else 'N/A'}")

    print("\n" + "="*60)
    print("Test data includes:")
    print("  • 3 KPIs (MRR, Churn, Customers)")
    print("  • 2 days of KPI data points")
    print("  • 1 Daily Brief with highlights")
    print("="*60 + "\n")

if __name__ == "__main__":
    seed_database()
