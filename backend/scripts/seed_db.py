#!/usr/bin/env python3
"""
Database seed script for Bespin.

Creates dummy data for all database tables for development and testing.
Run from the backend directory: python -m scripts.seed_db
"""

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add the backend directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal, engine, Base
from app.gateway.models import (
    GatewayTenant,
    GatewayUser,
    AuditLog,
    UsageEvent,
    IdempotencyKey,
    KPIDefinition,
    KPIPoint,
    Brief,
    NotificationPref,
    NotificationOutbox,
    Conversation,
    Message,
    TenantLimit,
    UsageRollupDaily,
)


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


def iso_now() -> str:
    """Return current UTC time as ISO string."""
    return utc_now().isoformat()


def date_str(days_ago: int = 0) -> str:
    """Return date string in YYYY-MM-DD format."""
    return (utc_now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def datetime_ago(days: int = 0, hours: int = 0) -> datetime:
    """Return datetime object for a time in the past."""
    return utc_now() - timedelta(days=days, hours=hours)


def iso_ago(days: int = 0, hours: int = 0) -> str:
    """Return ISO string for a time in the past."""
    return datetime_ago(days, hours).isoformat()


def seed_database():
    """Seed the database with dummy data."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # Check if data already exists
        existing_tenants = db.query(GatewayTenant).count()
        if existing_tenants > 0:
            print(f"Database already has {existing_tenants} tenant(s). Skipping seed.")
            print("To re-seed, clear the database first.")
            return

        print("Seeding database with dummy data...")

        # ============================================
        # 1. Create Tenants
        # ============================================
        print("  Creating tenants...")
        tenants = [
            GatewayTenant(
                tenant_id="tenant-acme-001",
                name="Acme Corporation",
                region="us-west-2",
                api_key="acme_api_key_" + "x" * 48,
                created_at=datetime_ago(days=90),
            ),
            GatewayTenant(
                tenant_id="tenant-globex-002",
                name="Globex Industries",
                region="eu-west-1",
                api_key="globex_api_key_" + "y" * 46,
                created_at=datetime_ago(days=60),
            ),
            GatewayTenant(
                tenant_id="tenant-initech-003",
                name="Initech",
                region="us-east-1",
                api_key="initech_api_key_" + "z" * 45,
                created_at=datetime_ago(days=30),
            ),
        ]
        db.add_all(tenants)

        # ============================================
        # 2. Create Users
        # ============================================
        print("  Creating users...")
        users = [
            # Acme users
            GatewayUser(
                user_id="user-alice-001",
                tenant_id="tenant-acme-001",
                email="alice@acme.com",
                role="admin",
                created_at=datetime_ago(days=89),
            ),
            GatewayUser(
                user_id="user-bob-002",
                tenant_id="tenant-acme-001",
                email="bob@acme.com",
                role="member",
                created_at=datetime_ago(days=85),
            ),
            GatewayUser(
                user_id="user-carol-003",
                tenant_id="tenant-acme-001",
                email="carol@acme.com",
                role="member",
                created_at=datetime_ago(days=80),
            ),
            # Globex users
            GatewayUser(
                user_id="user-dave-004",
                tenant_id="tenant-globex-002",
                email="dave@globex.com",
                role="admin",
                created_at=datetime_ago(days=59),
            ),
            GatewayUser(
                user_id="user-eve-005",
                tenant_id="tenant-globex-002",
                email="eve@globex.com",
                role="member",
                created_at=datetime_ago(days=55),
            ),
            # Initech users
            GatewayUser(
                user_id="user-frank-006",
                tenant_id="tenant-initech-003",
                email="frank@initech.com",
                role="admin",
                created_at=datetime_ago(days=29),
            ),
            GatewayUser(
                user_id="user-grace-007",
                tenant_id="tenant-initech-003",
                email="grace@initech.com",
                role="member",
                created_at=datetime_ago(days=25),
            ),
        ]
        db.add_all(users)

        # ============================================
        # 3. Create Tenant Limits
        # ============================================
        print("  Creating tenant limits...")
        tenant_limits = [
            TenantLimit(
                tenant_id="tenant-acme-001",
                assistant_query_daily_limit=200,
                tool_invocation_daily_limit=500,
                daily_brief_generated_daily_limit=20,
                notification_enqueued_daily_limit=1000,
                created_at=datetime_ago(days=90),
            ),
            TenantLimit(
                tenant_id="tenant-globex-002",
                assistant_query_daily_limit=100,
                tool_invocation_daily_limit=250,
                daily_brief_generated_daily_limit=10,
                notification_enqueued_daily_limit=500,
                created_at=datetime_ago(days=60),
            ),
            TenantLimit(
                tenant_id="tenant-initech-003",
                assistant_query_daily_limit=50,
                tool_invocation_daily_limit=100,
                daily_brief_generated_daily_limit=5,
                notification_enqueued_daily_limit=200,
                created_at=datetime_ago(days=30),
            ),
        ]
        db.add_all(tenant_limits)

        # ============================================
        # 4. Create KPI Definitions
        # ============================================
        print("  Creating KPI definitions...")
        kpi_definitions = [
            # Acme KPIs
            KPIDefinition(
                kpi_id="kpi-acme-revenue-001",
                tenant_id="tenant-acme-001",
                name="Monthly Revenue",
                unit="USD",
                description="Total monthly revenue in USD",
                created_at=datetime_ago(days=88),
            ),
            KPIDefinition(
                kpi_id="kpi-acme-users-002",
                tenant_id="tenant-acme-001",
                name="Active Users",
                unit="count",
                description="Number of monthly active users",
                created_at=datetime_ago(days=88),
            ),
            KPIDefinition(
                kpi_id="kpi-acme-churn-003",
                tenant_id="tenant-acme-001",
                name="Churn Rate",
                unit="percent",
                description="Monthly customer churn rate",
                created_at=datetime_ago(days=88),
            ),
            KPIDefinition(
                kpi_id="kpi-acme-nps-004",
                tenant_id="tenant-acme-001",
                name="NPS Score",
                unit="score",
                description="Net Promoter Score",
                created_at=datetime_ago(days=88),
            ),
            # Globex KPIs
            KPIDefinition(
                kpi_id="kpi-globex-sales-001",
                tenant_id="tenant-globex-002",
                name="Weekly Sales",
                unit="EUR",
                description="Weekly sales in EUR",
                created_at=datetime_ago(days=58),
            ),
            KPIDefinition(
                kpi_id="kpi-globex-leads-002",
                tenant_id="tenant-globex-002",
                name="New Leads",
                unit="count",
                description="Number of new leads per week",
                created_at=datetime_ago(days=58),
            ),
            # Initech KPIs
            KPIDefinition(
                kpi_id="kpi-initech-tickets-001",
                tenant_id="tenant-initech-003",
                name="Open Tickets",
                unit="count",
                description="Number of open support tickets",
                created_at=datetime_ago(days=28),
            ),
            KPIDefinition(
                kpi_id="kpi-initech-response-002",
                tenant_id="tenant-initech-003",
                name="Avg Response Time",
                unit="hours",
                description="Average ticket response time in hours",
                created_at=datetime_ago(days=28),
            ),
        ]
        db.add_all(kpi_definitions)

        # ============================================
        # 5. Create KPI Points (time series data)
        # ============================================
        print("  Creating KPI data points...")
        kpi_points = []

        # Acme Revenue data (last 30 days)
        for i in range(30):
            kpi_points.append(KPIPoint(
                tenant_id="tenant-acme-001",
                kpi_id="kpi-acme-revenue-001",
                ts=iso_ago(days=i),
                value=150000 + (i * 500) + (i % 7) * 1000,
                created_at=datetime_ago(days=i),
            ))

        # Acme Active Users (last 30 days)
        for i in range(30):
            kpi_points.append(KPIPoint(
                tenant_id="tenant-acme-001",
                kpi_id="kpi-acme-users-002",
                ts=iso_ago(days=i),
                value=5000 + (i * 10) + (i % 5) * 50,
                created_at=datetime_ago(days=i),
            ))

        # Acme Churn Rate (last 30 days)
        for i in range(30):
            kpi_points.append(KPIPoint(
                tenant_id="tenant-acme-001",
                kpi_id="kpi-acme-churn-003",
                ts=iso_ago(days=i),
                value=2.5 + (i % 10) * 0.1,
                created_at=datetime_ago(days=i),
            ))

        # Acme NPS (last 30 days)
        for i in range(30):
            kpi_points.append(KPIPoint(
                tenant_id="tenant-acme-001",
                kpi_id="kpi-acme-nps-004",
                ts=iso_ago(days=i),
                value=45 + (i % 15),
                created_at=datetime_ago(days=i),
            ))

        # Globex Sales (last 14 days)
        for i in range(14):
            kpi_points.append(KPIPoint(
                tenant_id="tenant-globex-002",
                kpi_id="kpi-globex-sales-001",
                ts=iso_ago(days=i),
                value=75000 + (i * 300) + (i % 3) * 500,
                created_at=datetime_ago(days=i),
            ))

        # Globex Leads (last 14 days)
        for i in range(14):
            kpi_points.append(KPIPoint(
                tenant_id="tenant-globex-002",
                kpi_id="kpi-globex-leads-002",
                ts=iso_ago(days=i),
                value=120 + (i * 5) + (i % 4) * 10,
                created_at=datetime_ago(days=i),
            ))

        # Initech Tickets (last 7 days)
        for i in range(7):
            kpi_points.append(KPIPoint(
                tenant_id="tenant-initech-003",
                kpi_id="kpi-initech-tickets-001",
                ts=iso_ago(days=i),
                value=25 + (i % 5) * 3,
                created_at=datetime_ago(days=i),
            ))

        # Initech Response Time (last 7 days)
        for i in range(7):
            kpi_points.append(KPIPoint(
                tenant_id="tenant-initech-003",
                kpi_id="kpi-initech-response-002",
                ts=iso_ago(days=i),
                value=4.5 + (i % 3) * 0.5,
                created_at=datetime_ago(days=i),
            ))

        db.add_all(kpi_points)

        # ============================================
        # 6. Create Briefs
        # ============================================
        print("  Creating daily briefs...")
        briefs = [
            Brief(
                brief_id="brief-acme-001",
                tenant_id="tenant-acme-001",
                brief_date=date_str(0),
                window_days=7,
                top_n=5,
                content_json=json.dumps({
                    "summary": "Strong week with revenue up 3.2% and active users increasing steadily.",
                    "highlights": [
                        {"kpi": "Monthly Revenue", "change": "+3.2%", "trend": "up"},
                        {"kpi": "Active Users", "change": "+2.1%", "trend": "up"},
                        {"kpi": "Churn Rate", "change": "-0.3%", "trend": "down"},
                        {"kpi": "NPS Score", "change": "+5 points", "trend": "up"},
                    ],
                    "alerts": [],
                    "recommendations": ["Consider scaling infrastructure for growing user base."],
                }),
                request_id=generate_uuid(),
                created_at=datetime_ago(hours=6),
            ),
            Brief(
                brief_id="brief-acme-002",
                tenant_id="tenant-acme-001",
                brief_date=date_str(1),
                window_days=7,
                top_n=5,
                content_json=json.dumps({
                    "summary": "Stable performance with minor fluctuations in key metrics.",
                    "highlights": [
                        {"kpi": "Monthly Revenue", "change": "+1.8%", "trend": "up"},
                        {"kpi": "Active Users", "change": "+1.5%", "trend": "up"},
                    ],
                    "alerts": [{"kpi": "Churn Rate", "message": "Slight uptick observed"}],
                    "recommendations": ["Review customer feedback for churn signals."],
                }),
                request_id=generate_uuid(),
                created_at=datetime_ago(days=1, hours=6),
            ),
            Brief(
                brief_id="brief-globex-001",
                tenant_id="tenant-globex-002",
                brief_date=date_str(0),
                window_days=7,
                top_n=3,
                content_json=json.dumps({
                    "summary": "Sales momentum continues with strong lead generation.",
                    "highlights": [
                        {"kpi": "Weekly Sales", "change": "+4.5%", "trend": "up"},
                        {"kpi": "New Leads", "change": "+8.2%", "trend": "up"},
                    ],
                    "alerts": [],
                    "recommendations": ["Expand sales team to capture lead momentum."],
                }),
                request_id=generate_uuid(),
                created_at=datetime_ago(hours=5),
            ),
        ]
        db.add_all(briefs)

        # ============================================
        # 7. Create Notification Preferences
        # ============================================
        print("  Creating notification preferences...")
        notification_prefs = [
            NotificationPref(
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                daily_brief_enabled=1,
                delivery_method="email",
                created_at=datetime_ago(days=85),
            ),
            NotificationPref(
                tenant_id="tenant-acme-001",
                user_id="user-bob-002",
                daily_brief_enabled=1,
                delivery_method="in_app",
                created_at=datetime_ago(days=80),
            ),
            NotificationPref(
                tenant_id="tenant-acme-001",
                user_id="user-carol-003",
                daily_brief_enabled=0,
                delivery_method="in_app",
                created_at=datetime_ago(days=75),
            ),
            NotificationPref(
                tenant_id="tenant-globex-002",
                user_id="user-dave-004",
                daily_brief_enabled=1,
                delivery_method="email",
                created_at=datetime_ago(days=55),
            ),
            NotificationPref(
                tenant_id="tenant-globex-002",
                user_id="user-eve-005",
                daily_brief_enabled=1,
                delivery_method="slack",
                created_at=datetime_ago(days=50),
            ),
            NotificationPref(
                tenant_id="tenant-initech-003",
                user_id="user-frank-006",
                daily_brief_enabled=1,
                delivery_method="email",
                created_at=datetime_ago(days=25),
            ),
        ]
        db.add_all(notification_prefs)

        # ============================================
        # 8. Create Notification Outbox
        # ============================================
        print("  Creating notification outbox...")
        notification_outbox = [
            NotificationOutbox(
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                notification_type="daily_brief",
                notif_date=date_str(0),
                status="queued",
                payload_json=json.dumps({
                    "brief_id": "brief-acme-001",
                    "subject": "Your Daily Brief - " + date_str(0),
                }),
                request_id=generate_uuid(),
                created_at=datetime_ago(hours=5),
            ),
            NotificationOutbox(
                tenant_id="tenant-acme-001",
                user_id="user-bob-002",
                notification_type="daily_brief",
                notif_date=date_str(0),
                status="acked",
                payload_json=json.dumps({
                    "brief_id": "brief-acme-001",
                    "subject": "Your Daily Brief - " + date_str(0),
                }),
                request_id=generate_uuid(),
                created_at=datetime_ago(hours=4),
            ),
            NotificationOutbox(
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                notification_type="daily_brief",
                notif_date=date_str(1),
                status="acked",
                payload_json=json.dumps({
                    "brief_id": "brief-acme-002",
                    "subject": "Your Daily Brief - " + date_str(1),
                }),
                request_id=generate_uuid(),
                created_at=datetime_ago(days=1, hours=4),
            ),
            NotificationOutbox(
                tenant_id="tenant-globex-002",
                user_id="user-dave-004",
                notification_type="daily_brief",
                notif_date=date_str(0),
                status="queued",
                payload_json=json.dumps({
                    "brief_id": "brief-globex-001",
                    "subject": "Your Daily Brief - " + date_str(0),
                }),
                request_id=generate_uuid(),
                created_at=datetime_ago(hours=3),
            ),
        ]
        db.add_all(notification_outbox)

        # ============================================
        # 9. Create Conversations
        # ============================================
        print("  Creating conversations...")
        conversations = [
            Conversation(
                conversation_id="conv-acme-alice-001",
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                title="Q4 Revenue Strategy",
                created_at=iso_ago(days=5),
            ),
            Conversation(
                conversation_id="conv-acme-alice-002",
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                title="Customer Churn Analysis",
                created_at=iso_ago(days=2),
            ),
            Conversation(
                conversation_id="conv-acme-bob-001",
                tenant_id="tenant-acme-001",
                user_id="user-bob-002",
                title="Product Feature Roadmap",
                created_at=iso_ago(days=3),
            ),
            Conversation(
                conversation_id="conv-globex-dave-001",
                tenant_id="tenant-globex-002",
                user_id="user-dave-004",
                title="European Expansion Plan",
                created_at=iso_ago(days=4),
            ),
            Conversation(
                conversation_id="conv-initech-frank-001",
                tenant_id="tenant-initech-003",
                user_id="user-frank-006",
                title="Support Team Scaling",
                created_at=iso_ago(days=1),
            ),
        ]
        db.add_all(conversations)

        # ============================================
        # 10. Create Messages
        # ============================================
        print("  Creating messages...")
        messages = [
            # Conversation: Q4 Revenue Strategy
            Message(
                message_id="msg-001",
                conversation_id="conv-acme-alice-001",
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                role="user",
                content="What are our top revenue drivers for Q4?",
                metadata_json=json.dumps({}),
                created_at=iso_ago(days=5, hours=2),
            ),
            Message(
                message_id="msg-002",
                conversation_id="conv-acme-alice-001",
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                role="assistant",
                content="Based on your KPI data, your top revenue drivers for Q4 are:\n\n1. **Enterprise Subscriptions** - Contributing 45% of total revenue\n2. **Professional Services** - 25% of revenue with growing demand\n3. **Platform Add-ons** - 18% and showing strong growth\n\nYour Monthly Revenue KPI shows a consistent upward trend of approximately 3.2% week-over-week.",
                metadata_json=json.dumps({
                    "cards": [
                        {"type": "kpi_summary", "kpi_id": "kpi-acme-revenue-001"}
                    ]
                }),
                created_at=iso_ago(days=5, hours=1),
            ),
            Message(
                message_id="msg-003",
                conversation_id="conv-acme-alice-001",
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                role="user",
                content="How can we accelerate growth in the Professional Services segment?",
                metadata_json=json.dumps({}),
                created_at=iso_ago(days=5),
            ),
            Message(
                message_id="msg-004",
                conversation_id="conv-acme-alice-001",
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                role="assistant",
                content="To accelerate Professional Services growth, consider these strategies:\n\n1. **Expand service offerings** - Add implementation and training packages\n2. **Partner program** - Certify system integrators to extend reach\n3. **Outcome-based pricing** - Align fees with customer success metrics\n\nGiven your current NPS of 52, customer satisfaction is strong enough to support premium service tiers.",
                metadata_json=json.dumps({}),
                created_at=iso_ago(days=4, hours=23),
            ),

            # Conversation: Customer Churn Analysis
            Message(
                message_id="msg-005",
                conversation_id="conv-acme-alice-002",
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                role="user",
                content="Our churn rate increased slightly last week. What could be causing this?",
                metadata_json=json.dumps({}),
                created_at=iso_ago(days=2, hours=3),
            ),
            Message(
                message_id="msg-006",
                conversation_id="conv-acme-alice-002",
                tenant_id="tenant-acme-001",
                user_id="user-alice-001",
                role="assistant",
                content="Your Churn Rate KPI shows a 0.3% increase last week. Analyzing the pattern, here are potential causes:\n\n1. **Seasonal factor** - Historical data shows slight upticks in this period\n2. **Competitor activity** - Recent market movements may be attracting your SMB segment\n3. **Onboarding friction** - New cohort from 2 months ago may be hitting renewal decisions\n\nRecommendation: Review exit surveys from recent churned accounts for actionable insights.",
                metadata_json=json.dumps({
                    "cards": [
                        {"type": "kpi_trend", "kpi_id": "kpi-acme-churn-003"}
                    ]
                }),
                created_at=iso_ago(days=2, hours=2),
            ),

            # Conversation: Product Feature Roadmap
            Message(
                message_id="msg-007",
                conversation_id="conv-acme-bob-001",
                tenant_id="tenant-acme-001",
                user_id="user-bob-002",
                role="user",
                content="What features should we prioritize based on user engagement data?",
                metadata_json=json.dumps({}),
                created_at=iso_ago(days=3, hours=5),
            ),
            Message(
                message_id="msg-008",
                conversation_id="conv-acme-bob-001",
                tenant_id="tenant-acme-001",
                user_id="user-bob-002",
                role="assistant",
                content="Based on your Active Users KPI and engagement patterns:\n\n**High Priority:**\n- Dashboard customization (requested by 67% of power users)\n- API improvements (growing developer segment)\n\n**Medium Priority:**\n- Mobile app enhancements\n- Collaboration features\n\nYour active user count is growing at 2.1% weekly, indicating strong product-market fit. Focus on features that increase stickiness.",
                metadata_json=json.dumps({}),
                created_at=iso_ago(days=3, hours=4),
            ),

            # Conversation: European Expansion Plan
            Message(
                message_id="msg-009",
                conversation_id="conv-globex-dave-001",
                tenant_id="tenant-globex-002",
                user_id="user-dave-004",
                role="user",
                content="Should we expand to the Nordic markets given our current sales trends?",
                metadata_json=json.dumps({}),
                created_at=iso_ago(days=4, hours=6),
            ),
            Message(
                message_id="msg-010",
                conversation_id="conv-globex-dave-001",
                tenant_id="tenant-globex-002",
                user_id="user-dave-004",
                role="assistant",
                content="Your Weekly Sales KPI shows strong momentum at +4.5% growth. For Nordic expansion:\n\n**Positive indicators:**\n- Strong lead generation (+8.2%) suggests market demand\n- EU-west-1 infrastructure already supports the region\n\n**Considerations:**\n- Regulatory compliance (GDPR already covered)\n- Local language support requirements\n- Time zone alignment with current team\n\nRecommendation: Start with a pilot in Sweden, which has the highest English proficiency.",
                metadata_json=json.dumps({
                    "cards": [
                        {"type": "kpi_summary", "kpi_id": "kpi-globex-sales-001"},
                        {"type": "kpi_summary", "kpi_id": "kpi-globex-leads-002"}
                    ]
                }),
                created_at=iso_ago(days=4, hours=5),
            ),

            # Conversation: Support Team Scaling
            Message(
                message_id="msg-011",
                conversation_id="conv-initech-frank-001",
                tenant_id="tenant-initech-003",
                user_id="user-frank-006",
                role="user",
                content="We're seeing ticket volume increase. Should we hire more support staff?",
                metadata_json=json.dumps({}),
                created_at=iso_ago(days=1, hours=4),
            ),
            Message(
                message_id="msg-012",
                conversation_id="conv-initech-frank-001",
                tenant_id="tenant-initech-003",
                user_id="user-frank-006",
                role="assistant",
                content="Looking at your support KPIs:\n\n- **Open Tickets**: Averaging 28 with moderate fluctuation\n- **Avg Response Time**: 5.2 hours, slightly above target\n\n**Analysis:**\nBefore hiring, consider:\n1. Implement self-service documentation for common issues\n2. Add chatbot for tier-1 queries\n3. Review ticket categorization for automation opportunities\n\nIf response time exceeds 6 hours consistently, then additional headcount would be justified.",
                metadata_json=json.dumps({
                    "cards": [
                        {"type": "kpi_trend", "kpi_id": "kpi-initech-tickets-001"},
                        {"type": "kpi_trend", "kpi_id": "kpi-initech-response-002"}
                    ]
                }),
                created_at=iso_ago(days=1, hours=3),
            ),
        ]
        db.add_all(messages)

        # ============================================
        # 11. Create Audit Logs
        # ============================================
        print("  Creating audit logs...")
        audit_logs = []
        actions = ["tool_invoked", "brief_generated", "conversation_created", "message_sent", "kpi_upserted"]
        tool_names = ["kpi_store", "daily_brief", "cofounder_chat", None, None]

        for i in range(50):
            tenant = ["tenant-acme-001", "tenant-globex-002", "tenant-initech-003"][i % 3]
            user_map = {
                "tenant-acme-001": ["user-alice-001", "user-bob-002", "user-carol-003"],
                "tenant-globex-002": ["user-dave-004", "user-eve-005"],
                "tenant-initech-003": ["user-frank-006", "user-grace-007"],
            }
            user = user_map[tenant][i % len(user_map[tenant])]
            action_idx = i % len(actions)

            audit_logs.append(AuditLog(
                tenant_id=tenant,
                user_id=user,
                action=actions[action_idx],
                tool_name=tool_names[action_idx],
                request_id=generate_uuid(),
                created_at=datetime_ago(days=i // 5, hours=i % 24),
            ))
        db.add_all(audit_logs)

        # ============================================
        # 12. Create Usage Events
        # ============================================
        print("  Creating usage events...")
        usage_events = []
        activity_types = ["tool_invocation", "assistant_query", "daily_brief_generated", "notification_enqueued"]

        for i in range(100):
            tenant = ["tenant-acme-001", "tenant-globex-002", "tenant-initech-003"][i % 3]
            user_map = {
                "tenant-acme-001": ["user-alice-001", "user-bob-002", "user-carol-003"],
                "tenant-globex-002": ["user-dave-004", "user-eve-005"],
                "tenant-initech-003": ["user-frank-006", "user-grace-007"],
            }
            user = user_map[tenant][i % len(user_map[tenant])]
            activity_type = activity_types[i % len(activity_types)]

            usage_events.append(UsageEvent(
                tenant_id=tenant,
                user_id=user,
                activity_type=activity_type,
                units=1 if activity_type != "tool_invocation" else (i % 3) + 1,
                tool_name="kpi_store" if activity_type == "tool_invocation" else None,
                request_id=generate_uuid(),
                created_at=datetime_ago(days=i // 10, hours=i % 24),
            ))
        db.add_all(usage_events)

        # ============================================
        # 13. Create Usage Rollups
        # ============================================
        print("  Creating usage rollups...")
        usage_rollups = []
        for tenant in ["tenant-acme-001", "tenant-globex-002", "tenant-initech-003"]:
            for days_ago in range(7):
                for activity_type in activity_types:
                    base_units = {"tenant-acme-001": 50, "tenant-globex-002": 30, "tenant-initech-003": 15}
                    multiplier = {"tool_invocation": 2, "assistant_query": 1.5, "daily_brief_generated": 0.1, "notification_enqueued": 0.5}

                    usage_rollups.append(UsageRollupDaily(
                        tenant_id=tenant,
                        rollup_date=date_str(days_ago),
                        activity_type=activity_type,
                        units=int(base_units[tenant] * multiplier[activity_type]),
                        updated_at=datetime_ago(days=days_ago),
                    ))
        db.add_all(usage_rollups)

        # ============================================
        # 14. Create Idempotency Keys
        # ============================================
        print("  Creating idempotency keys...")
        idempotency_keys = [
            IdempotencyKey(
                tenant_id="tenant-acme-001",
                endpoint="/v1/tools/invoke",
                idempotency_key="idem-key-001",
                request_hash="a" * 64,
                response_json=json.dumps({"status": "success", "tool": "kpi_store"}),
                created_at=datetime_ago(hours=2),
            ),
            IdempotencyKey(
                tenant_id="tenant-acme-001",
                endpoint="/v1/briefs",
                idempotency_key="idem-key-002",
                request_hash="b" * 64,
                response_json=json.dumps({"status": "success", "brief_id": "brief-acme-001"}),
                created_at=datetime_ago(hours=1),
            ),
            IdempotencyKey(
                tenant_id="tenant-globex-002",
                endpoint="/v1/tools/invoke",
                idempotency_key="idem-key-003",
                request_hash="c" * 64,
                response_json=json.dumps({"status": "success", "tool": "daily_brief"}),
                created_at=datetime_ago(hours=3),
            ),
        ]
        db.add_all(idempotency_keys)

        # Commit all changes
        db.commit()

        print("\nDatabase seeded successfully!")
        print("\nSummary:")
        print(f"  - Tenants: 3")
        print(f"  - Users: 7")
        print(f"  - Tenant Limits: 3")
        print(f"  - KPI Definitions: 8")
        print(f"  - KPI Data Points: {len(kpi_points)}")
        print(f"  - Briefs: 3")
        print(f"  - Notification Preferences: 6")
        print(f"  - Notification Outbox: 4")
        print(f"  - Conversations: 5")
        print(f"  - Messages: 12")
        print(f"  - Audit Logs: 50")
        print(f"  - Usage Events: 100")
        print(f"  - Usage Rollups: {len(usage_rollups)}")
        print(f"  - Idempotency Keys: 3")

    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def clear_database():
    """Clear all data from the database (use with caution)."""
    print("Clearing database...")
    db = SessionLocal()
    try:
        # Delete in reverse order of dependencies
        db.query(Message).delete()
        db.query(Conversation).delete()
        db.query(NotificationOutbox).delete()
        db.query(NotificationPref).delete()
        db.query(Brief).delete()
        db.query(KPIPoint).delete()
        db.query(KPIDefinition).delete()
        db.query(IdempotencyKey).delete()
        db.query(UsageRollupDaily).delete()
        db.query(UsageEvent).delete()
        db.query(AuditLog).delete()
        db.query(TenantLimit).delete()
        db.query(GatewayUser).delete()
        db.query(GatewayTenant).delete()
        db.commit()
        print("Database cleared successfully!")
    except Exception as e:
        print(f"Error clearing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed or clear the Bespin database")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the database before seeding",
    )
    parser.add_argument(
        "--clear-only",
        action="store_true",
        help="Only clear the database, don't seed",
    )

    args = parser.parse_args()

    if args.clear_only:
        clear_database()
    elif args.clear:
        clear_database()
        seed_database()
    else:
        seed_database()
