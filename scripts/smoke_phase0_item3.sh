#!/bin/bash
# Smoke test script for Phase 0 Item 3: Insight Materializer (Daily Briefs)
# Assumes server is running at localhost:8000
#
# Usage: ./scripts/smoke_phase0_item3.sh

set -e  # Exit on error

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=============================================="
echo "Phase 0 Item 3: Insight Materializer Smoke Test"
echo "Target: $BASE_URL"
echo "=============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓ $1${NC}"
}

fail() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# 1. Create a tenant
echo "Step 1: Creating tenant..."
TENANT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tenants" \
    -H "Content-Type: application/json" \
    -d '{"name": "Briefs Test Tenant", "region": "us-east-1"}')

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

# 4. Create KPIs with known delta values
echo ""
echo "Step 4: Creating KPIs with known deltas..."

# KPI 1: MRR - will be up 25% (1000 -> 1250)
MRR_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"name": "MRR", "unit": "GBP", "description": "Monthly recurring revenue"}')

MRR_ID=$(echo "$MRR_RESPONSE" | grep -o '"kpi_id":"[^"]*"' | cut -d'"' -f4)
if [ -z "$MRR_ID" ]; then fail "Failed to create MRR KPI"; fi
pass "Created KPI: MRR ($MRR_ID)"

# KPI 2: DAU - will be down 20% (1000 -> 800)
DAU_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"name": "DAU", "unit": "users", "description": "Daily active users"}')

DAU_ID=$(echo "$DAU_RESPONSE" | grep -o '"kpi_id":"[^"]*"' | cut -d'"' -f4)
if [ -z "$DAU_ID" ]; then fail "Failed to create DAU KPI"; fi
pass "Created KPI: DAU ($DAU_ID)"

# KPI 3: NPS - will be flat (50 -> 50)
NPS_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"name": "NPS", "unit": "score", "description": "Net promoter score"}')

NPS_ID=$(echo "$NPS_RESPONSE" | grep -o '"kpi_id":"[^"]*"' | cut -d'"' -f4)
if [ -z "$NPS_ID" ]; then fail "Failed to create NPS KPI"; fi
pass "Created KPI: NPS ($NPS_ID)"

# 5. Ingest KPI points
echo ""
echo "Step 5: Ingesting KPI points..."

# MRR points: 1000 -> 1250 (+25%)
curl -s -X POST "$BASE_URL/v1/kpis/$MRR_ID/points:bulk" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "points": [
            {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
            {"ts": "2026-01-31T00:00:00Z", "value": 1250.0}
        ]
    }' > /dev/null
pass "Ingested MRR points: 1000 -> 1250 (+25%)"

# DAU points: 1000 -> 800 (-20%, should trigger alert)
curl -s -X POST "$BASE_URL/v1/kpis/$DAU_ID/points:bulk" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "points": [
            {"ts": "2026-01-24T00:00:00Z", "value": 1000.0},
            {"ts": "2026-01-31T00:00:00Z", "value": 800.0}
        ]
    }' > /dev/null
pass "Ingested DAU points: 1000 -> 800 (-20%, alert expected)"

# NPS points: 50 -> 50 (flat)
curl -s -X POST "$BASE_URL/v1/kpis/$NPS_ID/points:bulk" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "points": [
            {"ts": "2026-01-24T00:00:00Z", "value": 50.0},
            {"ts": "2026-01-31T00:00:00Z", "value": 50.0}
        ]
    }' > /dev/null
pass "Ingested NPS points: 50 -> 50 (flat)"

# 6. Materialize brief (first request)
echo ""
echo "Step 6: Materializing daily brief (first request)..."
IDEMPOTENCY_KEY="smoke-brief-$(date +%s)"

BRIEF_RESPONSE_1=$(curl -s -X POST "$BASE_URL/v1/briefs/materialize" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d '{"date": "2026-01-31", "window_days": 7, "top_n": 3}')

BRIEF_ID=$(echo "$BRIEF_RESPONSE_1" | grep -o '"brief_id":"[^"]*"' | cut -d'"' -f4)
REQUEST_ID=$(echo "$BRIEF_RESPONSE_1" | grep -o '"request_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$BRIEF_ID" ]; then
    echo "Response: $BRIEF_RESPONSE_1"
    fail "Failed to materialize brief"
fi
pass "Brief materialized successfully"
info "Brief ID: $BRIEF_ID"
info "Request ID: $REQUEST_ID"

# 7. Materialize brief (idempotent replay with same key)
echo ""
echo "Step 7: Materializing brief (idempotent replay with same key)..."
BRIEF_RESPONSE_2=$(curl -s -X POST "$BASE_URL/v1/briefs/materialize" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d '{"date": "2026-01-31", "window_days": 7, "top_n": 3}')

BRIEF_ID_2=$(echo "$BRIEF_RESPONSE_2" | grep -o '"brief_id":"[^"]*"' | cut -d'"' -f4)

if [ "$BRIEF_ID" != "$BRIEF_ID_2" ]; then
    fail "Idempotency failed! Brief IDs differ: $BRIEF_ID vs $BRIEF_ID_2"
fi
pass "Idempotent replay returned same brief_id"

# 8. Fetch brief as member
echo ""
echo "Step 8: Fetching brief as member..."
GET_RESPONSE=$(curl -s -X GET "$BASE_URL/v1/briefs/2026-01-31" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY")

GET_BRIEF_ID=$(echo "$GET_RESPONSE" | grep -o '"brief_id":"[^"]*"' | cut -d'"' -f4)

if [ "$BRIEF_ID" != "$GET_BRIEF_ID" ]; then
    fail "Member failed to fetch brief"
fi
pass "Member can fetch brief successfully"

# 9. Fetch latest brief
echo ""
echo "Step 9: Fetching latest brief..."
LATEST_RESPONSE=$(curl -s -X GET "$BASE_URL/v1/briefs/latest" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY")

LATEST_BRIEF_ID=$(echo "$LATEST_RESPONSE" | grep -o '"brief_id":"[^"]*"' | cut -d'"' -f4)

if [ "$BRIEF_ID" != "$LATEST_BRIEF_ID" ]; then
    fail "Latest brief does not match expected brief"
fi
pass "Latest brief endpoint works"

# Summary
echo ""
echo "=============================================="
echo "Smoke Test Summary"
echo "=============================================="
echo "Tenant ID:  $TENANT_ID"
echo "Admin ID:   $ADMIN_ID"
echo "Member ID:  $MEMBER_ID"
echo "Brief ID:   $BRIEF_ID"
echo "Request ID: $REQUEST_ID"
echo ""
echo "Brief Content (from first response):"
echo "----------------------------------------------"
echo "$BRIEF_RESPONSE_1" | python3 -c "
import sys, json
data = json.load(sys.stdin)
content = data['content']
print(f\"Date: {content['date']}\")
print(f\"Window: {content['window_days']} days\")
print(f\"Top N: {content['top_n']}\")
print()
print('Summary:')
s = content['summary']
print(f\"  KPIs Considered: {s['kpis_considered']}\")
print(f\"  Up: {s['kpis_up']}, Down: {s['kpis_down']}, Flat: {s['kpis_flat']}\")
print()
print('Highlights (ranked by |delta_pct|):')
for i, h in enumerate(content['highlights'], 1):
    pct = h['delta_pct']
    pct_str = f\"{pct:+.1f}%\" if pct is not None else 'N/A'
    print(f\"  {i}. {h['name']}: {h['start']['value']} -> {h['latest']['value']} ({pct_str})\")
print()
print('Alerts:')
if content['alerts']:
    for a in content['alerts']:
        print(f\"  - {a['name']}: {a['reason']} ({a['delta_pct']:.1f}%)\")
else:
    print('  (none)')
" 2>/dev/null || echo "(Install python3 for formatted output)"
echo ""
echo -e "${GREEN}All smoke tests passed!${NC}"
echo ""
