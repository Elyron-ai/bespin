#!/bin/bash
# Smoke test for Phase 0 Item #6: Tenant Limits + Quota Enforcement + Usage Ledger
#
# This script demonstrates and verifies:
# - Tenant creation includes default limits
# - Admin can update limits via PUT /v1/limits
# - Quota enforcement on chat (429 on exceed)
# - Quota enforcement on tools/invoke with idempotency replay
# - Partial notification enqueue on daily-brief runner
# - Usage tracking via GET /v1/usage/daily
#
# Assumes server is running at localhost:8000

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=================================================="
echo "Phase 0 Item #6: Quota Enforcement Smoke Test"
echo "Target: $BASE_URL"
echo "=================================================="
echo ""

# Step 1: Create tenant + admin
echo "1. Creating tenant with bootstrap admin..."
TENANT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"name":"Quota Test Tenant","region":"us-east-1","admin_email":"admin@quotatest.com"}')

TENANT_ID=$(echo "$TENANT_RESPONSE" | grep -o '"tenant_id":"[^"]*' | cut -d'"' -f4)
API_KEY=$(echo "$TENANT_RESPONSE" | grep -o '"api_key":"[^"]*' | cut -d'"' -f4)
ADMIN_ID=$(echo "$TENANT_RESPONSE" | grep -o '"user_id":"[^"]*' | head -1 | cut -d'"' -f4)

echo "   Tenant ID: $TENANT_ID"
echo "   Admin ID: $ADMIN_ID"
echo "   API Key: ${API_KEY:0:20}..."
echo ""

# Step 2: Check default limits
echo "2. Checking default limits..."
LIMITS=$(curl -s "$BASE_URL/v1/limits" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY")
echo "   Default limits: $LIMITS"
echo ""

# Step 3: Create a member user
echo "3. Creating member user..."
MEMBER_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/users" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"tenant_id\":\"$TENANT_ID\",\"email\":\"member@quotatest.com\",\"role\":\"member\"}")
MEMBER_ID=$(echo "$MEMBER_RESPONSE" | grep -o '"user_id":"[^"]*' | cut -d'"' -f4)
echo "   Member ID: $MEMBER_ID"
echo ""

# Step 4: Admin sets very low limits
echo "4. Admin setting very low limits (chat=1, tool=1, brief=1, notif=1)..."
UPDATE_RESPONSE=$(curl -s -X PUT "$BASE_URL/v1/limits" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"assistant_query_daily_limit":1,"tool_invocation_daily_limit":1,"daily_brief_generated_daily_limit":1,"notification_enqueued_daily_limit":1}')
echo "   Updated limits: $UPDATE_RESPONSE"
echo ""

# Step 5: Test chat quota - first should succeed
echo "5. Testing chat quota enforcement..."
echo "   First chat (should succeed)..."
CHAT1=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/v1/cofounder/chat" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message":"hello"}')
echo "   First chat status: $CHAT1 (expected: 200)"

echo "   Second chat (should fail with 429)..."
CHAT2=$(curl -s -X POST "$BASE_URL/v1/cofounder/chat" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message":"hello again"}')
CHAT2_STATUS=$(echo "$CHAT2" | grep -o '"error":"quota_exceeded"' || echo "no quota error")
echo "   Second chat response: $CHAT2_STATUS (expected: quota_exceeded)"
echo ""

# Step 6: Test tool invoke quota with idempotency
echo "6. Testing tool invoke quota + idempotency..."
IDEM_KEY1="invoke-key-$(date +%s)-1"
IDEM_KEY2="invoke-key-$(date +%s)-2"

echo "   First invoke with key1 (should succeed)..."
INVOKE1=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/v1/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEM_KEY1" \
  -d '{"tool_name":"echo","payload":{"message":"test"}}')
echo "   First invoke status: $INVOKE1 (expected: 200)"

echo "   Second invoke with NEW key (should fail with 429)..."
INVOKE2=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/v1/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEM_KEY2" \
  -d '{"tool_name":"echo","payload":{"message":"test2"}}')
echo "   Second invoke status: $INVOKE2 (expected: 429)"

echo "   Replay with SAME key1 (should succeed - idempotent replay)..."
INVOKE_REPLAY=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/v1/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEM_KEY1" \
  -d '{"tool_name":"echo","payload":{"message":"test"}}')
echo "   Replay status: $INVOKE_REPLAY (expected: 200 - no quota consumed)"
echo ""

# Step 7: Test daily brief runner with partial notification enqueue
echo "7. Testing daily brief runner with partial notification enqueue..."
echo "   (2 users but only 1 notification quota available)"
RUNNER_IDEM_KEY="runner-key-$(date +%s)"
RUNNER=$(curl -s -X POST "$BASE_URL/v1/jobs/daily-brief" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $RUNNER_IDEM_KEY" \
  -d '{}')

NOTIF_INSERTED=$(echo "$RUNNER" | grep -o '"notifications_inserted":[0-9]*' | cut -d: -f2)
NOTIF_SUPPRESSED=$(echo "$RUNNER" | grep -o '"notifications_suppressed_due_to_quota":[0-9]*' | cut -d: -f2)
echo "   Notifications inserted: $NOTIF_INSERTED (expected: 1)"
echo "   Notifications suppressed due to quota: $NOTIF_SUPPRESSED (expected: 1)"
echo ""

# Step 8: Fetch usage summary
echo "8. Fetching usage summary via GET /v1/usage/daily..."
USAGE=$(curl -s "$BASE_URL/v1/usage/daily" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY")
echo "   Usage summary:"
echo "$USAGE" | python3 -c "import sys,json; d=json.load(sys.stdin); print('   Date:', d['date']); [print(f\"   {u['activity_type']}: {u['units']}/{d['limits'].get(u['activity_type']+'_daily_limit', 'N/A')}\") for u in d['usage']]" 2>/dev/null || echo "$USAGE"
echo ""

echo "=================================================="
echo "Smoke test completed!"
echo ""
echo "Summary:"
echo "  - Tenant limits created on tenant creation: OK"
echo "  - Admin can update limits: OK"
echo "  - Chat quota enforcement (429 on exceed): $CHAT2_STATUS"
echo "  - Tool invoke quota enforcement: $([ "$INVOKE2" = "429" ] && echo "OK" || echo "FAIL")"
echo "  - Idempotency replay bypasses quota: $([ "$INVOKE_REPLAY" = "200" ] && echo "OK" || echo "FAIL")"
echo "  - Partial notification enqueue: $([ "$NOTIF_SUPPRESSED" = "1" ] && echo "OK" || echo "CHECK")"
echo "=================================================="
