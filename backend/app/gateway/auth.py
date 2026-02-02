"""Shared authentication and tenant context for the Gateway API.

This module provides centralized authentication logic for all routers,
avoiding duplication of TenantContext classes and authentication code.
"""
import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.gateway.models import GatewayTenant, GatewayUser


@dataclass
class TenantContext:
    """Tenant context populated from request headers.

    Attributes:
        tenant_id: The authenticated tenant's ID.
        user_id: The authenticated user's ID.
        tenant: The GatewayTenant database record.
        user: The GatewayUser database record.
    """
    tenant_id: str
    user_id: str
    tenant: GatewayTenant
    user: GatewayUser

    @property
    def is_admin(self) -> bool:
        """Check if the current user has admin role."""
        return self.user.role == "admin"


def _validate_and_authenticate(
    db: Session,
    x_tenant_id: str | None,
    x_user_id: str | None,
    x_api_key: str | None,
) -> TenantContext:
    """Common validation and authentication logic for tenant context.

    Args:
        db: Database session.
        x_tenant_id: Tenant ID from header.
        x_user_id: User ID from header.
        x_api_key: API key from header.

    Returns:
        TenantContext with authenticated tenant and user.

    Raises:
        HTTPException: On missing headers, auth failure, or authorization failure.
    """
    # Validate required headers are present
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: X-Tenant-ID",
        )
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: X-User-ID",
        )
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: X-API-Key",
        )

    # Authenticate: verify tenant exists and API key matches
    tenant = db.query(GatewayTenant).filter(
        GatewayTenant.tenant_id == x_tenant_id
    ).first()

    # Use constant-time comparison to prevent timing attacks
    if not tenant or not secrets.compare_digest(tenant.api_key, x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant ID or API key",
        )

    # Verify user exists and belongs to this tenant
    user = db.query(GatewayUser).filter(
        GatewayUser.user_id == x_user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found",
        )

    if user.tenant_id != x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this tenant",
        )

    return TenantContext(
        tenant_id=x_tenant_id,
        user_id=x_user_id,
        tenant=tenant,
        user=user,
    )


def get_tenant_context(
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> TenantContext:
    """FastAPI dependency to get authenticated tenant context.

    This dependency validates request headers and returns a TenantContext
    containing the authenticated tenant and user information.

    Args:
        x_tenant_id: Tenant ID from X-Tenant-ID header.
        x_user_id: User ID from X-User-ID header.
        x_api_key: API key from X-API-Key header.
        db: Database session from dependency injection.

    Returns:
        TenantContext with authenticated tenant and user.

    Raises:
        HTTPException: On missing headers, auth failure, or authorization failure.
    """
    return _validate_and_authenticate(db, x_tenant_id, x_user_id, x_api_key)


def require_admin(context: TenantContext) -> None:
    """Require admin role, raise 403 if not admin.

    Args:
        context: The authenticated tenant context.

    Raises:
        HTTPException: If the user is not an admin.
    """
    if not context.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user.role}' is not authorized for this action"
        )
