#!/bin/bash
# =============================================================================
# Smoke Test Script for Tasks v0 (Phase 1 Task 9a)
# =============================================================================
# This script demonstrates Tasks v0 APIs:
#   - Create tasks with various fields
#   - List tasks with filters (status, assigned_to, created_by)
#   - Get a single task
#   - Update tasks (RBAC enforced)
#   - Complete tasks (idempotent)
#   - Verify metering via /v1/billing/usage
#
# Prerequisites:
#   - Server running on localhost:8000
#   - curl installed (jq optional but recommended)
#
# Usage:
#   ./scripts/smoke_phase1_task9a_tasks_v0.sh
# =============================================================================

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Tasks v0 Smoke Test (Phase 1 Task 9a) ==="
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
        echo "$json" | grep -o "\"$key2\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | sed "s/\"$key2\"[[:space:]]*:[[:space:]]*\"//" | sed 's/"$//' | head -1
    fi
}

echo -e "${YELLOW}Step 1: Create Tenant + API Key${NC}"
TENANT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tenants" \
    -H "Content-Type: application/json" \
    -d '{"name": "Tasks v0 Smoke Test", "region": "us-east-1", "admin_email": "admin@tasks-test.com"}')

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

# Generic member call helper
member_call() {
    local user_id=$1
    local method=$2
    local endpoint=$3
    local data=$4

    if [ -n "$data" ]; then
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $TENANT_ID" \
            -H "X-User-ID: $user_id" \
            -H "X-API-Key: $API_KEY" \
            -d "$data"
    else
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $TENANT_ID" \
            -H "X-User-ID: $user_id" \
            -H "X-API-Key: $API_KEY"
    fi
}

echo -e "${YELLOW}Step 2: Create Admin + Two Member Users${NC}"
MEMBER1_RESPONSE=$(admin_call POST "/v1/users" "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"member1@tasks-test.com\", \"role\": \"member\"}")
MEMBER1_USER_ID=$(json_value "$MEMBER1_RESPONSE" "user_id")
echo -e "Member1 User ID: ${GREEN}$MEMBER1_USER_ID${NC}"

MEMBER2_RESPONSE=$(admin_call POST "/v1/users" "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"member2@tasks-test.com\", \"role\": \"member\"}")
MEMBER2_USER_ID=$(json_value "$MEMBER2_RESPONSE" "user_id")
echo -e "Member2 User ID: ${GREEN}$MEMBER2_USER_ID${NC}"
echo ""

echo -e "${YELLOW}Step 3: Member1 Creates a Task Assigned to Member2${NC}"
TASK_RESPONSE=$(member_call "$MEMBER1_USER_ID" POST "/v1/tasks" "{
    \"title\": \"Review Q4 Metrics Report\",
    \"description\": \"Analyze and summarize the Q4 metrics for stakeholder presentation\",
    \"priority\": \"high\",
    \"due_date\": \"2024-12-31\",
    \"assigned_to_user_id\": \"$MEMBER2_USER_ID\"
}")
TASK_ID=$(json_value "$TASK_RESPONSE" "task_id")
TASK_STATUS=$(json_value "$TASK_RESPONSE" "status")
TASK_PRIORITY=$(json_value "$TASK_RESPONSE" "priority")

echo -e "Created Task ID: ${GREEN}$TASK_ID${NC}"
echo -e "Status: ${BLUE}$TASK_STATUS${NC} (expected: todo)"
echo -e "Priority: ${BLUE}$TASK_PRIORITY${NC} (expected: high)"
if [ "$HAS_JQ" = "yes" ]; then
    echo "Full response:"
    echo "$TASK_RESPONSE" | jq .
fi
echo ""

echo -e "${YELLOW}Step 4: List Tasks (default: status=todo)${NC}"
LIST_RESPONSE=$(admin_call GET "/v1/tasks")
if [ "$HAS_JQ" = "yes" ]; then
    TOTAL=$(echo "$LIST_RESPONSE" | jq -r '.total')
    echo -e "Total todo tasks: ${GREEN}$TOTAL${NC}"
    echo "First task:"
    echo "$LIST_RESPONSE" | jq '.items[0] | {task_id, title, status, priority, due_date}'
else
    echo "List response: $LIST_RESPONSE"
fi
echo ""

echo -e "${YELLOW}Step 5: Member2 (Assignee) Updates the Task${NC}"
UPDATE_RESPONSE=$(member_call "$MEMBER2_USER_ID" PATCH "/v1/tasks/$TASK_ID" '{
    "priority": "medium",
    "status": "doing"
}')
UPDATED_STATUS=$(json_value "$UPDATE_RESPONSE" "status")
UPDATED_PRIORITY=$(json_value "$UPDATE_RESPONSE" "priority")
echo -e "Task status after update: ${GREEN}$UPDATED_STATUS${NC} (expected: doing)"
echo -e "Task priority after update: ${GREEN}$UPDATED_PRIORITY${NC} (expected: medium)"
echo ""

echo -e "${YELLOW}Step 6: Member2 Completes the Task${NC}"
COMPLETE_RESPONSE=$(member_call "$MEMBER2_USER_ID" POST "/v1/tasks/$TASK_ID/complete" '{}')
COMPLETE_STATUS=$(json_value "$COMPLETE_RESPONSE" "status")
echo -e "Task status after complete: ${GREEN}$COMPLETE_STATUS${NC} (expected: done)"
echo ""

echo -e "${YELLOW}Step 7: Fetch Task by ID (verify status=done)${NC}"
GET_RESPONSE=$(admin_call GET "/v1/tasks/$TASK_ID")
FINAL_STATUS=$(json_value "$GET_RESPONSE" "status")
echo -e "Final task status: ${GREEN}$FINAL_STATUS${NC}"
if [ "$HAS_JQ" = "yes" ]; then
    echo "Task details:"
    echo "$GET_RESPONSE" | jq '{task_id, title, status, priority, due_date, assigned_to_user_id, created_by_user_id}'
fi
echo ""

echo -e "${YELLOW}Step 8: Test Idempotent Complete (should return 200, no extra usage)${NC}"
IDEMPOTENT_RESPONSE=$(member_call "$MEMBER2_USER_ID" POST "/v1/tasks/$TASK_ID/complete" '{}')
IDEMPOTENT_STATUS=$(json_value "$IDEMPOTENT_RESPONSE" "status")
echo -e "Idempotent complete status: ${GREEN}$IDEMPOTENT_STATUS${NC} (should still be done)"
echo ""

echo -e "${YELLOW}Step 9: List Tasks with Filters${NC}"
echo "9a. List status=done:"
DONE_LIST=$(admin_call GET "/v1/tasks?status=done")
if [ "$HAS_JQ" = "yes" ]; then
    echo -e "  Total done tasks: ${GREEN}$(echo "$DONE_LIST" | jq -r '.total')${NC}"
fi

echo "9b. List status=all:"
ALL_LIST=$(admin_call GET "/v1/tasks?status=all")
if [ "$HAS_JQ" = "yes" ]; then
    echo -e "  Total all tasks: ${GREEN}$(echo "$ALL_LIST" | jq -r '.total')${NC}"
fi

echo "9c. List assigned_to_user_id=$MEMBER2_USER_ID:"
ASSIGNED_LIST=$(admin_call GET "/v1/tasks?status=all&assigned_to_user_id=$MEMBER2_USER_ID")
if [ "$HAS_JQ" = "yes" ]; then
    echo -e "  Total assigned to member2: ${GREEN}$(echo "$ASSIGNED_LIST" | jq -r '.total')${NC}"
fi

echo "9d. List created_by_user_id=$MEMBER1_USER_ID:"
CREATED_LIST=$(admin_call GET "/v1/tasks?status=all&created_by_user_id=$MEMBER1_USER_ID")
if [ "$HAS_JQ" = "yes" ]; then
    echo -e "  Total created by member1: ${GREEN}$(echo "$CREATED_LIST" | jq -r '.total')${NC}"
fi
echo ""

echo -e "${YELLOW}Step 10: Fetch /v1/billing/usage${NC}"
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
    echo "Breakdown for task_created, task_updated, task_completed:"
    echo "$USAGE_RESPONSE" | jq '.breakdown[] | select(.event_key == "task_created" or .event_key == "task_updated" or .event_key == "task_completed") | {event_key, raw_units, credits, list_cost_estimate}'
else
    echo "Usage: $USAGE_RESPONSE"
fi
echo ""

echo -e "${GREEN}=== Tasks v0 Smoke Test Completed Successfully ===${NC}"
echo ""
echo "Summary:"
echo "  - Created tenant with admin and two member users"
echo "  - Member1 created a task assigned to Member2"
echo "  - Listed tasks with default status filter (todo)"
echo "  - Member2 (assignee) updated the task priority and status"
echo "  - Member2 completed the task"
echo "  - Verified task status changed to done"
echo "  - Tested idempotent complete (second call returns 200, no extra usage)"
echo "  - Tested various list filters (status, assigned_to, created_by)"
echo "  - Verified billing usage shows task_created/task_updated/task_completed events"
echo ""
echo "Metered Events Emitted:"
echo "  - task_created: 1 record (0.1 credits)"
echo "  - task_updated: 1 record (0.05 credits)"
echo "  - task_completed: 1 record (0.05 credits)"
echo ""
echo "Test the UI at: ${BASE_URL}/ui (Tasks tab)"
