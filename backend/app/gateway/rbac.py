"""Role-Based Access Control for the Tool Invocation Gateway."""
from enum import Enum


class Role(str, Enum):
    """Available user roles."""
    ADMIN = "admin"
    MEMBER = "member"


class Permission(str, Enum):
    """Available permissions."""
    INVOKE_TOOLS = "invoke_tools"
    KPI_WRITE = "kpi_write"  # Create KPI definitions, ingest points
    KPI_READ = "kpi_read"    # Read KPI definitions and points
    BRIEF_MATERIALIZE = "brief_materialize"  # Materialize daily briefs
    BRIEF_READ = "brief_read"  # Read daily briefs
    RUN_JOBS = "run_jobs"  # Run background jobs (e.g., daily brief runner)


# Role to permissions mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        Permission.INVOKE_TOOLS,
        Permission.KPI_WRITE,
        Permission.KPI_READ,
        Permission.BRIEF_MATERIALIZE,
        Permission.BRIEF_READ,
        Permission.RUN_JOBS,
    },
    Role.MEMBER: {Permission.KPI_READ, Permission.BRIEF_READ},  # Members can read KPIs and briefs
}


def has_permission(role: str, permission: Permission) -> bool:
    """Check if a role has a specific permission.

    Args:
        role: The user's role as a string.
        permission: The permission to check.

    Returns:
        True if the role has the permission, False otherwise.
    """
    try:
        role_enum = Role(role)
        return permission in ROLE_PERMISSIONS.get(role_enum, set())
    except ValueError:
        return False


def can_invoke_tools(role: str) -> bool:
    """Check if a role can invoke tools.

    Args:
        role: The user's role as a string.

    Returns:
        True if the role can invoke tools, False otherwise.
    """
    return has_permission(role, Permission.INVOKE_TOOLS)


def can_write_kpis(role: str) -> bool:
    """Check if a role can create KPI definitions and ingest points.

    Args:
        role: The user's role as a string.

    Returns:
        True if the role can write KPIs, False otherwise.
    """
    return has_permission(role, Permission.KPI_WRITE)


def can_read_kpis(role: str) -> bool:
    """Check if a role can read KPI definitions and points.

    Args:
        role: The user's role as a string.

    Returns:
        True if the role can read KPIs, False otherwise.
    """
    return has_permission(role, Permission.KPI_READ)


def can_materialize_briefs(role: str) -> bool:
    """Check if a role can materialize daily briefs.

    Args:
        role: The user's role as a string.

    Returns:
        True if the role can materialize briefs, False otherwise.
    """
    return has_permission(role, Permission.BRIEF_MATERIALIZE)


def can_read_briefs(role: str) -> bool:
    """Check if a role can read daily briefs.

    Args:
        role: The user's role as a string.

    Returns:
        True if the role can read briefs, False otherwise.
    """
    return has_permission(role, Permission.BRIEF_READ)


def can_run_jobs(role: str) -> bool:
    """Check if a role can run background jobs.

    Args:
        role: The user's role as a string.

    Returns:
        True if the role can run jobs, False otherwise.
    """
    return has_permission(role, Permission.RUN_JOBS)
