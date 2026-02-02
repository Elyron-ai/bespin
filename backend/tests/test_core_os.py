"""Tests for the Core Business OS (Actions, Tasks, Decisions, Meetings, Memory, Timeline, Search)."""
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
    Action,
    Task,
    Decision,
    MeetingNote,
    MemoryFact,
    EvidenceLink,
    TimelineEvent,
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

os.environ["PLATFORM_ADMIN_KEY"] = "test-admin-key"


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
def tenant_a(client):
    """Create test tenant A with bootstrap admin."""
    response = client.post(
        "/v1/tenants",
        json={"name": "Tenant A", "region": "us-east-1", "admin_email": "admin-a@test.com"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def tenant_b(client):
    """Create test tenant B with bootstrap admin."""
    response = client.post(
        "/v1/tenants",
        json={"name": "Tenant B", "region": "us-east-1", "admin_email": "admin-b@test.com"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def admin_a_headers(tenant_a):
    """Get headers for tenant A admin user."""
    return {
        "X-Tenant-ID": tenant_a["tenant_id"],
        "X-User-ID": tenant_a["admin"]["user_id"],
        "X-API-Key": tenant_a["api_key"],
    }


@pytest.fixture
def admin_b_headers(tenant_b):
    """Get headers for tenant B admin user."""
    return {
        "X-Tenant-ID": tenant_b["tenant_id"],
        "X-User-ID": tenant_b["admin"]["user_id"],
        "X-API-Key": tenant_b["api_key"],
    }


@pytest.fixture
def member_a(client, tenant_a, admin_a_headers):
    """Create a member user for tenant A."""
    response = client.post(
        "/v1/users",
        json={
            "tenant_id": tenant_a["tenant_id"],
            "email": "member-a@test.com",
            "role": "member",
        },
        headers=admin_a_headers,
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def member_a_headers(tenant_a, member_a):
    """Get headers for tenant A member user."""
    return {
        "X-Tenant-ID": tenant_a["tenant_id"],
        "X-User-ID": member_a["user_id"],
        "X-API-Key": tenant_a["api_key"],
    }


# =============================================================================
# Tenant Isolation Tests
# =============================================================================

class TestTenantIsolation:
    """Test that tenant data is properly isolated."""

    def test_tenant_b_cannot_see_tenant_a_action(self, client, admin_a_headers, admin_b_headers):
        """Tenant B should not be able to access Tenant A's action."""
        # Tenant A creates an action
        response = client.post(
            "/v1/actions",
            json={"title": "Tenant A Action", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        assert response.status_code == 201
        action_id = response.json()["action_id"]

        # Tenant B tries to access it
        response = client.get(f"/v1/actions/{action_id}", headers=admin_b_headers)
        assert response.status_code == 404

    def test_tenant_b_cannot_see_tenant_a_task(self, client, admin_a_headers, admin_b_headers):
        """Tenant B should not be able to access Tenant A's task."""
        # Tenant A creates a task
        response = client.post(
            "/v1/tasks",
            json={"title": "Tenant A Task", "priority": "medium"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201
        task_id = response.json()["task_id"]

        # Tenant B tries to access it
        response = client.get(f"/v1/tasks/{task_id}", headers=admin_b_headers)
        assert response.status_code == 404

    def test_tenant_b_cannot_see_tenant_a_memory_fact(self, client, admin_a_headers, admin_b_headers):
        """Tenant B should not be able to access Tenant A's memory fact."""
        # Tenant A creates a memory fact
        response = client.post(
            "/v1/memory/facts",
            json={"category": "icp", "fact_key": "ICP.primary", "fact_value": "Enterprise customers"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201
        fact_id = response.json()["fact_id"]

        # Tenant B tries to access it
        response = client.get(f"/v1/memory/facts/{fact_id}", headers=admin_b_headers)
        assert response.status_code == 404

    def test_tenant_b_cannot_attach_evidence_to_tenant_a_task(
        self, client, admin_a_headers, admin_b_headers
    ):
        """Tenant B should not be able to attach evidence to Tenant A's task."""
        # Tenant A creates a task
        response = client.post(
            "/v1/tasks",
            json={"title": "Tenant A Task", "priority": "medium"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201
        task_id = response.json()["task_id"]

        # Tenant B tries to attach evidence
        response = client.post(
            "/v1/evidence",
            json={
                "entity_type": "task",
                "entity_id": task_id,
                "source_type": "manual",
                "source_ref": {"note": "test"},
            },
            headers=admin_b_headers,
        )
        assert response.status_code == 404


# =============================================================================
# RBAC Tests
# =============================================================================

class TestRBAC:
    """Test role-based access control rules."""

    def test_member_can_create_action(self, client, member_a_headers):
        """Member should be able to create (propose) an action."""
        response = client.post(
            "/v1/actions",
            json={"title": "Member Action", "action_type": "general", "payload": {}},
            headers=member_a_headers,
        )
        assert response.status_code == 201
        assert response.json()["status"] == "proposed"

    def test_member_cannot_approve_action(self, client, admin_a_headers, member_a_headers):
        """Member should not be able to approve an action."""
        # Create action as admin
        response = client.post(
            "/v1/actions",
            json={"title": "Test Action", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Try to approve as member
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={},
            headers=member_a_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_execute_action(self, client, admin_a_headers, member_a_headers):
        """Member should not be able to execute an action."""
        # Create and approve action as admin
        response = client.post(
            "/v1/actions",
            json={"title": "Test Action", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Try to execute as member
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {}},
            headers=member_a_headers,
        )
        assert response.status_code == 403

    def test_member_can_create_task(self, client, member_a_headers):
        """Member should be able to create a task."""
        response = client.post(
            "/v1/tasks",
            json={"title": "Member Task", "priority": "medium"},
            headers=member_a_headers,
        )
        assert response.status_code == 201

    def test_member_cannot_create_decision(self, client, member_a_headers):
        """Member should not be able to create a decision (admin only)."""
        response = client.post(
            "/v1/decisions",
            json={
                "decision_date": "2024-01-15",
                "title": "Test Decision",
                "decision": "We will do X",
            },
            headers=member_a_headers,
        )
        assert response.status_code == 403

    def test_member_can_read_decision(self, client, admin_a_headers, member_a_headers):
        """Member should be able to read decisions."""
        # Create as admin
        response = client.post(
            "/v1/decisions",
            json={
                "decision_date": "2024-01-15",
                "title": "Test Decision",
                "decision": "We will do X",
            },
            headers=admin_a_headers,
        )
        decision_id = response.json()["decision_id"]

        # Read as member
        response = client.get(f"/v1/decisions/{decision_id}", headers=member_a_headers)
        assert response.status_code == 200

    def test_member_cannot_create_memory_fact(self, client, member_a_headers):
        """Member should not be able to create a memory fact (admin only)."""
        response = client.post(
            "/v1/memory/facts",
            json={"category": "icp", "fact_key": "ICP.test", "fact_value": "Test value"},
            headers=member_a_headers,
        )
        assert response.status_code == 403

    def test_member_can_read_memory_fact(self, client, admin_a_headers, member_a_headers):
        """Member should be able to read memory facts."""
        # Create as admin
        response = client.post(
            "/v1/memory/facts",
            json={"category": "icp", "fact_key": "ICP.test", "fact_value": "Test value"},
            headers=admin_a_headers,
        )
        fact_id = response.json()["fact_id"]

        # Read as member
        response = client.get(f"/v1/memory/facts/{fact_id}", headers=member_a_headers)
        assert response.status_code == 200


# =============================================================================
# Metering Tests
# =============================================================================

class TestMetering:
    """Test that operations are metered correctly."""

    def test_action_created_metered(self, client, admin_a_headers, tenant_a):
        """Creating an action should emit action_created usage."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Metered Action", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        assert response.status_code == 201

        # Check billing usage
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        assert response.status_code == 200
        breakdown = response.json()["breakdown"]

        action_created = next((b for b in breakdown if b["event_key"] == "action_created"), None)
        assert action_created is not None
        assert action_created["raw_units"] == 1
        assert action_created["credits"] == 0.2  # 1 * 0.2 credits_per_unit

    def test_action_approved_metered(self, client, admin_a_headers):
        """Approving an action should emit action_approved usage."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Approve action
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Check billing usage
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]

        action_approved = next((b for b in breakdown if b["event_key"] == "action_approved"), None)
        assert action_approved is not None
        assert action_approved["raw_units"] == 1
        assert action_approved["credits"] == 0.2

    def test_search_query_metered(self, client, admin_a_headers):
        """Search queries should emit search_query usage."""
        # Perform search
        response = client.get("/v1/search?q=test", headers=admin_a_headers)
        assert response.status_code == 200

        # Check billing usage
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]

        search_query = next((b for b in breakdown if b["event_key"] == "search_query"), None)
        assert search_query is not None
        assert search_query["raw_units"] == 1
        assert search_query["credits"] == 0.05

    def test_task_created_metered(self, client, admin_a_headers):
        """Creating a task should emit task_created usage."""
        # Create task
        response = client.post(
            "/v1/tasks",
            json={"title": "Metered Task", "priority": "high"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201

        # Check billing usage
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]

        task_created = next((b for b in breakdown if b["event_key"] == "task_created"), None)
        assert task_created is not None
        assert task_created["raw_units"] == 1


# =============================================================================
# Timeline Tests
# =============================================================================

class TestTimeline:
    """Test that timeline events are logged correctly."""

    def test_action_created_logged_to_timeline(self, client, admin_a_headers, tenant_a):
        """Creating an action should log a timeline event."""
        response = client.post(
            "/v1/actions",
            json={"title": "Timeline Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Check timeline
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id}",
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        events = response.json()["items"]
        assert len(events) >= 1

        event = next((e for e in events if e["event_type"] == "action_created"), None)
        assert event is not None
        assert "Action proposed" in event["summary"]

    def test_action_approved_logged_to_timeline(self, client, admin_a_headers):
        """Approving an action should log a timeline event."""
        response = client.post(
            "/v1/actions",
            json={"title": "Approve Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Approve
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Check timeline
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id}",
            headers=admin_a_headers,
        )
        events = response.json()["items"]

        approved_event = next((e for e in events if e["event_type"] == "action_approved"), None)
        assert approved_event is not None

    def test_task_completed_logged_to_timeline(self, client, admin_a_headers):
        """Completing a task should log a timeline event."""
        # Create task
        response = client.post(
            "/v1/tasks",
            json={"title": "Complete Test", "priority": "medium"},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Complete
        client.post(f"/v1/tasks/{task_id}/complete", headers=admin_a_headers)

        # Check timeline
        response = client.get(
            f"/v1/timeline?entity_type=task&entity_id={task_id}",
            headers=admin_a_headers,
        )
        events = response.json()["items"]

        completed_event = next((e for e in events if e["event_type"] == "task_completed"), None)
        assert completed_event is not None


# =============================================================================
# Evidence Links Tests
# =============================================================================

class TestEvidenceLinks:
    """Test evidence linking functionality."""

    def test_create_evidence_link_for_action(self, client, admin_a_headers):
        """Should be able to attach evidence to an action."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Evidence Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Create evidence link
        response = client.post(
            "/v1/evidence",
            json={
                "entity_type": "action",
                "entity_id": action_id,
                "source_type": "kpi",
                "source_ref": {"table": "kpi_points", "id": "123", "field": "value"},
                "snippet": "KPI showed 50% increase",
            },
            headers=admin_a_headers,
        )
        assert response.status_code == 201
        assert response.json()["entity_id"] == action_id

    def test_list_evidence_for_entity(self, client, admin_a_headers):
        """Should be able to list evidence for a specific entity."""
        # Create task
        response = client.post(
            "/v1/tasks",
            json={"title": "Evidence List Test", "priority": "medium"},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Create two evidence links
        for i in range(2):
            client.post(
                "/v1/evidence",
                json={
                    "entity_type": "task",
                    "entity_id": task_id,
                    "source_type": "manual",
                    "source_ref": {"note": f"Evidence {i}"},
                },
                headers=admin_a_headers,
            )

        # List evidence
        response = client.get(
            f"/v1/evidence?entity_type=task&entity_id={task_id}",
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_evidence_included_in_record_explorer(self, client, admin_a_headers):
        """Record explorer should include evidence links."""
        # Create action with evidence
        response = client.post(
            "/v1/actions",
            json={"title": "Explorer Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        client.post(
            "/v1/evidence",
            json={
                "entity_type": "action",
                "entity_id": action_id,
                "source_type": "brief",
                "source_ref": {"brief_id": "abc123"},
            },
            headers=admin_a_headers,
        )

        # Get via record explorer
        response = client.get(f"/v1/records/action/{action_id}", headers=admin_a_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["evidence"]) == 1
        assert data["evidence"][0]["source_type"] == "brief"


# =============================================================================
# Search Tests
# =============================================================================

class TestGlobalSearch:
    """Test global search functionality."""

    def test_search_finds_action_by_title(self, client, admin_a_headers):
        """Search should find actions by title."""
        client.post(
            "/v1/actions",
            json={"title": "Unique Alpha Action", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )

        response = client.get("/v1/search?q=Alpha", headers=admin_a_headers)
        assert response.status_code == 200
        results = response.json()["results"]
        assert any(r["entity_type"] == "action" and "Alpha" in r["title"] for r in results)

    def test_search_finds_memory_fact_by_value(self, client, admin_a_headers):
        """Search should find memory facts by value."""
        client.post(
            "/v1/memory/facts",
            json={"category": "icp", "fact_key": "test.key", "fact_value": "Special unique content beta"},
            headers=admin_a_headers,
        )

        response = client.get("/v1/search?q=beta", headers=admin_a_headers)
        results = response.json()["results"]
        assert any(r["entity_type"] == "memory_fact" for r in results)

    def test_search_is_tenant_scoped(self, client, admin_a_headers, admin_b_headers):
        """Search should only return results from the requesting tenant."""
        # Tenant A creates action
        client.post(
            "/v1/actions",
            json={"title": "Gamma Secret Action", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )

        # Tenant B searches
        response = client.get("/v1/search?q=Gamma", headers=admin_b_headers)
        results = response.json()["results"]
        assert len(results) == 0


# =============================================================================
# Full Workflow Tests
# =============================================================================

class TestFullWorkflows:
    """Test complete workflows through the system."""

    def test_action_full_lifecycle(self, client, admin_a_headers):
        """Test action from creation through execution."""
        # Create
        response = client.post(
            "/v1/actions",
            json={"title": "Lifecycle Test", "action_type": "create_task", "payload": {"task_name": "New Task"}},
            headers=admin_a_headers,
        )
        assert response.status_code == 201
        action = response.json()
        assert action["status"] == "proposed"

        # Approve
        response = client.post(
            f"/v1/actions/{action['action_id']}/approve",
            json={"comment": "Looks good"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        # Execute
        response = client.post(
            f"/v1/actions/{action['action_id']}/execute",
            json={"execution_status": "succeeded", "result": {"message": "Task created"}},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "executed"

        # Verify timeline has all events
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action['action_id']}",
            headers=admin_a_headers,
        )
        events = response.json()["items"]
        event_types = [e["event_type"] for e in events]
        assert "action_created" in event_types
        assert "action_approved" in event_types
        assert "action_executed" in event_types

    def test_memory_fact_supersede_workflow(self, client, admin_a_headers):
        """Test superseding a memory fact."""
        # Create original fact
        response = client.post(
            "/v1/memory/facts",
            json={"category": "pricing", "fact_key": "base.price", "fact_value": "$100/month"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201
        original_id = response.json()["fact_id"]

        # Supersede with new value
        response = client.post(
            f"/v1/memory/facts/{original_id}/supersede",
            json={"fact_value": "$150/month"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        new_fact = response.json()
        assert new_fact["fact_value"] == "$150/month"
        assert new_fact["supersedes_fact_id"] == original_id

        # Original should be superseded
        response = client.get(f"/v1/memory/facts/{original_id}", headers=admin_a_headers)
        assert response.json()["status"] == "superseded"

        # Only active fact should appear in default list
        response = client.get("/v1/memory/facts?status=active", headers=admin_a_headers)
        facts = response.json()["items"]
        base_price_facts = [f for f in facts if f["fact_key"] == "base.price"]
        assert len(base_price_facts) == 1
        assert base_price_facts[0]["fact_value"] == "$150/month"
