#!/bin/bash
# Smoke test script for Phase 0 Item 4: Notifications v0 + Daily Brief Runner
# Assumes server is running at localhost:8000
#
# Usage: ./scripts/smoke_phase0_item4.sh

set -e  # Exit on error

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=============================================="
echo "Phase 0 Item 4: Notifications + Runner Smoke Test"
echo "Target: $BASE_URL"
echo "=============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}[PASS] $1${NC}"
}

fail() {
    echo -e "${RED}[FAIL] $1${NC}"
    exit 1
}

info() {
    echo -e "${YELLOW}[INFO] $1${NC}"
}

# 1. Create a tenant
echo "Step 1: Creating tenant..."
TENANT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tenants" \
    -H "Content-Type: application/json" \
    -d '{"name": "Notifications Test Tenant", "region": "us-east-1"}')

TENANT_ID=$(echo "$TENANT_RESPONSE" | grep -o '"tenant_id":"[^"]*"' | cut -d'"' -f4)
API_KEY=$(echo "$TENANT_RESPONSE" | grep -o '"api_key":"[^"]*"' | cut -d'"' -f4)

if [ -z "$TENANT_ID" ]; then
    fail "Failed to create tenant"
fi
pass "Created tenant: $TENANT_ID"

# 2. Create admin user
echo ""
echo "Step 2: Creating admin user..."
ADMIN_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/users" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"admin@test.com\", \"role\": \"admin\"}")

ADMIN_ID=$(echo "$ADMIN_RESPONSE" | grep -o '"user_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ADMIN_ID" ]; then
    fail "Failed to create admin user"
fi
pass "Created admin user: $ADMIN_ID"

# 3. Create member user
echo ""
echo "Step 3: Creating member user..."
MEMBER_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/users" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"member@test.com\", \"role\": \"member\"}")

MEMBER_ID=$(echo "$MEMBER_RESPONSE" | grep -o '"user_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$MEMBER_ID" ]; then
    fail "Failed to create member user"
fi
pass "Created member user: $MEMBER_ID"

# 4. Member sets notification preferences (daily_brief_enabled=true)
echo ""
echo "Step 4: Member sets notification preferences..."
PREFS_RESPONSE=$(curl -s -X PUT "$BASE_URL/v1/notifications/prefs" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"daily_brief_enabled": true, "delivery_method": "in_app"}')

if echo "$PREFS_RESPONSE" | grep -q '"daily_brief_enabled":true'; then
    pass "Member enabled daily brief notifications"
else
    echo "Response: $PREFS_RESPONSE"
    fail "Failed to set member prefs"
fi

# 5. Admin creates 2 KPIs with points
echo ""
echo "Step 5: Creating KPIs and points..."

# KPI 1: Revenue
REVENUE_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"name": "Revenue", "unit": "USD", "description": "Monthly revenue"}')

REVENUE_ID=$(echo "$REVENUE_RESPONSE" | grep -o '"kpi_id":"[^"]*"' | cut -d'"' -f4)
if [ -z "$REVENUE_ID" ]; then fail "Failed to create Revenue KPI"; fi
pass "Created KPI: Revenue ($REVENUE_ID)"

# KPI 2: Active Users
USERS_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"name": "Active Users", "unit": "count", "description": "Monthly active users"}')

USERS_ID=$(echo "$USERS_RESPONSE" | grep -o '"kpi_id":"[^"]*"' | cut -d'"' -f4)
if [ -z "$USERS_ID" ]; then fail "Failed to create Active Users KPI"; fi
pass "Created KPI: Active Users ($USERS_ID)"

# Ingest points for Revenue
curl -s -X POST "$BASE_URL/v1/kpis/$REVENUE_ID/points:bulk" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "points": [
            {"ts": "2026-01-24T00:00:00Z", "value": 50000.0},
            {"ts": "2026-01-31T00:00:00Z", "value": 62500.0}
        ]
    }' > /dev/null
pass "Ingested Revenue points: 50000 -> 62500 (+25%)"

# Ingest points for Active Users
curl -s -X POST "$BASE_URL/v1/kpis/$USERS_ID/points:bulk" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "points": [
            {"ts": "2026-01-24T00:00:00Z", "value": 10000.0},
            {"ts": "2026-01-31T00:00:00Z", "value": 8500.0}
        ]
    }' > /dev/null
pass "Ingested Active Users points: 10000 -> 8500 (-15%)"

# 6. Run daily brief job (first request)
echo ""
echo "Step 6: Running daily brief job (first request)..."
IDEMPOTENCY_KEY="smoke-runner-$(date +%s)"
TEST_DATE="2026-01-31"

RUNNER_RESPONSE_1=$(curl -s -X POST "$BASE_URL/v1/jobs/daily-brief" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d "{\"date\": \"$TEST_DATE\", \"window_days\": 7, \"top_n\": 3}")

BRIEF_ID=$(echo "$RUNNER_RESPONSE_1" | grep -o '"brief_id":"[^"]*"' | cut -d'"' -f4)
BRIEF_CREATED=$(echo "$RUNNER_RESPONSE_1" | grep -o '"brief_created":[^,}]*' | cut -d':' -f2)
NOTIFS_INSERTED=$(echo "$RUNNER_RESPONSE_1" | grep -o '"notifications_inserted":[^,}]*' | cut -d':' -f2)

if [ -z "$BRIEF_ID" ]; then
    echo "Response: $RUNNER_RESPONSE_1"
    fail "Failed to run daily brief job"
fi
pass "Daily brief job completed"
info "Brief ID: $BRIEF_ID"
info "Brief Created: $BRIEF_CREATED"
info "Notifications Inserted: $NOTIFS_INSERTED"

# 7. Run daily brief job (idempotent replay)
echo ""
echo "Step 7: Running daily brief job (idempotent replay)..."
RUNNER_RESPONSE_2=$(curl -s -X POST "$BASE_URL/v1/jobs/daily-brief" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d "{\"date\": \"$TEST_DATE\", \"window_days\": 7, \"top_n\": 3}")

BRIEF_ID_2=$(echo "$RUNNER_RESPONSE_2" | grep -o '"brief_id":"[^"]*"' | cut -d'"' -f4)

if [ "$BRIEF_ID" != "$BRIEF_ID_2" ]; then
    fail "Idempotency failed! Brief IDs differ: $BRIEF_ID vs $BRIEF_ID_2"
fi
pass "Idempotent replay returned same brief_id"

# 8. Member checks notification outbox
echo ""
echo "Step 8: Member checking notification outbox..."
OUTBOX_RESPONSE=$(curl -s -X GET "$BASE_URL/v1/notifications/outbox?date=$TEST_DATE" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY")

NOTIF_ID=$(echo "$OUTBOX_RESPONSE" | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)
NOTIF_STATUS=$(echo "$OUTBOX_RESPONSE" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$NOTIF_ID" ]; then
    echo "Response: $OUTBOX_RESPONSE"
    fail "Member has no notifications"
fi
pass "Member has notification (ID: $NOTIF_ID, Status: $NOTIF_STATUS)"

# 9. Member acknowledges notification
echo ""
echo "Step 9: Member acknowledging notification..."
ACK_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/notifications/$NOTIF_ID/ack" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY")

ACK_STATUS=$(echo "$ACK_RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

if [ "$ACK_STATUS" != "acked" ]; then
    echo "Response: $ACK_RESPONSE"
    fail "Failed to acknowledge notification"
fi
pass "Notification acknowledged (Status: $ACK_STATUS)"

# 10. Verify member cannot run runner (RBAC check)
echo ""
echo "Step 10: Verifying RBAC (member cannot run runner)..."
RBAC_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/v1/jobs/daily-brief" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "Idempotency-Key: member-attempt-$(date +%s)" \
    -d "{\"date\": \"2026-02-01\"}")

HTTP_CODE=$(echo "$RBAC_RESPONSE" | tail -1)

if [ "$HTTP_CODE" = "403" ]; then
    pass "RBAC enforced: member got 403 Forbidden"
else
    fail "RBAC not enforced! Expected 403, got $HTTP_CODE"
fi

# Summary
echo ""
echo "=============================================="
echo "Smoke Test Summary"
echo "=============================================="
echo "Tenant ID:  $TENANT_ID"
echo "Admin ID:   $ADMIN_ID"
echo "Member ID:  $MEMBER_ID"
echo "Brief ID:   $BRIEF_ID"
echo "Test Date:  $TEST_DATE"
echo ""
echo "Runner Response (first request):"
echo "----------------------------------------------"
echo "$RUNNER_RESPONSE_1" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Date: {data['date']}\")
print(f\"Brief ID: {data['brief_id']}\")
print(f\"Brief Created: {data['brief_created']}\")
print(f\"Notifications Inserted: {data['notifications_inserted']}\")
print(f\"Notifications Ignored: {data['notifications_ignored']}\")
" 2>/dev/null || echo "(Install python3 for formatted output)"
echo ""
echo -e "${GREEN}All smoke tests passed!${NC}"
echo ""
