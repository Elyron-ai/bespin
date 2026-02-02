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

### Item 6: Tenant Limits + Quota Enforcement + Usage Ledger
- Per-tenant daily quotas for key activity types
- Inline quota enforcement on chat, tools/invoke, briefs, and job runner
- Daily usage rollup table for efficient quota checking
- Limits and usage summary API endpoints
- Usage panel in Playground UI with warning indicators
- Idempotent replays do NOT consume quota

### Item 7: Plans + Entitlements + Metered Events + Weighted Costs
- **Metered Event Catalog**: Define event types with credits/unit weights and list prices
- **Plans**: Monthly billing with included credits and overage pricing
- **Capabilities**: Per-plan feature entitlements (chat, tools, briefs, notifications, kpi_ingest, kpi_read)
- **Tenant Subscriptions**: Auto-assign starter plan on tenant creation
- **Credits-based Quotas**: Enforce monthly credit limits + optional per-event caps
- **Usage Consumption**: Materialized monthly rollups with credits and estimated costs
- **Platform Admin APIs**: Manage metered events, plans, and subscriptions
- **Tenant Billing APIs**: View plan, usage, and ledger

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
./scripts/smoke_phase0_item6.sh   # Quota Enforcement smoke test
./scripts/smoke_phase0_item7.sh   # Billing + Metering smoke test
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
| `GET /v1/limits` | Get tenant's daily quota limits |
| `PUT /v1/limits` | Update tenant's daily quota limits (admin only) |
| `GET /v1/usage/daily` | Get daily usage summary for the tenant |
| `GET /v1/billing/events` | Get active metered event types |
| `GET /v1/billing/plan` | Get tenant subscription with plan details |
| `GET /v1/billing/usage` | Get billing usage (credits used, remaining, breakdown) |
| `GET /v1/billing/ledger` | Get usage event ledger for the period |
| `GET /v1/admin/metered-events` | List metered events (platform admin) |
| `POST /v1/admin/metered-events` | Create metered event (platform admin) |
| `PUT /v1/admin/metered-events/{event_key}` | Update metered event (platform admin) |
| `GET /v1/admin/plans` | List plans (platform admin) |
| `POST /v1/admin/plans` | Create plan (platform admin) |
| `PUT /v1/admin/plans/{plan_id}` | Update plan (platform admin) |
| `PUT /v1/admin/plans/{plan_id}/capabilities` | Set plan capabilities (platform admin) |
| `PUT /v1/admin/plans/{plan_id}/caps` | Set plan event caps (platform admin) |
| `PUT /v1/admin/tenants/{tenant_id}/subscription` | Update tenant subscription (platform admin) |
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

## Quota Enforcement

Bespin enforces per-tenant daily quotas on key activity types to manage usage and prevent abuse.

### Activity Types and Default Limits

| Activity Type | Default Daily Limit | Enforced On |
|---------------|---------------------|-------------|
| `assistant_query` | 100 | `/v1/cofounder/chat` |
| `tool_invocation` | 100 | `/v1/tools/invoke` |
| `daily_brief_generated` | 10 | `/v1/briefs/materialize`, `/v1/jobs/daily-brief` |
| `notification_enqueued` | 500 | `/v1/jobs/daily-brief` |

### Quota Behavior

- When quota is exceeded, the endpoint returns HTTP 429 with structured error:
  ```json
  {
    "error": "quota_exceeded",
    "activity_type": "assistant_query",
    "limit": 100,
    "current": 100,
    "requested": 1
  }
  ```

- **Idempotent replays do NOT consume quota**: When using the same `Idempotency-Key` for tool invocation or daily brief, replays return the cached response without incrementing usage.

- **Partial notification enqueue**: The daily-brief runner will insert as many notifications as quota allows and report `notifications_suppressed_due_to_quota` for the rest.

### Managing Limits

```bash
# Get current limits
curl http://localhost:8000/v1/limits \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY"

# Update limits (admin only)
curl -X PUT http://localhost:8000/v1/limits \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "assistant_query_daily_limit": 200,
    "tool_invocation_daily_limit": 200,
    "daily_brief_generated_daily_limit": 20,
    "notification_enqueued_daily_limit": 1000
  }'

# Get daily usage summary
curl http://localhost:8000/v1/usage/daily \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY"
```

## Billing and Metering (Item #7)

Bespin implements a usage-based billing system with credits, plans, and entitlements.

### Platform Admin API

Platform admin endpoints require the `X-Platform-Admin-Key` header. Set the key via environment variable:

```bash
export PLATFORM_ADMIN_KEY=your-admin-key
```

### Default Metered Events

| Event Key | Unit | Credits/Unit | Price/Credit | Description |
|-----------|------|--------------|--------------|-------------|
| `assistant_query` | call | 1.0 | $0.02 | Chat message to assistant |
| `tool_invocation` | call | 2.0 | $0.02 | Tool invoked via API |
| `daily_brief_generated` | brief | 5.0 | $0.02 | Brief materialized |
| `notification_enqueued` | notification | 0.2 | $0.02 | Notification queued |
| `kpi_definition_created` | kpi | 0.5 | $0.02 | KPI definition created |
| `kpi_points_ingested` | row | 0.001 | $0.02 | KPI data point ingested |

### Default Plans

| Plan ID | Name | Monthly Credits | Overage Price |
|---------|------|-----------------|---------------|
| `starter` | Starter | 500 | $0.02/credit |
| `growth` | Growth | 2000 | $0.015/credit |
| `scale` | Scale | 10000 | $0.01/credit |

All plans include all capabilities by default. The `starter` plan has optional caps on `daily_brief_generated` (50/month) and `tool_invocation` (2000/month).

### How Quotas Work

1. **Credits Quota**: Total credits used in billing period must not exceed `plan.included_credits`
2. **Per-Event Caps** (optional): Individual event types can have raw unit caps per period
3. **Idempotency**: Replays with same `Idempotency-Key` return cached response WITHOUT consuming credits
4. **Partial Enqueue**: Daily brief runner enqueues as many notifications as quota allows

### Viewing Usage

```bash
# Get current plan and subscription
curl http://localhost:8000/v1/billing/plan \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY"

# Get billing usage (credits used, remaining, breakdown by event)
curl http://localhost:8000/v1/billing/usage \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY"
```

Example response:
```json
{
  "period_start": "2026-02-01",
  "period_end": "2026-03-01",
  "plan": {"plan_id": "starter", "name": "Starter", "included_credits": 500, ...},
  "credits": {
    "included": 500,
    "used": 23.4,
    "remaining": 476.6,
    "overage_credits": 0,
    "estimated_overage_cost": 0.0,
    "estimated_list_cost": 0.468
  },
  "breakdown": [
    {"event_key": "assistant_query", "unit_name": "call", "raw_units": 12, "credits": 12.0, "list_cost_estimate": 0.24},
    {"event_key": "tool_invocation", "unit_name": "call", "raw_units": 5, "credits": 10.0, "list_cost_estimate": 0.20}
  ]
}
```

### Changing Event Weights (Admin)

Update the `credits_per_unit` for an event type to change how much it costs:

```bash
curl -X PUT http://localhost:8000/v1/admin/metered-events/assistant_query \
  -H "Content-Type: application/json" \
  -H "X-Platform-Admin-Key: $ADMIN_KEY" \
  -d '{"credits_per_unit": 5.0}'
```

Changes take effect for NEW usage events only (existing events keep their original credits).

### Assigning Plans (Admin)

```bash
curl -X PUT http://localhost:8000/v1/admin/tenants/$TENANT_ID/subscription \
  -H "Content-Type: application/json" \
  -H "X-Platform-Admin-Key: $ADMIN_KEY" \
  -d '{"plan_id": "growth", "status": "active"}'
```

### Running the Billing Smoke Test

```bash
export PLATFORM_ADMIN_KEY=adminkey
./scripts/smoke_phase0_item7.sh
```

The smoke test demonstrates:
1. Creating a tenant and viewing initial usage
2. Updating event weights and verifying consumption
3. Testing quota enforcement with a limited plan
4. Running the daily brief job with notification metering

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
│   │   │   ├── briefs.py        # Brief generation logic
│   │   │   ├── quota.py         # Legacy daily quota enforcement
│   │   │   ├── billing_period.py # Billing period utilities
│   │   │   ├── billing_seed.py  # Default billing data
│   │   │   ├── billing_router.py # Admin + tenant billing APIs
│   │   │   ├── metering.py      # Centralized usage emission
│   │   │   └── entitlements.py  # Capability + credits quota enforcement
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
    ├── smoke_phase0_item5.sh    # Cofounder Chat smoke test
    ├── smoke_phase0_item6.sh    # Quota Enforcement smoke test
    └── smoke_phase0_item7.sh    # Billing + Metering smoke test
```
