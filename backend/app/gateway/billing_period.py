"""Billing period utilities for monthly billing cycles."""
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta


def get_current_utc_date() -> str:
    """Get current UTC date as YYYY-MM-DD string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_current_utc_datetime_iso() -> str:
    """Get current UTC datetime as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def get_period_start(date_utc: str | None = None) -> str:
    """Get the billing period start date (first day of month).

    Args:
        date_utc: A date string in YYYY-MM-DD format, or None for current date.

    Returns:
        The first day of the month as YYYY-MM-01.
    """
    if date_utc is None:
        dt = datetime.now(timezone.utc)
    else:
        dt = datetime.strptime(date_utc, "%Y-%m-%d")

    return dt.strftime("%Y-%m-01")


def get_period_end(period_start: str) -> str:
    """Get the billing period end date (first day of next month).

    Args:
        period_start: The period start date as YYYY-MM-01.

    Returns:
        The first day of the next month as YYYY-MM-01.
    """
    dt = datetime.strptime(period_start, "%Y-%m-%d")
    next_month = dt + relativedelta(months=1)
    return next_month.strftime("%Y-%m-01")


def is_date_in_period(date_utc: str, period_start: str, period_end: str) -> bool:
    """Check if a date falls within a billing period.

    Args:
        date_utc: The date to check as YYYY-MM-DD.
        period_start: Period start as YYYY-MM-01.
        period_end: Period end as YYYY-MM-01.

    Returns:
        True if date is in [period_start, period_end).
    """
    return period_start <= date_utc < period_end
