# Tool Invocation Gateway v0

A minimal, verifiable Phase 0 deliverable for the AI Co-Founder architecture.

## Overview

This gateway proves the following core capabilities:

1. **Tenant Scoping**: Every request requires tenant context (no tenant = fail)
2. **RBAC Enforcement**: Users must belong to tenant and have permission
3. **Audit Logging**: Every tool invocation writes an audit log record
4. **Usage Metering**: Every tool invocation emits a usage/metering event
5. **Idempotency**: Prevents double-charging/double-logging on retries
6. **KPI Store**: Canonical data model for KPIs with time series ingestion and querying

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
PYTHONPATH=. pytest tests/test_tools_invoke.py -v

# Or using poetry
poetry run pytest tests/test_tools_invoke.py -v
```

## Run Smoke Test

```bash
# Start server first, then in another terminal:
./scripts/smoke_phase0.sh
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

Available tools: `echo`, `kpi_summary`

### 4. Create KPI Definition (Admin Only)

```
POST /v1/kpis
```

Required Headers: `X-Tenant-ID`, `X-User-ID`, `X-API-Key`

### 5. Bulk Ingest KPI Points (Admin Only)

```
POST /v1/kpis/{kpi_id}/points:bulk
```

Required Headers: `X-Tenant-ID`, `X-User-ID`, `X-API-Key`

### 6. List KPI Definitions (Admin & Member)

```
GET /v1/kpis
```

Required Headers: `X-Tenant-ID`, `X-User-ID`, `X-API-Key`

### 7. Get Latest KPI Point (Admin & Member)

```
GET /v1/kpis/{kpi_id}/latest
```

Required Headers: `X-Tenant-ID`, `X-User-ID`, `X-API-Key`

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

### 4. Create a KPI Definition

```bash
curl -X POST http://localhost:8000/v1/kpis \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: 660e8400-e29b-41d4-a716-446655440001" \
  -H "X-API-Key: abc123xyz..." \
  -d '{"name": "MRR", "unit": "GBP", "description": "Monthly recurring revenue"}'
```

Response:
```json
{
  "kpi_id": "880e8400-e29b-41d4-a716-446655440003",
  "name": "MRR",
  "unit": "GBP",
  "description": "Monthly recurring revenue"
}
```

### 5. Bulk Ingest KPI Points

```bash
curl -X POST http://localhost:8000/v1/kpis/880e8400-e29b-41d4-a716-446655440003/points:bulk \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: 660e8400-e29b-41d4-a716-446655440001" \
  -H "X-API-Key: abc123xyz..." \
  -d '{
    "points": [
      {"ts": "2026-01-01T00:00:00Z", "value": 1000.0},
      {"ts": "2026-01-08T00:00:00Z", "value": 1250.0}
    ]
  }'
```

Response:
```json
{
  "inserted": 2,
  "ignored": 0
}
```

### 6. Invoke kpi_summary Tool

```bash
curl -X POST http://localhost:8000/v1/tools/invoke \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: 660e8400-e29b-41d4-a716-446655440001" \
  -H "X-API-Key: abc123xyz..." \
  -H "Idempotency-Key: kpi-summary-request-1" \
  -d '{
    "tool_name": "kpi_summary",
    "payload": {
      "kpi_id": "880e8400-e29b-41d4-a716-446655440003",
      "window_days": 7
    }
  }'
```

Response:
```json
{
  "request_id": "990e8400-e29b-41d4-a716-446655440004",
  "result": {
    "kpi_id": "880e8400-e29b-41d4-a716-446655440003",
    "latest": {"ts": "2026-01-08T00:00:00Z", "value": 1250.0},
    "start": {"ts": "2026-01-01T00:00:00Z", "value": 1000.0},
    "delta_abs": 250.0,
    "delta_pct": 25.0
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
- **kpi_definitions**: KPI definitions scoped to tenants (name, unit, description)
- **kpi_points**: Time series data points for KPIs (tenant_id, kpi_id, ts, value)

### RBAC

Currently implemented roles:
- **admin**: Can invoke tools, create KPI definitions, ingest KPI points
- **member**: Can read KPIs (list definitions, get latest point)

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
