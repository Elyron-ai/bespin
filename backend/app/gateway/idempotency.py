"""Idempotency handling for the Tool Invocation Gateway."""
import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.gateway.models import IdempotencyKey


class IdempotencyConflictError(Exception):
    """Raised when the same idempotency key is used with a different request body."""
    pass


def compute_request_hash(request_body: dict[str, Any]) -> str:
    """Compute a SHA-256 hash of the request body.

    Args:
        request_body: The request body dictionary.

    Returns:
        A hex string of the SHA-256 hash.
    """
    canonical_json = json.dumps(request_body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def check_idempotency(
    db: Session,
    tenant_id: str,
    endpoint: str,
    idempotency_key: str,
    request_body: dict[str, Any],
) -> dict[str, Any] | None:
    """Check if a request with this idempotency key already exists.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        endpoint: The endpoint path.
        idempotency_key: The idempotency key from the request header.
        request_body: The request body for hash comparison.

    Returns:
        The stored response if found and hashes match, None if not found.

    Raises:
        IdempotencyConflictError: If the key exists but the request hash differs.
    """
    existing = db.query(IdempotencyKey).filter(
        IdempotencyKey.tenant_id == tenant_id,
        IdempotencyKey.endpoint == endpoint,
        IdempotencyKey.idempotency_key == idempotency_key,
    ).first()

    if existing is None:
        return None

    current_hash = compute_request_hash(request_body)
    if existing.request_hash != current_hash:
        raise IdempotencyConflictError(
            f"Idempotency key '{idempotency_key}' was already used with a different request body"
        )

    return json.loads(existing.response_json)


def store_idempotency(
    db: Session,
    tenant_id: str,
    endpoint: str,
    idempotency_key: str,
    request_body: dict[str, Any],
    response: dict[str, Any],
) -> None:
    """Store an idempotency record.

    Args:
        db: Database session.
        tenant_id: The tenant ID.
        endpoint: The endpoint path.
        idempotency_key: The idempotency key from the request header.
        request_body: The request body for hash computation.
        response: The response to store.

    Note:
        This function does NOT commit the transaction. The caller is responsible
        for committing to ensure the idempotency record is stored atomically
        with the main operation.
    """
    record = IdempotencyKey(
        tenant_id=tenant_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_hash=compute_request_hash(request_body),
        response_json=json.dumps(response),
    )
    db.add(record)
    db.flush()  # Flush to detect constraint violations early, but don't commit
