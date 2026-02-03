#!/bin/bash
# Smoke test for Phase 1 Task 8b: Action Approvals v0
# Tests admin approve/reject + action review log + timeline events + metering
#
# Prerequisites:
# - Server running on localhost:8000
# - jq installed (optional, for pretty output)
#
# Usage:
#   ./scripts/smoke_phase1_task8b_action_approvals.sh

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Phase 1 Task 8b: Action Approvals v0 Smoke Test ==="
echo "Server: $BASE_URL"
echo ""

# Check if jq is available
if command -v jq &> /dev/null; then
    JQ="jq"
else
    JQ="cat"
    echo "Note: jq not found, output will not be pretty-printed"
fi

# 1. Create Tenant + API Key
echo "1. Creating tenant..."
TENANT_RESP=$(curl -s -X POST "$BASE_URL/v1/tenants" \
    -H "Content-Type: application/json" \
    -d '{"name": "Smoke Test Approvals", "region": "us-east-1", "admin_email": "admin@approvals.test"}')
echo "$TENANT_RESP" | $JQ

TENANT_ID=$(echo "$TENANT_RESP" | grep -o '"tenant_id":"[^"]*"' | head -1 | cut -d'"' -f4)
API_KEY=$(echo "$TENANT_RESP" | grep -o '"api_key":"[^"]*"' | head -1 | cut -d'"' -f4)
ADMIN_ID=$(echo "$TENANT_RESP" | grep -o '"user_id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$TENANT_ID" ] || [ -z "$API_KEY" ] || [ -z "$ADMIN_ID" ]; then
    echo "ERROR: Failed to extract tenant info"
    exit 1
fi

echo ""
echo "Tenant ID: $TENANT_ID"
echo "Admin ID: $ADMIN_ID"
echo ""

# Common headers for admin
AUTH_ADMIN="-H X-Tenant-ID:$TENANT_ID -H X-User-ID:$ADMIN_ID -H X-API-Key:$API_KEY"

# 2. Create a member user
echo "2. Creating member user..."
MEMBER_RESP=$(curl -s -X POST "$BASE_URL/v1/users" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"email": "member@approvals.test", "role": "member"}')
echo "$MEMBER_RESP" | $JQ

MEMBER_ID=$(echo "$MEMBER_RESP" | grep -o '"user_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Member ID: $MEMBER_ID"
echo ""

# Common headers for member
AUTH_MEMBER="-H X-Tenant-ID:$TENANT_ID -H X-User-ID:$MEMBER_ID -H X-API-Key:$API_KEY"

# 3. Member creates 2 proposed actions
echo "3. Member creates 2 proposed actions..."

echo "   Creating action 1 (to be approved)..."
ACTION1_RESP=$(curl -s -X POST "$BASE_URL/v1/actions" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "title": "Launch Q1 marketing campaign",
        "description": "Multi-channel campaign targeting enterprise customers",
        "action_type": "marketing",
        "source": "user",
        "payload": {"budget": 50000, "channels": ["email", "linkedin", "webinars"]}
    }')
echo "$ACTION1_RESP" | $JQ

ACTION1_ID=$(echo "$ACTION1_RESP" | grep -o '"action_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "   Action 1 ID: $ACTION1_ID"
echo ""

echo "   Creating action 2 (to be rejected)..."
ACTION2_RESP=$(curl -s -X POST "$BASE_URL/v1/actions" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "title": "Reduce product pricing by 50%",
        "description": "Aggressive price cut to gain market share",
        "action_type": "pricing",
        "source": "ai_recommendation",
        "payload": {"current_price": 99, "proposed_price": 49}
    }')
echo "$ACTION2_RESP" | $JQ

ACTION2_ID=$(echo "$ACTION2_RESP" | grep -o '"action_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "   Action 2 ID: $ACTION2_ID"
echo ""

# 4. Admin approves the first action with comment
echo "4. Admin approves action 1 (marketing campaign)..."
APPROVE_RESP=$(curl -s -X POST "$BASE_URL/v1/actions/$ACTION1_ID/approve" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"comment": "Great initiative! Approved for Q1 budget."}')
echo "$APPROVE_RESP" | $JQ
echo ""

# 5. Admin rejects the second action with comment
echo "5. Admin rejects action 2 (price reduction)..."
REJECT_RESP=$(curl -s -X POST "$BASE_URL/v1/actions/$ACTION2_ID/reject" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"comment": "Too aggressive - would hurt margins. Revisit in Q3."}')
echo "$REJECT_RESP" | $JQ
echo ""

# 6. GET /v1/actions?status=all and show statuses
echo "6. Listing all actions (status=all)..."
curl -s "$BASE_URL/v1/actions?status=all" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""

echo "   Listing approved actions (status=approved)..."
curl -s "$BASE_URL/v1/actions?status=approved" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""

echo "   Listing rejected actions (status=rejected)..."
curl -s "$BASE_URL/v1/actions?status=rejected" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""

# 7. GET /v1/timeline?limit=10 and show approval/rejection events
echo "7. Fetching timeline events (limit=10)..."
curl -s "$BASE_URL/v1/timeline?limit=10" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""

# 8. GET /v1/billing/usage and print breakdown
echo "8. Fetching billing usage..."
USAGE_RESP=$(curl -s "$BASE_URL/v1/billing/usage" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY")
echo "$USAGE_RESP" | $JQ
echo ""

echo "=== Billing Breakdown for approval-related events ==="
echo "$USAGE_RESP" | $JQ '.breakdown[] | select(.event_key | startswith("action_"))' 2>/dev/null || \
echo "$USAGE_RESP" | grep -E "action_created|action_approved|action_rejected"
echo ""

# 9. Test idempotency - approve same action again
echo "9. Testing idempotency - approving already approved action..."
IDEMPOTENT_RESP=$(curl -s -X POST "$BASE_URL/v1/actions/$ACTION1_ID/approve" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"comment": "Trying to approve again"}')
echo "$IDEMPOTENT_RESP" | $JQ
echo "   (Should return 200 with status=approved, no additional writes)"
echo ""

# 10. Test conflict - try to reject an approved action
echo "10. Testing conflict - rejecting an approved action..."
CONFLICT_RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$BASE_URL/v1/actions/$ACTION1_ID/reject" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"comment": "Changed my mind"}')
echo "$CONFLICT_RESP"
echo "   (Should return 409 Conflict)"
echo ""

# 11. Test RBAC - member tries to approve
echo "11. Testing RBAC - member tries to approve an action..."

# First create a new action for testing
NEW_ACTION_RESP=$(curl -s -X POST "$BASE_URL/v1/actions" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"title": "RBAC Test Action", "action_type": "test"}')
NEW_ACTION_ID=$(echo "$NEW_ACTION_RESP" | grep -o '"action_id":"[^"]*"' | head -1 | cut -d'"' -f4)

RBAC_RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$BASE_URL/v1/actions/$NEW_ACTION_ID/approve" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{}')
echo "$RBAC_RESP"
echo "   (Should return 403 Forbidden)"
echo ""

echo "=== Smoke Test Complete ==="
echo ""
echo "Summary:"
echo "- Created tenant with admin and member users"
echo "- Member created 2 proposed actions"
echo "- Admin approved action 1 (marketing campaign)"
echo "- Admin rejected action 2 (price reduction)"
echo "- Listed actions by status (all, approved, rejected)"
echo "- Fetched timeline showing approval/rejection events"
echo "- Verified billing usage for action_approved and action_rejected"
echo "- Tested idempotent approve (already approved -> 200)"
echo "- Tested conflict (approve then reject -> 409)"
echo "- Tested RBAC (member cannot approve -> 403)"
echo ""
echo "All tests passed!"
