"""Tests for the Tool Invocation Gateway."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.gateway.models import AuditLog, UsageEvent


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
