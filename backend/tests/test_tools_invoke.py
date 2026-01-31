"""Tests for the Tool Invocation Gateway."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.gateway.models import AuditLog, Brief, KPIDefinition, KPIPoint, UsageEvent


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


@pytest.fixture(scope="function")
def client():
    """Create test client with fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def tenant(client):
    """Create a test tenant."""
    response = client.post(
        "/v1/tenants",
        json={"name": "Test Tenant", "region": "us-east-1"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def admin_user(client, tenant):
    """Create an admin user for the test tenant."""
    response = client.post(
        "/v1/users",
        json={
            "tenant_id": tenant["tenant_id"],
            "email": "admin@test.com",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def member_user(client, tenant):
    """Create a member user for the test tenant."""
    response = client.post(
        "/v1/users",
        json={
            "tenant_id": tenant["tenant_id"],
            "email": "member@test.com",
            "role": "member",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def other_tenant(client):
    """Create a different tenant."""
    response = client.post(
        "/v1/tenants",
        json={"name": "Other Tenant", "region": "eu-west-1"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def other_tenant_user(client, other_tenant):
    """Create a user for the other tenant."""
    response = client.post(
        "/v1/users",
        json={
            "tenant_id": other_tenant["tenant_id"],
            "email": "other@test.com",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    return response.json()


class TestTenantCreation:
    """Tests for tenant creation endpoint."""

    def test_create_tenant_success(self, client):
        """Test successful tenant creation."""
        response = client.post(
            "/v1/tenants",
            json={"name": "My Tenant", "region": "us-west-2"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "tenant_id" in data
        assert data["name"] == "My Tenant"
        assert data["region"] == "us-west-2"
        assert "api_key" in data
        assert len(data["api_key"]) > 20  # Ensure API key is substantial

    def test_create_tenant_missing_name(self, client):
        """Test tenant creation with missing name."""
        response = client.post(
            "/v1/tenants",
            json={"region": "us-east-1"},
        )
        assert response.status_code == 422


class TestUserCreation:
    """Tests for user creation endpoint."""

    def test_create_user_success(self, client, tenant):
        """Test successful user creation."""
        response = client.post(
            "/v1/users",
            json={
                "tenant_id": tenant["tenant_id"],
                "email": "user@test.com",
                "role": "admin",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "user_id" in data
        assert data["tenant_id"] == tenant["tenant_id"]
        assert data["email"] == "user@test.com"
        assert data["role"] == "admin"

    def test_create_user_invalid_tenant(self, client):
        """Test user creation with non-existent tenant."""
        response = client.post(
            "/v1/users",
            json={
                "tenant_id": "00000000-0000-0000-0000-000000000000",
                "email": "user@test.com",
                "role": "admin",
            },
        )
        assert response.status_code == 404

    def test_create_user_invalid_role(self, client, tenant):
        """Test user creation with invalid role."""
        response = client.post(
            "/v1/users",
            json={
                "tenant_id": tenant["tenant_id"],
                "email": "user@test.com",
                "role": "superuser",  # Invalid role
            },
        )
        assert response.status_code == 422


class TestToolInvokeMissingHeaders:
    """Tests for missing header validation."""

    def test_missing_tenant_id(self, client):
        """Test that missing X-Tenant-ID returns 400."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-User-ID": "some-user-id",
                "X-API-Key": "some-key",
                "Idempotency-Key": "test-key",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 400
        assert "X-Tenant-ID" in response.json()["detail"]

    def test_missing_user_id(self, client, tenant):
        """Test that missing X-User-ID returns 400."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "test-key",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 400
        assert "X-User-ID" in response.json()["detail"]

    def test_missing_api_key(self, client, tenant):
        """Test that missing X-API-Key returns 400."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": "some-user-id",
                "Idempotency-Key": "test-key",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 400
        assert "X-API-Key" in response.json()["detail"]

    def test_missing_idempotency_key(self, client, tenant, admin_user):
        """Test that missing Idempotency-Key returns 400."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 400
        assert "Idempotency-Key" in response.json()["detail"]


class TestToolInvokeAuthentication:
    """Tests for authentication."""

    def test_wrong_api_key(self, client, tenant, admin_user):
        """Test that wrong API key returns 401."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": "wrong-api-key",
                "Idempotency-Key": "test-key",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 401
        assert "Invalid tenant ID or API key" in response.json()["detail"]

    def test_nonexistent_tenant(self, client, admin_user, tenant):
        """Test that non-existent tenant returns 401."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": "00000000-0000-0000-0000-000000000000",
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "test-key",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 401


class TestToolInvokeAuthorization:
    """Tests for authorization."""

    def test_user_from_different_tenant(self, client, tenant, other_tenant_user):
        """Test that user from different tenant returns 403."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "test-key",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 403
        assert "does not belong to this tenant" in response.json()["detail"]

    def test_member_cannot_invoke(self, client, tenant, member_user):
        """Test that member role cannot invoke tools - returns 403."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": member_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "test-key",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 403
        assert "not authorized to invoke tools" in response.json()["detail"]

    def test_nonexistent_user(self, client, tenant):
        """Test that non-existent user returns 403."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": "00000000-0000-0000-0000-000000000000",
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "test-key",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 403
        assert "User not found" in response.json()["detail"]


class TestToolInvokeSuccess:
    """Tests for successful tool invocation."""

    def test_successful_invoke_returns_200(self, client, tenant, admin_user):
        """Test successful invoke returns 200 with correct result."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "unique-key-1",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["result"] == {"echo": {"text": "hello"}}

    def test_successful_invoke_creates_audit_log(self, client, tenant, admin_user):
        """Test that successful invoke creates exactly 1 audit log row."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "unique-key-2",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 200
        request_id = response.json()["request_id"]

        # Check audit log
        db = TestingSessionLocal()
        try:
            audit_logs = db.query(AuditLog).filter(
                AuditLog.request_id == request_id
            ).all()
            assert len(audit_logs) == 1
            assert audit_logs[0].tenant_id == tenant["tenant_id"]
            assert audit_logs[0].user_id == admin_user["user_id"]
            assert audit_logs[0].action == "tools.invoke"
            assert audit_logs[0].tool_name == "echo"
        finally:
            db.close()

    def test_successful_invoke_creates_usage_event(self, client, tenant, admin_user):
        """Test that successful invoke creates exactly 1 usage event row."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "unique-key-3",
            },
            json={"tool_name": "echo", "payload": {"text": "hello"}},
        )
        assert response.status_code == 200
        request_id = response.json()["request_id"]

        # Check usage event
        db = TestingSessionLocal()
        try:
            usage_events = db.query(UsageEvent).filter(
                UsageEvent.request_id == request_id
            ).all()
            assert len(usage_events) == 1
            assert usage_events[0].tenant_id == tenant["tenant_id"]
            assert usage_events[0].user_id == admin_user["user_id"]
            assert usage_events[0].activity_type == "tool_invocation"
            assert usage_events[0].units == 1
            assert usage_events[0].tool_name == "echo"
        finally:
            db.close()

    def test_tool_not_found(self, client, tenant, admin_user):
        """Test that invoking a non-existent tool returns 404."""
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "unique-key-4",
            },
            json={"tool_name": "nonexistent", "payload": {}},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestIdempotency:
    """Tests for idempotency behavior."""

    def test_idempotent_request_returns_same_response(self, client, tenant, admin_user):
        """Test that two identical requests with same Idempotency-Key return same request_id."""
        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
            "Idempotency-Key": "idempotent-key-1",
        }
        body = {"tool_name": "echo", "payload": {"text": "idempotent"}}

        # First request
        response1 = client.post("/v1/tools/invoke", headers=headers, json=body)
        assert response1.status_code == 200
        data1 = response1.json()

        # Second identical request
        response2 = client.post("/v1/tools/invoke", headers=headers, json=body)
        assert response2.status_code == 200
        data2 = response2.json()

        # Same request_id should be returned
        assert data1["request_id"] == data2["request_id"]
        assert data1["result"] == data2["result"]

    def test_idempotent_request_no_duplicate_audit_logs(self, client, tenant, admin_user):
        """Test that idempotent requests do NOT create additional audit log rows."""
        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
            "Idempotency-Key": "idempotent-key-2",
        }
        body = {"tool_name": "echo", "payload": {"text": "no-dup-audit"}}

        # First request
        response1 = client.post("/v1/tools/invoke", headers=headers, json=body)
        assert response1.status_code == 200
        request_id = response1.json()["request_id"]

        # Second identical request
        response2 = client.post("/v1/tools/invoke", headers=headers, json=body)
        assert response2.status_code == 200

        # Check only 1 audit log exists
        db = TestingSessionLocal()
        try:
            audit_logs = db.query(AuditLog).filter(
                AuditLog.request_id == request_id
            ).all()
            assert len(audit_logs) == 1
        finally:
            db.close()

    def test_idempotent_request_no_duplicate_usage_events(self, client, tenant, admin_user):
        """Test that idempotent requests do NOT create additional usage event rows."""
        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
            "Idempotency-Key": "idempotent-key-3",
        }
        body = {"tool_name": "echo", "payload": {"text": "no-dup-usage"}}

        # First request
        response1 = client.post("/v1/tools/invoke", headers=headers, json=body)
        assert response1.status_code == 200
        request_id = response1.json()["request_id"]

        # Second identical request
        response2 = client.post("/v1/tools/invoke", headers=headers, json=body)
        assert response2.status_code == 200

        # Check only 1 usage event exists
        db = TestingSessionLocal()
        try:
            usage_events = db.query(UsageEvent).filter(
                UsageEvent.request_id == request_id
            ).all()
            assert len(usage_events) == 1
        finally:
            db.close()

    def test_idempotency_conflict_different_body(self, client, tenant, admin_user):
        """Test that same Idempotency-Key with different body returns 409 Conflict."""
        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
            "Idempotency-Key": "conflict-key-1",
        }

        # First request
        body1 = {"tool_name": "echo", "payload": {"text": "first"}}
        response1 = client.post("/v1/tools/invoke", headers=headers, json=body1)
        assert response1.status_code == 200

        # Second request with different body but same idempotency key
        body2 = {"tool_name": "echo", "payload": {"text": "second"}}
        response2 = client.post("/v1/tools/invoke", headers=headers, json=body2)
        assert response2.status_code == 409
        assert "already used with a different request body" in response2.json()["detail"]

    def test_different_idempotency_keys_create_separate_records(self, client, tenant, admin_user):
        """Test that different idempotency keys create separate audit/usage records."""
        body = {"tool_name": "echo", "payload": {"text": "same-body"}}

        # First request with key1
        response1 = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "different-key-1",
            },
            json=body,
        )
        assert response1.status_code == 200
        request_id1 = response1.json()["request_id"]

        # Second request with key2
        response2 = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "different-key-2",
            },
            json=body,
        )
        assert response2.status_code == 200
        request_id2 = response2.json()["request_id"]

        # Different request_ids
        assert request_id1 != request_id2

        # Check 2 separate audit logs
        db = TestingSessionLocal()
        try:
            audit_logs = db.query(AuditLog).filter(
                AuditLog.tenant_id == tenant["tenant_id"]
            ).all()
            assert len(audit_logs) == 2
        finally:
            db.close()


class TestTenantIsolation:
    """Tests for tenant isolation."""

    def test_idempotency_keys_are_tenant_scoped(self, client, tenant, admin_user, other_tenant, other_tenant_user):
        """Test that the same idempotency key can be used by different tenants."""
        body = {"tool_name": "echo", "payload": {"text": "tenant-scoped"}}
        idempotency_key = "shared-key-across-tenants"

        # First tenant's request
        response1 = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": idempotency_key,
            },
            json=body,
        )
        assert response1.status_code == 200
        request_id1 = response1.json()["request_id"]

        # Second tenant's request with same idempotency key
        response2 = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": other_tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": other_tenant["api_key"],
                "Idempotency-Key": idempotency_key,
            },
            json=body,
        )
        assert response2.status_code == 200
        request_id2 = response2.json()["request_id"]

        # Different request_ids because different tenants
        assert request_id1 != request_id2


# --- KPI Tests ---


class TestKPICreateAndIngest:
    """Tests for KPI creation and point ingestion."""

    def test_admin_can_create_kpi(self, client, tenant, admin_user):
        """Test that admin can create a KPI definition."""
        response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "MRR", "unit": "GBP", "description": "Monthly recurring revenue"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "kpi_id" in data
        assert data["name"] == "MRR"
        assert data["unit"] == "GBP"
        assert data["description"] == "Monthly recurring revenue"

    def test_admin_can_bulk_ingest_points(self, client, tenant, admin_user):
        """Test that admin can bulk ingest KPI points."""
        # First create a KPI
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "MRR", "unit": "GBP"},
        )
        assert kpi_response.status_code == 201
        kpi_id = kpi_response.json()["kpi_id"]

        # Ingest points
        response = client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={
                "points": [
                    {"ts": "2026-01-01T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-08T00:00:00Z", "value": 1250.0},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["inserted"] == 2
        assert data["ignored"] == 0

    def test_bulk_ingest_ignores_duplicates(self, client, tenant, admin_user):
        """Test that bulk ingest ignores duplicate timestamps."""
        # Create KPI
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "DAU", "unit": "users"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
        }

        # First ingest
        response1 = client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers=headers,
            json={"points": [{"ts": "2026-01-01T00:00:00Z", "value": 100.0}]},
        )
        assert response1.status_code == 200
        assert response1.json()["inserted"] == 1

        # Second ingest with same timestamp - should be ignored
        response2 = client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers=headers,
            json={"points": [{"ts": "2026-01-01T00:00:00Z", "value": 200.0}]},
        )
        assert response2.status_code == 200
        assert response2.json()["inserted"] == 0
        assert response2.json()["ignored"] == 1


class TestKPIRBAC:
    """Tests for KPI RBAC (member can read, cannot write)."""

    def test_member_cannot_create_kpi(self, client, tenant, member_user):
        """Test that member cannot create KPI definitions - returns 403."""
        response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": member_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "MRR", "unit": "GBP"},
        )
        assert response.status_code == 403
        assert "not authorized to create KPIs" in response.json()["detail"]

    def test_member_cannot_ingest_points(self, client, tenant, admin_user, member_user):
        """Test that member cannot ingest KPI points - returns 403."""
        # Create KPI as admin
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "MRR", "unit": "GBP"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        # Try to ingest as member
        response = client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": member_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-01T00:00:00Z", "value": 1000.0}]},
        )
        assert response.status_code == 403
        assert "not authorized to ingest KPI points" in response.json()["detail"]

    def test_member_can_list_kpis(self, client, tenant, admin_user, member_user):
        """Test that member can list KPI definitions."""
        # Create KPI as admin
        client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "MRR", "unit": "GBP"},
        )

        # List as member
        response = client.get(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": member_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "MRR"

    def test_member_can_get_latest(self, client, tenant, admin_user, member_user):
        """Test that member can get latest KPI point."""
        # Create KPI and ingest points as admin
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "MRR", "unit": "GBP"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={
                "points": [
                    {"ts": "2026-01-01T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-08T00:00:00Z", "value": 1250.0},
                ]
            },
        )

        # Get latest as member
        response = client.get(
            f"/v1/kpis/{kpi_id}/latest",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": member_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["kpi_id"] == kpi_id
        assert data["ts"] == "2026-01-08T00:00:00Z"
        assert data["value"] == 1250.0


class TestKPITenantIsolation:
    """Tests for KPI tenant isolation."""

    def test_tenant_cannot_see_other_tenant_kpis(self, client, tenant, admin_user, other_tenant, other_tenant_user):
        """Test that tenant A cannot see tenant B's KPIs."""
        # Create KPI for tenant A
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Secret KPI", "unit": "units"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        # Tenant B tries to list KPIs - should only see their own (none)
        response = client.get(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": other_tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": other_tenant["api_key"],
            },
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_tenant_cannot_access_other_tenant_kpi_by_id(self, client, tenant, admin_user, other_tenant, other_tenant_user):
        """Test that tenant B cannot access tenant A's KPI by ID (returns 404)."""
        # Create KPI for tenant A
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Secret KPI", "unit": "units"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        # Tenant B tries to get latest for tenant A's KPI - should get 404
        response = client.get(
            f"/v1/kpis/{kpi_id}/latest",
            headers={
                "X-Tenant-ID": other_tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": other_tenant["api_key"],
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_tenant_cannot_ingest_to_other_tenant_kpi(self, client, tenant, admin_user, other_tenant, other_tenant_user):
        """Test that tenant B cannot ingest points to tenant A's KPI."""
        # Create KPI for tenant A
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Secret KPI", "unit": "units"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        # Tenant B tries to ingest to tenant A's KPI - should get 404
        response = client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": other_tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": other_tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-01T00:00:00Z", "value": 9999.0}]},
        )
        assert response.status_code == 404


class TestKPISummaryTool:
    """Tests for the kpi_summary tool."""

    def test_kpi_summary_correct_delta_calculation(self, client, tenant, admin_user):
        """Test that kpi_summary computes correct delta_abs and delta_pct."""
        # Create KPI
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "MRR", "unit": "GBP"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        # Ingest points: start=1000, latest=1250 (25% increase)
        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={
                "points": [
                    {"ts": "2026-01-01T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-08T00:00:00Z", "value": 1250.0},
                ]
            },
        )

        # Invoke kpi_summary tool with window_days=7
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "kpi-summary-test-1",
            },
            json={
                "tool_name": "kpi_summary",
                "payload": {"kpi_id": kpi_id, "window_days": 7},
            },
        )
        assert response.status_code == 200
        result = response.json()["result"]

        assert result["kpi_id"] == kpi_id
        assert result["latest"]["ts"] == "2026-01-08T00:00:00Z"
        assert result["latest"]["value"] == 1250.0
        assert result["start"]["ts"] == "2026-01-01T00:00:00Z"
        assert result["start"]["value"] == 1000.0
        assert result["delta_abs"] == 250.0
        assert result["delta_pct"] == 25.0

    def test_kpi_summary_single_point_in_window(self, client, tenant, admin_user):
        """Test kpi_summary with only one point in window (delta=0)."""
        # Create KPI
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "DAU", "unit": "users"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        # Ingest only one point
        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-08T00:00:00Z", "value": 500.0}]},
        )

        # Invoke kpi_summary
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "kpi-summary-single-point",
            },
            json={
                "tool_name": "kpi_summary",
                "payload": {"kpi_id": kpi_id, "window_days": 7},
            },
        )
        assert response.status_code == 200
        result = response.json()["result"]

        # With only one point, start == latest and delta == 0
        assert result["latest"]["value"] == 500.0
        assert result["start"]["value"] == 500.0
        assert result["delta_abs"] == 0.0
        assert result["delta_pct"] == 0.0

    def test_kpi_summary_creates_audit_and_usage(self, client, tenant, admin_user):
        """Test that kpi_summary creates exactly one audit_log and one usage_event."""
        # Create KPI and ingest points
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Test KPI"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-01T00:00:00Z", "value": 100.0}]},
        )

        # Invoke kpi_summary
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "audit-usage-test",
            },
            json={
                "tool_name": "kpi_summary",
                "payload": {"kpi_id": kpi_id, "window_days": 7},
            },
        )
        assert response.status_code == 200
        request_id = response.json()["request_id"]

        # Verify audit log
        db = TestingSessionLocal()
        try:
            audit_logs = db.query(AuditLog).filter(
                AuditLog.request_id == request_id
            ).all()
            assert len(audit_logs) == 1
            assert audit_logs[0].tool_name == "kpi_summary"

            # Verify usage event
            usage_events = db.query(UsageEvent).filter(
                UsageEvent.request_id == request_id
            ).all()
            assert len(usage_events) == 1
            assert usage_events[0].tool_name == "kpi_summary"
        finally:
            db.close()

    def test_kpi_summary_idempotent_replay_no_duplicate_logs(self, client, tenant, admin_user):
        """Test that idempotent replay of kpi_summary does NOT create more audit/usage logs."""
        # Create KPI and ingest points
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Idempotent Test KPI"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-01T00:00:00Z", "value": 100.0}]},
        )

        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
            "Idempotency-Key": "idempotent-kpi-summary-key",
        }
        body = {
            "tool_name": "kpi_summary",
            "payload": {"kpi_id": kpi_id, "window_days": 7},
        }

        # First request
        response1 = client.post("/v1/tools/invoke", headers=headers, json=body)
        assert response1.status_code == 200
        request_id1 = response1.json()["request_id"]

        # Second identical request (idempotent replay)
        response2 = client.post("/v1/tools/invoke", headers=headers, json=body)
        assert response2.status_code == 200
        request_id2 = response2.json()["request_id"]

        # Same request_id
        assert request_id1 == request_id2

        # Only one audit log and one usage event
        db = TestingSessionLocal()
        try:
            audit_logs = db.query(AuditLog).filter(
                AuditLog.request_id == request_id1
            ).all()
            assert len(audit_logs) == 1

            usage_events = db.query(UsageEvent).filter(
                UsageEvent.request_id == request_id1
            ).all()
            assert len(usage_events) == 1
        finally:
            db.close()

    def test_kpi_summary_zero_start_value_null_pct(self, client, tenant, admin_user):
        """Test that delta_pct is null when start value is 0."""
        # Create KPI
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Zero Start KPI"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        # Ingest points with start=0
        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={
                "points": [
                    {"ts": "2026-01-01T00:00:00Z", "value": 0.0},
                    {"ts": "2026-01-08T00:00:00Z", "value": 100.0},
                ]
            },
        )

        # Invoke kpi_summary
        response = client.post(
            "/v1/tools/invoke",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "zero-start-test",
            },
            json={
                "tool_name": "kpi_summary",
                "payload": {"kpi_id": kpi_id, "window_days": 7},
            },
        )
        assert response.status_code == 200
        result = response.json()["result"]

        assert result["start"]["value"] == 0.0
        assert result["latest"]["value"] == 100.0
        assert result["delta_abs"] == 100.0
        assert result["delta_pct"] is None  # Division by zero protection


# --- Brief Tests ---


class TestBriefMaterialize:
    """Tests for brief materialization endpoint."""

    def test_admin_can_materialize_brief(self, client, tenant, admin_user):
        """Test that admin can materialize a brief after creating KPI + points."""
        # Create KPI
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "MRR", "unit": "GBP"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        # Ingest points
        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 1250.0},
                ]
            },
        )

        # Materialize brief
        response = client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "brief-test-1",
            },
            json={"date": "2026-01-31", "window_days": 7, "top_n": 3},
        )
        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "brief_id" in data
        assert "request_id" in data
        assert "content" in data
        assert data["content"]["date"] == "2026-01-31"
        assert data["content"]["window_days"] == 7
        assert data["content"]["top_n"] == 3
        assert "summary" in data["content"]
        assert "highlights" in data["content"]
        assert "alerts" in data["content"]

        # Verify summary counts
        assert data["content"]["summary"]["kpis_considered"] == 1
        assert data["content"]["summary"]["kpis_up"] == 1
        assert data["content"]["summary"]["kpis_down"] == 0
        assert data["content"]["summary"]["kpis_flat"] == 0

    def test_materialize_creates_audit_and_usage(self, client, tenant, admin_user):
        """Test that materialize writes exactly 1 audit_log and 1 usage_event."""
        # Create KPI and points
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "DAU", "unit": "users"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 500.0}]},
        )

        # Materialize brief
        response = client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "audit-usage-brief-test",
            },
            json={"date": "2026-01-31"},
        )
        assert response.status_code == 200
        request_id = response.json()["request_id"]

        # Check database
        db = TestingSessionLocal()
        try:
            # Verify exactly 1 audit log
            audit_logs = db.query(AuditLog).filter(
                AuditLog.request_id == request_id
            ).all()
            assert len(audit_logs) == 1
            assert audit_logs[0].action == "briefs.materialize"
            assert audit_logs[0].tool_name == "daily_brief"

            # Verify exactly 1 usage event
            usage_events = db.query(UsageEvent).filter(
                UsageEvent.request_id == request_id
            ).all()
            assert len(usage_events) == 1
            assert usage_events[0].activity_type == "daily_brief_generated"
            assert usage_events[0].tool_name == "daily_brief"
            assert usage_events[0].units == 1
        finally:
            db.close()


class TestBriefIdempotency:
    """Tests for brief materialization idempotency."""

    def test_idempotent_returns_same_brief_id(self, client, tenant, admin_user):
        """Test that same Idempotency-Key + same body returns same brief_id."""
        # Create KPI and points
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Revenue"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 100.0}]},
        )

        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
            "Idempotency-Key": "idempotent-brief-test",
        }
        body = {"date": "2026-01-31", "window_days": 7, "top_n": 3}

        # First request
        response1 = client.post("/v1/briefs/materialize", headers=headers, json=body)
        assert response1.status_code == 200
        brief_id1 = response1.json()["brief_id"]

        # Second identical request
        response2 = client.post("/v1/briefs/materialize", headers=headers, json=body)
        assert response2.status_code == 200
        brief_id2 = response2.json()["brief_id"]

        # Same brief_id
        assert brief_id1 == brief_id2

    def test_idempotent_no_duplicate_audit_usage(self, client, tenant, admin_user):
        """Test that idempotent replay does NOT create additional audit/usage rows."""
        # Create KPI and points
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Sessions"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 200.0}]},
        )

        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
            "Idempotency-Key": "no-dup-audit-brief",
        }
        body = {"date": "2026-01-31"}

        # First request
        response1 = client.post("/v1/briefs/materialize", headers=headers, json=body)
        assert response1.status_code == 200
        request_id = response1.json()["request_id"]

        # Second identical request (idempotent replay)
        response2 = client.post("/v1/briefs/materialize", headers=headers, json=body)
        assert response2.status_code == 200

        # Check only 1 audit log and 1 usage event
        db = TestingSessionLocal()
        try:
            audit_logs = db.query(AuditLog).filter(
                AuditLog.request_id == request_id
            ).all()
            assert len(audit_logs) == 1

            usage_events = db.query(UsageEvent).filter(
                UsageEvent.request_id == request_id
            ).all()
            assert len(usage_events) == 1
        finally:
            db.close()

    def test_idempotency_conflict_different_body(self, client, tenant, admin_user):
        """Test that same Idempotency-Key with different body returns 409."""
        # Create KPI
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Conflict Test KPI"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 100.0}]},
        )

        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
            "Idempotency-Key": "conflict-brief-key",
        }

        # First request
        body1 = {"date": "2026-01-31", "window_days": 7}
        response1 = client.post("/v1/briefs/materialize", headers=headers, json=body1)
        assert response1.status_code == 200

        # Second request with different body
        body2 = {"date": "2026-01-31", "window_days": 14}  # Different window_days
        response2 = client.post("/v1/briefs/materialize", headers=headers, json=body2)
        assert response2.status_code == 409
        assert "already used with a different request body" in response2.json()["detail"]


class TestBriefRBAC:
    """Tests for brief RBAC (member cannot materialize, but can read)."""

    def test_member_cannot_materialize(self, client, tenant, member_user):
        """Test that member cannot materialize briefs - returns 403."""
        response = client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": member_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "member-attempt",
            },
            json={"date": "2026-01-31"},
        )
        assert response.status_code == 403
        assert "not authorized to materialize briefs" in response.json()["detail"]

    def test_member_can_get_brief_by_date(self, client, tenant, admin_user, member_user):
        """Test that member can GET /v1/briefs/{date}."""
        # Create KPI and points as admin
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Test KPI"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 100.0}]},
        )

        # Materialize as admin
        client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "admin-brief",
            },
            json={"date": "2026-01-31"},
        )

        # Fetch as member
        response = client.get(
            "/v1/briefs/2026-01-31",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": member_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
        )
        assert response.status_code == 200
        assert response.json()["content"]["date"] == "2026-01-31"

    def test_member_can_get_latest_brief(self, client, tenant, admin_user, member_user):
        """Test that member can GET /v1/briefs/latest."""
        # Create KPI and points as admin
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Latest Test KPI"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 100.0}]},
        )

        # Materialize as admin
        client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "admin-latest-brief",
            },
            json={"date": "2026-01-31"},
        )

        # Fetch latest as member
        response = client.get(
            "/v1/briefs/latest",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": member_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
        )
        assert response.status_code == 200
        assert response.json()["content"]["date"] == "2026-01-31"


class TestBriefTenantIsolation:
    """Tests for brief tenant isolation."""

    def test_tenant_cannot_fetch_other_tenant_brief(
        self, client, tenant, admin_user, other_tenant, other_tenant_user
    ):
        """Test that tenant A cannot fetch tenant B's brief (404)."""
        # Create KPI for tenant A
        kpi_response = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "Tenant A KPI"},
        )
        kpi_id = kpi_response.json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_id}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 100.0}]},
        )

        # Materialize brief for tenant A
        client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "tenant-a-brief",
            },
            json={"date": "2026-01-31"},
        )

        # Tenant B tries to fetch the same date - should get 404
        response = client.get(
            "/v1/briefs/2026-01-31",
            headers={
                "X-Tenant-ID": other_tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": other_tenant["api_key"],
            },
        )
        assert response.status_code == 404

    def test_two_tenants_same_date_independent_briefs(
        self, client, tenant, admin_user, other_tenant, other_tenant_user
    ):
        """Test that two tenants can create briefs for the same date independently."""
        # Create KPI for tenant A
        kpi_a = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"name": "KPI A"},
        ).json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_a}/points:bulk",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 100.0}]},
        )

        # Create KPI for tenant B
        kpi_b = client.post(
            "/v1/kpis",
            headers={
                "X-Tenant-ID": other_tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": other_tenant["api_key"],
            },
            json={"name": "KPI B"},
        ).json()["kpi_id"]

        client.post(
            f"/v1/kpis/{kpi_b}/points:bulk",
            headers={
                "X-Tenant-ID": other_tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": other_tenant["api_key"],
            },
            json={"points": [{"ts": "2026-01-31T00:00:00Z", "value": 200.0}]},
        )

        # Materialize brief for tenant A
        response_a = client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
                "Idempotency-Key": "tenant-a-iso",
            },
            json={"date": "2026-01-31"},
        )
        assert response_a.status_code == 200
        brief_id_a = response_a.json()["brief_id"]

        # Materialize brief for tenant B (same date)
        response_b = client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": other_tenant["tenant_id"],
                "X-User-ID": other_tenant_user["user_id"],
                "X-API-Key": other_tenant["api_key"],
                "Idempotency-Key": "tenant-b-iso",
            },
            json={"date": "2026-01-31"},
        )
        assert response_b.status_code == 200
        brief_id_b = response_b.json()["brief_id"]

        # Different brief IDs
        assert brief_id_a != brief_id_b


class TestBriefHighlightRanking:
    """Tests for highlight ranking correctness."""

    def test_highlights_ranked_by_abs_delta_pct(self, client, tenant, admin_user):
        """Test that highlights are ranked by ABS(delta_pct) descending."""
        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
        }

        # Create 3 KPIs with known deltas
        # KPI 1: 1000 -> 1100 = +10%
        kpi1 = client.post(
            "/v1/kpis", headers=headers, json={"name": "KPI1", "unit": "units"}
        ).json()["kpi_id"]
        client.post(
            f"/v1/kpis/{kpi1}/points:bulk",
            headers=headers,
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 1100.0},
                ]
            },
        )

        # KPI 2: 1000 -> 500 = -50%
        kpi2 = client.post(
            "/v1/kpis", headers=headers, json={"name": "KPI2", "unit": "units"}
        ).json()["kpi_id"]
        client.post(
            f"/v1/kpis/{kpi2}/points:bulk",
            headers=headers,
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 500.0},
                ]
            },
        )

        # KPI 3: 1000 -> 1250 = +25%
        kpi3 = client.post(
            "/v1/kpis", headers=headers, json={"name": "KPI3", "unit": "units"}
        ).json()["kpi_id"]
        client.post(
            f"/v1/kpis/{kpi3}/points:bulk",
            headers=headers,
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 1250.0},
                ]
            },
        )

        # Materialize brief with top_n=3
        response = client.post(
            "/v1/briefs/materialize",
            headers={**headers, "Idempotency-Key": "ranking-test"},
            json={"date": "2026-01-31", "window_days": 7, "top_n": 3},
        )
        assert response.status_code == 200
        highlights = response.json()["content"]["highlights"]

        # Order should be: KPI2 (-50%), KPI3 (+25%), KPI1 (+10%)
        assert len(highlights) == 3
        assert highlights[0]["name"] == "KPI2"  # abs(-50%) = 50%
        assert highlights[0]["delta_pct"] == -50.0
        assert highlights[1]["name"] == "KPI3"  # abs(+25%) = 25%
        assert highlights[1]["delta_pct"] == 25.0
        assert highlights[2]["name"] == "KPI1"  # abs(+10%) = 10%
        assert highlights[2]["delta_pct"] == 10.0

    def test_alerts_for_negative_delta_below_threshold(self, client, tenant, admin_user):
        """Test that alerts include KPIs with delta_pct <= -10%."""
        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
        }

        # KPI 1: 1000 -> 850 = -15% (should trigger alert)
        kpi1 = client.post(
            "/v1/kpis", headers=headers, json={"name": "Declining KPI"}
        ).json()["kpi_id"]
        client.post(
            f"/v1/kpis/{kpi1}/points:bulk",
            headers=headers,
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 850.0},
                ]
            },
        )

        # KPI 2: 1000 -> 1100 = +10% (no alert)
        kpi2 = client.post(
            "/v1/kpis", headers=headers, json={"name": "Growing KPI"}
        ).json()["kpi_id"]
        client.post(
            f"/v1/kpis/{kpi2}/points:bulk",
            headers=headers,
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 1100.0},
                ]
            },
        )

        # Materialize brief
        response = client.post(
            "/v1/briefs/materialize",
            headers={**headers, "Idempotency-Key": "alert-test"},
            json={"date": "2026-01-31", "window_days": 7, "top_n": 5},
        )
        assert response.status_code == 200
        alerts = response.json()["content"]["alerts"]

        # Only the declining KPI should trigger an alert
        assert len(alerts) == 1
        assert alerts[0]["name"] == "Declining KPI"
        assert alerts[0]["severity"] == "high"
        assert alerts[0]["reason"] == "delta_pct_below_threshold"
        assert alerts[0]["delta_pct"] == -15.0

    def test_summary_counts_correct(self, client, tenant, admin_user):
        """Test that summary counts (up/down/flat) are correct."""
        headers = {
            "X-Tenant-ID": tenant["tenant_id"],
            "X-User-ID": admin_user["user_id"],
            "X-API-Key": tenant["api_key"],
        }

        # KPI 1: +10% (up)
        kpi1 = client.post(
            "/v1/kpis", headers=headers, json={"name": "Up KPI"}
        ).json()["kpi_id"]
        client.post(
            f"/v1/kpis/{kpi1}/points:bulk",
            headers=headers,
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 100.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 110.0},
                ]
            },
        )

        # KPI 2: -20% (down)
        kpi2 = client.post(
            "/v1/kpis", headers=headers, json={"name": "Down KPI"}
        ).json()["kpi_id"]
        client.post(
            f"/v1/kpis/{kpi2}/points:bulk",
            headers=headers,
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 100.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 80.0},
                ]
            },
        )

        # KPI 3: 0% (flat)
        kpi3 = client.post(
            "/v1/kpis", headers=headers, json={"name": "Flat KPI"}
        ).json()["kpi_id"]
        client.post(
            f"/v1/kpis/{kpi3}/points:bulk",
            headers=headers,
            json={
                "points": [
                    {"ts": "2026-01-24T00:00:00Z", "value": 100.0},
                    {"ts": "2026-01-31T00:00:00Z", "value": 100.0},
                ]
            },
        )

        # Materialize brief
        response = client.post(
            "/v1/briefs/materialize",
            headers={**headers, "Idempotency-Key": "summary-test"},
            json={"date": "2026-01-31", "window_days": 7, "top_n": 5},
        )
        assert response.status_code == 200
        summary = response.json()["content"]["summary"]

        assert summary["kpis_considered"] == 3
        assert summary["kpis_up"] == 1
        assert summary["kpis_down"] == 1
        assert summary["kpis_flat"] == 1


class TestBriefMissingHeaders:
    """Tests for missing header validation on brief endpoints."""

    def test_materialize_missing_idempotency_key(self, client, tenant, admin_user):
        """Test that missing Idempotency-Key returns 400."""
        response = client.post(
            "/v1/briefs/materialize",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
            json={"date": "2026-01-31"},
        )
        assert response.status_code == 400
        assert "Idempotency-Key" in response.json()["detail"]

    def test_get_brief_missing_tenant_id(self, client):
        """Test that missing X-Tenant-ID returns 400."""
        response = client.get(
            "/v1/briefs/2026-01-31",
            headers={
                "X-User-ID": "some-user",
                "X-API-Key": "some-key",
            },
        )
        assert response.status_code == 400
        assert "X-Tenant-ID" in response.json()["detail"]


class TestBriefNotFound:
    """Tests for brief not found scenarios."""

    def test_get_brief_not_found(self, client, tenant, admin_user):
        """Test that fetching non-existent brief returns 404."""
        response = client.get(
            "/v1/briefs/2026-12-31",  # No brief for this date
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
        )
        assert response.status_code == 404

    def test_get_latest_no_briefs(self, client, tenant, admin_user):
        """Test that fetching latest when no briefs exist returns 404."""
        response = client.get(
            "/v1/briefs/latest",
            headers={
                "X-Tenant-ID": tenant["tenant_id"],
                "X-User-ID": admin_user["user_id"],
                "X-API-Key": tenant["api_key"],
            },
        )
        assert response.status_code == 404
