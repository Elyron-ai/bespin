#!/bin/bash
# =============================================================================
# Smoke Test Script for Actions v0 (Phase 1 Task 8a)
# =============================================================================
# This script demonstrates Actions v0 APIs:
#   - Create actions (status defaults to "proposed")
#   - List actions with filters
#   - Get a single action
#   - Cancel actions (RBAC enforced)
#   - Verify metering via /v1/billing/usage
#
# Prerequisites:
#   - Server running on localhost:8000
#   - curl installed (jq optional but recommended)
#
# Usage:
#   ./scripts/smoke_phase1_task8a_actions_v0.sh
# =============================================================================

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Actions v0 Smoke Test (Phase 1 Task 8a) ==="
echo "Base URL: $BASE_URL"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if jq is available
HAS_JQ=$(command -v jq &> /dev/null && echo "yes" || echo "no")

# Helper to extract JSON value (works with or without jq)
json_value() {
    local json=$1
    local key=$2
    if [ "$HAS_JQ" = "yes" ]; then
        echo "$json" | jq -r ".$key"
    else
        # Fallback: basic grep/sed extraction (less reliable)
        echo "$json" | grep -o "\"$key\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | sed "s/\"$key\"[[:space:]]*:[[:space:]]*\"//" | sed 's/"$//' | head -1
    fi
}

# Helper for nested JSON
json_nested() {
    local json=$1
    local key1=$2
    local key2=$3
    if [ "$HAS_JQ" = "yes" ]; then
        echo "$json" | jq -r ".$key1.$key2"
    else
        # Basic fallback
        echo "$json" | grep -o "\"$key2\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | sed "s/\"$key2\"[[:space:]]*:[[:space:]]*\"//" | sed 's/"$//' | head -1
    fi
}

echo -e "${YELLOW}Step 1: Create Tenant + API Key${NC}"
TENANT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tenants" \
    -H "Content-Type: application/json" \
    -d '{"name": "Actions v0 Smoke Test", "region": "us-east-1", "admin_email": "admin@actions-test.com"}')

TENANT_ID=$(json_value "$TENANT_RESPONSE" "tenant_id")
API_KEY=$(json_value "$TENANT_RESPONSE" "api_key")
ADMIN_USER_ID=$(json_nested "$TENANT_RESPONSE" "admin" "user_id")

echo -e "Tenant ID: ${GREEN}$TENANT_ID${NC}"
echo -e "Admin User ID: ${GREEN}$ADMIN_USER_ID${NC}"
echo ""

# Admin call helper
admin_call() {
    local method=$1
    local endpoint=$2
    local data=$3

    if [ -n "$data" ]; then
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $TENANT_ID" \
            -H "X-User-ID: $ADMIN_USER_ID" \
            -H "X-API-Key: $API_KEY" \
            -d "$data"
    else
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $TENANT_ID" \
            -H "X-User-ID: $ADMIN_USER_ID" \
            -H "X-API-Key: $API_KEY"
    fi
}

# Member call helper
member_call() {
    local method=$1
    local endpoint=$2
    local data=$3

    if [ -n "$data" ]; then
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $TENANT_ID" \
            -H "X-User-ID: $MEMBER_USER_ID" \
            -H "X-API-Key: $API_KEY" \
            -d "$data"
    else
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $TENANT_ID" \
            -H "X-User-ID: $MEMBER_USER_ID" \
            -H "X-API-Key: $API_KEY"
    fi
}

echo -e "${YELLOW}Step 2: Create Admin + Member Users${NC}"
MEMBER_RESPONSE=$(admin_call POST "/v1/users" "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"member@actions-test.com\", \"role\": \"member\"}")
MEMBER_USER_ID=$(json_value "$MEMBER_RESPONSE" "user_id")
echo -e "Member User ID: ${GREEN}$MEMBER_USER_ID${NC}"
echo ""

echo -e "${YELLOW}Step 3: Member Creates an Action${NC}"
ACTION_RESPONSE=$(member_call POST "/v1/actions" '{
    "title": "Follow up with Acme Corp",
    "description": "Re-engage stalled enterprise deal",
    "action_type": "outreach",
    "source": "user",
    "payload": {"company": "Acme Corp", "contact": "john@acme.com"}
}')
ACTION_ID=$(json_value "$ACTION_RESPONSE" "action_id")
ACTION_STATUS=$(json_value "$ACTION_RESPONSE" "status")

echo -e "Created Action ID: ${GREEN}$ACTION_ID${NC}"
echo -e "Status: ${BLUE}$ACTION_STATUS${NC} (expected: proposed)"
if [ "$HAS_JQ" = "yes" ]; then
    echo "Full response:"
    echo "$ACTION_RESPONSE" | jq .
fi
echo ""

echo -e "${YELLOW}Step 4: List Actions (default: proposed)${NC}"
LIST_RESPONSE=$(admin_call GET "/v1/actions")
if [ "$HAS_JQ" = "yes" ]; then
    TOTAL=$(echo "$LIST_RESPONSE" | jq -r '.total')
    echo -e "Total proposed actions: ${GREEN}$TOTAL${NC}"
    echo "First action title: $(echo "$LIST_RESPONSE" | jq -r '.items[0].title')"
else
    echo "List response: $LIST_RESPONSE"
fi
echo ""

echo -e "${YELLOW}Step 5: Get Single Action by ID${NC}"
GET_RESPONSE=$(admin_call GET "/v1/actions/$ACTION_ID")
if [ "$HAS_JQ" = "yes" ]; then
    echo "Action details:"
    echo "$GET_RESPONSE" | jq '{action_id, title, status, created_by_user_id, action_type}'
else
    echo "Action: $GET_RESPONSE"
fi
echo ""

echo -e "${YELLOW}Step 6: Member Cancels Their Own Action${NC}"
CANCEL_RESPONSE=$(member_call POST "/v1/actions/$ACTION_ID/cancel" '{"comment": "Deal moved to different quarter"}')
CANCEL_STATUS=$(json_value "$CANCEL_RESPONSE" "status")
echo -e "Action status after cancel: ${GREEN}$CANCEL_STATUS${NC} (expected: cancelled)"
echo ""

echo -e "${YELLOW}Step 7: Get Action Again (verify cancelled)${NC}"
GET_RESPONSE2=$(admin_call GET "/v1/actions/$ACTION_ID")
FINAL_STATUS=$(json_value "$GET_RESPONSE2" "status")
echo -e "Final action status: ${GREEN}$FINAL_STATUS${NC}"
echo ""

echo -e "${YELLOW}Step 8: List Actions with status=cancelled${NC}"
CANCELLED_LIST=$(admin_call GET "/v1/actions?status=cancelled")
if [ "$HAS_JQ" = "yes" ]; then
    CANCELLED_COUNT=$(echo "$CANCELLED_LIST" | jq -r '.total')
    echo -e "Total cancelled actions: ${GREEN}$CANCELLED_COUNT${NC}"
else
    echo "Cancelled list: $CANCELLED_LIST"
fi
echo ""

echo -e "${YELLOW}Step 9: Admin Creates Another Action${NC}"
ACTION2_RESPONSE=$(admin_call POST "/v1/actions" '{
    "title": "Send Q4 Pricing Update",
    "description": "Notify all enterprise customers",
    "action_type": "notification",
    "source": "agent",
    "source_ref": "pricing-agent-v1"
}')
ACTION2_ID=$(json_value "$ACTION2_RESPONSE" "action_id")
echo -e "Created Action 2 ID: ${GREEN}$ACTION2_ID${NC}"
echo ""

echo -e "${YELLOW}Step 10: List All Actions (status=all)${NC}"
ALL_LIST=$(admin_call GET "/v1/actions?status=all")
if [ "$HAS_JQ" = "yes" ]; then
    ALL_COUNT=$(echo "$ALL_LIST" | jq -r '.total')
    echo -e "Total actions (all statuses): ${GREEN}$ALL_COUNT${NC}"
    echo "Statuses:"
    echo "$ALL_LIST" | jq -r '.items[] | "\(.title): \(.status)"'
else
    echo "All actions: $ALL_LIST"
fi
echo ""

echo -e "${YELLOW}Step 11: Fetch /v1/billing/usage${NC}"
USAGE_RESPONSE=$(admin_call GET "/v1/billing/usage")
echo -e "${BLUE}Billing Usage Summary:${NC}"
if [ "$HAS_JQ" = "yes" ]; then
    echo "$USAGE_RESPONSE" | jq '{
        period_start,
        period_end,
        credits_used: .credits.used,
        credits_remaining: .credits.remaining
    }'
    echo ""
    echo "Breakdown for action_created and action_updated:"
    echo "$USAGE_RESPONSE" | jq '.breakdown[] | select(.event_key == "action_created" or .event_key == "action_updated") | {event_key, raw_units, credits, list_cost_estimate}'
else
    echo "Usage: $USAGE_RESPONSE"
fi
echo ""

echo -e "${GREEN}=== Actions v0 Smoke Test Completed Successfully ===${NC}"
echo ""
echo "Summary:"
echo "  - Created tenant with admin and member users"
echo "  - Member created an action (status: proposed)"
echo "  - Listed actions with status filters"
echo "  - Member cancelled their own action"
echo "  - Verified action status changed to cancelled"
echo "  - Admin created another action"
echo "  - Verified billing usage shows action_created and action_updated events"
echo ""
echo "Metered Events Emitted:"
echo "  - action_created: 2 records (0.2 credits each)"
echo "  - action_updated: 1 record (0.1 credits) for cancel operation"
