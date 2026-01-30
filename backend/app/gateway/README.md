# Tool Invocation Gateway v0

A minimal, verifiable Phase 0 deliverable for the AI Co-Founder architecture.

## Overview

This gateway proves the following core capabilities:

1. **Tenant Scoping**: Every request requires tenant context (no tenant = fail)
2. **RBAC Enforcement**: Users must belong to tenant and have permission
3. **Audit Logging**: Every tool invocation writes an audit log record
4. **Usage Metering**: Every tool invocation emits a usage/metering event
5. **Idempotency**: Prevents double-charging/double-logging on retries

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLite (via SQLAlchemy)
- Pydantic models
- pytest + httpx for tests

## Setup

```bash
cd backend

# Install dependencies
pip install poetry
poetry install

# Or with pip
pip install -r requirements.txt
```

## Run Server

```bash
cd backend

# Using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using poetry
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server will be available at `http://localhost:8000`.

## Run Tests

```bash
cd backend

# Using pytest directly
pytest tests/test_tools_invoke.py -v

# Or using poetry
poetry run pytest tests/test_tools_invoke.py -v
```

## API Endpoints

### 1. Create Tenant (Open - No Auth)

```
POST /v1/tenants
```

Creates a new tenant with auto-generated UUID and API key.

### 2. Create User

```
POST /v1/users
```

Creates a user under a tenant. Roles: `admin` or `member`.

### 3. Invoke Tool

```
POST /v1/tools/invoke
```

Required Headers:
- `X-Tenant-ID`: Tenant UUID
- `X-User-ID`: User UUID
- `X-API-Key`: Tenant API key
- `Idempotency-Key`: Unique key for idempotent requests

## Example curl Sequence

### 1. Create a Tenant

```bash
curl -X POST http://localhost:8000/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "region": "us-east-1"}'
```

Response:
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Acme Corp",
  "region": "us-east-1",
  "api_key": "abc123xyz...",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 2. Create an Admin User

```bash
curl -X POST http://localhost:8000/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "admin@acme.com",
    "role": "admin"
  }'
```

Response:
```json
{
  "user_id": "660e8400-e29b-41d4-a716-446655440001",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "admin@acme.com",
  "role": "admin",
  "created_at": "2024-01-15T10:31:00Z"
}
```

### 3. Invoke the Echo Tool

```bash
curl -X POST http://localhost:8000/v1/tools/invoke \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: 660e8400-e29b-41d4-a716-446655440001" \
  -H "X-API-Key: abc123xyz..." \
  -H "Idempotency-Key: my-unique-request-1" \
  -d '{"tool_name": "echo", "payload": {"text": "Hello, World!"}}'
```

Response:
```json
{
  "request_id": "770e8400-e29b-41d4-a716-446655440002",
  "result": {
    "echo": {
      "text": "Hello, World!"
    }
  }
}
```

## Data Model

### Tables

- **gateway_tenants**: Tenant registry with API keys
- **gateway_users**: Users scoped to tenants with roles
- **audit_logs**: Immutable log of all tool invocations
- **usage_events**: Metering events for billing/analytics
- **idempotency_keys**: Prevents duplicate processing

### RBAC

Currently implemented roles:
- **admin**: Can invoke tools
- **member**: Cannot invoke tools (future: read-only access)

## Error Responses

| Status | Condition |
|--------|-----------|
| 400 | Missing required header |
| 401 | Invalid tenant ID or API key |
| 403 | User not found, wrong tenant, or insufficient permissions |
| 404 | Tool not found |
| 409 | Idempotency key reused with different request body |

## Architecture Notes

- **TenantContext**: Populated from headers via FastAPI dependency
- **Idempotency**: Uses SHA-256 hash of canonical JSON to detect body changes
- **Tool Registry**: In-process registry with decorator-based registration
- **Audit/Usage**: Written transactionally after successful tool execution
