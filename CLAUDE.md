# CLAUDE.md - AI Assistant Guide for Bespin

This document provides AI assistants with essential context for working with the Bespin codebase.

## Project Overview

**Bespin** is a Tool Invocation Gateway (Phase 0) - a minimal, verifiable MVP for AI Co-Founder multi-tenant architecture. It provides:

- **Tool Invocation Gateway**: Multi-tenant tool execution with isolation, RBAC, audit logging, and idempotency
- **KPI Store**: Canonical data model for KPI definitions and time series data
- **kpi_summary tool**: Context-aware data analysis for KPI trends

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12+ | Core language |
| FastAPI | ^0.116.1 | Web framework with async support |
| SQLAlchemy | ^2.0.42 | ORM for database abstraction |
| SQLite | 3.x | Development database |
| psycopg | ^3.2.9 | PostgreSQL driver (production) |
| pytest | ^8.0.0 | Testing framework |
| httpx | ^0.27.0 | HTTP client for tests |
| Black | 23.3.0 | Code formatter (88 char lines) |
| Flake8 | 6.0.0 | Code linter |

## Codebase Structure

```
bespin/
├── backend/                          # Python FastAPI application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app entry point
│   │   ├── database.py               # SQLAlchemy setup & sessions
│   │   └── gateway/                  # Phase 0 core implementation
│   │       ├── models.py             # SQLAlchemy ORM models (9 tables)
│   │       ├── schemas.py            # Pydantic request/response schemas
│   │       ├── router.py             # FastAPI endpoints (7 routes)
│   │       ├── tools.py              # Tool registry & implementations
│   │       ├── rbac.py               # Role-based access control
│   │       ├── idempotency.py        # Idempotency handling
│   │       └── README.md             # Detailed API documentation
│   │
│   ├── tests/
│   │   └── test_tools_invoke.py      # Comprehensive test suite (50+ tests)
│   │
│   ├── pyproject.toml                # Poetry dependencies
│   ├── poetry.lock
│   └── .env                          # Environment variables (test keys)
│
├── scripts/
│   └── smoke_phase0.sh               # End-to-end smoke test
│
├── .pre-commit-config.yaml           # Pre-commit hooks
├── pyproject.toml                    # Root config (Black/Flake8 settings)
└── README.md                         # Project overview
```

## Development Commands

### Setup and Run

```bash
# Install dependencies
cd backend && poetry install

# Run development server
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
poetry run pytest tests/test_tools_invoke.py -v

# Run smoke test (requires running server)
./scripts/smoke_phase0.sh

# Code quality
poetry run black --check app/ tests/
poetry run flake8 app/ tests/
```

### Key File Locations

| Task | Files |
|------|-------|
| Add new endpoint | `backend/app/gateway/router.py` |
| Add new tool | `backend/app/gateway/tools.py` |
| Modify data models | `backend/app/gateway/models.py` |
| Update schemas | `backend/app/gateway/schemas.py` |
| Add/modify tests | `backend/tests/test_tools_invoke.py` |
| RBAC changes | `backend/app/gateway/rbac.py` |

## API Endpoints

| Method | Endpoint | Auth | RBAC | Purpose |
|--------|----------|------|------|---------|
| GET | `/healthz` | None | None | Health check |
| POST | `/v1/tenants` | None | None | Create tenant |
| POST | `/v1/users` | None | None | Create user |
| POST | `/v1/tools/invoke` | API Key | admin | Invoke tool |
| POST | `/v1/kpis` | API Key | admin | Create KPI definition |
| POST | `/v1/kpis/{kpi_id}/points:bulk` | API Key | admin | Bulk ingest KPI points |
| GET | `/v1/kpis` | API Key | admin/member | List KPI definitions |
| GET | `/v1/kpis/{kpi_id}/latest` | API Key | admin/member | Get latest KPI point |

### Required Headers

```
X-Tenant-ID: <tenant-uuid>
X-User-ID: <user-uuid>
X-API-Key: <tenant-api-key>
Idempotency-Key: <unique-request-key>  # For POST /v1/tools/invoke
```

## Code Patterns and Conventions

### Dependency Injection

All endpoints use FastAPI's dependency injection:

```python
from fastapi import Depends
from app.database import get_db
from app.gateway.router import get_tenant_context

@router.post("/v1/example")
def endpoint(
    request: RequestSchema,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context)
):
    ...
```

### TenantContext Pattern

Every authenticated endpoint receives tenant context:

```python
@dataclass
class TenantContext:
    tenant_id: str
    user_id: str
    tenant: GatewayTenant
    user: GatewayUser
```

### Tool Registration

Tools are registered via decorators:

```python
# Simple tool (no context needed)
@registry.register("tool_name")
def my_tool(payload: dict[str, Any]) -> dict[str, Any]:
    return {"result": payload}

# Context-aware tool (needs DB/tenant access)
@registry.register_context_tool("tool_name")
def my_context_tool(payload: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    # context.db, context.tenant_id available
    return {"result": ...}
```

### RBAC

Roles: `admin`, `member`

Permissions:
- `INVOKE_TOOLS`: admin only
- `KPI_WRITE`: admin only
- `KPI_READ`: admin + member

### Idempotency

- Uses SHA-256 hash of canonical JSON request body
- Same `Idempotency-Key` with same body = cached response replayed
- Same `Idempotency-Key` with different body = 409 Conflict
- Scoped per tenant

### Naming Conventions

| Item | Convention | Example |
|------|------------|---------|
| Database tables | snake_case, module prefix | `gateway_tenants`, `kpi_definitions` |
| API routes | RESTful, colon for actions | `/v1/kpis/{id}/points:bulk` |
| Headers | X- prefix for custom | `X-Tenant-ID`, `X-User-ID` |
| Python files | snake_case | `tools.py`, `idempotency.py` |
| Functions | snake_case | `get_tenant_context()` |
| Classes | PascalCase | `TenantContext`, `GatewayUser` |

### Code Style

- **Line length**: 88 characters (Black default)
- **Formatting**: Black
- **Linting**: Flake8 with E203, W503 ignored
- **Type hints**: Required throughout (Python 3.12 style)
- **Docstrings**: Required on classes and public functions

## Database Schema

### Tables

| Table | Purpose |
|-------|---------|
| `gateway_tenants` | Tenant registry with API keys |
| `gateway_users` | Users scoped to tenants with roles |
| `audit_logs` | Immutable tool invocation log |
| `usage_events` | Metering events for billing |
| `idempotency_keys` | Prevents duplicate processing |
| `kpi_definitions` | KPI metadata (name, unit, description) |
| `kpi_points` | Time series data (tenant_id, kpi_id, ts, value) |

### Key Constraints

- All tables have `tenant_id` for multi-tenant isolation
- UUIDs (36 chars) for tenant_id, user_id, kpi_id, request_id
- ISO 8601 timestamps with 'Z' suffix for KPI data
- Unique constraint on `(tenant_id, kpi_id, ts)` for KPI points

## Testing Guidelines

### Test Structure

Tests use pytest with FastAPI TestClient and in-memory SQLite:

```python
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db

# Override database for tests
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)
```

### Test Categories

1. **Authentication**: API key validation
2. **Authorization**: RBAC enforcement
3. **Tenant Isolation**: Cross-tenant data protection
4. **Idempotency**: Replay detection
5. **Audit/Usage**: Record creation verification
6. **Error Handling**: 400, 401, 403, 404, 409 responses

### Running Tests

```bash
cd backend
poetry run pytest tests/test_tools_invoke.py -v          # All tests
poetry run pytest tests/test_tools_invoke.py -v -k auth  # Filter by name
poetry run pytest tests/test_tools_invoke.py -v -x       # Stop on first failure
```

## Common AI Assistant Tasks

### Adding a New Tool

1. Edit `backend/app/gateway/tools.py`
2. Register with `@registry.register("name")` or `@registry.register_context_tool("name")`
3. Add tests in `backend/tests/test_tools_invoke.py`
4. Update documentation if needed

### Adding a New Endpoint

1. Add route in `backend/app/gateway/router.py`
2. Add Pydantic schemas in `backend/app/gateway/schemas.py`
3. Add ORM models if needed in `backend/app/gateway/models.py`
4. Add RBAC permission check if authenticated
5. Add tests in `backend/tests/test_tools_invoke.py`

### Modifying RBAC

1. Edit `backend/app/gateway/rbac.py`
2. Add new permission to `Permission` enum
3. Map permission to roles in `ROLE_PERMISSIONS`
4. Add helper function if needed
5. Update tests

## Error Response Format

```json
{
  "detail": "Error message",
  "error_code": "ERROR_CODE"
}
```

| Status | Meaning |
|--------|---------|
| 400 | Missing required header/parameter |
| 401 | Invalid tenant ID or API key |
| 403 | User not found, wrong tenant, or insufficient permissions |
| 404 | Resource not found (tool, KPI, etc.) |
| 409 | Idempotency conflict (same key, different body) |

## Security Considerations

**Implemented:**
- API key authentication
- Tenant isolation in all queries
- Role-based access control
- Audit logging
- Idempotency protection
- Input validation via Pydantic

**Not implemented (MVP scope):**
- Rate limiting
- JWT/OAuth
- HTTPS enforcement (handled by deployment)

## Git Workflow

- Pre-commit hooks enforce Black and Flake8
- Run `poetry run black app/ tests/` before committing
- All tests should pass before pushing

## Quick Reference

```bash
# Start server
cd backend && poetry run uvicorn app.main:app --reload --port 8000

# Run all tests
poetry run pytest tests/ -v

# Format code
poetry run black app/ tests/

# Lint code
poetry run flake8 app/ tests/
```
