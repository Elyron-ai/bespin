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


@pytest.fixture
def member_a2(client, tenant_a, admin_a_headers):
    """Create a second member user for tenant A."""
    response = client.post(
        "/v1/users",
        json={
            "tenant_id": tenant_a["tenant_id"],
            "email": "member-a2@test.com",
            "role": "member",
        },
        headers=admin_a_headers,
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def member_a2_headers(tenant_a, member_a2):
    """Get headers for tenant A second member user."""
    return {
        "X-Tenant-ID": tenant_a["tenant_id"],
        "X-User-ID": member_a2["user_id"],
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
        # Execute returns {action: {...}, execution: {...}}
        assert response.json()["action"]["status"] == "executed"
        assert response.json()["execution"]["execution_status"] == "succeeded"

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


# =============================================================================
# Actions v0 Tests (Phase 1, Task 8a)
# =============================================================================

class TestActionsV0Create:
    """Test action creation (Phase 1 Task 8a)."""

    def test_member_creates_action(self, client, member_a_headers):
        """Member can create an action. Status defaults to proposed."""
        response = client.post(
            "/v1/actions",
            json={"title": "Test Action", "action_type": "general", "payload": {"key": "value"}},
            headers=member_a_headers,
        )
        assert response.status_code == 201
        action = response.json()
        assert action["status"] == "proposed"
        assert "action_id" in action
        assert action["title"] == "Test Action"
        assert action["action_type"] == "general"
        assert action["payload"] == {"key": "value"}

    def test_action_with_source_options(self, client, admin_a_headers):
        """Action can specify source (user, agent, system)."""
        for source in ["user", "agent", "system"]:
            response = client.post(
                "/v1/actions",
                json={
                    "title": f"Action from {source}",
                    "action_type": "general",
                    "source": source,
                    "source_ref": f"ref-{source}",
                },
                headers=admin_a_headers,
            )
            assert response.status_code == 201
            assert response.json()["source"] == source
            assert response.json()["source_ref"] == f"ref-{source}"


class TestActionsV0TenantIsolation:
    """Test tenant isolation for actions (Phase 1 Task 8a)."""

    def test_cross_tenant_access_returns_404(self, client, admin_a_headers, admin_b_headers):
        """Accessing another tenant's action returns 404 (not 403)."""
        # Create action in tenant A
        response = client.post(
            "/v1/actions",
            json={"title": "Tenant A Secret", "action_type": "confidential"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201
        action_id = response.json()["action_id"]

        # Tenant B tries to GET the action
        response = client.get(f"/v1/actions/{action_id}", headers=admin_b_headers)
        assert response.status_code == 404

    def test_cross_tenant_cancel_returns_404(self, client, admin_a_headers, admin_b_headers):
        """Attempting to cancel another tenant's action returns 404."""
        # Create action in tenant A
        response = client.post(
            "/v1/actions",
            json={"title": "Tenant A Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Tenant B tries to cancel
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=admin_b_headers,
        )
        assert response.status_code == 404

    def test_cross_tenant_list_is_empty(self, client, admin_a_headers, admin_b_headers):
        """Listing actions from another tenant shows nothing."""
        # Create action in tenant A
        client.post(
            "/v1/actions",
            json={"title": "Tenant A Only", "action_type": "general"},
            headers=admin_a_headers,
        )

        # Tenant B lists actions
        response = client.get("/v1/actions?status=all", headers=admin_b_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 0


class TestActionsV0ListFilters:
    """Test action listing with filters (Phase 1 Task 8a)."""

    def test_list_status_filter_proposed(self, client, admin_a_headers):
        """Default status filter is 'proposed'."""
        # Create an action
        client.post(
            "/v1/actions",
            json={"title": "Proposed Action", "action_type": "general"},
            headers=admin_a_headers,
        )

        # List with default (proposed)
        response = client.get("/v1/actions", headers=admin_a_headers)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert all(a["status"] == "proposed" for a in items)

    def test_list_status_filter_cancelled(self, client, admin_a_headers):
        """Can filter by status=cancelled."""
        # Create and cancel an action
        response = client.post(
            "/v1/actions",
            json={"title": "To Cancel", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/cancel", json={}, headers=admin_a_headers)

        # Create another that stays proposed
        client.post(
            "/v1/actions",
            json={"title": "Stay Proposed", "action_type": "general"},
            headers=admin_a_headers,
        )

        # List cancelled only
        response = client.get("/v1/actions?status=cancelled", headers=admin_a_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["title"] == "To Cancel"
        assert items[0]["status"] == "cancelled"

    def test_list_status_filter_all(self, client, admin_a_headers):
        """Can list all actions with status=all."""
        # Create two actions
        response = client.post(
            "/v1/actions",
            json={"title": "Action 1", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        client.post(
            "/v1/actions",
            json={"title": "Action 2", "action_type": "general"},
            headers=admin_a_headers,
        )

        # Cancel the first
        client.post(f"/v1/actions/{action_id}/cancel", json={}, headers=admin_a_headers)

        # List all
        response = client.get("/v1/actions?status=all", headers=admin_a_headers)
        items = response.json()["items"]
        assert len(items) == 2

    def test_list_created_by_filter(self, client, admin_a_headers, member_a_headers, member_a):
        """Can filter by created_by_user_id."""
        # Admin creates an action
        client.post(
            "/v1/actions",
            json={"title": "Admin Action", "action_type": "general"},
            headers=admin_a_headers,
        )

        # Member creates an action
        client.post(
            "/v1/actions",
            json={"title": "Member Action", "action_type": "general"},
            headers=member_a_headers,
        )

        # Filter by member's ID
        response = client.get(
            f"/v1/actions?status=all&created_by_user_id={member_a['user_id']}",
            headers=admin_a_headers,
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Member Action"

    def test_list_assigned_to_filter(self, client, admin_a_headers, member_a):
        """Can filter by assigned_to_user_id."""
        # Create unassigned action
        client.post(
            "/v1/actions",
            json={"title": "Unassigned", "action_type": "general"},
            headers=admin_a_headers,
        )

        # Create assigned action
        client.post(
            "/v1/actions",
            json={
                "title": "Assigned to Member",
                "action_type": "general",
                "assigned_to_user_id": member_a["user_id"],
            },
            headers=admin_a_headers,
        )

        # Filter by assignee
        response = client.get(
            f"/v1/actions?status=all&assigned_to_user_id={member_a['user_id']}",
            headers=admin_a_headers,
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Assigned to Member"


class TestActionsV0CancelRBAC:
    """Test cancel RBAC rules (Phase 1 Task 8a)."""

    def test_member_can_cancel_own_proposed_action(self, client, member_a_headers):
        """Member can cancel their own proposed action."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "My Action", "action_type": "general"},
            headers=member_a_headers,
        )
        action_id = response.json()["action_id"]

        # Cancel it
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={"comment": "Changed my mind"},
            headers=member_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_member_cannot_cancel_others_action(self, client, admin_a_headers, member_a_headers):
        """Member cannot cancel someone else's action (403)."""
        # Admin creates action
        response = client.post(
            "/v1/actions",
            json={"title": "Admin's Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Member tries to cancel
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=member_a_headers,
        )
        assert response.status_code == 403
        assert "Not authorized" in response.json()["detail"]

    def test_member_cannot_cancel_other_members_action(
        self, client, member_a_headers, member_a2_headers
    ):
        """One member cannot cancel another member's action (403)."""
        # First member creates action
        response = client.post(
            "/v1/actions",
            json={"title": "Member 1's Action", "action_type": "general"},
            headers=member_a_headers,
        )
        action_id = response.json()["action_id"]

        # Second member tries to cancel
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=member_a2_headers,
        )
        assert response.status_code == 403

    def test_admin_can_cancel_any_proposed_action(self, client, admin_a_headers, member_a_headers):
        """Admin can cancel any proposed action in the tenant."""
        # Member creates action
        response = client.post(
            "/v1/actions",
            json={"title": "Member's Action", "action_type": "general"},
            headers=member_a_headers,
        )
        action_id = response.json()["action_id"]

        # Admin cancels it
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cannot_cancel_non_proposed_action(self, client, admin_a_headers):
        """Cannot cancel an action that is not in proposed status."""
        # Create and approve action
        response = client.post(
            "/v1/actions",
            json={"title": "Approved Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Try to cancel
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 400
        assert "proposed" in response.json()["detail"].lower()


class TestActionsV0Metering:
    """Test metering for action operations (Phase 1 Task 8a)."""

    def test_action_created_metered(self, client, admin_a_headers):
        """Creating an action emits action_created usage."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Metered Create", "action_type": "general"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201

        # Check usage
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        action_created = next((b for b in breakdown if b["event_key"] == "action_created"), None)
        assert action_created is not None
        assert action_created["raw_units"] >= 1
        assert action_created["credits"] == action_created["raw_units"] * 0.2

    def test_action_cancel_metered_as_updated(self, client, admin_a_headers):
        """Cancelling an action emits action_updated usage."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "To Cancel", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Get baseline usage
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        updated_before = next(
            (b for b in breakdown if b["event_key"] == "action_updated"),
            {"raw_units": 0, "credits": 0}
        )

        # Cancel action
        client.post(f"/v1/actions/{action_id}/cancel", json={}, headers=admin_a_headers)

        # Check usage increased
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        updated_after = next((b for b in breakdown if b["event_key"] == "action_updated"), None)
        assert updated_after is not None
        assert updated_after["raw_units"] == updated_before["raw_units"] + 1


class TestActionsV0QuotaEnforcement:
    """Test quota enforcement for actions (Phase 1 Task 8a)."""

    def test_quota_exceeded_returns_429(self, client, tenant_a, admin_a_headers):
        """When quota exceeded, returns 429 and no row created."""
        # Set up a plan with cap of 1 action_created per month
        # Use platform admin to add an event cap
        platform_headers = {"X-Platform-Admin-Key": "test-admin-key"}

        # Create a test plan with a cap
        response = client.post(
            "/v1/admin/plans",
            json={
                "plan_id": "test_action_limited",
                "name": "Action Limited",
                "included_credits": 1000,
                "overage_price_per_credit": 0.02,
            },
            headers=platform_headers,
        )
        # May already exist, that's fine
        assert response.status_code in [200, 201, 409]

        # Add all capabilities (required for action_center access)
        client.put(
            "/v1/admin/plans/test_action_limited/capabilities",
            json={"capabilities": ["action_center"]},
            headers=platform_headers,
        )

        # Add event cap of 1 for action_created
        client.put(
            "/v1/admin/plans/test_action_limited/caps",
            json={
                "caps": [
                    {"event_key": "action_created", "period": "monthly", "cap_raw_units": 1}
                ]
            },
            headers=platform_headers,
        )

        # Assign the limited plan to the tenant
        client.put(
            f"/v1/admin/tenants/{tenant_a['tenant_id']}/subscription",
            json={"plan_id": "test_action_limited", "status": "active"},
            headers=platform_headers,
        )

        # First action should succeed
        response = client.post(
            "/v1/actions",
            json={"title": "First Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201

        # Second action should fail with 429
        response = client.post(
            "/v1/actions",
            json={"title": "Second Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        assert response.status_code == 429
        # Response can be structured dict or string - just verify it contains quota-related info
        detail = response.json().get("detail", "")
        if isinstance(detail, dict):
            # Structured quota error response
            assert "event_key" in detail or "cap" in detail or "limit" in detail
        else:
            assert "quota" in str(detail).lower() or "exceeded" in str(detail).lower()

        # Verify only one action exists
        response = client.get("/v1/actions?status=all", headers=admin_a_headers)
        assert response.json()["total"] == 1

    def test_quota_failure_does_not_emit_usage(self, client, tenant_a, admin_a_headers):
        """When quota fails, no usage is emitted."""
        platform_headers = {"X-Platform-Admin-Key": "test-admin-key"}

        # Create a plan with cap of 0 for action_created (immediate failure)
        response = client.post(
            "/v1/admin/plans",
            json={
                "plan_id": "test_no_actions",
                "name": "No Actions Plan",
                "included_credits": 1000,
                "overage_price_per_credit": 0.02,
            },
            headers=platform_headers,
        )
        assert response.status_code in [200, 201, 409]

        # Add capabilities
        client.put(
            "/v1/admin/plans/test_no_actions/capabilities",
            json={"capabilities": ["action_center"]},
            headers=platform_headers,
        )

        # Add event cap of 0
        client.put(
            "/v1/admin/plans/test_no_actions/caps",
            json={
                "caps": [
                    {"event_key": "action_created", "period": "monthly", "cap_raw_units": 0}
                ]
            },
            headers=platform_headers,
        )

        # Assign plan
        client.put(
            f"/v1/admin/tenants/{tenant_a['tenant_id']}/subscription",
            json={"plan_id": "test_no_actions", "status": "active"},
            headers=platform_headers,
        )

        # Get baseline usage
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        usage_before = sum(b.get("raw_units", 0) for b in response.json()["breakdown"])

        # Try to create action (should fail)
        response = client.post(
            "/v1/actions",
            json={"title": "Should Fail", "action_type": "general"},
            headers=admin_a_headers,
        )
        assert response.status_code == 429

        # Usage should not have increased for action_created
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        action_created = next(
            (b for b in response.json()["breakdown"] if b["event_key"] == "action_created"),
            None
        )
        assert action_created is None or action_created["raw_units"] == 0


class TestActionsV0CancelIdempotency:
    """Test cancel idempotency (Phase 1 Task 8a)."""

    def test_cancel_idempotent(self, client, admin_a_headers):
        """Cancelling an already cancelled action returns 200 without emitting usage."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Cancel Twice", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # First cancel
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

        # Get usage after first cancel
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        updated_after_first = next(
            (b for b in breakdown if b["event_key"] == "action_updated"),
            {"raw_units": 0}
        )

        # Second cancel (idempotent)
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

        # Usage should NOT have incremented
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        updated_after_second = next(
            (b for b in breakdown if b["event_key"] == "action_updated"),
            {"raw_units": 0}
        )
        assert updated_after_second["raw_units"] == updated_after_first["raw_units"]


# =============================================================================
# Actions Approvals v0 Tests (Phase 1, Task 8b)
# =============================================================================

class TestActionsApprovalsV0AdminApprove:
    """Test admin approve flow (Phase 1 Task 8b)."""

    def test_admin_approve_flow(self, client, admin_a_headers, member_a_headers):
        """Admin can approve a proposed action created by member."""
        # Member creates action
        response = client.post(
            "/v1/actions",
            json={"title": "Member's Proposal", "action_type": "general", "payload": {}},
            headers=member_a_headers,
        )
        assert response.status_code == 201
        action_id = response.json()["action_id"]
        assert response.json()["status"] == "proposed"

        # Admin approves
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={"comment": "Looks good!"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        # Verify action_reviews has exactly 1 row for this action with decision "approved"
        db = TestingSessionLocal()
        from app.gateway.models import ActionReview
        reviews = db.query(ActionReview).filter(
            ActionReview.action_id == action_id
        ).all()
        assert len(reviews) == 1
        assert reviews[0].decision == "approved"
        assert reviews[0].comment == "Looks good!"
        db.close()

        # Verify timeline has exactly 1 action_approved event
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id}",
            headers=admin_a_headers,
        )
        events = response.json()["items"]
        approved_events = [e for e in events if e["event_type"] == "action_approved"]
        assert len(approved_events) == 1
        assert "approved" in approved_events[0]["metadata"]["decision"]

        # Verify billing usage includes action_approved
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        action_approved = next((b for b in breakdown if b["event_key"] == "action_approved"), None)
        assert action_approved is not None
        assert action_approved["raw_units"] >= 1


class TestActionsApprovalsV0AdminReject:
    """Test admin reject flow (Phase 1 Task 8b)."""

    def test_admin_reject_flow(self, client, admin_a_headers, member_a_headers):
        """Admin can reject a proposed action."""
        # Member creates action
        response = client.post(
            "/v1/actions",
            json={"title": "Questionable Proposal", "action_type": "general", "payload": {}},
            headers=member_a_headers,
        )
        assert response.status_code == 201
        action_id = response.json()["action_id"]

        # Admin rejects
        response = client.post(
            f"/v1/actions/{action_id}/reject",
            json={"comment": "Not aligned with goals"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"

        # Verify action_reviews has exactly 1 row with decision "rejected"
        db = TestingSessionLocal()
        from app.gateway.models import ActionReview
        reviews = db.query(ActionReview).filter(
            ActionReview.action_id == action_id
        ).all()
        assert len(reviews) == 1
        assert reviews[0].decision == "rejected"
        assert reviews[0].comment == "Not aligned with goals"
        db.close()

        # Verify timeline has action_rejected event
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id}",
            headers=admin_a_headers,
        )
        events = response.json()["items"]
        rejected_events = [e for e in events if e["event_type"] == "action_rejected"]
        assert len(rejected_events) == 1

        # Verify billing usage includes action_rejected
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        action_rejected = next((b for b in breakdown if b["event_key"] == "action_rejected"), None)
        assert action_rejected is not None
        assert action_rejected["raw_units"] >= 1


class TestActionsApprovalsV0RBAC:
    """Test RBAC rules for approve/reject (Phase 1 Task 8b)."""

    def test_member_cannot_approve(self, client, admin_a_headers, member_a_headers):
        """Member should not be able to approve an action."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Member tries to approve
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={},
            headers=member_a_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_reject(self, client, admin_a_headers, member_a_headers):
        """Member should not be able to reject an action."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Member tries to reject
        response = client.post(
            f"/v1/actions/{action_id}/reject",
            json={},
            headers=member_a_headers,
        )
        assert response.status_code == 403


class TestActionsApprovalsV0TenantIsolation:
    """Test tenant isolation for approve/reject (Phase 1 Task 8b)."""

    def test_cross_tenant_approve_returns_404(self, client, admin_a_headers, admin_b_headers):
        """Tenant B admin cannot approve Tenant A's action (returns 404)."""
        # Create action in tenant A
        response = client.post(
            "/v1/actions",
            json={"title": "Tenant A Secret", "action_type": "confidential"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Tenant B admin tries to approve
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={},
            headers=admin_b_headers,
        )
        assert response.status_code == 404

    def test_cross_tenant_reject_returns_404(self, client, admin_a_headers, admin_b_headers):
        """Tenant B admin cannot reject Tenant A's action (returns 404)."""
        # Create action in tenant A
        response = client.post(
            "/v1/actions",
            json={"title": "Tenant A Secret", "action_type": "confidential"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Tenant B admin tries to reject
        response = client.post(
            f"/v1/actions/{action_id}/reject",
            json={},
            headers=admin_b_headers,
        )
        assert response.status_code == 404


class TestActionsApprovalsV0Idempotency:
    """Test idempotent retry behavior (Phase 1 Task 8b)."""

    def test_approve_idempotent(self, client, admin_a_headers):
        """Approving an already approved action returns 200 without additional writes."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Idempotent Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # First approve
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={"comment": "First approval"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        # Get usage after first approve
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        approved_after_first = next(
            (b for b in breakdown if b["event_key"] == "action_approved"),
            {"raw_units": 0}
        )

        # Get review count after first approve
        db = TestingSessionLocal()
        from app.gateway.models import ActionReview
        reviews_count_1 = db.query(ActionReview).filter(ActionReview.action_id == action_id).count()
        db.close()

        # Second approve (idempotent)
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={"comment": "Second approval attempt"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        # Usage should NOT have incremented
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        approved_after_second = next(
            (b for b in breakdown if b["event_key"] == "action_approved"),
            {"raw_units": 0}
        )
        assert approved_after_second["raw_units"] == approved_after_first["raw_units"]

        # Review count should NOT have incremented
        db = TestingSessionLocal()
        reviews_count_2 = db.query(ActionReview).filter(ActionReview.action_id == action_id).count()
        db.close()
        assert reviews_count_2 == reviews_count_1

    def test_reject_idempotent(self, client, admin_a_headers):
        """Rejecting an already rejected action returns 200 without additional writes."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Reject Idempotent Test", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # First reject
        response = client.post(
            f"/v1/actions/{action_id}/reject",
            json={"comment": "First rejection"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"

        # Get usage after first reject
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        rejected_after_first = next(
            (b for b in breakdown if b["event_key"] == "action_rejected"),
            {"raw_units": 0}
        )

        # Second reject (idempotent)
        response = client.post(
            f"/v1/actions/{action_id}/reject",
            json={"comment": "Second rejection attempt"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"

        # Usage should NOT have incremented
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        rejected_after_second = next(
            (b for b in breakdown if b["event_key"] == "action_rejected"),
            {"raw_units": 0}
        )
        assert rejected_after_second["raw_units"] == rejected_after_first["raw_units"]


class TestActionsApprovalsV0ConflictTransitions:
    """Test conflict transition returns 409 (Phase 1 Task 8b)."""

    def test_approve_then_reject_returns_409(self, client, admin_a_headers):
        """After approving, trying to reject returns 409 Conflict."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Approve Then Reject", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Approve
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 200

        # Try to reject -> 409
        response = client.post(
            f"/v1/actions/{action_id}/reject",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 409
        assert "approved" in response.json()["detail"].lower()

    def test_reject_then_approve_returns_409(self, client, admin_a_headers):
        """After rejecting, trying to approve returns 409 Conflict."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "Reject Then Approve", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Reject
        response = client.post(
            f"/v1/actions/{action_id}/reject",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 200

        # Try to approve -> 409
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 409
        assert "rejected" in response.json()["detail"].lower()

    def test_cancelled_action_cannot_be_approved(self, client, admin_a_headers):
        """A cancelled action cannot be approved (returns 409)."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "To Cancel", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Cancel
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 200

        # Try to approve -> 409
        response = client.post(
            f"/v1/actions/{action_id}/approve",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 409
        assert "cancelled" in response.json()["detail"].lower()

    def test_cancelled_action_cannot_be_rejected(self, client, admin_a_headers):
        """A cancelled action cannot be rejected (returns 409)."""
        # Create action
        response = client.post(
            "/v1/actions",
            json={"title": "To Cancel 2", "action_type": "general", "payload": {}},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Cancel
        response = client.post(
            f"/v1/actions/{action_id}/cancel",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 200

        # Try to reject -> 409
        response = client.post(
            f"/v1/actions/{action_id}/reject",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 409
        assert "cancelled" in response.json()["detail"].lower()


class TestActionsApprovalsV0QuotaEnforcement:
    """Test quota enforcement for approve (Phase 1 Task 8b)."""

    def test_approve_quota_exceeded_returns_429_no_partial_writes(self, client, tenant_a, admin_a_headers):
        """When approve quota exceeded, returns 429 and no partial writes happen."""
        platform_headers = {"X-Platform-Admin-Key": "test-admin-key"}

        # Create a test plan with cap of 1 for action_approved
        response = client.post(
            "/v1/admin/plans",
            json={
                "plan_id": "test_approve_limited",
                "name": "Approve Limited",
                "included_credits": 1000,
                "overage_price_per_credit": 0.02,
            },
            headers=platform_headers,
        )
        assert response.status_code in [200, 201, 409]

        # Add capabilities
        client.put(
            "/v1/admin/plans/test_approve_limited/capabilities",
            json={"capabilities": ["action_center", "timeline"]},
            headers=platform_headers,
        )

        # Add event cap of 1 for action_approved
        client.put(
            "/v1/admin/plans/test_approve_limited/caps",
            json={
                "caps": [
                    {"event_key": "action_approved", "period": "monthly", "cap_raw_units": 1}
                ]
            },
            headers=platform_headers,
        )

        # Assign the limited plan to the tenant
        client.put(
            f"/v1/admin/tenants/{tenant_a['tenant_id']}/subscription",
            json={"plan_id": "test_approve_limited", "status": "active"},
            headers=platform_headers,
        )

        # Create two actions
        response = client.post(
            "/v1/actions",
            json={"title": "First Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id_1 = response.json()["action_id"]

        response = client.post(
            "/v1/actions",
            json={"title": "Second Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id_2 = response.json()["action_id"]

        # First approve should succeed
        response = client.post(
            f"/v1/actions/{action_id_1}/approve",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 200

        # Second approve should fail with 429
        response = client.post(
            f"/v1/actions/{action_id_2}/approve",
            json={},
            headers=admin_a_headers,
        )
        assert response.status_code == 429

        # Verify second action remains "proposed"
        response = client.get(f"/v1/actions/{action_id_2}", headers=admin_a_headers)
        assert response.json()["status"] == "proposed"

        # Verify no action_reviews row for second action
        db = TestingSessionLocal()
        from app.gateway.models import ActionReview
        reviews_for_second = db.query(ActionReview).filter(
            ActionReview.action_id == action_id_2
        ).count()
        assert reviews_for_second == 0
        db.close()

        # Verify no additional timeline event for second action approval
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id_2}",
            headers=admin_a_headers,
        )
        events = response.json()["items"]
        approved_events = [e for e in events if e["event_type"] == "action_approved"]
        assert len(approved_events) == 0


class TestActionsApprovalsV0ListFilters:
    """Test list endpoint filters for approved/rejected status (Phase 1 Task 8b)."""

    def test_list_status_filter_approved(self, client, admin_a_headers):
        """Can filter by status=approved."""
        # Create and approve an action
        response = client.post(
            "/v1/actions",
            json={"title": "To Approve", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Create another action that stays proposed
        client.post(
            "/v1/actions",
            json={"title": "Stay Proposed", "action_type": "general"},
            headers=admin_a_headers,
        )

        # List approved only
        response = client.get("/v1/actions?status=approved", headers=admin_a_headers)
        items = response.json()["items"]
        assert len(items) >= 1
        assert all(a["status"] == "approved" for a in items)

    def test_list_status_filter_rejected(self, client, admin_a_headers):
        """Can filter by status=rejected."""
        # Create and reject an action
        response = client.post(
            "/v1/actions",
            json={"title": "To Reject", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/reject", json={}, headers=admin_a_headers)

        # List rejected only
        response = client.get("/v1/actions?status=rejected", headers=admin_a_headers)
        items = response.json()["items"]
        assert len(items) >= 1
        assert all(a["status"] == "rejected" for a in items)


# =============================================================================
# Actions Execute v0 Tests (Phase 1, Task 8c)
# =============================================================================

class TestActionsExecuteV0HappyPath:
    """Test action execute happy path (Phase 1 Task 8c)."""

    def test_execute_happy_path(self, client, admin_a_headers, member_a_headers):
        """Admin can execute an approved action; creates execution record + timeline + metering."""
        # Member creates action
        response = client.post(
            "/v1/actions",
            json={"title": "Execute Test", "action_type": "general", "payload": {"key": "value"}},
            headers=member_a_headers,
        )
        assert response.status_code == 201
        action_id = response.json()["action_id"]

        # Admin approves action
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Admin executes action
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {"message": "Done"}},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Check action status
        assert data["action"]["status"] == "executed"

        # Check execution record
        assert "execution" in data
        assert data["execution"]["execution_status"] == "succeeded"
        assert data["execution"]["result"] == {"message": "Done"}
        assert "execution_id" in data["execution"]

        # Verify exactly one action_executions row exists
        db = TestingSessionLocal()
        from app.gateway.models import ActionExecution
        executions = db.query(ActionExecution).filter(
            ActionExecution.action_id == action_id
        ).all()
        assert len(executions) == 1
        assert executions[0].execution_status == "succeeded"
        db.close()

        # Verify timeline has action_executed event
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id}",
            headers=admin_a_headers,
        )
        events = response.json()["items"]
        executed_events = [e for e in events if e["event_type"] == "action_executed"]
        assert len(executed_events) == 1
        assert "execution_id" in executed_events[0]["metadata"]

        # Verify billing usage includes action_executed
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        action_executed = next((b for b in breakdown if b["event_key"] == "action_executed"), None)
        assert action_executed is not None
        assert action_executed["raw_units"] >= 1
        assert action_executed["credits"] == action_executed["raw_units"] * 0.3

    def test_execute_includes_action_detail_with_execution(self, client, admin_a_headers):
        """GET action detail includes execution data after execution."""
        # Create, approve, and execute action
        response = client.post(
            "/v1/actions",
            json={"title": "Detail Test", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)
        client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {"output": "test"}},
            headers=admin_a_headers,
        )

        # Get action detail
        response = client.get(f"/v1/actions/{action_id}", headers=admin_a_headers)
        assert response.status_code == 200
        data = response.json()

        # Check review and execution are present
        assert data["review"] is not None
        assert data["review"]["decision"] == "approved"
        assert data["execution"] is not None
        assert data["execution"]["execution_status"] == "succeeded"


class TestActionsExecuteV0RBAC:
    """Test RBAC for action execute (Phase 1 Task 8c)."""

    def test_member_cannot_execute(self, client, admin_a_headers, member_a_headers):
        """Member should not be able to execute an action (403)."""
        # Create and approve action as admin
        response = client.post(
            "/v1/actions",
            json={"title": "RBAC Test", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Member tries to execute
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {}},
            headers=member_a_headers,
        )
        assert response.status_code == 403


class TestActionsExecuteV0TenantIsolation:
    """Test tenant isolation for action execute (Phase 1 Task 8c)."""

    def test_cross_tenant_execute_returns_404(self, client, admin_a_headers, admin_b_headers):
        """Tenant B admin cannot execute Tenant A's action (returns 404)."""
        # Create and approve action in tenant A
        response = client.post(
            "/v1/actions",
            json={"title": "Tenant A Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Tenant B admin tries to execute
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {}},
            headers=admin_b_headers,
        )
        assert response.status_code == 404


class TestActionsExecuteV0StatusTransitions:
    """Test status transition enforcement for execute (Phase 1 Task 8c)."""

    def test_execute_proposed_returns_409(self, client, admin_a_headers):
        """Cannot execute a proposed action (returns 409)."""
        # Create action (stays proposed)
        response = client.post(
            "/v1/actions",
            json={"title": "Proposed Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]

        # Try to execute
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {}},
            headers=admin_a_headers,
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error"] == "invalid_status_transition"
        assert detail["current_status"] == "proposed"

    def test_execute_rejected_returns_409(self, client, admin_a_headers):
        """Cannot execute a rejected action (returns 409)."""
        # Create and reject action
        response = client.post(
            "/v1/actions",
            json={"title": "Rejected Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/reject", json={}, headers=admin_a_headers)

        # Try to execute
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {}},
            headers=admin_a_headers,
        )
        assert response.status_code == 409
        assert response.json()["detail"]["current_status"] == "rejected"

    def test_execute_cancelled_returns_409(self, client, admin_a_headers):
        """Cannot execute a cancelled action (returns 409)."""
        # Create and cancel action
        response = client.post(
            "/v1/actions",
            json={"title": "Cancelled Action", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/cancel", json={}, headers=admin_a_headers)

        # Try to execute
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {}},
            headers=admin_a_headers,
        )
        assert response.status_code == 409
        assert response.json()["detail"]["current_status"] == "cancelled"


class TestActionsExecuteV0Idempotency:
    """Test idempotent retry behavior for execute (Phase 1 Task 8c)."""

    def test_execute_idempotent(self, client, admin_a_headers):
        """Executing an already executed action returns 200 without additional writes."""
        # Create and approve action
        response = client.post(
            "/v1/actions",
            json={"title": "Idempotent Test", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # First execute
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {"first": True}},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        first_execution_id = response.json()["execution"]["execution_id"]

        # Get usage after first execute
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        executed_after_first = next(
            (b for b in breakdown if b["event_key"] == "action_executed"),
            {"raw_units": 0}
        )

        # Get execution count
        db = TestingSessionLocal()
        from app.gateway.models import ActionExecution
        exec_count_1 = db.query(ActionExecution).filter(ActionExecution.action_id == action_id).count()
        db.close()

        # Get timeline event count
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id}",
            headers=admin_a_headers,
        )
        executed_events_1 = len([e for e in response.json()["items"] if e["event_type"] == "action_executed"])

        # Second execute (idempotent)
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "failed", "result": {"second": True}},  # Different values
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        # Should return original execution, not the new one
        assert response.json()["execution"]["execution_id"] == first_execution_id
        assert response.json()["execution"]["result"] == {"first": True}

        # Usage should NOT have incremented
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        executed_after_second = next(
            (b for b in breakdown if b["event_key"] == "action_executed"),
            {"raw_units": 0}
        )
        assert executed_after_second["raw_units"] == executed_after_first["raw_units"]

        # Execution count should NOT have incremented
        db = TestingSessionLocal()
        exec_count_2 = db.query(ActionExecution).filter(ActionExecution.action_id == action_id).count()
        db.close()
        assert exec_count_2 == exec_count_1

        # Timeline event count should NOT have incremented
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id}",
            headers=admin_a_headers,
        )
        executed_events_2 = len([e for e in response.json()["items"] if e["event_type"] == "action_executed"])
        assert executed_events_2 == executed_events_1


class TestActionsExecuteV0QuotaEnforcement:
    """Test quota enforcement for execute (no partial writes) (Phase 1 Task 8c)."""

    def test_execute_quota_exceeded_no_partial_writes(self, client, tenant_a, admin_a_headers):
        """When execute quota exceeded, returns 429 and no partial writes happen."""
        platform_headers = {"X-Platform-Admin-Key": "test-admin-key"}

        # Create a test plan with cap of 0 for action_executed (immediate failure)
        response = client.post(
            "/v1/admin/plans",
            json={
                "plan_id": "test_no_execute",
                "name": "No Execute Plan",
                "included_credits": 1000,
                "overage_price_per_credit": 0.02,
            },
            headers=platform_headers,
        )
        assert response.status_code in [200, 201, 409]

        # Add capabilities
        client.put(
            "/v1/admin/plans/test_no_execute/capabilities",
            json={"capabilities": ["action_center", "timeline"]},
            headers=platform_headers,
        )

        # Add event cap of 0 for action_executed
        client.put(
            "/v1/admin/plans/test_no_execute/caps",
            json={
                "caps": [
                    {"event_key": "action_executed", "period": "monthly", "cap_raw_units": 0}
                ]
            },
            headers=platform_headers,
        )

        # Assign the limited plan to the tenant
        client.put(
            f"/v1/admin/tenants/{tenant_a['tenant_id']}/subscription",
            json={"plan_id": "test_no_execute", "status": "active"},
            headers=platform_headers,
        )

        # Create and approve action
        response = client.post(
            "/v1/actions",
            json={"title": "Quota Test", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)

        # Try to execute (should fail with 429)
        response = client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {}},
            headers=admin_a_headers,
        )
        assert response.status_code == 429

        # Verify action remains "approved"
        response = client.get(f"/v1/actions/{action_id}", headers=admin_a_headers)
        assert response.json()["status"] == "approved"

        # Verify no execution row was created
        db = TestingSessionLocal()
        from app.gateway.models import ActionExecution
        exec_count = db.query(ActionExecution).filter(ActionExecution.action_id == action_id).count()
        assert exec_count == 0
        db.close()

        # Verify no action_executed timeline event
        response = client.get(
            f"/v1/timeline?entity_type=action&entity_id={action_id}",
            headers=admin_a_headers,
        )
        events = response.json()["items"]
        executed_events = [e for e in events if e["event_type"] == "action_executed"]
        assert len(executed_events) == 0


class TestActionsExecuteV0ListFilter:
    """Test list endpoint filter for executed status (Phase 1 Task 8c)."""

    def test_list_status_filter_executed(self, client, admin_a_headers):
        """Can filter by status=executed."""
        # Create, approve, and execute an action
        response = client.post(
            "/v1/actions",
            json={"title": "To Execute", "action_type": "general"},
            headers=admin_a_headers,
        )
        action_id = response.json()["action_id"]
        client.post(f"/v1/actions/{action_id}/approve", json={}, headers=admin_a_headers)
        client.post(
            f"/v1/actions/{action_id}/execute",
            json={"execution_status": "succeeded", "result": {}},
            headers=admin_a_headers,
        )

        # Create another action that stays proposed
        client.post(
            "/v1/actions",
            json={"title": "Stay Proposed", "action_type": "general"},
            headers=admin_a_headers,
        )

        # List executed only
        response = client.get("/v1/actions?status=executed", headers=admin_a_headers)
        items = response.json()["items"]
        assert len(items) >= 1
        assert all(a["status"] == "executed" for a in items)


# =============================================================================
# /v1/me Endpoint Tests (Phase 1, Task 8c)
# =============================================================================

class TestMeEndpoint:
    """Test /v1/me endpoint."""

    def test_me_returns_user_info(self, client, admin_a_headers, tenant_a):
        """GET /v1/me returns user info including role and email."""
        response = client.get("/v1/me", headers=admin_a_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == tenant_a["admin"]["user_id"]
        assert data["tenant_id"] == tenant_a["tenant_id"]
        assert data["role"] == "admin"
        assert data["email"] == "admin-a@test.com"

    def test_me_returns_member_role(self, client, member_a_headers, member_a):
        """GET /v1/me returns correct role for member."""
        response = client.get("/v1/me", headers=member_a_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"
        assert data["email"] == "member-a@test.com"

    def test_me_cross_tenant_user_returns_403(self, client, tenant_a, member_a, tenant_b):
        """GET /v1/me with cross-tenant user_id returns 403."""
        # Try to use tenant B's API key with tenant A's user_id
        cross_tenant_headers = {
            "X-Tenant-ID": tenant_b["tenant_id"],
            "X-User-ID": member_a["user_id"],  # User from tenant A
            "X-API-Key": tenant_b["api_key"],  # API key from tenant B
        }
        response = client.get("/v1/me", headers=cross_tenant_headers)
        # Should fail because user doesn't belong to tenant B
        assert response.status_code == 403

    def test_me_invalid_api_key_returns_401(self, client, tenant_a):
        """GET /v1/me with invalid API key returns 401."""
        invalid_headers = {
            "X-Tenant-ID": tenant_a["tenant_id"],
            "X-User-ID": tenant_a["admin"]["user_id"],
            "X-API-Key": "invalid-api-key",
        }
        response = client.get("/v1/me", headers=invalid_headers)
        assert response.status_code == 401

    def test_me_missing_headers_returns_400(self, client):
        """GET /v1/me with missing headers returns 400."""
        response = client.get("/v1/me", headers={})
        assert response.status_code == 400


# =============================================================================
# Tasks v0 Tests (Phase 1, Task 9a)
# =============================================================================

class TestTasksV0Create:
    """Test task creation (Phase 1 Task 9a)."""

    def test_member_can_create_task_with_defaults(self, client, member_a_headers):
        """Member can create a task with default status=todo and priority=medium."""
        response = client.post(
            "/v1/tasks",
            json={"title": "My Task"},
            headers=member_a_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "todo"
        assert data["priority"] == "medium"
        assert data["title"] == "My Task"

    def test_create_task_with_all_fields(self, client, member_a_headers, member_a):
        """Create task with all fields specified."""
        response = client.post(
            "/v1/tasks",
            json={
                "title": "Full Task",
                "description": "A complete task",
                "priority": "high",
                "due_date": "2024-12-31",
                "assigned_to_user_id": member_a["user_id"],
                "linked_entity_type": "action",
                "linked_entity_id": "some-action-id",
            },
            headers=member_a_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Full Task"
        assert data["description"] == "A complete task"
        assert data["priority"] == "high"
        assert data["due_date"] == "2024-12-31"
        assert data["linked_entity_type"] == "action"
        assert data["linked_entity_id"] == "some-action-id"

    def test_admin_can_create_task(self, client, admin_a_headers):
        """Admin can also create tasks."""
        response = client.post(
            "/v1/tasks",
            json={"title": "Admin Task"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201


class TestTasksV0TenantIsolation:
    """Test tenant isolation for tasks (Phase 1 Task 9a)."""

    def test_tenant_b_cannot_see_tenant_a_task(self, client, admin_a_headers, admin_b_headers):
        """Tenant B should not be able to access Tenant A's task (returns 404)."""
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

    def test_tenant_b_cannot_update_tenant_a_task(self, client, admin_a_headers, admin_b_headers):
        """Tenant B cannot update Tenant A's task (returns 404)."""
        # Tenant A creates a task
        response = client.post(
            "/v1/tasks",
            json={"title": "Tenant A Task"},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Tenant B tries to update it
        response = client.patch(
            f"/v1/tasks/{task_id}",
            json={"title": "Hijacked!"},
            headers=admin_b_headers,
        )
        assert response.status_code == 404

    def test_tenant_b_cannot_complete_tenant_a_task(self, client, admin_a_headers, admin_b_headers):
        """Tenant B cannot complete Tenant A's task (returns 404)."""
        # Tenant A creates a task
        response = client.post(
            "/v1/tasks",
            json={"title": "Tenant A Task"},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Tenant B tries to complete it
        response = client.post(f"/v1/tasks/{task_id}/complete", headers=admin_b_headers)
        assert response.status_code == 404


class TestTasksV0RBACUpdate:
    """Test RBAC rules for task update (Phase 1 Task 9a)."""

    def test_creator_can_update_own_task(self, client, member_a_headers):
        """Creator can update their own task."""
        # Create a task
        response = client.post(
            "/v1/tasks",
            json={"title": "My Task"},
            headers=member_a_headers,
        )
        task_id = response.json()["task_id"]

        # Update it
        response = client.patch(
            f"/v1/tasks/{task_id}",
            json={"title": "Updated Task", "priority": "high"},
            headers=member_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Task"
        assert response.json()["priority"] == "high"

    def test_assignee_can_update_assigned_task(
        self, client, member_a_headers, member_a2_headers, member_a2
    ):
        """Assignee can update tasks assigned to them."""
        # Member A creates task assigned to member A2
        response = client.post(
            "/v1/tasks",
            json={"title": "Task for A2", "assigned_to_user_id": member_a2["user_id"]},
            headers=member_a_headers,
        )
        task_id = response.json()["task_id"]

        # Member A2 (assignee) can update
        response = client.patch(
            f"/v1/tasks/{task_id}",
            json={"priority": "high", "status": "doing"},
            headers=member_a2_headers,
        )
        assert response.status_code == 200
        assert response.json()["priority"] == "high"
        assert response.json()["status"] == "doing"

    def test_non_assignee_non_creator_cannot_update(
        self, client, admin_a_headers, member_a_headers, member_a2_headers, member_a2
    ):
        """Member who is neither creator nor assignee cannot update (403)."""
        # Admin creates a task assigned to member A2
        response = client.post(
            "/v1/tasks",
            json={"title": "Task for A2", "assigned_to_user_id": member_a2["user_id"]},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Member A (not creator, not assignee) tries to update
        response = client.patch(
            f"/v1/tasks/{task_id}",
            json={"title": "Hijacked!"},
            headers=member_a_headers,
        )
        assert response.status_code == 403

    def test_admin_can_update_any_task(
        self, client, member_a_headers, admin_a_headers
    ):
        """Admin can update any task in the tenant."""
        # Member creates a task
        response = client.post(
            "/v1/tasks",
            json={"title": "Member Task"},
            headers=member_a_headers,
        )
        task_id = response.json()["task_id"]

        # Admin can update
        response = client.patch(
            f"/v1/tasks/{task_id}",
            json={"priority": "high"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200
        assert response.json()["priority"] == "high"

    def test_update_no_changes_does_not_emit_usage(
        self, client, admin_a_headers
    ):
        """If update body results in no changes, no usage/audit is emitted."""
        # Create a task
        response = client.post(
            "/v1/tasks",
            json={"title": "Test Task", "priority": "medium"},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Get initial billing usage
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        initial_breakdown = response.json()["breakdown"]
        initial_updated = next(
            (b for b in initial_breakdown if b["event_key"] == "task_updated"), None
        )
        initial_updated_units = initial_updated["raw_units"] if initial_updated else 0

        # Update with same values (no actual change)
        response = client.patch(
            f"/v1/tasks/{task_id}",
            json={"title": "Test Task", "priority": "medium"},  # Same values
            headers=admin_a_headers,
        )
        assert response.status_code == 200

        # Check billing - should NOT have increased
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        final_breakdown = response.json()["breakdown"]
        final_updated = next(
            (b for b in final_breakdown if b["event_key"] == "task_updated"), None
        )
        final_updated_units = final_updated["raw_units"] if final_updated else 0

        assert final_updated_units == initial_updated_units


class TestTasksV0RBACComplete:
    """Test RBAC rules for task complete (Phase 1 Task 9a)."""

    def test_creator_can_complete_own_task(self, client, member_a_headers):
        """Creator can complete their own task."""
        response = client.post(
            "/v1/tasks",
            json={"title": "My Task"},
            headers=member_a_headers,
        )
        task_id = response.json()["task_id"]

        response = client.post(f"/v1/tasks/{task_id}/complete", headers=member_a_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "done"

    def test_assignee_can_complete_assigned_task(
        self, client, member_a_headers, member_a2_headers, member_a2
    ):
        """Assignee can complete tasks assigned to them."""
        response = client.post(
            "/v1/tasks",
            json={"title": "Task for A2", "assigned_to_user_id": member_a2["user_id"]},
            headers=member_a_headers,
        )
        task_id = response.json()["task_id"]

        response = client.post(f"/v1/tasks/{task_id}/complete", headers=member_a2_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "done"

    def test_non_assignee_non_creator_cannot_complete(
        self, client, admin_a_headers, member_a_headers, member_a2_headers, member_a2
    ):
        """Member who is neither creator nor assignee cannot complete (403)."""
        # Admin creates task assigned to member A2
        response = client.post(
            "/v1/tasks",
            json={"title": "Task for A2", "assigned_to_user_id": member_a2["user_id"]},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Member A tries to complete
        response = client.post(f"/v1/tasks/{task_id}/complete", headers=member_a_headers)
        assert response.status_code == 403

    def test_admin_can_complete_any_task(self, client, member_a_headers, admin_a_headers):
        """Admin can complete any task in the tenant."""
        response = client.post(
            "/v1/tasks",
            json={"title": "Member Task"},
            headers=member_a_headers,
        )
        task_id = response.json()["task_id"]

        response = client.post(f"/v1/tasks/{task_id}/complete", headers=admin_a_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "done"


class TestTasksV0CompleteIdempotent:
    """Test idempotent complete behavior (Phase 1 Task 9a)."""

    def test_complete_already_done_returns_200_no_usage(self, client, admin_a_headers):
        """Completing an already-done task returns 200 without emitting additional usage."""
        # Create a task
        response = client.post(
            "/v1/tasks",
            json={"title": "Idempotent Task"},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Complete first time
        response = client.post(f"/v1/tasks/{task_id}/complete", headers=admin_a_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "done"

        # Get billing usage after first complete
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        completed = next((b for b in breakdown if b["event_key"] == "task_completed"), None)
        assert completed is not None
        first_complete_units = completed["raw_units"]

        # Complete second time (already done)
        response = client.post(f"/v1/tasks/{task_id}/complete", headers=admin_a_headers)
        assert response.status_code == 200  # Should still return 200
        assert response.json()["status"] == "done"

        # Check billing - should NOT have increased
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        completed = next((b for b in breakdown if b["event_key"] == "task_completed"), None)
        assert completed["raw_units"] == first_complete_units  # No increase


class TestTasksV0Metering:
    """Test metering for task operations (Phase 1 Task 9a)."""

    def test_task_created_metered(self, client, admin_a_headers):
        """Creating a task emits task_created usage."""
        response = client.post(
            "/v1/tasks",
            json={"title": "Metered Task"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201

        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        task_created = next((b for b in breakdown if b["event_key"] == "task_created"), None)
        assert task_created is not None
        assert task_created["raw_units"] >= 1
        assert task_created["credits"] == task_created["raw_units"] * 0.1  # 0.1 credits per unit

    def test_task_updated_metered(self, client, admin_a_headers):
        """Updating a task emits task_updated usage."""
        response = client.post(
            "/v1/tasks",
            json={"title": "To Update"},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Get initial
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        initial = response.json()["breakdown"]
        initial_updated = next((b for b in initial if b["event_key"] == "task_updated"), None)
        initial_units = initial_updated["raw_units"] if initial_updated else 0

        # Update
        response = client.patch(
            f"/v1/tasks/{task_id}",
            json={"title": "Updated Title"},
            headers=admin_a_headers,
        )
        assert response.status_code == 200

        # Check billing
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        task_updated = next((b for b in breakdown if b["event_key"] == "task_updated"), None)
        assert task_updated is not None
        assert task_updated["raw_units"] == initial_units + 1
        assert task_updated["credits"] == task_updated["raw_units"] * 0.05  # 0.05 credits per unit

    def test_task_completed_metered(self, client, admin_a_headers):
        """Completing a task emits task_completed usage."""
        response = client.post(
            "/v1/tasks",
            json={"title": "To Complete"},
            headers=admin_a_headers,
        )
        task_id = response.json()["task_id"]

        # Complete
        response = client.post(f"/v1/tasks/{task_id}/complete", headers=admin_a_headers)
        assert response.status_code == 200

        # Check billing
        response = client.get("/v1/billing/usage", headers=admin_a_headers)
        breakdown = response.json()["breakdown"]
        task_completed = next((b for b in breakdown if b["event_key"] == "task_completed"), None)
        assert task_completed is not None
        assert task_completed["raw_units"] >= 1
        assert task_completed["credits"] == task_completed["raw_units"] * 0.05  # 0.05 credits per unit


class TestTasksV0QuotaEnforcement:
    """Test quota enforcement for tasks (Phase 1 Task 9a)."""

    def test_quota_enforcement_no_partial_writes(self, client, admin_a_headers, tenant_a):
        """When quota is exceeded, no partial write occurs."""
        platform_headers = {"X-Platform-Admin-Key": "test-admin-key"}

        # Create a limited plan with cap of 1 task_created per month
        response = client.post(
            "/v1/admin/plans",
            json={
                "plan_id": "test_task_limited",
                "name": "Task Limited",
                "included_credits": 1000,
                "overage_price_per_credit": 0.02,
            },
            headers=platform_headers,
        )
        # May already exist, that's fine
        assert response.status_code in [200, 201, 409]

        # Add tasks capability (required for task access)
        client.put(
            "/v1/admin/plans/test_task_limited/capabilities",
            json={"capabilities": ["tasks"]},
            headers=platform_headers,
        )

        # Add event cap of 1 for task_created
        client.put(
            "/v1/admin/plans/test_task_limited/caps",
            json={
                "caps": [
                    {"event_key": "task_created", "period": "monthly", "cap_raw_units": 1}
                ]
            },
            headers=platform_headers,
        )

        # Assign the limited plan to the tenant
        client.put(
            f"/v1/admin/tenants/{tenant_a['tenant_id']}/subscription",
            json={"plan_id": "test_task_limited", "status": "active"},
            headers=platform_headers,
        )

        # First task should succeed
        response = client.post(
            "/v1/tasks",
            json={"title": "First Task"},
            headers=admin_a_headers,
        )
        assert response.status_code == 201

        # Second task should fail with 429
        response = client.post(
            "/v1/tasks",
            json={"title": "Second Task"},
            headers=admin_a_headers,
        )
        assert response.status_code == 429

        # Verify no partial write: list should only have 1 task
        response = client.get("/v1/tasks?status=all", headers=admin_a_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["title"] == "First Task"


class TestTasksV0ListFilters:
    """Test task list endpoint with filters (Phase 1 Task 9a)."""

    def test_list_default_status_is_todo(self, client, admin_a_headers):
        """Default status filter is 'todo'."""
        # Create todo task
        client.post("/v1/tasks", json={"title": "Todo Task"}, headers=admin_a_headers)

        # Create and complete a task
        response = client.post(
            "/v1/tasks",
            json={"title": "Done Task"},
            headers=admin_a_headers,
        )
        done_id = response.json()["task_id"]
        client.post(f"/v1/tasks/{done_id}/complete", headers=admin_a_headers)

        # List without filter
        response = client.get("/v1/tasks", headers=admin_a_headers)
        items = response.json()["items"]
        # Should only show todo tasks by default
        assert all(t["status"] == "todo" for t in items)

    def test_list_status_all(self, client, admin_a_headers):
        """status=all returns all tasks."""
        # Create tasks with different statuses
        client.post("/v1/tasks", json={"title": "Todo"}, headers=admin_a_headers)
        resp = client.post("/v1/tasks", json={"title": "Done"}, headers=admin_a_headers)
        client.post(f"/v1/tasks/{resp.json()['task_id']}/complete", headers=admin_a_headers)

        # List with status=all
        response = client.get("/v1/tasks?status=all", headers=admin_a_headers)
        items = response.json()["items"]
        statuses = {t["status"] for t in items}
        assert "todo" in statuses or "done" in statuses

    def test_list_assigned_to_user_id_filter(
        self, client, admin_a_headers, member_a, member_a_headers
    ):
        """Can filter by assigned_to_user_id."""
        # Create task assigned to member A
        client.post(
            "/v1/tasks",
            json={"title": "Assigned to A", "assigned_to_user_id": member_a["user_id"]},
            headers=admin_a_headers,
        )
        # Create another unassigned task
        client.post("/v1/tasks", json={"title": "Unassigned"}, headers=admin_a_headers)

        # List filtered
        response = client.get(
            f"/v1/tasks?status=all&assigned_to_user_id={member_a['user_id']}",
            headers=admin_a_headers,
        )
        items = response.json()["items"]
        assert all(t["assigned_to_user_id"] == member_a["user_id"] for t in items)

    def test_list_created_by_user_id_filter(
        self, client, admin_a_headers, member_a_headers, member_a, tenant_a
    ):
        """Can filter by created_by_user_id."""
        # Member creates a task
        client.post("/v1/tasks", json={"title": "By Member"}, headers=member_a_headers)
        # Admin creates a task
        client.post("/v1/tasks", json={"title": "By Admin"}, headers=admin_a_headers)

        # List filtered by member
        response = client.get(
            f"/v1/tasks?status=all&created_by_user_id={member_a['user_id']}",
            headers=admin_a_headers,
        )
        items = response.json()["items"]
        assert all(t["created_by_user_id"] == member_a["user_id"] for t in items)

    def test_list_due_date_filters(self, client, admin_a_headers):
        """Can filter by due_before and due_after."""
        # Create tasks with different due dates
        client.post(
            "/v1/tasks",
            json={"title": "Early", "due_date": "2024-01-15"},
            headers=admin_a_headers,
        )
        client.post(
            "/v1/tasks",
            json={"title": "Late", "due_date": "2024-12-15"},
            headers=admin_a_headers,
        )

        # Filter due_before
        response = client.get("/v1/tasks?status=all&due_before=2024-06-01", headers=admin_a_headers)
        items = response.json()["items"]
        assert all(t["due_date"] is None or t["due_date"] <= "2024-06-01" for t in items)

        # Filter due_after
        response = client.get("/v1/tasks?status=all&due_after=2024-06-01", headers=admin_a_headers)
        items = response.json()["items"]
        assert all(t["due_date"] is None or t["due_date"] >= "2024-06-01" for t in items)
