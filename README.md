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

### Item 3: Insight Materializer (Daily Briefs)
- Materialize daily briefs per tenant (one per date)
- Highlights ranked by absolute delta percentage
- Alerts for KPIs with significant decline (>= 10%)
- Full idempotency with Idempotency-Key header
- Audit logging and usage metering for brief generation

### Item 4: Notifications v0 + Daily Brief Runner
- User notification preferences (daily brief on/off, in_app delivery)
- Notification outbox for queued in-app notifications
- Daily brief runner job (creates brief + enqueues notifications)
- Runner idempotency (retries don't create duplicates)
- Dev console UI for inspecting database state

### Item 5: Cofounder Conversation API + Playground UI
- Conversation persistence (conversations + messages tables)
- Deterministic intent-based chat responses (no LLM required)
- Chat commands: brief, kpis, kpi:<name>, outbox, help
- Strict tenant isolation for conversations
- Audit logging and usage metering for every chat request
- Playground UI for interactive testing

## Quick Start

```bash
cd backend

# Install dependencies
poetry install

# Run the server
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
poetry run pytest tests/test_tools_invoke.py -v

# Run smoke tests (server must be running)
./scripts/smoke_phase0.sh         # KPI Store smoke test
./scripts/smoke_phase0_item3.sh   # Daily Briefs smoke test
./scripts/smoke_phase0_item4.sh   # Notifications + Runner smoke test
./scripts/smoke_phase0_item5.sh   # Cofounder Chat smoke test
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
| `POST /v1/briefs/materialize` | Materialize daily brief (admin only, idempotent) |
| `GET /v1/briefs/{date}` | Get brief by date |
| `GET /v1/briefs/latest` | Get most recent brief |
| `GET /v1/notifications/prefs` | Get user's notification preferences |
| `PUT /v1/notifications/prefs` | Update user's notification preferences |
| `GET /v1/notifications/outbox` | List user's notifications |
| `POST /v1/notifications/{id}/ack` | Acknowledge a notification |
| `POST /v1/jobs/daily-brief` | Run daily brief job (admin only, idempotent) |
| `POST /v1/conversations` | Create a new conversation |
| `GET /v1/conversations` | List user's conversations |
| `GET /v1/conversations/{id}` | Get conversation with messages |
| `POST /v1/cofounder/chat` | Send message to Cofounder assistant |
| `GET /ui` | Playground UI (requires PLAYGROUND_UI_ENABLED=1) |

See [backend/app/gateway/README.md](backend/app/gateway/README.md) for detailed API documentation.

## Example: Daily Brief Workflow

```bash
# 1. Create tenant and admin user (see Quick Start)

# 2. Create a KPI
curl -X POST http://localhost:8000/v1/kpis \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"name": "MRR", "unit": "GBP"}'

# 3. Ingest KPI points
curl -X POST "http://localhost:8000/v1/kpis/$KPI_ID/points:bulk" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "points": [
      {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
      {"ts": "2026-01-31T00:00:00Z", "value": 1250.0}
    ]
  }'

# 4. Materialize a daily brief (idempotent with Idempotency-Key)
curl -X POST http://localhost:8000/v1/briefs/materialize \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: my-unique-key" \
  -d '{"date": "2026-01-31", "window_days": 7, "top_n": 3}'

# 5. Fetch the brief (any user role)
curl http://localhost:8000/v1/briefs/2026-01-31 \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY"
```

## Dev Console (Database Inspector)

The Dev Console provides a read-only UI to inspect the database state. Useful for debugging and development.

### Enabling the Dev Console

Set these environment variables before starting the server:

```bash
export DEV_CONSOLE_ENABLED=1
export DEV_CONSOLE_KEY=your-secret-key

poetry run uvicorn app.main:app --reload
```

### Accessing the Console

Open in browser: `http://localhost:8000/console?key=your-secret-key`

### Available Pages

| URL | Description |
|-----|-------------|
| `/console?key=...` | Overview with database statistics |
| `/console/tenants?key=...` | List all tenants |
| `/console/tenants/{tenant_id}?key=...` | Tenant detail (users, KPIs, briefs, notifications) |
| `/console/db/{table}?key=...` | Table viewer (tenants, users, kpi_definitions, kpi_points, briefs, audit_logs, usage_events, idempotency_keys, notification_prefs, notification_outbox, conversations, messages) |
| `/console/db/download?key=...` | Download SQLite database file |

## Playground UI (Interactive Chat)

The Playground UI provides a user-facing interface for interacting with the Cofounder assistant.

### Enabling the Playground

Set the environment variable before starting the server:

```bash
export PLAYGROUND_UI_ENABLED=1

poetry run uvicorn app.main:app --reload
```

### Accessing the Playground

Open in browser: `http://localhost:8000/ui`

The UI allows you to:
- Configure credentials (Tenant ID, API Key, User ID) saved to localStorage
- Create and manage conversations
- Send messages and view assistant responses
- Use quick buttons for common commands

## Cofounder Chat Commands

The Cofounder assistant responds with deterministic, data-driven responses. No LLM API keys required.

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `today's brief` or `brief` | Get the latest daily brief with summary and highlights |
| `kpis` | List all KPIs with their latest values |
| `kpi:<name>` | Get detailed summary for a specific KPI (e.g., `kpi:MRR`) |
| `outbox` or `notifications` | View queued notifications |

### Example: Chat API

```bash
# Send a message (creates new conversation if conversation_id not provided)
curl -X POST http://localhost:8000/v1/cofounder/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message": "today'\''s brief"}'

# Continue conversation
curl -X POST http://localhost:8000/v1/cofounder/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"conversation_id": "...", "message": "kpis"}'
```

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
│   │   ├── gateway/             # Phase 0 implementation
│   │   │   ├── router.py        # API endpoints
│   │   │   ├── models.py        # Data models
│   │   │   ├── schemas.py       # Request/response schemas
│   │   │   ├── tools.py         # Tool registry
│   │   │   ├── rbac.py          # Access control
│   │   │   ├── idempotency.py   # Idempotency handling
│   │   │   └── briefs.py        # Brief generation logic
│   │   ├── console/             # Dev Console UI
│   │   │   └── router.py        # Console endpoints
│   │   └── playground/          # Playground UI
│   │       └── router.py        # Playground endpoints
│   └── tests/
│       └── test_tools_invoke.py # Comprehensive test suite
└── scripts/
    ├── smoke_phase0.sh          # KPI Store smoke test
    ├── smoke_phase0_item3.sh    # Daily Briefs smoke test
    ├── smoke_phase0_item4.sh    # Notifications + Runner smoke test
    └── smoke_phase0_item5.sh    # Cofounder Chat smoke test
```
