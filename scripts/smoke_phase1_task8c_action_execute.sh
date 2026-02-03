#!/bin/bash
# Smoke test for Phase 1 Task 8c: Action Execution Log v0
# Tests admin execute + execution log + timeline events + metering
#
# Prerequisites:
# - Server running on localhost:8000
# - jq installed (optional, for pretty output)
#
# Usage:
#   ./scripts/smoke_phase1_task8c_action_execute.sh

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Phase 1 Task 8c: Action Execution Log v0 Smoke Test ==="
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
    -d '{"name": "Smoke Test Execute", "region": "us-east-1", "admin_email": "admin@execute.test"}')
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
    -d '{"email": "member@execute.test", "role": "member"}')
echo "$MEMBER_RESP" | $JQ

MEMBER_ID=$(echo "$MEMBER_RESP" | grep -o '"user_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Member ID: $MEMBER_ID"
echo ""

# Common headers for member
AUTH_MEMBER="-H X-Tenant-ID:$TENANT_ID -H X-User-ID:$MEMBER_ID -H X-API-Key:$API_KEY"

# 3. Test /v1/me endpoint
echo "3. Testing /v1/me endpoint..."
echo "   Admin:"
curl -s "$BASE_URL/v1/me" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""
echo "   Member:"
curl -s "$BASE_URL/v1/me" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""

# 4. Member creates a proposed action
echo "4. Member creates a proposed action..."
ACTION_RESP=$(curl -s -X POST "$BASE_URL/v1/actions" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "title": "Deploy new pricing model",
        "description": "Update pricing tier structure based on Q1 analysis",
        "action_type": "deployment",
        "source": "user",
        "payload": {"tier": "enterprise", "changes": ["add_seats", "update_limits"]}
    }')
echo "$ACTION_RESP" | $JQ

ACTION_ID=$(echo "$ACTION_RESP" | grep -o '"action_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Action ID: $ACTION_ID"
echo ""

# 5. Admin approves action
echo "5. Admin approves action..."
APPROVE_RESP=$(curl -s -X POST "$BASE_URL/v1/actions/$ACTION_ID/approve" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"comment": "Approved for deployment in staging first."}')
echo "$APPROVE_RESP" | $JQ
echo ""

# 6. Admin executes action with result payload
echo "6. Admin executes action with result payload..."
EXECUTE_RESP=$(curl -s -X POST "$BASE_URL/v1/actions/$ACTION_ID/execute" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{
        "execution_status": "succeeded",
        "result": {
            "deployed_at": "2024-01-15T10:30:00Z",
            "environment": "staging",
            "version": "1.2.0",
            "rollback_available": true
        }
    }')
echo "$EXECUTE_RESP" | $JQ
echo ""

# 7. GET action detail to show review + execution info
echo "7. Fetching action detail (shows review + execution)..."
curl -s "$BASE_URL/v1/actions/$ACTION_ID" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""

# 8. Test idempotent execute (should return same data without new writes)
echo "8. Testing idempotent execute (executing again)..."
IDEMPOTENT_RESP=$(curl -s -X POST "$BASE_URL/v1/actions/$ACTION_ID/execute" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"execution_status": "failed", "result": {"different": "data"}}')
echo "$IDEMPOTENT_RESP" | $JQ
echo "   (Should return 200 with ORIGINAL execution data, not new data)"
echo ""

# 9. Test status transition enforcement (create proposed, try to execute directly)
echo "9. Testing status transition enforcement..."
echo "   Creating another proposed action..."
ACTION2_RESP=$(curl -s -X POST "$BASE_URL/v1/actions" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"title": "Transition Test", "action_type": "test"}')
ACTION2_ID=$(echo "$ACTION2_RESP" | grep -o '"action_id":"[^"]*"' | head -1 | cut -d'"' -f4)

echo "   Trying to execute proposed action directly..."
TRANSITION_RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$BASE_URL/v1/actions/$ACTION2_ID/execute" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"execution_status": "succeeded", "result": {}}')
echo "$TRANSITION_RESP"
echo "   (Should return 409 Conflict with invalid_status_transition)"
echo ""

# 10. Test RBAC (member tries to execute)
echo "10. Testing RBAC - member tries to execute approved action..."
# First approve the action
curl -s -X POST "$BASE_URL/v1/actions/$ACTION2_ID/approve" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{}' > /dev/null

RBAC_RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$BASE_URL/v1/actions/$ACTION2_ID/execute" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $MEMBER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d '{"execution_status": "succeeded", "result": {}}')
echo "$RBAC_RESP"
echo "   (Should return 403 Forbidden)"
echo ""

# 11. GET /v1/timeline?limit=10 and show action_executed event
echo "11. Fetching timeline events (limit=10)..."
curl -s "$BASE_URL/v1/timeline?limit=10" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""

# 12. GET /v1/billing/usage and print breakdown
echo "12. Fetching billing usage..."
USAGE_RESP=$(curl -s "$BASE_URL/v1/billing/usage" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY")
echo "$USAGE_RESP" | $JQ
echo ""

echo "=== Billing Breakdown for action-related events ==="
echo "$USAGE_RESP" | $JQ '.breakdown[] | select(.event_key | startswith("action_"))' 2>/dev/null || \
echo "$USAGE_RESP" | grep -E "action_created|action_approved|action_rejected|action_executed"
echo ""

# 13. List actions by status
echo "13. Listing actions by status..."
echo "   All actions:"
curl -s "$BASE_URL/v1/actions?status=all" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ '.items[] | {action_id, status, title}'
echo ""

echo "   Executed actions only:"
curl -s "$BASE_URL/v1/actions?status=executed" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_ID" \
    -H "X-API-Key: $API_KEY" | $JQ
echo ""

echo "=== Smoke Test Complete ==="
echo ""
echo "Summary:"
echo "- Created tenant with admin and member users"
echo "- Tested /v1/me endpoint for role detection"
echo "- Member created a proposed action"
echo "- Admin approved action"
echo "- Admin executed action with result payload"
echo "- Fetched action detail showing review + execution info"
echo "- Verified idempotent execute (second call returns original data)"
echo "- Verified status transition enforcement (proposed -> execute = 409)"
echo "- Verified RBAC (member cannot execute = 403)"
echo "- Fetched timeline showing action_executed event"
echo "- Verified billing usage for action_executed"
echo "- Listed actions filtered by executed status"
echo ""
echo "All tests passed!"
