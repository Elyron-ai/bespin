# Bespin - Tool Invocation Gateway (Phase 0)

A minimal, verifiable MVP for the AI Co-Founder multi-tenant architecture.

## Phase 0 Deliverables

### Item 1: Tool Invocation Gateway
- Multi-tenant architecture with complete isolation
- API key authentication with tenant context
- Role-based access control (admin, member)
- Audit logging for every tool invocation
- Usage metering for billing/analytics
- Idempotency support for retry safety

### Item 2: KPI Store + Ingestion API
- Canonical data model for KPIs (definitions + time series points)
- Bulk ingestion API for time series data
- `kpi_summary` tool for context-aware data analysis

## Quick Start

```bash
cd backend

# Install dependencies
poetry install

# Run the server
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
poetry run pytest tests/test_tools_invoke.py -v

# Run smoke test (server must be running)
./scripts/smoke_phase0.sh
```

## API Overview

| Endpoint | Description |
|----------|-------------|
| `POST /v1/tenants` | Create tenant (open) |
| `POST /v1/users` | Create user |
| `POST /v1/tools/invoke` | Invoke tool (admin only) |
| `POST /v1/kpis` | Create KPI definition (admin only) |
| `POST /v1/kpis/{kpi_id}/points:bulk` | Bulk ingest KPI points (admin only) |
| `GET /v1/kpis` | List KPI definitions |
| `GET /v1/kpis/{kpi_id}/latest` | Get latest KPI point |

See [backend/app/gateway/README.md](backend/app/gateway/README.md) for detailed API documentation.

## Tech Stack

- Python 3.12+
- FastAPI + Uvicorn
- SQLAlchemy + SQLite
- pytest + httpx

## Project Structure

```
bespin/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── database.py          # SQLAlchemy setup
│   │   └── gateway/             # Phase 0 implementation
│   │       ├── router.py        # API endpoints
│   │       ├── models.py        # Data models
│   │       ├── schemas.py       # Request/response schemas
│   │       ├── tools.py         # Tool registry
│   │       ├── rbac.py          # Access control
│   │       └── idempotency.py   # Idempotency handling
│   └── tests/
│       └── test_tools_invoke.py # Comprehensive test suite
└── scripts/
    └── smoke_phase0.sh          # End-to-end smoke test
```
