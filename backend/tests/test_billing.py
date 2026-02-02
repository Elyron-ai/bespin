"""Tests for the Billing and Metering system (Phase 0 Item #7)."""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Disable rate limiting for tests
os.environ["RATE_LIMIT_DISABLED"] = "1"

from app.database import Base, get_db
from app.main import app
from app.gateway.models import (
    MeteredEventType,
    Plan,
    PlanCapability,
    PlanEventCap,
    TenantSubscription,
    UsageEvent,
    UsageRollupPeriod,
)


# Create a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for tests."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Set platform admin key for tests
os.environ["PLATFORM_ADMIN_KEY"] = "test-admin-key"
ADMIN_KEY = "test-admin-key"


@pytest.fixture(scope="function")
def client():
    """Create test client with fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    # Seed billing data
    from app.gateway.billing_seed import seed_all_billing_data
    db = TestingSessionLocal()
    seed_all_billing_data(db)
    db.close()
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def tenant(client):
    """Create a test tenant with bootstrap admin."""
    response = client.post(
        "/v1/tenants",
        json={"name": "Test Tenant", "region": "us-east-1", "admin_email": "admin@test.com"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def admin_headers(tenant):
    """Get headers for admin user."""
    return {
        "X-Tenant-ID": tenant["tenant_id"],
        "X-User-ID": tenant["admin"]["user_id"],
        "X-API-Key": tenant["api_key"],
    }


@pytest.fixture
def admin_key_header():
    """Get platform admin key header."""
    return {"X-Platform-Admin-Key": ADMIN_KEY}


class TestSeeding:
    """Test that default billing data is seeded correctly."""

    def test_default_metered_events_exist(self, client):
        """Verify default metered event types are seeded on startup."""
        db = TestingSessionLocal()
        events = db.query(MeteredEventType).all()
        db.close()

        event_keys = [e.event_key for e in events]
        assert "assistant_query" in event_keys
        assert "tool_invocation" in event_keys
        assert "daily_brief_generated" in event_keys
        assert "notification_enqueued" in event_keys
        assert "kpi_definition_created" in event_keys
        assert "kpi_points_ingested" in event_keys

    def test_default_plans_exist(self, client):
        """Verify default plans are seeded on startup."""
        db = TestingSessionLocal()
        plans = db.query(Plan).all()
        db.close()

        plan_ids = [p.plan_id for p in plans]
        assert "starter" in plan_ids
        assert "growth" in plan_ids
        assert "scale" in plan_ids

    def test_tenant_auto_subscription(self, client, tenant):
        """Verify creating a tenant auto-creates a starter subscription."""
        db = TestingSessionLocal()
        subscription = db.query(TenantSubscription).filter(
            TenantSubscription.tenant_id == tenant["tenant_id"]
        ).first()
        db.close()

        assert subscription is not None
        assert subscription.plan_id == "starter"
        assert subscription.status == "active"


class TestWeightMaterializesConsumption:
    """Test that changing credits_per_unit affects consumption calculations."""

    def test_weight_update_affects_new_usage(self, client, tenant, admin_headers, admin_key_header):
        """Updating credits_per_unit should affect new usage events."""
        # Get initial weight for assistant_query
        db = TestingSessionLocal()
        event = db.query(MeteredEventType).filter(
            MeteredEventType.event_key == "assistant_query"
        ).first()
        original_weight = event.credits_per_unit
        db.close()

        # Update weight to 3.0 via admin API
        response = client.put(
            "/v1/admin/metered-events/assistant_query",
            headers=admin_key_header,
            json={"credits_per_unit": 3.0},
        )
        assert response.status_code == 200

        # Make a chat request
        response = client.post(
            "/v1/cofounder/chat",
            headers=admin_headers,
            json={"message": "help"},
        )
        assert response.status_code == 200

        # Verify usage event has credits=3.0
        db = TestingSessionLocal()
        usage = db.query(UsageEvent).filter(
            UsageEvent.tenant_id == tenant["tenant_id"],
            UsageEvent.activity_type == "assistant_query",
        ).first()
        assert usage is not None
        assert usage.credits == 3.0
        db.close()

        # Update weight to 1.0 and make another request
        client.put(
            "/v1/admin/metered-events/assistant_query",
            headers=admin_key_header,
            json={"credits_per_unit": 1.0},
        )

        response = client.post(
            "/v1/cofounder/chat",
            headers=admin_headers,
            json={"message": "kpis"},
        )
        assert response.status_code == 200

        # Verify second usage event has credits=1.0
        db = TestingSessionLocal()
        usages = db.query(UsageEvent).filter(
            UsageEvent.tenant_id == tenant["tenant_id"],
            UsageEvent.activity_type == "assistant_query",
        ).order_by(UsageEvent.id.desc()).all()
        assert len(usages) >= 2
        assert usages[0].credits == 1.0  # Most recent
        db.close()


class TestCreditsQuotaEnforcement:
    """Test credits-based quota enforcement."""

    def test_credits_quota_exceeded(self, client, tenant, admin_headers, admin_key_header):
        """Test that quota is enforced when credits are exceeded."""
        # Create a tiny plan with only 2 credits
        response = client.post(
            "/v1/admin/plans",
            headers=admin_key_header,
            json={
                "plan_id": "tiny",
                "name": "Tiny",
                "included_credits": 2,
                "overage_price_per_credit": 0.02,
            },
        )
        assert response.status_code == 201

        # Add all capabilities to the tiny plan
        client.put(
            "/v1/admin/plans/tiny/capabilities",
            headers=admin_key_header,
            json={"capabilities": ["chat", "tools", "briefs", "notifications", "kpi_ingest", "kpi_read"]},
        )

        # Assign tenant to tiny plan
        response = client.put(
            f"/v1/admin/tenants/{tenant['tenant_id']}/subscription",
            headers=admin_key_header,
            json={"plan_id": "tiny", "status": "active"},
        )
        assert response.status_code == 200

        # Set assistant_query to 1 credit per unit
        client.put(
            "/v1/admin/metered-events/assistant_query",
            headers=admin_key_header,
            json={"credits_per_unit": 1.0},
        )

        # First chat (1 credit) should succeed
        response = client.post(
            "/v1/cofounder/chat",
            headers=admin_headers,
            json={"message": "help"},
        )
        assert response.status_code == 200

        # Second chat (1 credit) should succeed (total: 2 credits)
        response = client.post(
            "/v1/cofounder/chat",
            headers=admin_headers,
            json={"message": "kpis"},
        )
        assert response.status_code == 200

        # Third chat should fail with 429 (would exceed 2 credits)
        response = client.post(
            "/v1/cofounder/chat",
            headers=admin_headers,
            json={"message": "outbox"},
        )
        assert response.status_code == 429
        assert "quota_exceeded" in response.json()["detail"]["error"]

        # Verify no usage event was created for the failed request
        db = TestingSessionLocal()
        usages = db.query(UsageEvent).filter(
            UsageEvent.tenant_id == tenant["tenant_id"],
            UsageEvent.activity_type == "assistant_query",
        ).all()
        db.close()
        assert len(usages) == 2  # Only 2 successful requests


class TestIdempotencyReplayNoQuota:
    """Test that idempotency replays don't consume quota."""

    def test_idempotent_replay_no_credits(self, client, tenant, admin_headers, admin_key_header):
        """Idempotent replay should return cached response without consuming credits."""
        # Create a plan with limited credits
        client.post(
            "/v1/admin/plans",
            headers=admin_key_header,
            json={"plan_id": "limited", "name": "Limited", "included_credits": 10, "overage_price_per_credit": 0.02},
        )
        client.put(
            "/v1/admin/plans/limited/capabilities",
            headers=admin_key_header,
            json={"capabilities": ["chat", "tools", "briefs", "notifications", "kpi_ingest", "kpi_read"]},
        )
        client.put(
            f"/v1/admin/tenants/{tenant['tenant_id']}/subscription",
            headers=admin_key_header,
            json={"plan_id": "limited", "status": "active"},
        )

        # Set tool_invocation to 2 credits
        client.put(
            "/v1/admin/metered-events/tool_invocation",
            headers=admin_key_header,
            json={"credits_per_unit": 2.0},
        )

        # First invocation with Idempotency-Key
        headers = {**admin_headers, "Idempotency-Key": "test-key-123"}
        response = client.post(
            "/v1/tools/invoke",
            headers=headers,
            json={"tool_name": "echo", "payload": {"msg": "hello"}},
        )
        assert response.status_code == 200
        first_request_id = response.json()["request_id"]

        # Get current usage
        db = TestingSessionLocal()
        rollup = db.query(UsageRollupPeriod).filter(
            UsageRollupPeriod.tenant_id == tenant["tenant_id"],
            UsageRollupPeriod.event_key == "tool_invocation",
        ).first()
        credits_after_first = rollup.credits if rollup else 0
        db.close()

        # Replay with same Idempotency-Key
        response = client.post(
            "/v1/tools/invoke",
            headers=headers,
            json={"tool_name": "echo", "payload": {"msg": "hello"}},
        )
        assert response.status_code == 200
        assert response.json()["request_id"] == first_request_id  # Same response

        # Credits should not have increased
        db = TestingSessionLocal()
        rollup = db.query(UsageRollupPeriod).filter(
            UsageRollupPeriod.tenant_id == tenant["tenant_id"],
            UsageRollupPeriod.event_key == "tool_invocation",
        ).first()
        credits_after_replay = rollup.credits if rollup else 0
        db.close()

        assert credits_after_replay == credits_after_first


class TestPerEventCapEnforcement:
    """Test per-event raw unit caps."""

    def test_event_cap_enforcement(self, client, tenant, admin_headers, admin_key_header):
        """Test that per-event caps are enforced even if credits remain."""
        # Create a plan with high credits but low daily_brief cap
        client.post(
            "/v1/admin/plans",
            headers=admin_key_header,
            json={"plan_id": "capped", "name": "Capped", "included_credits": 1000, "overage_price_per_credit": 0.02},
        )
        client.put(
            "/v1/admin/plans/capped/capabilities",
            headers=admin_key_header,
            json={"capabilities": ["chat", "tools", "briefs", "notifications", "kpi_ingest", "kpi_read"]},
        )
        # Set cap for daily_brief_generated to 1 raw unit
        client.put(
            "/v1/admin/plans/capped/caps",
            headers=admin_key_header,
            json={"caps": [{"event_key": "daily_brief_generated", "period": "monthly", "cap_raw_units": 1}]},
        )
        client.put(
            f"/v1/admin/tenants/{tenant['tenant_id']}/subscription",
            headers=admin_key_header,
            json={"plan_id": "capped", "status": "active"},
        )

        # First brief should succeed
        headers = {**admin_headers, "Idempotency-Key": "brief-1"}
        response = client.post(
            "/v1/briefs/materialize",
            headers=headers,
            json={"date": "2025-01-15", "window_days": 7, "top_n": 3},
        )
        assert response.status_code == 200

        # Second brief (different date) should fail due to cap
        headers = {**admin_headers, "Idempotency-Key": "brief-2"}
        response = client.post(
            "/v1/briefs/materialize",
            headers=headers,
            json={"date": "2025-01-16", "window_days": 7, "top_n": 3},
        )
        assert response.status_code == 429
        assert "quota_exceeded" in response.json()["detail"]["error"]


class TestCapabilityEntitlementEnforcement:
    """Test capability entitlement enforcement."""

    def test_capability_denied(self, client, tenant, admin_headers, admin_key_header):
        """Test that missing capability returns 403."""
        # Create a plan without 'tools' capability
        client.post(
            "/v1/admin/plans",
            headers=admin_key_header,
            json={"plan_id": "no-tools", "name": "No Tools", "included_credits": 1000, "overage_price_per_credit": 0.02},
        )
        # Only include chat, briefs, notifications (NOT tools)
        client.put(
            "/v1/admin/plans/no-tools/capabilities",
            headers=admin_key_header,
            json={"capabilities": ["chat", "briefs", "notifications", "kpi_ingest", "kpi_read"]},
        )
        client.put(
            f"/v1/admin/tenants/{tenant['tenant_id']}/subscription",
            headers=admin_key_header,
            json={"plan_id": "no-tools", "status": "active"},
        )

        # Tools invocation should fail with 403
        headers = {**admin_headers, "Idempotency-Key": "tool-test"}
        response = client.post(
            "/v1/tools/invoke",
            headers=headers,
            json={"tool_name": "echo", "payload": {"msg": "test"}},
        )
        assert response.status_code == 403
        assert "capability_denied" in response.json()["detail"]["error"]


class TestNotificationPartialEnqueue:
    """Test partial notification enqueue based on quota."""

    def test_partial_enqueue_due_to_quota(self, client, tenant, admin_headers, admin_key_header):
        """Test that notifications are partially enqueued when quota is limited."""
        # Create a plan with very limited notification credits
        # notification_enqueued is 0.2 credits per unit
        # With 0.3 included credits, only 1 notification can be sent (0.2 < 0.3 < 0.4)
        client.post(
            "/v1/admin/plans",
            headers=admin_key_header,
            json={"plan_id": "notif-limited", "name": "Notif Limited", "included_credits": 10, "overage_price_per_credit": 0.02},
        )
        client.put(
            "/v1/admin/plans/notif-limited/capabilities",
            headers=admin_key_header,
            json={"capabilities": ["chat", "tools", "briefs", "notifications", "kpi_ingest", "kpi_read"]},
        )
        # Set a cap of 1 notification
        client.put(
            "/v1/admin/plans/notif-limited/caps",
            headers=admin_key_header,
            json={"caps": [{"event_key": "notification_enqueued", "period": "monthly", "cap_raw_units": 1}]},
        )
        client.put(
            f"/v1/admin/tenants/{tenant['tenant_id']}/subscription",
            headers=admin_key_header,
            json={"plan_id": "notif-limited", "status": "active"},
        )

        # Create a second user (admin is auto-created)
        response = client.post(
            "/v1/users",
            headers=admin_headers,
            json={"tenant_id": tenant["tenant_id"], "email": "user2@test.com", "role": "member"},
        )
        assert response.status_code == 201

        # Run daily brief job (should have 2 users to notify)
        headers = {**admin_headers, "Idempotency-Key": "job-1"}
        response = client.post(
            "/v1/jobs/daily-brief",
            headers=headers,
            json={"date": "2025-01-17", "window_days": 7, "top_n": 3},
        )
        assert response.status_code == 200
        result = response.json()

        # Should have inserted 1 notification and suppressed 1
        assert result["notifications_inserted"] == 1
        assert result["notifications_suppressed_due_to_quota"] == 1


class TestBillingAPIEndpoints:
    """Test billing API endpoints."""

    def test_list_metered_events_admin(self, client, admin_key_header):
        """Test admin can list metered events."""
        response = client.get(
            "/v1/admin/metered-events",
            headers=admin_key_header,
        )
        assert response.status_code == 200
        events = response.json()
        assert len(events) >= 6

    def test_list_plans_admin(self, client, admin_key_header):
        """Test admin can list plans."""
        response = client.get(
            "/v1/admin/plans",
            headers=admin_key_header,
        )
        assert response.status_code == 200
        plans = response.json()
        assert len(plans) >= 3

    def test_get_billing_plan_tenant(self, client, tenant, admin_headers):
        """Test tenant can get their billing plan."""
        response = client.get(
            "/v1/billing/plan",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["plan_id"] == "starter"
        assert data["status"] == "active"
        assert "plan" in data
        assert "capabilities" in data

    def test_get_billing_usage_tenant(self, client, tenant, admin_headers):
        """Test tenant can get their billing usage."""
        response = client.get(
            "/v1/billing/usage",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "period_start" in data
        assert "period_end" in data
        assert "plan" in data
        assert "credits" in data
        assert "breakdown" in data

    def test_admin_endpoints_require_key(self, client):
        """Test admin endpoints return 404 without valid key."""
        response = client.get("/v1/admin/metered-events")
        assert response.status_code == 404

        response = client.get(
            "/v1/admin/metered-events",
            headers={"X-Platform-Admin-Key": "wrong-key"},
        )
        assert response.status_code == 404
