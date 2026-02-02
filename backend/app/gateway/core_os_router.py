"""Core Business OS API Router.

Provides APIs for:
- Action Center (proposed actions, approvals, execution)
- Tasks (Work OS)
- Decisions (Strategy OS)
- Meeting Notes
- Governed Memory (facts)
- Evidence/Provenance Links
- Unified Timeline
- Global Search
- Record Explorer
"""
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.gateway.models import (
    Action,
    ActionReview,
    ActionExecution,
    Task,
    MeetingNote,
    Decision,
    MemoryFact,
    EvidenceLink,
    TimelineEvent,
    AuditLog,
)
from app.gateway.auth import TenantContext, get_tenant_context, require_admin
from app.gateway.entitlements import check_entitlement, check_quota as check_billing_quota
from app.gateway.metering import emit_usage
from app.gateway.billing_period import get_current_utc_datetime_iso

router = APIRouter(prefix="/v1", tags=["core-os"])


# =============================================================================
# Schemas
# =============================================================================

# Action Schemas
class ActionCreate(BaseModel):
    """Request schema for creating an action."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    action_type: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    assigned_to_user_id: str | None = None
    source: str = Field(default="user", pattern="^(user|agent|system)$")
    source_ref: str | None = None


class ActionUpdate(BaseModel):
    """Request schema for updating an action."""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(None, pattern="^(cancelled)$")  # Only allow cancel via update


class ActionApproveReject(BaseModel):
    """Request schema for approving/rejecting an action."""
    comment: str | None = None


class ActionCancel(BaseModel):
    """Request schema for cancelling an action."""
    comment: str | None = None


class ActionExecute(BaseModel):
    """Request schema for executing an action."""
    execution_status: str = Field(..., pattern="^(succeeded|failed|skipped)$")
    result: dict[str, Any] = Field(default_factory=dict)


class ActionResponse(BaseModel):
    """Response schema for an action."""
    action_id: str
    tenant_id: str
    created_by_user_id: str
    assigned_to_user_id: str | None
    source: str
    source_ref: str | None
    status: str
    title: str
    description: str | None
    action_type: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ActionListResponse(BaseModel):
    """Response schema for listing actions."""
    items: list[ActionResponse]
    total: int
    limit: int
    offset: int


# Task Schemas
class TaskCreate(BaseModel):
    """Request schema for creating a task."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    assigned_to_user_id: str | None = None
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")
    due_date: str | None = Field(None, pattern="^\\d{4}-\\d{2}-\\d{2}$")
    linked_entity_type: str | None = None
    linked_entity_id: str | None = None


class TaskUpdate(BaseModel):
    """Request schema for updating a task."""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    assigned_to_user_id: str | None = None
    priority: str | None = Field(None, pattern="^(low|medium|high)$")
    due_date: str | None = Field(None, pattern="^\\d{4}-\\d{2}-\\d{2}$")
    status: str | None = Field(None, pattern="^(todo|doing|done)$")


class TaskResponse(BaseModel):
    """Response schema for a task."""
    task_id: str
    tenant_id: str
    created_by_user_id: str
    assigned_to_user_id: str | None
    status: str
    priority: str
    due_date: str | None
    title: str
    description: str | None
    linked_entity_type: str | None
    linked_entity_id: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Response schema for listing tasks."""
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


# Decision Schemas
class DecisionCreate(BaseModel):
    """Request schema for creating a decision."""
    decision_date: str = Field(..., pattern="^\\d{4}-\\d{2}-\\d{2}$")
    title: str = Field(..., min_length=1, max_length=255)
    context: str | None = None
    decision: str = Field(..., min_length=1)
    rationale: str | None = None


class DecisionUpdate(BaseModel):
    """Request schema for updating a decision."""
    title: str | None = Field(None, min_length=1, max_length=255)
    context: str | None = None
    decision: str | None = Field(None, min_length=1)
    rationale: str | None = None


class DecisionResponse(BaseModel):
    """Response schema for a decision."""
    decision_id: str
    tenant_id: str
    created_by_user_id: str
    decision_date: str
    title: str
    context: str | None
    decision: str
    rationale: str | None
    status: str
    superseded_by_decision_id: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class DecisionListResponse(BaseModel):
    """Response schema for listing decisions."""
    items: list[DecisionResponse]
    total: int
    limit: int
    offset: int


# Meeting Note Schemas
class MeetingNoteCreate(BaseModel):
    """Request schema for creating a meeting note."""
    meeting_date: str = Field(..., pattern="^\\d{4}-\\d{2}-\\d{2}$")
    title: str = Field(..., min_length=1, max_length=255)
    notes: str = Field(..., min_length=1)
    linked_entity_type: str | None = None
    linked_entity_id: str | None = None


class MeetingNoteUpdate(BaseModel):
    """Request schema for updating a meeting note."""
    title: str | None = Field(None, min_length=1, max_length=255)
    notes: str | None = Field(None, min_length=1)
    linked_entity_type: str | None = None
    linked_entity_id: str | None = None


class MeetingNoteResponse(BaseModel):
    """Response schema for a meeting note."""
    meeting_id: str
    tenant_id: str
    created_by_user_id: str
    meeting_date: str
    title: str
    notes: str
    linked_entity_type: str | None
    linked_entity_id: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MeetingNoteListResponse(BaseModel):
    """Response schema for listing meeting notes."""
    items: list[MeetingNoteResponse]
    total: int
    limit: int
    offset: int


# Memory Fact Schemas
class MemoryFactCreate(BaseModel):
    """Request schema for creating a memory fact."""
    category: str = Field(..., pattern="^(icp|positioning|pricing|goals|constraints|brand|other)$")
    fact_key: str = Field(..., min_length=1, max_length=255)
    fact_value: str = Field(..., min_length=1)


class MemoryFactUpdate(BaseModel):
    """Request schema for updating a memory fact."""
    fact_value: str | None = Field(None, min_length=1)


class MemoryFactSupersede(BaseModel):
    """Request schema for superseding a memory fact."""
    fact_value: str = Field(..., min_length=1)


class MemoryFactResponse(BaseModel):
    """Response schema for a memory fact."""
    fact_id: str
    tenant_id: str
    created_by_user_id: str
    category: str
    fact_key: str
    fact_value: str
    status: str
    supersedes_fact_id: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MemoryFactListResponse(BaseModel):
    """Response schema for listing memory facts."""
    items: list[MemoryFactResponse]
    total: int
    limit: int
    offset: int


# Evidence Link Schemas
class EvidenceLinkCreate(BaseModel):
    """Request schema for creating an evidence link."""
    entity_type: str = Field(..., pattern="^(action|task|decision|memory_fact)$")
    entity_id: str = Field(..., min_length=1)
    source_type: str = Field(..., pattern="^(kpi|brief|note|decision|task|manual)$")
    source_ref: dict[str, Any] = Field(...)
    snippet: str | None = None


class EvidenceLinkResponse(BaseModel):
    """Response schema for an evidence link."""
    evidence_id: str
    tenant_id: str
    entity_type: str
    entity_id: str
    source_type: str
    source_ref: dict[str, Any]
    snippet: str | None
    created_by_user_id: str
    created_at: str

    class Config:
        from_attributes = True


class EvidenceLinkListResponse(BaseModel):
    """Response schema for listing evidence links."""
    items: list[EvidenceLinkResponse]
    total: int


# Timeline Schemas
class TimelineEventResponse(BaseModel):
    """Response schema for a timeline event."""
    event_id: str
    tenant_id: str
    actor_user_id: str
    event_type: str
    entity_type: str
    entity_id: str
    summary: str
    metadata: dict[str, Any]
    created_at: str

    class Config:
        from_attributes = True


class TimelineListResponse(BaseModel):
    """Response schema for listing timeline events."""
    items: list[TimelineEventResponse]
    total: int
    limit: int
    offset: int


# Search Schemas
class SearchResultItem(BaseModel):
    """A single search result item."""
    entity_type: str
    entity_id: str
    title: str
    snippet: str | None
    updated_at: str


class SearchResponse(BaseModel):
    """Response schema for search results."""
    q: str
    results: list[SearchResultItem]
    total: int


# Record Explorer Schemas
class RecordExplorerResponse(BaseModel):
    """Response schema for record explorer."""
    entity: dict[str, Any]
    evidence: list[EvidenceLinkResponse]
    timeline: list[TimelineEventResponse]


# =============================================================================
# Helper Functions
# =============================================================================

def log_timeline_event(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> TimelineEvent:
    """Log an event to the unified timeline."""
    now_iso = get_current_utc_datetime_iso()
    event = TimelineEvent(
        event_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        metadata_json=json.dumps(metadata or {}),
        created_at=now_iso,
    )
    db.add(event)
    return event


def log_audit(
    db: Session,
    tenant_id: str,
    user_id: str,
    action: str,
    tool_name: str,
    request_id: str,
) -> AuditLog:
    """Log an audit record."""
    audit = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        tool_name=tool_name,
        request_id=request_id,
    )
    db.add(audit)
    return audit


# =============================================================================
# Action Center Endpoints
# =============================================================================

@router.post("/actions", response_model=ActionResponse, status_code=status.HTTP_201_CREATED)
def create_action(
    action_data: ActionCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ActionResponse:
    """Create a new proposed action."""
    request_id = str(uuid.uuid4())

    # Entitlement check
    check_entitlement(db, context.tenant_id, "action_center")

    # Quota check
    check_billing_quota(db, context.tenant_id, "action_created", 1)

    now_iso = get_current_utc_datetime_iso()
    action_id = str(uuid.uuid4())

    action = Action(
        action_id=action_id,
        tenant_id=context.tenant_id,
        created_by_user_id=context.user_id,
        assigned_to_user_id=action_data.assigned_to_user_id,
        source=action_data.source,
        source_ref=action_data.source_ref,
        status="proposed",
        title=action_data.title,
        description=action_data.description,
        action_type=action_data.action_type,
        payload_json=json.dumps(action_data.payload),
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(action)

    # Log timeline event
    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "action_created", "action", action_id,
        f"Action proposed: {action_data.title}",
        {"action_type": action_data.action_type, "source": action_data.source}
    )

    # Audit log
    log_audit(db, context.tenant_id, context.user_id, "actions.create", "action_center", request_id)

    # Emit usage
    emit_usage(db, context.tenant_id, context.user_id, "action_created", 1, request_id, "action_center")

    db.commit()
    db.refresh(action)

    return ActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        created_by_user_id=action.created_by_user_id,
        assigned_to_user_id=action.assigned_to_user_id,
        source=action.source,
        source_ref=action.source_ref,
        status=action.status,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        payload=json.loads(action.payload_json),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.get("/actions", response_model=ActionListResponse)
def list_actions(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    status_filter: str | None = Query("proposed", alias="status"),
    created_by_user_id: str | None = None,
    assigned_to_user_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ActionListResponse:
    """List actions for the tenant.

    Args:
        status: Filter by status (proposed, approved, rejected, cancelled, executed, or all). Default: proposed.
        created_by_user_id: Filter by creator.
        assigned_to_user_id: Filter by assignee.
        limit: Max results (1-200). Default: 50.
        offset: Skip results for pagination.
    """
    check_entitlement(db, context.tenant_id, "action_center")

    query = db.query(Action).filter(Action.tenant_id == context.tenant_id)

    # Filter by status (default "proposed", "all" returns everything)
    if status_filter and status_filter != "all":
        query = query.filter(Action.status == status_filter)
    if created_by_user_id:
        query = query.filter(Action.created_by_user_id == created_by_user_id)
    if assigned_to_user_id:
        query = query.filter(Action.assigned_to_user_id == assigned_to_user_id)

    total = query.count()
    actions = query.order_by(Action.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        ActionResponse(
            action_id=a.action_id,
            tenant_id=a.tenant_id,
            created_by_user_id=a.created_by_user_id,
            assigned_to_user_id=a.assigned_to_user_id,
            source=a.source,
            source_ref=a.source_ref,
            status=a.status,
            title=a.title,
            description=a.description,
            action_type=a.action_type,
            payload=json.loads(a.payload_json),
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in actions
    ]

    return ActionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/actions/{action_id}", response_model=ActionResponse)
def get_action(
    action_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ActionResponse:
    """Get a specific action."""
    check_entitlement(db, context.tenant_id, "action_center")

    action = db.query(Action).filter(
        Action.action_id == action_id,
        Action.tenant_id == context.tenant_id
    ).first()

    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    return ActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        created_by_user_id=action.created_by_user_id,
        assigned_to_user_id=action.assigned_to_user_id,
        source=action.source,
        source_ref=action.source_ref,
        status=action.status,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        payload=json.loads(action.payload_json),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.patch("/actions/{action_id}", response_model=ActionResponse)
def update_action(
    action_id: str,
    update_data: ActionUpdate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ActionResponse:
    """Update an action."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "action_center")

    action = db.query(Action).filter(
        Action.action_id == action_id,
        Action.tenant_id == context.tenant_id
    ).first()

    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    # RBAC: Only creator can update proposed actions (unless admin)
    is_admin = context.user.role == "admin"
    is_creator = action.created_by_user_id == context.user_id

    if not is_admin and not is_creator:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this action")

    if not is_admin and action.status != "proposed":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only update proposed actions")

    # Track if anything changed
    changed = False

    if update_data.title is not None and update_data.title != action.title:
        action.title = update_data.title
        changed = True
    if update_data.description is not None and update_data.description != action.description:
        action.description = update_data.description
        changed = True
    if update_data.status == "cancelled" and action.status == "proposed":
        action.status = "cancelled"
        changed = True

    if changed:
        check_billing_quota(db, context.tenant_id, "action_updated", 1)
        action.updated_at = get_current_utc_datetime_iso()

        log_timeline_event(
            db, context.tenant_id, context.user_id,
            "action_updated", "action", action_id,
            f"Action updated: {action.title}",
            {"status": action.status}
        )

        log_audit(db, context.tenant_id, context.user_id, "actions.update", "action_center", request_id)
        emit_usage(db, context.tenant_id, context.user_id, "action_updated", 1, request_id, "action_center")
        db.commit()
        db.refresh(action)

    return ActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        created_by_user_id=action.created_by_user_id,
        assigned_to_user_id=action.assigned_to_user_id,
        source=action.source,
        source_ref=action.source_ref,
        status=action.status,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        payload=json.loads(action.payload_json),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.post("/actions/{action_id}/cancel", response_model=ActionResponse)
def cancel_action(
    action_id: str,
    cancel_data: ActionCancel,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ActionResponse:
    """Cancel an action.

    RBAC Rules:
    - Member can cancel their own proposed actions.
    - Admin can cancel any proposed action in the tenant.

    Idempotent: If action is already cancelled, returns 200 without emitting usage/audit.
    """
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "action_center")

    action = db.query(Action).filter(
        Action.action_id == action_id,
        Action.tenant_id == context.tenant_id
    ).first()

    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    # If already cancelled, return without emitting usage/audit (idempotent)
    if action.status == "cancelled":
        return ActionResponse(
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            created_by_user_id=action.created_by_user_id,
            assigned_to_user_id=action.assigned_to_user_id,
            source=action.source,
            source_ref=action.source_ref,
            status=action.status,
            title=action.title,
            description=action.description,
            action_type=action.action_type,
            payload=json.loads(action.payload_json),
            created_at=action.created_at,
            updated_at=action.updated_at,
        )

    # Can only cancel proposed actions
    if action.status != "proposed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only cancel proposed actions"
        )

    # RBAC check
    is_admin = context.user.role == "admin"
    is_creator = action.created_by_user_id == context.user_id

    if not is_admin and not is_creator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to cancel this action"
        )

    # Quota check before write
    check_billing_quota(db, context.tenant_id, "action_updated", 1)

    # Perform the cancellation
    action.status = "cancelled"
    action.updated_at = get_current_utc_datetime_iso()

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "action_cancelled", "action", action_id,
        f"Action cancelled: {action.title}",
        {"comment": cancel_data.comment}
    )

    log_audit(db, context.tenant_id, context.user_id, "actions.cancel", "action_center", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "action_updated", 1, request_id, "action_center")

    db.commit()
    db.refresh(action)

    return ActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        created_by_user_id=action.created_by_user_id,
        assigned_to_user_id=action.assigned_to_user_id,
        source=action.source,
        source_ref=action.source_ref,
        status=action.status,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        payload=json.loads(action.payload_json),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.post("/actions/{action_id}/approve", response_model=ActionResponse)
def approve_action(
    action_id: str,
    approve_data: ActionApproveReject,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ActionResponse:
    """Approve an action (admin only).

    Idempotent: If already approved, returns 200 without emitting usage/audit/timeline.
    Returns 409 Conflict if:
    - Action is cancelled (cannot approve cancelled action)
    - Action is already rejected (cannot change decision)
    """
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "action_center")
    require_admin(context)

    action = db.query(Action).filter(
        Action.action_id == action_id,
        Action.tenant_id == context.tenant_id
    ).first()

    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    # Idempotent: if already approved, return without new writes
    if action.status == "approved":
        return ActionResponse(
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            created_by_user_id=action.created_by_user_id,
            assigned_to_user_id=action.assigned_to_user_id,
            source=action.source,
            source_ref=action.source_ref,
            status=action.status,
            title=action.title,
            description=action.description,
            action_type=action.action_type,
            payload=json.loads(action.payload_json),
            created_at=action.created_at,
            updated_at=action.updated_at,
        )

    # 409 Conflict for cancelled actions
    if action.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot approve a cancelled action"
        )

    # 409 Conflict for rejected actions (cannot change decision)
    if action.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot approve an already rejected action"
        )

    # Can only approve proposed actions
    if action.status != "proposed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot approve action with status '{action.status}'"
        )

    check_billing_quota(db, context.tenant_id, "action_approved", 1)

    now_iso = get_current_utc_datetime_iso()

    # Create review record
    review = ActionReview(
        tenant_id=context.tenant_id,
        action_id=action_id,
        reviewer_user_id=context.user_id,
        decision="approved",
        comment=approve_data.comment,
        created_at=now_iso,
    )
    db.add(review)

    action.status = "approved"
    action.updated_at = now_iso

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "action_approved", "action", action_id,
        f"Action approved: {action.title}",
        {"action_id": action_id, "decision": "approved", "comment": approve_data.comment, "reviewer_user_id": context.user_id}
    )

    log_audit(db, context.tenant_id, context.user_id, "actions.approve", "action_center", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "action_approved", 1, request_id, "action_center")

    db.commit()
    db.refresh(action)

    return ActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        created_by_user_id=action.created_by_user_id,
        assigned_to_user_id=action.assigned_to_user_id,
        source=action.source,
        source_ref=action.source_ref,
        status=action.status,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        payload=json.loads(action.payload_json),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.post("/actions/{action_id}/reject", response_model=ActionResponse)
def reject_action(
    action_id: str,
    reject_data: ActionApproveReject,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ActionResponse:
    """Reject an action (admin only).

    Idempotent: If already rejected, returns 200 without emitting usage/audit/timeline.
    Returns 409 Conflict if:
    - Action is cancelled (cannot reject cancelled action)
    - Action is already approved (cannot change decision)
    """
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "action_center")
    require_admin(context)

    action = db.query(Action).filter(
        Action.action_id == action_id,
        Action.tenant_id == context.tenant_id
    ).first()

    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    # Idempotent: if already rejected, return without new writes
    if action.status == "rejected":
        return ActionResponse(
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            created_by_user_id=action.created_by_user_id,
            assigned_to_user_id=action.assigned_to_user_id,
            source=action.source,
            source_ref=action.source_ref,
            status=action.status,
            title=action.title,
            description=action.description,
            action_type=action.action_type,
            payload=json.loads(action.payload_json),
            created_at=action.created_at,
            updated_at=action.updated_at,
        )

    # 409 Conflict for cancelled actions
    if action.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot reject a cancelled action"
        )

    # 409 Conflict for approved actions (cannot change decision)
    if action.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot reject an already approved action"
        )

    # Can only reject proposed actions
    if action.status != "proposed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reject action with status '{action.status}'"
        )

    check_billing_quota(db, context.tenant_id, "action_rejected", 1)

    now_iso = get_current_utc_datetime_iso()

    review = ActionReview(
        tenant_id=context.tenant_id,
        action_id=action_id,
        reviewer_user_id=context.user_id,
        decision="rejected",
        comment=reject_data.comment,
        created_at=now_iso,
    )
    db.add(review)

    action.status = "rejected"
    action.updated_at = now_iso

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "action_rejected", "action", action_id,
        f"Action rejected: {action.title}",
        {"action_id": action_id, "decision": "rejected", "comment": reject_data.comment, "reviewer_user_id": context.user_id}
    )

    log_audit(db, context.tenant_id, context.user_id, "actions.reject", "action_center", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "action_rejected", 1, request_id, "action_center")

    db.commit()
    db.refresh(action)

    return ActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        created_by_user_id=action.created_by_user_id,
        assigned_to_user_id=action.assigned_to_user_id,
        source=action.source,
        source_ref=action.source_ref,
        status=action.status,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        payload=json.loads(action.payload_json),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.post("/actions/{action_id}/execute", response_model=ActionResponse)
def execute_action(
    action_id: str,
    execute_data: ActionExecute,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ActionResponse:
    """Execute an approved action (admin only, stub for now)."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "action_center")
    require_admin(context)

    action = db.query(Action).filter(
        Action.action_id == action_id,
        Action.tenant_id == context.tenant_id
    ).first()

    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    if action.status != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only execute approved actions")

    check_billing_quota(db, context.tenant_id, "action_executed", 1)

    now_iso = get_current_utc_datetime_iso()

    # Create execution record (stub - does not actually invoke anything yet)
    execution = ActionExecution(
        tenant_id=context.tenant_id,
        action_id=action_id,
        executed_by_user_id=context.user_id,
        execution_status=execute_data.execution_status,
        result_json=json.dumps(execute_data.result),
        created_at=now_iso,
    )
    db.add(execution)

    action.status = "executed"
    action.updated_at = now_iso

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "action_executed", "action", action_id,
        f"Action executed: {action.title} ({execute_data.execution_status})",
        {"executor": context.user_id, "execution_status": execute_data.execution_status}
    )

    log_audit(db, context.tenant_id, context.user_id, "actions.execute", "action_center", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "action_executed", 1, request_id, "action_center")

    db.commit()
    db.refresh(action)

    return ActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        created_by_user_id=action.created_by_user_id,
        assigned_to_user_id=action.assigned_to_user_id,
        source=action.source,
        source_ref=action.source_ref,
        status=action.status,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        payload=json.loads(action.payload_json),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


# =============================================================================
# Tasks Endpoints
# =============================================================================

@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    task_data: TaskCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Create a new task."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "tasks")
    check_billing_quota(db, context.tenant_id, "task_created", 1)

    now_iso = get_current_utc_datetime_iso()
    task_id = str(uuid.uuid4())

    task = Task(
        task_id=task_id,
        tenant_id=context.tenant_id,
        created_by_user_id=context.user_id,
        assigned_to_user_id=task_data.assigned_to_user_id,
        status="todo",
        priority=task_data.priority,
        due_date=task_data.due_date,
        title=task_data.title,
        description=task_data.description,
        linked_entity_type=task_data.linked_entity_type,
        linked_entity_id=task_data.linked_entity_id,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(task)

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "task_created", "task", task_id,
        f"Task created: {task_data.title}",
        {"priority": task_data.priority, "assigned_to": task_data.assigned_to_user_id}
    )

    log_audit(db, context.tenant_id, context.user_id, "tasks.create", "tasks", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "task_created", 1, request_id, "tasks")

    db.commit()
    db.refresh(task)

    return TaskResponse.model_validate(task)


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    assigned_to_user_id: str | None = None,
    due_before: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TaskListResponse:
    """List tasks for the tenant."""
    check_entitlement(db, context.tenant_id, "tasks")

    query = db.query(Task).filter(Task.tenant_id == context.tenant_id)

    if status_filter:
        query = query.filter(Task.status == status_filter)
    if assigned_to_user_id:
        query = query.filter(Task.assigned_to_user_id == assigned_to_user_id)
    if due_before:
        query = query.filter(Task.due_date <= due_before)

    total = query.count()
    tasks = query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).offset(offset).limit(limit).all()

    return TaskListResponse(
        items=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Get a specific task."""
    check_entitlement(db, context.tenant_id, "tasks")

    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.tenant_id == context.tenant_id
    ).first()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return TaskResponse.model_validate(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    update_data: TaskUpdate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Update a task."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "tasks")

    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.tenant_id == context.tenant_id
    ).first()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # RBAC: creator, assignee, or admin can update
    is_admin = context.user.role == "admin"
    is_creator = task.created_by_user_id == context.user_id
    is_assignee = task.assigned_to_user_id == context.user_id

    if not (is_admin or is_creator or is_assignee):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this task")

    changed = False
    update_dict = update_data.model_dump(exclude_unset=True)

    for field, value in update_dict.items():
        if getattr(task, field) != value:
            setattr(task, field, value)
            changed = True

    if changed:
        check_billing_quota(db, context.tenant_id, "task_updated", 1)
        task.updated_at = get_current_utc_datetime_iso()

        log_timeline_event(
            db, context.tenant_id, context.user_id,
            "task_updated", "task", task_id,
            f"Task updated: {task.title}",
            {"status": task.status, "priority": task.priority}
        )

        log_audit(db, context.tenant_id, context.user_id, "tasks.update", "tasks", request_id)
        emit_usage(db, context.tenant_id, context.user_id, "task_updated", 1, request_id, "tasks")
        db.commit()
        db.refresh(task)

    return TaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/complete", response_model=TaskResponse)
def complete_task(
    task_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Mark a task as complete."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "tasks")

    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.tenant_id == context.tenant_id
    ).first()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # RBAC: assignee or admin can complete
    is_admin = context.user.role == "admin"
    is_assignee = task.assigned_to_user_id == context.user_id

    if not (is_admin or is_assignee):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to complete this task")

    if task.status == "done":
        return TaskResponse.model_validate(task)

    check_billing_quota(db, context.tenant_id, "task_completed", 1)

    task.status = "done"
    task.updated_at = get_current_utc_datetime_iso()

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "task_completed", "task", task_id,
        f"Task completed: {task.title}",
        {"completed_by": context.user_id}
    )

    log_audit(db, context.tenant_id, context.user_id, "tasks.complete", "tasks", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "task_completed", 1, request_id, "tasks")

    db.commit()
    db.refresh(task)

    return TaskResponse.model_validate(task)


# =============================================================================
# Decisions Endpoints
# =============================================================================

@router.post("/decisions", response_model=DecisionResponse, status_code=status.HTTP_201_CREATED)
def create_decision(
    decision_data: DecisionCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> DecisionResponse:
    """Create a new decision (admin only)."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "decisions")
    require_admin(context)
    check_billing_quota(db, context.tenant_id, "decision_created", 1)

    now_iso = get_current_utc_datetime_iso()
    decision_id = str(uuid.uuid4())

    decision = Decision(
        decision_id=decision_id,
        tenant_id=context.tenant_id,
        created_by_user_id=context.user_id,
        decision_date=decision_data.decision_date,
        title=decision_data.title,
        context=decision_data.context,
        decision=decision_data.decision,
        rationale=decision_data.rationale,
        status="active",
        superseded_by_decision_id=None,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(decision)

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "decision_created", "decision", decision_id,
        f"Decision recorded: {decision_data.title}",
        {"decision_date": decision_data.decision_date}
    )

    log_audit(db, context.tenant_id, context.user_id, "decisions.create", "decisions", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "decision_created", 1, request_id, "decisions")

    db.commit()
    db.refresh(decision)

    return DecisionResponse.model_validate(decision)


@router.get("/decisions", response_model=DecisionListResponse)
def list_decisions(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> DecisionListResponse:
    """List decisions for the tenant."""
    check_entitlement(db, context.tenant_id, "decisions")

    query = db.query(Decision).filter(Decision.tenant_id == context.tenant_id)
    total = query.count()
    decisions = query.order_by(Decision.decision_date.desc()).offset(offset).limit(limit).all()

    return DecisionListResponse(
        items=[DecisionResponse.model_validate(d) for d in decisions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/decisions/{decision_id}", response_model=DecisionResponse)
def get_decision(
    decision_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> DecisionResponse:
    """Get a specific decision."""
    check_entitlement(db, context.tenant_id, "decisions")

    decision = db.query(Decision).filter(
        Decision.decision_id == decision_id,
        Decision.tenant_id == context.tenant_id
    ).first()

    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")

    return DecisionResponse.model_validate(decision)


@router.patch("/decisions/{decision_id}", response_model=DecisionResponse)
def update_decision(
    decision_id: str,
    update_data: DecisionUpdate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> DecisionResponse:
    """Update a decision (admin only)."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "decisions")
    require_admin(context)

    decision = db.query(Decision).filter(
        Decision.decision_id == decision_id,
        Decision.tenant_id == context.tenant_id
    ).first()

    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")

    changed = False
    update_dict = update_data.model_dump(exclude_unset=True)

    for field, value in update_dict.items():
        if getattr(decision, field) != value:
            setattr(decision, field, value)
            changed = True

    if changed:
        check_billing_quota(db, context.tenant_id, "decision_updated", 1)
        decision.updated_at = get_current_utc_datetime_iso()

        log_timeline_event(
            db, context.tenant_id, context.user_id,
            "decision_updated", "decision", decision_id,
            f"Decision updated: {decision.title}",
            {}
        )

        log_audit(db, context.tenant_id, context.user_id, "decisions.update", "decisions", request_id)
        emit_usage(db, context.tenant_id, context.user_id, "decision_updated", 1, request_id, "decisions")
        db.commit()
        db.refresh(decision)

    return DecisionResponse.model_validate(decision)


# =============================================================================
# Meeting Notes Endpoints
# =============================================================================

@router.post("/meetings", response_model=MeetingNoteResponse, status_code=status.HTTP_201_CREATED)
def create_meeting_note(
    meeting_data: MeetingNoteCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> MeetingNoteResponse:
    """Create a new meeting note."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "meetings")
    check_billing_quota(db, context.tenant_id, "meeting_note_created", 1)

    now_iso = get_current_utc_datetime_iso()
    meeting_id = str(uuid.uuid4())

    meeting = MeetingNote(
        meeting_id=meeting_id,
        tenant_id=context.tenant_id,
        created_by_user_id=context.user_id,
        meeting_date=meeting_data.meeting_date,
        title=meeting_data.title,
        notes=meeting_data.notes,
        linked_entity_type=meeting_data.linked_entity_type,
        linked_entity_id=meeting_data.linked_entity_id,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(meeting)

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "meeting_note_created", "meeting", meeting_id,
        f"Meeting note created: {meeting_data.title}",
        {"meeting_date": meeting_data.meeting_date}
    )

    log_audit(db, context.tenant_id, context.user_id, "meetings.create", "meetings", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "meeting_note_created", 1, request_id, "meetings")

    db.commit()
    db.refresh(meeting)

    return MeetingNoteResponse.model_validate(meeting)


@router.get("/meetings", response_model=MeetingNoteListResponse)
def list_meeting_notes(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> MeetingNoteListResponse:
    """List meeting notes for the tenant."""
    check_entitlement(db, context.tenant_id, "meetings")

    query = db.query(MeetingNote).filter(MeetingNote.tenant_id == context.tenant_id)

    if from_date:
        query = query.filter(MeetingNote.meeting_date >= from_date)
    if to_date:
        query = query.filter(MeetingNote.meeting_date <= to_date)

    total = query.count()
    meetings = query.order_by(MeetingNote.meeting_date.desc()).offset(offset).limit(limit).all()

    return MeetingNoteListResponse(
        items=[MeetingNoteResponse.model_validate(m) for m in meetings],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/meetings/{meeting_id}", response_model=MeetingNoteResponse)
def get_meeting_note(
    meeting_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> MeetingNoteResponse:
    """Get a specific meeting note."""
    check_entitlement(db, context.tenant_id, "meetings")

    meeting = db.query(MeetingNote).filter(
        MeetingNote.meeting_id == meeting_id,
        MeetingNote.tenant_id == context.tenant_id
    ).first()

    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting note not found")

    return MeetingNoteResponse.model_validate(meeting)


@router.patch("/meetings/{meeting_id}", response_model=MeetingNoteResponse)
def update_meeting_note(
    meeting_id: str,
    update_data: MeetingNoteUpdate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> MeetingNoteResponse:
    """Update a meeting note."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "meetings")

    meeting = db.query(MeetingNote).filter(
        MeetingNote.meeting_id == meeting_id,
        MeetingNote.tenant_id == context.tenant_id
    ).first()

    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting note not found")

    # RBAC: creator or admin can update
    is_admin = context.user.role == "admin"
    is_creator = meeting.created_by_user_id == context.user_id

    if not (is_admin or is_creator):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this meeting note")

    changed = False
    update_dict = update_data.model_dump(exclude_unset=True)

    for field, value in update_dict.items():
        if getattr(meeting, field) != value:
            setattr(meeting, field, value)
            changed = True

    if changed:
        check_billing_quota(db, context.tenant_id, "meeting_note_updated", 1)
        meeting.updated_at = get_current_utc_datetime_iso()

        log_timeline_event(
            db, context.tenant_id, context.user_id,
            "meeting_note_updated", "meeting", meeting_id,
            f"Meeting note updated: {meeting.title}",
            {}
        )

        log_audit(db, context.tenant_id, context.user_id, "meetings.update", "meetings", request_id)
        emit_usage(db, context.tenant_id, context.user_id, "meeting_note_updated", 1, request_id, "meetings")
        db.commit()
        db.refresh(meeting)

    return MeetingNoteResponse.model_validate(meeting)


# =============================================================================
# Memory Facts Endpoints
# =============================================================================

@router.post("/memory/facts", response_model=MemoryFactResponse, status_code=status.HTTP_201_CREATED)
def create_memory_fact(
    fact_data: MemoryFactCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> MemoryFactResponse:
    """Create a new memory fact (admin only)."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "memory")
    require_admin(context)
    check_billing_quota(db, context.tenant_id, "memory_fact_created", 1)

    # Check if there's already an active fact with this key
    existing = db.query(MemoryFact).filter(
        MemoryFact.tenant_id == context.tenant_id,
        MemoryFact.fact_key == fact_data.fact_key,
        MemoryFact.status == "active"
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active fact with key '{fact_data.fact_key}' already exists. Use supersede to update."
        )

    now_iso = get_current_utc_datetime_iso()
    fact_id = str(uuid.uuid4())

    fact = MemoryFact(
        fact_id=fact_id,
        tenant_id=context.tenant_id,
        created_by_user_id=context.user_id,
        category=fact_data.category,
        fact_key=fact_data.fact_key,
        fact_value=fact_data.fact_value,
        status="active",
        supersedes_fact_id=None,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(fact)

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "memory_fact_created", "memory_fact", fact_id,
        f"Memory fact created: {fact_data.fact_key}",
        {"category": fact_data.category}
    )

    log_audit(db, context.tenant_id, context.user_id, "memory.create", "memory", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "memory_fact_created", 1, request_id, "memory")

    db.commit()
    db.refresh(fact)

    return MemoryFactResponse.model_validate(fact)


@router.get("/memory/facts", response_model=MemoryFactListResponse)
def list_memory_facts(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    category: str | None = None,
    status_filter: str | None = Query("active", alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> MemoryFactListResponse:
    """List memory facts for the tenant."""
    check_entitlement(db, context.tenant_id, "memory")

    query = db.query(MemoryFact).filter(MemoryFact.tenant_id == context.tenant_id)

    if category:
        query = query.filter(MemoryFact.category == category)
    if status_filter:
        query = query.filter(MemoryFact.status == status_filter)

    total = query.count()
    facts = query.order_by(MemoryFact.category, MemoryFact.fact_key).offset(offset).limit(limit).all()

    return MemoryFactListResponse(
        items=[MemoryFactResponse.model_validate(f) for f in facts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/memory/facts/{fact_id}", response_model=MemoryFactResponse)
def get_memory_fact(
    fact_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> MemoryFactResponse:
    """Get a specific memory fact."""
    check_entitlement(db, context.tenant_id, "memory")

    fact = db.query(MemoryFact).filter(
        MemoryFact.fact_id == fact_id,
        MemoryFact.tenant_id == context.tenant_id
    ).first()

    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory fact not found")

    return MemoryFactResponse.model_validate(fact)


@router.patch("/memory/facts/{fact_id}", response_model=MemoryFactResponse)
def update_memory_fact(
    fact_id: str,
    update_data: MemoryFactUpdate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> MemoryFactResponse:
    """Update a memory fact (admin only)."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "memory")
    require_admin(context)

    fact = db.query(MemoryFact).filter(
        MemoryFact.fact_id == fact_id,
        MemoryFact.tenant_id == context.tenant_id
    ).first()

    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory fact not found")

    changed = False
    if update_data.fact_value is not None and update_data.fact_value != fact.fact_value:
        fact.fact_value = update_data.fact_value
        changed = True

    if changed:
        check_billing_quota(db, context.tenant_id, "memory_fact_updated", 1)
        fact.updated_at = get_current_utc_datetime_iso()

        log_timeline_event(
            db, context.tenant_id, context.user_id,
            "memory_fact_updated", "memory_fact", fact_id,
            f"Memory fact updated: {fact.fact_key}",
            {}
        )

        log_audit(db, context.tenant_id, context.user_id, "memory.update", "memory", request_id)
        emit_usage(db, context.tenant_id, context.user_id, "memory_fact_updated", 1, request_id, "memory")
        db.commit()
        db.refresh(fact)

    return MemoryFactResponse.model_validate(fact)


@router.post("/memory/facts/{fact_id}/supersede", response_model=MemoryFactResponse)
def supersede_memory_fact(
    fact_id: str,
    supersede_data: MemoryFactSupersede,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> MemoryFactResponse:
    """Supersede a memory fact with a new version (admin only)."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "memory")
    require_admin(context)

    old_fact = db.query(MemoryFact).filter(
        MemoryFact.fact_id == fact_id,
        MemoryFact.tenant_id == context.tenant_id
    ).first()

    if not old_fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory fact not found")

    if old_fact.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only supersede active facts")

    check_billing_quota(db, context.tenant_id, "memory_fact_superseded", 1)

    now_iso = get_current_utc_datetime_iso()
    new_fact_id = str(uuid.uuid4())

    # Mark old fact as superseded
    old_fact.status = "superseded"
    old_fact.updated_at = now_iso

    # Create new fact
    new_fact = MemoryFact(
        fact_id=new_fact_id,
        tenant_id=context.tenant_id,
        created_by_user_id=context.user_id,
        category=old_fact.category,
        fact_key=old_fact.fact_key,
        fact_value=supersede_data.fact_value,
        status="active",
        supersedes_fact_id=fact_id,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(new_fact)

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "memory_fact_superseded", "memory_fact", new_fact_id,
        f"Memory fact superseded: {old_fact.fact_key}",
        {"supersedes_fact_id": fact_id}
    )

    log_audit(db, context.tenant_id, context.user_id, "memory.supersede", "memory", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "memory_fact_superseded", 1, request_id, "memory")

    db.commit()
    db.refresh(new_fact)

    return MemoryFactResponse.model_validate(new_fact)


# =============================================================================
# Evidence Links Endpoints
# =============================================================================

@router.post("/evidence", response_model=EvidenceLinkResponse, status_code=status.HTTP_201_CREATED)
def create_evidence_link(
    evidence_data: EvidenceLinkCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> EvidenceLinkResponse:
    """Create an evidence link."""
    request_id = str(uuid.uuid4())

    # Check entity exists and user has edit rights
    entity_type = evidence_data.entity_type
    entity_id = evidence_data.entity_id

    if entity_type == "action":
        check_entitlement(db, context.tenant_id, "action_center")
        entity = db.query(Action).filter(
            Action.action_id == entity_id,
            Action.tenant_id == context.tenant_id
        ).first()
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
        # Must be creator or admin
        if context.user.role != "admin" and entity.created_by_user_id != context.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to add evidence to this action")

    elif entity_type == "task":
        check_entitlement(db, context.tenant_id, "tasks")
        entity = db.query(Task).filter(
            Task.task_id == entity_id,
            Task.tenant_id == context.tenant_id
        ).first()
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        # Must be creator, assignee, or admin
        is_creator = entity.created_by_user_id == context.user_id
        is_assignee = entity.assigned_to_user_id == context.user_id
        if context.user.role != "admin" and not is_creator and not is_assignee:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to add evidence to this task")

    elif entity_type == "decision":
        check_entitlement(db, context.tenant_id, "decisions")
        require_admin(context)
        entity = db.query(Decision).filter(
            Decision.decision_id == entity_id,
            Decision.tenant_id == context.tenant_id
        ).first()
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")

    elif entity_type == "memory_fact":
        check_entitlement(db, context.tenant_id, "memory")
        require_admin(context)
        entity = db.query(MemoryFact).filter(
            MemoryFact.fact_id == entity_id,
            MemoryFact.tenant_id == context.tenant_id
        ).first()
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory fact not found")

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid entity_type: {entity_type}")

    check_billing_quota(db, context.tenant_id, "evidence_link_created", 1)

    now_iso = get_current_utc_datetime_iso()
    evidence_id = str(uuid.uuid4())

    evidence = EvidenceLink(
        evidence_id=evidence_id,
        tenant_id=context.tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        source_type=evidence_data.source_type,
        source_ref_json=json.dumps(evidence_data.source_ref),
        snippet=evidence_data.snippet,
        created_by_user_id=context.user_id,
        created_at=now_iso,
    )
    db.add(evidence)

    log_timeline_event(
        db, context.tenant_id, context.user_id,
        "evidence_link_created", entity_type, entity_id,
        f"Evidence linked to {entity_type}",
        {"source_type": evidence_data.source_type}
    )

    log_audit(db, context.tenant_id, context.user_id, "evidence.create", "evidence", request_id)
    emit_usage(db, context.tenant_id, context.user_id, "evidence_link_created", 1, request_id, "evidence")

    db.commit()
    db.refresh(evidence)

    return EvidenceLinkResponse(
        evidence_id=evidence.evidence_id,
        tenant_id=evidence.tenant_id,
        entity_type=evidence.entity_type,
        entity_id=evidence.entity_id,
        source_type=evidence.source_type,
        source_ref=json.loads(evidence.source_ref_json),
        snippet=evidence.snippet,
        created_by_user_id=evidence.created_by_user_id,
        created_at=evidence.created_at,
    )


@router.get("/evidence", response_model=EvidenceLinkListResponse)
def list_evidence_links(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    entity_type: str = Query(...),
    entity_id: str = Query(...),
) -> EvidenceLinkListResponse:
    """List evidence links for an entity."""
    # Validate entity exists in tenant
    if entity_type == "action":
        check_entitlement(db, context.tenant_id, "action_center")
    elif entity_type == "task":
        check_entitlement(db, context.tenant_id, "tasks")
    elif entity_type == "decision":
        check_entitlement(db, context.tenant_id, "decisions")
    elif entity_type == "memory_fact":
        check_entitlement(db, context.tenant_id, "memory")

    evidence_list = db.query(EvidenceLink).filter(
        EvidenceLink.tenant_id == context.tenant_id,
        EvidenceLink.entity_type == entity_type,
        EvidenceLink.entity_id == entity_id
    ).order_by(EvidenceLink.created_at.desc()).all()

    items = [
        EvidenceLinkResponse(
            evidence_id=e.evidence_id,
            tenant_id=e.tenant_id,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            source_type=e.source_type,
            source_ref=json.loads(e.source_ref_json),
            snippet=e.snippet,
            created_by_user_id=e.created_by_user_id,
            created_at=e.created_at,
        )
        for e in evidence_list
    ]

    return EvidenceLinkListResponse(items=items, total=len(items))


# =============================================================================
# Timeline Endpoints
# =============================================================================

@router.get("/timeline", response_model=TimelineListResponse)
def list_timeline_events(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TimelineListResponse:
    """List timeline events for the tenant."""
    check_entitlement(db, context.tenant_id, "timeline")

    query = db.query(TimelineEvent).filter(TimelineEvent.tenant_id == context.tenant_id)

    if entity_type:
        query = query.filter(TimelineEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(TimelineEvent.entity_id == entity_id)

    total = query.count()
    events = query.order_by(TimelineEvent.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        TimelineEventResponse(
            event_id=e.event_id,
            tenant_id=e.tenant_id,
            actor_user_id=e.actor_user_id,
            event_type=e.event_type,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            summary=e.summary,
            metadata=json.loads(e.metadata_json),
            created_at=e.created_at,
        )
        for e in events
    ]

    return TimelineListResponse(items=items, total=total, limit=limit, offset=offset)


# =============================================================================
# Global Search Endpoint
# =============================================================================

@router.get("/search", response_model=SearchResponse)
def global_search(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    types: str | None = Query(None, description="Comma-separated entity types to search"),
    limit: int = Query(50, ge=1, le=100),
) -> SearchResponse:
    """Global search across core entities."""
    request_id = str(uuid.uuid4())
    check_entitlement(db, context.tenant_id, "search")
    check_billing_quota(db, context.tenant_id, "search_query", 1)

    search_types = types.split(",") if types else ["actions", "tasks", "decisions", "meetings", "memory"]
    search_pattern = f"%{q}%"
    results: list[SearchResultItem] = []

    if "actions" in search_types:
        actions = db.query(Action).filter(
            Action.tenant_id == context.tenant_id,
            or_(
                Action.title.ilike(search_pattern),
                Action.description.ilike(search_pattern)
            )
        ).limit(limit).all()
        for a in actions:
            snippet = a.description[:100] if a.description else None
            results.append(SearchResultItem(
                entity_type="action",
                entity_id=a.action_id,
                title=a.title,
                snippet=snippet,
                updated_at=a.updated_at,
            ))

    if "tasks" in search_types:
        tasks = db.query(Task).filter(
            Task.tenant_id == context.tenant_id,
            or_(
                Task.title.ilike(search_pattern),
                Task.description.ilike(search_pattern)
            )
        ).limit(limit).all()
        for t in tasks:
            snippet = t.description[:100] if t.description else None
            results.append(SearchResultItem(
                entity_type="task",
                entity_id=t.task_id,
                title=t.title,
                snippet=snippet,
                updated_at=t.updated_at,
            ))

    if "decisions" in search_types:
        decisions = db.query(Decision).filter(
            Decision.tenant_id == context.tenant_id,
            or_(
                Decision.title.ilike(search_pattern),
                Decision.context.ilike(search_pattern),
                Decision.decision.ilike(search_pattern),
                Decision.rationale.ilike(search_pattern)
            )
        ).limit(limit).all()
        for d in decisions:
            snippet = d.context[:100] if d.context else d.decision[:100]
            results.append(SearchResultItem(
                entity_type="decision",
                entity_id=d.decision_id,
                title=d.title,
                snippet=snippet,
                updated_at=d.updated_at,
            ))

    if "meetings" in search_types:
        meetings = db.query(MeetingNote).filter(
            MeetingNote.tenant_id == context.tenant_id,
            or_(
                MeetingNote.title.ilike(search_pattern),
                MeetingNote.notes.ilike(search_pattern)
            )
        ).limit(limit).all()
        for m in meetings:
            snippet = m.notes[:100] if m.notes else None
            results.append(SearchResultItem(
                entity_type="meeting",
                entity_id=m.meeting_id,
                title=m.title,
                snippet=snippet,
                updated_at=m.updated_at,
            ))

    if "memory" in search_types:
        facts = db.query(MemoryFact).filter(
            MemoryFact.tenant_id == context.tenant_id,
            MemoryFact.status == "active",
            or_(
                MemoryFact.fact_key.ilike(search_pattern),
                MemoryFact.fact_value.ilike(search_pattern)
            )
        ).limit(limit).all()
        for f in facts:
            results.append(SearchResultItem(
                entity_type="memory_fact",
                entity_id=f.fact_id,
                title=f.fact_key,
                snippet=f.fact_value[:100],
                updated_at=f.updated_at,
            ))

    # Sort by updated_at descending and limit
    results.sort(key=lambda x: x.updated_at, reverse=True)
    results = results[:limit]

    emit_usage(db, context.tenant_id, context.user_id, "search_query", 1, request_id, "search")
    db.commit()

    return SearchResponse(q=q, results=results, total=len(results))


# =============================================================================
# Record Explorer Endpoint
# =============================================================================

@router.get("/records/{entity_type}/{entity_id}", response_model=RecordExplorerResponse)
def get_record(
    entity_type: str,
    entity_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> RecordExplorerResponse:
    """Get a record with its evidence and timeline."""
    entity_dict: dict[str, Any] = {}

    if entity_type == "action":
        check_entitlement(db, context.tenant_id, "action_center")
        action = db.query(Action).filter(
            Action.action_id == entity_id,
            Action.tenant_id == context.tenant_id
        ).first()
        if not action:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
        entity_dict = {
            "action_id": action.action_id,
            "tenant_id": action.tenant_id,
            "created_by_user_id": action.created_by_user_id,
            "assigned_to_user_id": action.assigned_to_user_id,
            "source": action.source,
            "source_ref": action.source_ref,
            "status": action.status,
            "title": action.title,
            "description": action.description,
            "action_type": action.action_type,
            "payload": json.loads(action.payload_json),
            "created_at": action.created_at,
            "updated_at": action.updated_at,
        }

    elif entity_type == "task":
        check_entitlement(db, context.tenant_id, "tasks")
        task = db.query(Task).filter(
            Task.task_id == entity_id,
            Task.tenant_id == context.tenant_id
        ).first()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        entity_dict = {
            "task_id": task.task_id,
            "tenant_id": task.tenant_id,
            "created_by_user_id": task.created_by_user_id,
            "assigned_to_user_id": task.assigned_to_user_id,
            "status": task.status,
            "priority": task.priority,
            "due_date": task.due_date,
            "title": task.title,
            "description": task.description,
            "linked_entity_type": task.linked_entity_type,
            "linked_entity_id": task.linked_entity_id,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    elif entity_type == "decision":
        check_entitlement(db, context.tenant_id, "decisions")
        decision = db.query(Decision).filter(
            Decision.decision_id == entity_id,
            Decision.tenant_id == context.tenant_id
        ).first()
        if not decision:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
        entity_dict = {
            "decision_id": decision.decision_id,
            "tenant_id": decision.tenant_id,
            "created_by_user_id": decision.created_by_user_id,
            "decision_date": decision.decision_date,
            "title": decision.title,
            "context": decision.context,
            "decision": decision.decision,
            "rationale": decision.rationale,
            "status": decision.status,
            "superseded_by_decision_id": decision.superseded_by_decision_id,
            "created_at": decision.created_at,
            "updated_at": decision.updated_at,
        }

    elif entity_type == "meeting":
        check_entitlement(db, context.tenant_id, "meetings")
        meeting = db.query(MeetingNote).filter(
            MeetingNote.meeting_id == entity_id,
            MeetingNote.tenant_id == context.tenant_id
        ).first()
        if not meeting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting note not found")
        entity_dict = {
            "meeting_id": meeting.meeting_id,
            "tenant_id": meeting.tenant_id,
            "created_by_user_id": meeting.created_by_user_id,
            "meeting_date": meeting.meeting_date,
            "title": meeting.title,
            "notes": meeting.notes,
            "linked_entity_type": meeting.linked_entity_type,
            "linked_entity_id": meeting.linked_entity_id,
            "created_at": meeting.created_at,
            "updated_at": meeting.updated_at,
        }

    elif entity_type == "memory_fact":
        check_entitlement(db, context.tenant_id, "memory")
        fact = db.query(MemoryFact).filter(
            MemoryFact.fact_id == entity_id,
            MemoryFact.tenant_id == context.tenant_id
        ).first()
        if not fact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory fact not found")
        entity_dict = {
            "fact_id": fact.fact_id,
            "tenant_id": fact.tenant_id,
            "created_by_user_id": fact.created_by_user_id,
            "category": fact.category,
            "fact_key": fact.fact_key,
            "fact_value": fact.fact_value,
            "status": fact.status,
            "supersedes_fact_id": fact.supersedes_fact_id,
            "created_at": fact.created_at,
            "updated_at": fact.updated_at,
        }

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid entity_type: {entity_type}")

    # Get evidence links
    evidence_list = db.query(EvidenceLink).filter(
        EvidenceLink.tenant_id == context.tenant_id,
        EvidenceLink.entity_type == entity_type,
        EvidenceLink.entity_id == entity_id
    ).order_by(EvidenceLink.created_at.desc()).all()

    evidence_items = [
        EvidenceLinkResponse(
            evidence_id=e.evidence_id,
            tenant_id=e.tenant_id,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            source_type=e.source_type,
            source_ref=json.loads(e.source_ref_json),
            snippet=e.snippet,
            created_by_user_id=e.created_by_user_id,
            created_at=e.created_at,
        )
        for e in evidence_list
    ]

    # Get timeline events (last 20)
    timeline_list = db.query(TimelineEvent).filter(
        TimelineEvent.tenant_id == context.tenant_id,
        TimelineEvent.entity_type == entity_type,
        TimelineEvent.entity_id == entity_id
    ).order_by(TimelineEvent.created_at.desc()).limit(20).all()

    timeline_items = [
        TimelineEventResponse(
            event_id=e.event_id,
            tenant_id=e.tenant_id,
            actor_user_id=e.actor_user_id,
            event_type=e.event_type,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            summary=e.summary,
            metadata=json.loads(e.metadata_json),
            created_at=e.created_at,
        )
        for e in timeline_list
    ]

    return RecordExplorerResponse(
        entity=entity_dict,
        evidence=evidence_items,
        timeline=timeline_items,
    )
