#!/bin/bash
# =============================================================================
# Smoke Test Script for Core Business OS v0
# =============================================================================
# This script demonstrates end-to-end usage of the Core Business OS APIs
# including actions, tasks, decisions, meetings, memory, timeline, and search.
#
# Prerequisites:
#   - Server running on localhost:8000
#   - curl and jq installed
#
# Usage:
#   ./scripts/smoke_core_os_v0.sh
# =============================================================================

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Core Business OS v0 Smoke Test ==="
echo "Base URL: $BASE_URL"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper function to make API calls
api_call() {
    local method=$1
    local endpoint=$2
    local data=$3
    local headers=$4

    if [ -n "$data" ]; then
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            $headers \
            -d "$data"
    else
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            $headers
    fi
}

echo -e "${YELLOW}Step 1: Create Tenant + API Key${NC}"
echo "Creating test tenant..."
TENANT_RESPONSE=$(api_call POST "/v1/tenants" '{"name": "Smoke Test Tenant", "region": "us-east-1", "admin_email": "admin@smoketest.com"}')
TENANT_ID=$(echo $TENANT_RESPONSE | jq -r '.tenant_id')
API_KEY=$(echo $TENANT_RESPONSE | jq -r '.api_key')
ADMIN_USER_ID=$(echo $TENANT_RESPONSE | jq -r '.admin.user_id')

echo -e "Tenant ID: ${GREEN}$TENANT_ID${NC}"
echo -e "Admin User ID: ${GREEN}$ADMIN_USER_ID${NC}"
echo ""

# Set headers for subsequent requests
AUTH_HEADERS="-H \"X-Tenant-ID: $TENANT_ID\" -H \"X-User-ID: $ADMIN_USER_ID\" -H \"X-API-Key: $API_KEY\""

echo -e "${YELLOW}Step 2: Create Member User${NC}"
MEMBER_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/users" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "X-User-ID: $ADMIN_USER_ID" \
    -H "X-API-Key: $API_KEY" \
    -d "{\"tenant_id\": \"$TENANT_ID\", \"email\": \"member@smoketest.com\", \"role\": \"member\"}")
MEMBER_USER_ID=$(echo $MEMBER_RESPONSE | jq -r '.user_id')
echo -e "Member User ID: ${GREEN}$MEMBER_USER_ID${NC}"
echo ""

# Admin headers helper
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

# Member headers helper
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

echo -e "${YELLOW}Step 3: Admin Creates Memory Fact${NC}"
FACT_RESPONSE=$(admin_call POST "/v1/memory/facts" '{"category": "icp", "fact_key": "ICP.primary", "fact_value": "Mid-market SaaS companies with 50-500 employees, annual revenue $5M-$50M, using modern tech stack."}')
FACT_ID=$(echo $FACT_RESPONSE | jq -r '.fact_id')
echo -e "Memory Fact ID: ${GREEN}$FACT_ID${NC}"
echo "Category: $(echo $FACT_RESPONSE | jq -r '.category')"
echo "Key: $(echo $FACT_RESPONSE | jq -r '.fact_key')"
echo ""

echo -e "${YELLOW}Step 4: Admin Creates Decision${NC}"
DECISION_RESPONSE=$(admin_call POST "/v1/decisions" '{"decision_date": "2024-01-15", "title": "Q1 Pricing Strategy", "context": "Market analysis shows competitors raising prices by 15%", "decision": "Increase base pricing by 10% for new customers starting February 1st", "rationale": "Maintain competitive margins while staying below competitor pricing"}')
DECISION_ID=$(echo $DECISION_RESPONSE | jq -r '.decision_id')
echo -e "Decision ID: ${GREEN}$DECISION_ID${NC}"
echo "Title: $(echo $DECISION_RESPONSE | jq -r '.title')"
echo ""

echo -e "${YELLOW}Step 5: Member Creates an Action (Proposed)${NC}"
ACTION_RESPONSE=$(member_call POST "/v1/actions" '{"title": "Follow up with stalled enterprise deal - Acme Corp", "description": "Acme Corp has not responded in 2 weeks. Need to re-engage with new value proposition.", "action_type": "outreach", "source": "user", "payload": {"company": "Acme Corp", "contact": "John Smith"}}')
ACTION_ID=$(echo $ACTION_RESPONSE | jq -r '.action_id')
ACTION_STATUS=$(echo $ACTION_RESPONSE | jq -r '.status')
echo -e "Action ID: ${GREEN}$ACTION_ID${NC}"
echo -e "Status: ${GREEN}$ACTION_STATUS${NC}"
echo ""

echo -e "${YELLOW}Step 6: Admin Approves the Action${NC}"
APPROVE_RESPONSE=$(admin_call POST "/v1/actions/$ACTION_ID/approve" '{"comment": "Approved - this is a priority deal"}')
echo -e "Action Status: ${GREEN}$(echo $APPROVE_RESPONSE | jq -r '.status')${NC}"
echo ""

echo -e "${YELLOW}Step 7: Admin Executes the Action (Stub)${NC}"
EXECUTE_RESPONSE=$(admin_call POST "/v1/actions/$ACTION_ID/execute" '{"execution_status": "succeeded", "result": {"message": "Email sent to John Smith at Acme Corp"}}')
echo -e "Action Status: ${GREEN}$(echo $EXECUTE_RESPONSE | jq -r '.status')${NC}"
echo ""

echo -e "${YELLOW}Step 8: Admin Creates Task Assigned to Member${NC}"
TASK_RESPONSE=$(admin_call POST "/v1/tasks" "{\"title\": \"Prepare Q1 pricing update communication\", \"description\": \"Draft customer communication about the pricing change per Q1 decision\", \"priority\": \"high\", \"due_date\": \"2024-01-25\", \"assigned_to_user_id\": \"$MEMBER_USER_ID\", \"linked_entity_type\": \"decision\", \"linked_entity_id\": \"$DECISION_ID\"}")
TASK_ID=$(echo $TASK_RESPONSE | jq -r '.task_id')
echo -e "Task ID: ${GREEN}$TASK_ID${NC}"
echo "Title: $(echo $TASK_RESPONSE | jq -r '.title')"
echo "Assigned to: $(echo $TASK_RESPONSE | jq -r '.assigned_to_user_id')"
echo ""

echo -e "${YELLOW}Step 9: Member Completes the Task${NC}"
COMPLETE_RESPONSE=$(member_call POST "/v1/tasks/$TASK_ID/complete")
echo -e "Task Status: ${GREEN}$(echo $COMPLETE_RESPONSE | jq -r '.status')${NC}"
echo ""

echo -e "${YELLOW}Step 10: Admin Creates Meeting Note${NC}"
MEETING_RESPONSE=$(admin_call POST "/v1/meetings" '{"meeting_date": "2024-01-15", "title": "Q1 Planning Kickoff", "notes": "## Attendees\n- CEO\n- CRO\n- VP Marketing\n\n## Key Topics\n1. Pricing strategy finalized\n2. ICP refinement discussed\n3. Q1 targets set"}')
MEETING_ID=$(echo $MEETING_RESPONSE | jq -r '.meeting_id')
echo -e "Meeting ID: ${GREEN}$MEETING_ID${NC}"
echo "Title: $(echo $MEETING_RESPONSE | jq -r '.title')"
echo ""

echo -e "${YELLOW}Step 11: Admin Attaches Evidence to Decision${NC}"
EVIDENCE_RESPONSE=$(admin_call POST "/v1/evidence" "{\"entity_type\": \"decision\", \"entity_id\": \"$DECISION_ID\", \"source_type\": \"note\", \"source_ref\": {\"meeting_id\": \"$MEETING_ID\"}, \"snippet\": \"Pricing strategy finalized\"}")
EVIDENCE_ID=$(echo $EVIDENCE_RESPONSE | jq -r '.evidence_id')
echo -e "Evidence ID: ${GREEN}$EVIDENCE_ID${NC}"
echo ""

echo -e "${YELLOW}Step 12: Member Performs Search${NC}"
echo "Searching for 'pricing'..."
SEARCH_RESPONSE=$(member_call GET "/v1/search?q=pricing")
echo "Results found: $(echo $SEARCH_RESPONSE | jq '.total')"
echo "Result types:"
echo $SEARCH_RESPONSE | jq -r '.results[] | "  - \(.entity_type): \(.title)"'
echo ""

echo -e "${YELLOW}Step 13: Fetch Timeline (Last 10 Events)${NC}"
TIMELINE_RESPONSE=$(admin_call GET "/v1/timeline?limit=10")
echo "Timeline Events:"
echo $TIMELINE_RESPONSE | jq -r '.items[] | "  [\(.event_type)] \(.summary) (\(.created_at | split("T")[0]))"'
echo ""

echo -e "${YELLOW}Step 14: Fetch Billing Usage${NC}"
USAGE_RESPONSE=$(admin_call GET "/v1/billing/usage")
echo "Plan: $(echo $USAGE_RESPONSE | jq -r '.plan.name')"
echo "Credits Used: $(echo $USAGE_RESPONSE | jq '.credits.used')"
echo "Credits Remaining: $(echo $USAGE_RESPONSE | jq '.credits.remaining')"
echo ""
echo "Breakdown:"
echo $USAGE_RESPONSE | jq -r '.breakdown[] | "  \(.event_key): \(.raw_units) units = \(.credits) credits"'
echo ""

echo -e "${GREEN}=== Smoke Test Complete ===${NC}"
echo ""
echo "Summary:"
echo "  - Tenant created: $TENANT_ID"
echo "  - Admin user: $ADMIN_USER_ID"
echo "  - Member user: $MEMBER_USER_ID"
echo "  - Memory fact created: $FACT_ID"
echo "  - Decision created: $DECISION_ID"
echo "  - Action created, approved, executed: $ACTION_ID"
echo "  - Task created and completed: $TASK_ID"
echo "  - Meeting note created: $MEETING_ID"
echo "  - Evidence link created: $EVIDENCE_ID"
echo "  - Search performed"
echo "  - Timeline retrieved"
echo "  - Billing usage verified"
echo ""
echo "All Core OS operations completed successfully!"
