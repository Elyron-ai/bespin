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

### Item 8: Core Business OS Primitives v0
- **Action Center**: Proposed actions with approval workflow (propose → approve/reject → execute)
- **Tasks**: Work OS tasks with assignment, priority, due dates, and completion tracking
- **Decisions**: Strategic decisions log with rationale and context
- **Meeting Notes**: Meeting documentation with entity linking
- **Governed Memory**: Admin-curated facts about the business (ICP, pricing, goals, etc.)
- **Evidence/Provenance Links**: Link supporting evidence to actions, tasks, decisions, and facts
- **Unified Timeline**: User-facing "what happened" event stream
- **Global Search**: Search across all core entities (tenant-scoped)
- **Record Explorer**: Drilldown view with entity, evidence, and timeline

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
./scripts/smoke_phase0.sh                    # KPI Store smoke test
./scripts/smoke_phase0_item3.sh              # Daily Briefs smoke test
./scripts/smoke_phase0_item4.sh              # Notifications + Runner smoke test
./scripts/smoke_phase0_item5.sh              # Cofounder Chat smoke test
./scripts/smoke_phase0_item6.sh              # Quota Enforcement smoke test
./scripts/smoke_phase0_item7.sh              # Billing + Metering smoke test
./scripts/smoke_core_os_v0.sh                # Core Business OS smoke test
./scripts/smoke_phase1_task8a_actions_v0.sh  # Actions v0 smoke test
./scripts/smoke_phase1_task8b_action_approvals.sh  # Action Approvals smoke test
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
| `GET /app` | Core Business OS UI (requires PLAYGROUND_UI_ENABLED=1) |
| **Core Business OS - Actions** | |
| `POST /v1/actions` | Create action (proposed state) |
| `GET /v1/actions` | List actions (filters: status, created_by_user_id, assigned_to_user_id) |
| `GET /v1/actions/{action_id}` | Get action by ID |
| `PATCH /v1/actions/{action_id}` | Update action (creator or admin) |
| `POST /v1/actions/{action_id}/cancel` | Cancel proposed action (creator or admin) |
| `POST /v1/actions/{action_id}/approve` | Approve action (admin only) |
| `POST /v1/actions/{action_id}/reject` | Reject action (admin only) |
| `POST /v1/actions/{action_id}/execute` | Execute action (admin only) |
| **Core Business OS - Tasks** | |
| `POST /v1/tasks` | Create task |
| `GET /v1/tasks` | List tasks (optional status, priority, assignee filters) |
| `GET /v1/tasks/{task_id}` | Get task by ID |
| `PATCH /v1/tasks/{task_id}` | Update task |
| `POST /v1/tasks/{task_id}/complete` | Complete task |
| **Core Business OS - Decisions** | |
| `POST /v1/decisions` | Create decision (admin only) |
| `GET /v1/decisions` | List decisions |
| `GET /v1/decisions/{decision_id}` | Get decision by ID |
| `PATCH /v1/decisions/{decision_id}` | Update decision (admin only) |
| **Core Business OS - Meetings** | |
| `POST /v1/meetings` | Create meeting note |
| `GET /v1/meetings` | List meetings |
| `GET /v1/meetings/{meeting_id}` | Get meeting by ID |
| `PATCH /v1/meetings/{meeting_id}` | Update meeting |
| **Core Business OS - Memory** | |
| `POST /v1/memory/facts` | Create fact (admin only) |
| `GET /v1/memory/facts` | List facts (optional category filter) |
| `GET /v1/memory/facts/{fact_id}` | Get fact by ID |
| `PATCH /v1/memory/facts/{fact_id}` | Update fact (admin only) |
| `POST /v1/memory/facts/{fact_id}/supersede` | Supersede fact (admin only) |
| **Core Business OS - Evidence** | |
| `POST /v1/evidence` | Create evidence link |
| `GET /v1/evidence` | List evidence for entity |
| **Core Business OS - Timeline & Search** | |
| `GET /v1/timeline` | Get timeline events (paginated) |
| `GET /v1/search` | Global search across entities |
| `GET /v1/records/{entity_type}/{entity_id}` | Record explorer (entity + evidence + timeline) |

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
| **Core Business OS** | | | | |
| `action_created` | record | 0.2 | $0.02 | Action created |
| `action_approved` | event | 0.2 | $0.02 | Action approved |
| `action_rejected` | event | 0.1 | $0.02 | Action rejected |
| `action_executed` | event | 0.5 | $0.02 | Action executed |
| `task_created` | record | 0.1 | $0.02 | Task created |
| `task_updated` | record | 0.05 | $0.02 | Task updated |
| `task_completed` | record | 0.1 | $0.02 | Task completed |
| `decision_created` | record | 0.2 | $0.02 | Decision created |
| `decision_updated` | record | 0.1 | $0.02 | Decision updated |
| `meeting_created` | record | 0.15 | $0.02 | Meeting note created |
| `meeting_updated` | record | 0.05 | $0.02 | Meeting note updated |
| `memory_fact_created` | record | 0.2 | $0.02 | Memory fact created |
| `memory_fact_updated` | record | 0.1 | $0.02 | Memory fact updated |
| `memory_fact_superseded` | record | 0.15 | $0.02 | Memory fact superseded |
| `evidence_created` | record | 0.1 | $0.02 | Evidence link created |
| `search_query` | call | 0.05 | $0.02 | Global search query |
| `timeline_query` | call | 0.02 | $0.02 | Timeline query |
| `record_explorer_query` | call | 0.05 | $0.02 | Record explorer query |

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

## Core Business OS (Item #8)

The Core Business OS provides primitives for managing business operations: actions, tasks, decisions, meetings, memory, and evidence linking.

### RBAC Rules Summary

| Entity | Create | Read | Update | Delete/Special |
|--------|--------|------|--------|----------------|
| **Actions** | Any user | Any user | Creator or admin | Cancel: creator or admin (proposed only); Approve/Reject/Execute: admin only |
| **Tasks** | Any user | Any user | Any user | Complete: assignee or admin |
| **Decisions** | Admin only | Any user | Admin only | - |
| **Meetings** | Any user | Any user | Creator or admin | - |
| **Memory Facts** | Admin only | Any user | Admin only | Supersede: admin only |
| **Evidence** | Any user | Any user | - | - |
| **Timeline** | - | Any user | - | Auto-populated |
| **Search** | - | Any user | - | - |

### Core OS Capabilities

New capabilities added to plans:

| Capability | Description |
|------------|-------------|
| `action_center` | Access to Action Center APIs |
| `tasks` | Access to Tasks APIs |
| `decisions` | Access to Decisions APIs |
| `meetings` | Access to Meetings APIs |
| `memory` | Access to Memory Facts APIs |
| `timeline` | Access to Timeline APIs |
| `search` | Access to Global Search APIs |

### Core OS UI

Access the Core Business OS UI at `http://localhost:8000/app` (requires `PLAYGROUND_UI_ENABLED=1`).

Features:
- **Actions**: Create, view, approve/reject, execute actions
- **Tasks**: Create, assign, track, complete tasks
- **Decisions**: Log strategic decisions (admin only)
- **Meetings**: Document meeting notes
- **Memory**: Curate business facts (ICP, goals, pricing)
- **Search**: Global search across all entities
- **Timeline**: View recent activity stream

### Running the Core OS Smoke Test

```bash
# Server must be running
./scripts/smoke_core_os_v0.sh
```

The smoke test demonstrates:
1. Creating a tenant with admin and member users
2. Admin creates memory fact (ICP definition)
3. Admin creates decision (pricing strategy)
4. Member creates action (proposed outreach)
5. Admin approves and executes the action
6. Admin creates task assigned to member
7. Member completes the task
8. Admin creates meeting note
9. Admin attaches evidence to decision
10. Member performs global search
11. Fetching unified timeline
12. Viewing billing usage for Core OS operations

### Running the Actions v0 Smoke Test (Phase 1 Task 8a)

```bash
# Server must be running
./scripts/smoke_phase1_task8a_actions_v0.sh
```

The Actions v0 smoke test demonstrates:
1. Creating a tenant with admin and member users
2. Member creates an action (status: proposed)
3. Listing actions with status filters (proposed, cancelled, all)
4. Member cancels their own action
5. Verifying action status changed to cancelled
6. Fetching billing usage to see action_created and action_updated events

### Running the Action Approvals Smoke Test (Phase 1 Task 8b)

```bash
# Server must be running
./scripts/smoke_phase1_task8b_action_approvals.sh
```

The Action Approvals smoke test demonstrates:
1. Creating a tenant with admin and member users
2. Member creates 2 proposed actions
3. Admin approves first action with comment
4. Admin rejects second action with comment
5. Listing actions by status (all, approved, rejected)
6. Fetching timeline showing approval/rejection events
7. Verifying billing usage for action_approved/action_rejected
8. Testing idempotent retry (already approved -> 200)
9. Testing conflict transitions (approve then reject -> 409)
10. Testing RBAC (member cannot approve -> 403)

### Action Status Values

Actions can have the following statuses:
- `proposed` - Initial state when action is created
- `approved` - Admin approved the action
- `rejected` - Admin rejected the action
- `cancelled` - Creator or admin cancelled the action
- `executed` - Action has been executed (Phase 1 Task 8c)

### Action Review Log (v0)

- Each action can have at most **one review** (approval or rejection)
- Once approved or rejected, the decision cannot be changed (returns 409 Conflict)
- Cancelled actions cannot be approved or rejected (returns 409 Conflict)
- Review records are stored in the `action_reviews` table with:
  - `reviewer_user_id`: The admin who made the decision
  - `decision`: "approved" or "rejected"
  - `comment`: Optional reviewer comment
  - `created_at`: Timestamp of the review

### Idempotent Approve/Reject Behavior

- **Approving an already approved action**: Returns 200 with current action state, no additional writes
- **Rejecting an already rejected action**: Returns 200 with current action state, no additional writes
- **Changing a decision** (approve then reject, or vice versa): Returns 409 Conflict

### Actions v0 Metered Events

| Event Key | Unit | Credits/Unit | Description |
|-----------|------|--------------|-------------|
| `action_created` | record | 0.2 | Action created (any status) |
| `action_updated` | record | 0.1 | Action updated (including cancel) |
| `action_approved` | event | 0.2 | Action approved by admin |
| `action_rejected` | event | 0.1 | Action rejected by admin |

### Actions v0 Cancel RBAC Rules

- **Member**: Can cancel their own proposed actions only
- **Admin**: Can cancel any proposed action in the tenant
- **Idempotent**: Cancelling an already cancelled action returns 200 without emitting usage/audit
- **Cross-tenant**: Accessing another tenant's action returns 404 (not 403)

### Actions Approve/Reject RBAC Rules

- **Admin only**: Only admins can approve or reject actions
- **Member**: Cannot approve or reject (returns 403)
- **Cross-tenant**: Accessing another tenant's action returns 404 (not 403)

### Example: Action Workflow

```bash
# 1. Member proposes an action
curl -X POST http://localhost:8000/v1/actions \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "title": "Follow up with Acme Corp",
    "description": "Re-engage stalled enterprise deal",
    "action_type": "outreach",
    "source": "user",
    "payload": {"company": "Acme Corp"}
  }'

# 2. Admin approves the action
curl -X POST http://localhost:8000/v1/actions/$ACTION_ID/approve \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"comment": "Priority deal - approved"}'

# 3. Admin executes the action
curl -X POST http://localhost:8000/v1/actions/$ACTION_ID/execute \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"execution_status": "succeeded", "result": {"message": "Email sent"}}'
```

### Example: Cancel an Action

```bash
# Member cancels their own proposed action
curl -X POST http://localhost:8000/v1/actions/$ACTION_ID/cancel \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"comment": "Deal moved to next quarter"}'

# List cancelled actions
curl "http://localhost:8000/v1/actions?status=cancelled" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY"

# List all actions (proposed + cancelled)
curl "http://localhost:8000/v1/actions?status=all" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY"
```

### Example: Memory Facts (Admin Only)

```bash
# Create a governed fact
curl -X POST http://localhost:8000/v1/memory/facts \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "category": "icp",
    "fact_key": "ICP.primary",
    "fact_value": "Mid-market SaaS, 50-500 employees, $5M-$50M revenue"
  }'

# Supersede with updated value
curl -X POST http://localhost:8000/v1/memory/facts/$FACT_ID/supersede \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "fact_value": "Mid-market SaaS, 100-1000 employees, $10M-$100M revenue"
  }'
```

### Example: Global Search

```bash
# Search across all entities
curl "http://localhost:8000/v1/search?q=pricing" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY"
```

Response:
```json
{
  "query": "pricing",
  "total": 3,
  "results": [
    {"entity_type": "decision", "entity_id": "...", "title": "Q1 Pricing Strategy", "snippet": "...pricing..."},
    {"entity_type": "task", "entity_id": "...", "title": "Prepare pricing update", "snippet": "...pricing..."},
    {"entity_type": "memory_fact", "entity_id": "...", "title": "pricing.base", "snippet": "...pricing..."}
  ]
}
```

### Example: Record Explorer

```bash
# Get entity with evidence and timeline
curl "http://localhost:8000/v1/records/decision/$DECISION_ID" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $USER_ID" \
  -H "X-API-Key: $API_KEY"
```

Response includes the entity, all evidence links, and related timeline events.

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
│   │   │   ├── models.py        # Data models (incl. Core OS)
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
│   │   │   ├── entitlements.py  # Capability + credits quota enforcement
│   │   │   └── core_os_router.py # Core Business OS APIs
│   │   ├── console/             # Dev Console UI
│   │   │   └── router.py        # Console endpoints
│   │   └── playground/          # Playground UI
│   │       └── router.py        # Playground endpoints
│   └── tests/
│       ├── test_tools_invoke.py # Comprehensive test suite
│       └── test_core_os.py      # Core Business OS tests
└── scripts/
    ├── smoke_phase0.sh          # KPI Store smoke test
    ├── smoke_phase0_item3.sh    # Daily Briefs smoke test
    ├── smoke_phase0_item4.sh    # Notifications + Runner smoke test
    ├── smoke_phase0_item5.sh    # Cofounder Chat smoke test
    ├── smoke_phase0_item6.sh    # Quota Enforcement smoke test
    ├── smoke_phase0_item7.sh    # Billing + Metering smoke test
    └── smoke_core_os_v0.sh      # Core Business OS smoke test
```
