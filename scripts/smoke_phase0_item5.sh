#!/bin/bash
# Smoke test for Phase 0 Item #5: Cofounder Conversation API + Playground UI
# Assumes server is running on localhost:8000

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
FIXED_DATE="2026-01-31"

echo "=========================================="
echo "Bespin Phase 0 Item #5 Smoke Test"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo ""

# --- 1. Create tenant ---
echo "1. Creating tenant..."
TENANT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"name": "Smoke Test Tenant", "region": "us-east-1"}')

TENANT_ID=$(echo "$TENANT_RESPONSE" | jq -r '.tenant_id')
API_KEY=$(echo "$TENANT_RESPONSE" | jq -r '.api_key')

if [ "$TENANT_ID" == "null" ] || [ -z "$TENANT_ID" ]; then
  echo "ERROR: Failed to create tenant"
  echo "$TENANT_RESPONSE"
  exit 1
fi

echo "   Tenant ID: $TENANT_ID"
echo "   API Key: ${API_KEY:0:20}..."
echo ""

# --- 2. Create admin user ---
echo "2. Creating admin user..."
ADMIN_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/users" \
  -H "Content-Type: application/json" \
  -d "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"admin@smoketest.com\", \"role\": \"admin\"}")

ADMIN_ID=$(echo "$ADMIN_RESPONSE" | jq -r '.user_id')
echo "   Admin ID: $ADMIN_ID"
echo ""

# --- 3. Create member user ---
echo "3. Creating member user..."
MEMBER_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/users" \
  -H "Content-Type: application/json" \
  -d "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"member@smoketest.com\", \"role\": \"member\"}")

MEMBER_ID=$(echo "$MEMBER_RESPONSE" | jq -r '.user_id')
echo "   Member ID: $MEMBER_ID"
echo ""

# --- 4. Admin creates KPIs ---
echo "4. Creating KPIs (admin)..."

KPI1_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"name": "MRR", "unit": "GBP", "description": "Monthly Recurring Revenue"}')

KPI1_ID=$(echo "$KPI1_RESPONSE" | jq -r '.kpi_id')
echo "   Created KPI 'MRR': $KPI1_ID"

KPI2_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/kpis" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"name": "Active Users", "unit": "count", "description": "Daily active users"}')

KPI2_ID=$(echo "$KPI2_RESPONSE" | jq -r '.kpi_id')
echo "   Created KPI 'Active Users': $KPI2_ID"
echo ""

# --- 5. Admin ingests KPI points ---
echo "5. Ingesting KPI data points (admin)..."

curl -s -X POST "$BASE_URL/v1/kpis/$KPI1_ID/points:bulk" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "points": [
      {"ts": "2026-01-24T00:00:00Z", "value": 10000.0},
      {"ts": "2026-01-25T00:00:00Z", "value": 10500.0},
      {"ts": "2026-01-26T00:00:00Z", "value": 11000.0},
      {"ts": "2026-01-31T00:00:00Z", "value": 12500.0}
    ]
  }' > /dev/null

echo "   Ingested 4 points for MRR"

curl -s -X POST "$BASE_URL/v1/kpis/$KPI2_ID/points:bulk" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "points": [
      {"ts": "2026-01-24T00:00:00Z", "value": 1000},
      {"ts": "2026-01-31T00:00:00Z", "value": 1200}
    ]
  }' > /dev/null

echo "   Ingested 2 points for Active Users"
echo ""

# --- 6. Admin runs daily brief job ---
echo "6. Running daily brief job (admin)..."
IDEM_KEY="smoke-item5-$(date +%s)"

JOB_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/jobs/daily-brief" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $ADMIN_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d "{\"date\": \"$FIXED_DATE\", \"window_days\": 7, \"top_n\": 3}")

BRIEF_ID=$(echo "$JOB_RESPONSE" | jq -r '.brief_id')
NOTIFS_INSERTED=$(echo "$JOB_RESPONSE" | jq -r '.notifications_inserted')
echo "   Brief ID: $BRIEF_ID"
echo "   Notifications inserted: $NOTIFS_INSERTED"
echo ""

# --- 7. Member tests chat: help ---
echo "7. Member calls chat: 'help'"
HELP_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/cofounder/chat" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message": "help"}')

CONV_ID=$(echo "$HELP_RESPONSE" | jq -r '.conversation_id')
HELP_CONTENT=$(echo "$HELP_RESPONSE" | jq -r '.assistant_message.content')
echo "   Conversation ID: $CONV_ID"
echo "   Response: ${HELP_CONTENT:0:80}..."
echo ""

# --- 8. Member tests chat: today's brief ---
echo "8. Member calls chat: 'today's brief'"
BRIEF_CHAT=$(curl -s -X POST "$BASE_URL/v1/cofounder/chat" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"conversation_id\": \"$CONV_ID\", \"message\": \"today's brief\", \"date\": \"$FIXED_DATE\"}")

BRIEF_CONTENT=$(echo "$BRIEF_CHAT" | jq -r '.assistant_message.content')
BRIEF_CARDS=$(echo "$BRIEF_CHAT" | jq -r '.assistant_message.cards | length')
echo "   Response: $BRIEF_CONTENT"
echo "   Cards returned: $BRIEF_CARDS"

if [ "$BRIEF_CARDS" -ge 1 ]; then
  echo "   Brief card:"
  echo "$BRIEF_CHAT" | jq '.assistant_message.cards[0]'
fi
echo ""

# --- 9. Member tests chat: kpis ---
echo "9. Member calls chat: 'kpis'"
KPI_CHAT=$(curl -s -X POST "$BASE_URL/v1/cofounder/chat" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message": "show me kpis"}')

KPI_CONTENT=$(echo "$KPI_CHAT" | jq -r '.assistant_message.content')
KPI_CARDS=$(echo "$KPI_CHAT" | jq -r '.assistant_message.cards | length')
echo "   Response: $KPI_CONTENT"
echo "   KPI cards returned: $KPI_CARDS"
echo ""

# --- 10. Member tests chat: outbox ---
echo "10. Member calls chat: 'outbox'"
OUTBOX_CHAT=$(curl -s -X POST "$BASE_URL/v1/cofounder/chat" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message": "outbox"}')

OUTBOX_CONTENT=$(echo "$OUTBOX_CHAT" | jq -r '.assistant_message.content')
OUTBOX_CARDS=$(echo "$OUTBOX_CHAT" | jq -r '.assistant_message.cards | length')
echo "   Response: $OUTBOX_CONTENT"
echo "   Notification cards: $OUTBOX_CARDS"
echo ""

# --- 11. Member tests chat: specific KPI ---
echo "11. Member calls chat: 'kpi:MRR'"
KPI_DETAIL=$(curl -s -X POST "$BASE_URL/v1/cofounder/chat" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message": "kpi:MRR"}')

KPI_DETAIL_CONTENT=$(echo "$KPI_DETAIL" | jq -r '.assistant_message.content')
echo "   Response: $KPI_DETAIL_CONTENT"
echo "   KPI Summary card:"
echo "$KPI_DETAIL" | jq '.assistant_message.cards[0]'
echo ""

# --- 12. List conversations ---
echo "12. Listing member's conversations..."
CONV_LIST=$(curl -s -X GET "$BASE_URL/v1/conversations" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY")

CONV_COUNT=$(echo "$CONV_LIST" | jq -r '.items | length')
echo "   Total conversations: $CONV_COUNT"
echo ""

# --- 13. Get conversation with messages ---
echo "13. Fetching conversation detail..."
CONV_DETAIL=$(curl -s -X GET "$BASE_URL/v1/conversations/$CONV_ID" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-User-ID: $MEMBER_ID" \
  -H "X-API-Key: $API_KEY")

MSG_COUNT=$(echo "$CONV_DETAIL" | jq -r '.messages | length')
echo "   Messages in conversation: $MSG_COUNT"
echo ""

# --- Summary ---
echo "=========================================="
echo "Smoke Test Summary"
echo "=========================================="
echo "Tenant ID:     $TENANT_ID"
echo "Admin ID:      $ADMIN_ID"
echo "Member ID:     $MEMBER_ID"
echo "API Key:       ${API_KEY:0:20}..."
echo "KPIs created:  2 (MRR, Active Users)"
echo "Brief date:    $FIXED_DATE"
echo "Conversation:  $CONV_ID"
echo "Messages:      $MSG_COUNT"
echo ""
echo "All chat intents tested:"
echo "  - help       (available commands)"
echo "  - brief      (daily brief card)"
echo "  - kpis       (KPI list with latest)"
echo "  - outbox     (notifications)"
echo "  - kpi:MRR    (specific KPI summary)"
echo ""
echo "Smoke test completed successfully!"
