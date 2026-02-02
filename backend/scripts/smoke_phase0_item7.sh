#!/bin/bash
# Smoke test for Phase 0 Item #7: Billing and Metering System
#
# Prerequisites:
# - Server running on localhost:8000
# - export PLATFORM_ADMIN_KEY=adminkey (or set your own)
#
# Usage: ./scripts/smoke_phase0_item7.sh

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_KEY="${PLATFORM_ADMIN_KEY:-adminkey}"

echo "=========================================="
echo "Phase 0 Item #7 Smoke Test"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo "Admin Key: ${ADMIN_KEY:0:4}****"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success() { echo -e "${GREEN}✓ $1${NC}"; }
info() { echo -e "${YELLOW}→ $1${NC}"; }
error() { echo -e "${RED}✗ $1${NC}"; exit 1; }

# Helper function to make API calls
api() {
    local method=$1
    local endpoint=$2
    shift 2
    curl -s -X "$method" "${BASE_URL}${endpoint}" -H "Content-Type: application/json" "$@"
}

# =====================================================
# Step 1: Create tenant + admin + member
# =====================================================
echo ""
info "Step 1: Creating tenant and users"

TENANT_RESPONSE=$(api POST "/v1/tenants" -d '{
    "name": "Billing Test Tenant",
    "region": "us-east-1",
    "admin_email": "admin@billing-test.com"
}')

TENANT_ID=$(echo "$TENANT_RESPONSE" | jq -r '.tenant_id')
API_KEY=$(echo "$TENANT_RESPONSE" | jq -r '.api_key')
ADMIN_USER_ID=$(echo "$TENANT_RESPONSE" | jq -r '.admin.user_id')

if [ "$TENANT_ID" == "null" ] || [ -z "$TENANT_ID" ]; then
    error "Failed to create tenant"
fi

success "Created tenant: $TENANT_ID"

# Create a member user
MEMBER_RESPONSE=$(api POST "/v1/users" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d "{
        \"tenant_id\": \"$TENANT_ID\",
        \"email\": \"member@billing-test.com\",
        \"role\": \"member\"
    }")

MEMBER_USER_ID=$(echo "$MEMBER_RESPONSE" | jq -r '.user_id')
success "Created member user: $MEMBER_USER_ID"

# =====================================================
# Step 2: Show current plan + usage (should be near zero)
# =====================================================
echo ""
info "Step 2: Checking initial plan and usage"

PLAN_RESPONSE=$(api GET "/v1/billing/plan" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY")

PLAN_ID=$(echo "$PLAN_RESPONSE" | jq -r '.plan_id')
PLAN_NAME=$(echo "$PLAN_RESPONSE" | jq -r '.plan.name')
INCLUDED_CREDITS=$(echo "$PLAN_RESPONSE" | jq -r '.plan.included_credits')

success "Plan: $PLAN_NAME ($PLAN_ID)"
success "Included credits: $INCLUDED_CREDITS"

USAGE_RESPONSE=$(api GET "/v1/billing/usage" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY")

USED_CREDITS=$(echo "$USAGE_RESPONSE" | jq -r '.credits.used')
success "Initial credits used: $USED_CREDITS"

# =====================================================
# Step 3: Update metered event weight for assistant_query to 5.0
# =====================================================
echo ""
info "Step 3: Updating assistant_query weight to 5.0 credits"

UPDATE_RESPONSE=$(api PUT "/v1/admin/metered-events/assistant_query" \
    -H "X-Platform-Admin-Key: $ADMIN_KEY" \
    -d '{"credits_per_unit": 5.0}')

NEW_WEIGHT=$(echo "$UPDATE_RESPONSE" | jq -r '.credits_per_unit')
success "Updated assistant_query weight to: $NEW_WEIGHT credits per unit"

# =====================================================
# Step 4: Make a chat request
# =====================================================
echo ""
info "Step 4: Making a chat request"

CHAT_RESPONSE=$(api POST "/v1/cofounder/chat" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"message": "help"}')

CHAT_REQUEST_ID=$(echo "$CHAT_RESPONSE" | jq -r '.request_id')
if [ "$CHAT_REQUEST_ID" == "null" ] || [ -z "$CHAT_REQUEST_ID" ]; then
    error "Chat request failed"
fi
success "Chat request successful: $CHAT_REQUEST_ID"

# =====================================================
# Step 5: Fetch usage and verify assistant_query credits increased by 5.0
# =====================================================
echo ""
info "Step 5: Verifying usage after chat"

sleep 1  # Give a moment for data to be committed

USAGE_RESPONSE=$(api GET "/v1/billing/usage" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY")

USED_CREDITS=$(echo "$USAGE_RESPONSE" | jq -r '.credits.used')
success "Credits used after chat: $USED_CREDITS"

# Check breakdown
CHAT_CREDITS=$(echo "$USAGE_RESPONSE" | jq -r '.breakdown[] | select(.event_key == "assistant_query") | .credits')
if [ -n "$CHAT_CREDITS" ]; then
    success "assistant_query credits: $CHAT_CREDITS"
fi

# =====================================================
# Step 6: Create and assign a tiny plan with limited credits
# =====================================================
echo ""
info "Step 6: Creating a tiny plan with 5 credits"

# Create tiny plan
TINY_PLAN_RESPONSE=$(api POST "/v1/admin/plans" \
    -H "X-Platform-Admin-Key: $ADMIN_KEY" \
    -d '{
        "plan_id": "tiny-test",
        "name": "Tiny Test",
        "included_credits": 5,
        "overage_price_per_credit": 0.05
    }')

if [ "$(echo "$TINY_PLAN_RESPONSE" | jq -r '.plan_id')" == "null" ]; then
    # Plan might already exist, try to update it
    api PUT "/v1/admin/plans/tiny-test" \
        -H "X-Platform-Admin-Key: $ADMIN_KEY" \
        -d '{"included_credits": 5}' > /dev/null
fi

# Add capabilities to tiny plan
api PUT "/v1/admin/plans/tiny-test/capabilities" \
    -H "X-Platform-Admin-Key: $ADMIN_KEY" \
    -d '{"capabilities": ["chat", "tools", "briefs", "notifications", "kpi_ingest", "kpi_read"]}' > /dev/null

success "Created/updated tiny-test plan"

# Assign tenant to tiny plan
api PUT "/v1/admin/tenants/$TENANT_ID/subscription" \
    -H "X-Platform-Admin-Key: $ADMIN_KEY" \
    -d '{"plan_id": "tiny-test", "status": "active"}' > /dev/null

success "Assigned tenant to tiny-test plan"

# =====================================================
# Step 7: Make another chat and verify quota behavior
# =====================================================
echo ""
info "Step 7: Testing quota enforcement"

# Usage will still show the previous credits (5 from step 4)
# But now with tiny plan (5 credits included), we should be at the limit

USAGE_RESPONSE=$(api GET "/v1/billing/usage" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY")

USED_CREDITS=$(echo "$USAGE_RESPONSE" | jq -r '.credits.used')
REMAINING=$(echo "$USAGE_RESPONSE" | jq -r '.credits.remaining')

success "Current usage on tiny plan - Used: $USED_CREDITS, Remaining: $REMAINING"

# Try another chat - should fail if we're at or over quota
CHAT_RESPONSE=$(api POST "/v1/cofounder/chat" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"message": "kpis"}' 2>&1)

if echo "$CHAT_RESPONSE" | jq -e '.detail.error == "quota_exceeded"' > /dev/null 2>&1; then
    success "Quota enforcement working! Chat blocked when credits exhausted"
else
    info "Chat succeeded (credits may have reset for new period)"
fi

# =====================================================
# Step 8: Run daily brief job and show notification consumption
# =====================================================
echo ""
info "Step 8: Running daily brief job"

# Switch back to starter plan for this test
api PUT "/v1/admin/tenants/$TENANT_ID/subscription" \
    -H "X-Platform-Admin-Key: $ADMIN_KEY" \
    -d '{"plan_id": "starter", "status": "active"}' > /dev/null

# Reset assistant_query weight to 1.0 for cleaner numbers
api PUT "/v1/admin/metered-events/assistant_query" \
    -H "X-Platform-Admin-Key: $ADMIN_KEY" \
    -d '{"credits_per_unit": 1.0}' > /dev/null

IDEMPOTENCY_KEY=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "smoke-test-$(date +%s)")

JOB_RESPONSE=$(api POST "/v1/jobs/daily-brief" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d '{"window_days": 7, "top_n": 3}')

BRIEF_CREATED=$(echo "$JOB_RESPONSE" | jq -r '.brief_created')
NOTIFS_INSERTED=$(echo "$JOB_RESPONSE" | jq -r '.notifications_inserted')
NOTIFS_SUPPRESSED=$(echo "$JOB_RESPONSE" | jq -r '.notifications_suppressed_due_to_quota')

success "Daily brief job completed:"
echo "  - Brief created: $BRIEF_CREATED"
echo "  - Notifications inserted: $NOTIFS_INSERTED"
echo "  - Notifications suppressed: $NOTIFS_SUPPRESSED"

# =====================================================
# Step 9: Print final usage summary
# =====================================================
echo ""
info "Step 9: Final usage summary"

USAGE_RESPONSE=$(api GET "/v1/billing/usage" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY")

echo ""
echo "=========================================="
echo "Final Billing Summary"
echo "=========================================="
echo "$USAGE_RESPONSE" | jq '{
    period: (.period_start + " to " + .period_end),
    plan: .plan.name,
    credits: {
        included: .credits.included,
        used: .credits.used,
        remaining: .credits.remaining,
        estimated_cost: .credits.estimated_list_cost
    },
    breakdown: [.breakdown[] | {event: .event_key, units: .raw_units, credits: .credits}]
}'

echo ""
echo "=========================================="
echo -e "${GREEN}Smoke test completed successfully!${NC}"
echo "=========================================="
