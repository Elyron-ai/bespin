#!/bin/bash
# Smoke test script for Phase 0 KPI Store
# Assumes server is running at localhost:8000
#
# Usage: ./scripts/smoke_phase0.sh

set -e  # Exit on error

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=============================================="
echo "Phase 0 KPI Store Smoke Test"
echo "Target: $BASE_URL"
echo "=============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓ $1${NC}"
}

fail() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# 1. Create a tenant
echo "Step 1: Creating tenant..."
TENANT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tenants" \
    -H "Content-Type: application/json" \
    -d '{"name": "Smoke Test Tenant", "region": "eu-west-1"}')

TENANT_ID=$(echo "$TENANT_RESPONSE" | jq -r '.tenant_id')
API_KEY=$(echo "$TENANT_RESPONSE" | jq -r '.api_key')

if [ "$TENANT_ID" == "null" ] || [ -z "$TENANT_ID" ]; then
    fail "Failed to create tenant"
fi
pass "Created tenant: $TENANT_ID"

# 2. Create admin user
echo ""
echo "Step 2: Creating admin user..."
ADMIN_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/users" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"admin@smoketest.com\", \"role\": \"admin\"}")

ADMIN_ID=$(echo "$ADMIN_RESPONSE" | jq -r '.user_id')

if [ "$ADMIN_ID" == "null" ] || [ -z "$ADMIN_ID" ]; then
    fail "Failed to create admin user"
fi
pass "Created admin user: $ADMIN_ID"

# 3. Create member user
echo ""
echo "Step 3: Creating member user..."
MEMBER_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/users" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"member@smoketest.com\", \"role\": \"member\"}")

MEMBER_ID=$(echo "$MEMBER_RESPONSE" | jq -r '.user_id')

if [ "$MEMBER_ID" == "null" ] || [ -z "$MEMBER_ID" ]; then
    fail "Failed to create member user"
fi
pass "Created member user: $MEMBER_ID"

# 4. Create a KPI (as admin)
echo ""
echo "Step 4: Creating KPI definition (as admin)..."
KPI_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"name": "MRR", "unit": "GBP", "description": "Monthly recurring revenue"}')

KPI_ID=$(echo "$KPI_RESPONSE" | jq -r '.kpi_id')

if [ "$KPI_ID" == "null" ] || [ -z "$KPI_ID" ]; then
    fail "Failed to create KPI"
fi
pass "Created KPI: $KPI_ID"

# 5. Ingest KPI points (as admin)
echo ""
echo "Step 5: Ingesting KPI points (as admin)..."
INGEST_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis/$KPI_ID/points:bulk" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "points": [
            {"ts": "2026-01-01T00:00:00Z", "value": 1000.0},
            {"ts": "2026-01-08T00:00:00Z", "value": 1250.0},
            {"ts": "2026-01-15T00:00:00Z", "value": 1500.0}
        ]
    }')

INSERTED=$(echo "$INGEST_RESPONSE" | jq -r '.inserted')

if [ "$INSERTED" != "3" ]; then
    fail "Failed to ingest points, inserted: $INSERTED"
fi
pass "Ingested 3 KPI points"

# 6. List KPIs (as member - should work)
echo ""
echo "Step 6: Listing KPIs (as member)..."
LIST_RESPONSE=$(curl -s -X GET "$BASE_URL/v1/kpis" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY")

KPI_COUNT=$(echo "$LIST_RESPONSE" | jq -r 'length')

if [ "$KPI_COUNT" != "1" ]; then
    fail "Expected 1 KPI, got: $KPI_COUNT"
fi
pass "Member can list KPIs"

# 7. Get latest KPI point (as member)
echo ""
echo "Step 7: Getting latest KPI point (as member)..."
LATEST_RESPONSE=$(curl -s -X GET "$BASE_URL/v1/kpis/$KPI_ID/latest" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY")

LATEST_VALUE=$(echo "$LATEST_RESPONSE" | jq -r '.value')

if [ "$LATEST_VALUE" != "1500" ]; then
    fail "Expected latest value 1500, got: $LATEST_VALUE"
fi
pass "Latest value: $LATEST_VALUE GBP"

# 8. Invoke kpi_summary tool (first request)
echo ""
echo "Step 8: Invoking kpi_summary tool (first request)..."
IDEMPOTENCY_KEY="smoke-test-$(date +%s)"

INVOKE_RESPONSE_1=$(curl -s -X POST "$BASE_URL/v1/tools/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d "{
        \"tool_name\": \"kpi_summary\",
        \"payload\": {\"kpi_id\": \"$KPI_ID\", \"window_days\": 14}
    }")

REQUEST_ID_1=$(echo "$INVOKE_RESPONSE_1" | jq -r '.request_id')
DELTA_ABS=$(echo "$INVOKE_RESPONSE_1" | jq -r '.result.delta_abs')
DELTA_PCT=$(echo "$INVOKE_RESPONSE_1" | jq -r '.result.delta_pct')

if [ "$REQUEST_ID_1" == "null" ] || [ -z "$REQUEST_ID_1" ]; then
    fail "Failed to invoke kpi_summary tool"
fi
pass "kpi_summary result: delta_abs=$DELTA_ABS, delta_pct=$DELTA_PCT%"
echo "   Request ID: $REQUEST_ID_1"

# 9. Invoke kpi_summary tool (idempotent replay)
echo ""
echo "Step 9: Invoking kpi_summary tool (idempotent replay with same key)..."
INVOKE_RESPONSE_2=$(curl -s -X POST "$BASE_URL/v1/tools/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d "{
        \"tool_name\": \"kpi_summary\",
        \"payload\": {\"kpi_id\": \"$KPI_ID\", \"window_days\": 14}
    }")

REQUEST_ID_2=$(echo "$INVOKE_RESPONSE_2" | jq -r '.request_id')

if [ "$REQUEST_ID_1" != "$REQUEST_ID_2" ]; then
    fail "Idempotency failed! Request IDs differ: $REQUEST_ID_1 vs $REQUEST_ID_2"
fi
pass "Idempotent replay returned same request_id: $REQUEST_ID_2"

# Summary
echo ""
echo "=============================================="
echo "Smoke Test Summary"
echo "=============================================="
echo "Tenant ID:  $TENANT_ID"
echo "Admin ID:   $ADMIN_ID"
echo "Member ID:  $MEMBER_ID"
echo "KPI ID:     $KPI_ID"
echo ""
echo "KPI Summary (14-day window):"
echo "  - Latest: $(echo "$INVOKE_RESPONSE_1" | jq -r '.result.latest.value') GBP"
echo "  - Start:  $(echo "$INVOKE_RESPONSE_1" | jq -r '.result.start.value') GBP"
echo "  - Delta:  $DELTA_ABS GBP ($DELTA_PCT%)"
echo ""
echo -e "${GREEN}All smoke tests passed!${NC}"
echo ""
echo "=============================================="
echo "To check audit_logs and usage_events in SQLite:"
echo "=============================================="
echo "sqlite3 backend/test.db"
echo "  SELECT COUNT(*) FROM audit_logs WHERE tenant_id='$TENANT_ID';"
echo "  SELECT COUNT(*) FROM usage_events WHERE tenant_id='$TENANT_ID';"
echo "  SELECT * FROM audit_logs WHERE request_id='$REQUEST_ID_1';"
echo ""
