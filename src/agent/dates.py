"""Resolve natural-language date phrases to inclusive (start, end) ranges.

The resolver is intentionally small and predictable: it handles the
shorthand that comes up in chat ("last month", "this week", "june 2025",
"last 30 days", "ytd", ISO dates and ranges). Anything it can't parse
raises `ValueError` — callers should fall back to explicit ISO dates.

Conventions:
- Weeks run Monday..Sunday.
- "Last N <unit>" is N units ending today, inclusive of today.
- A bare month name picks the most recent past (or current) occurrence.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _week_bounds(d: date) -> tuple[date, date]:
    """Monday..Sunday containing d."""
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def _subtract_months(d: date, n: int) -> date:
    """Shift d back by n months, clamping the day to the target month length."""
    total = d.year * 12 + (d.month - 1) - n
    year, extra = divmod(total, 12)
    month = extra + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last))


def resolve_range(phrase: str, *, today: date | None = None) -> tuple[date, date]:
    """Resolve a natural-language date phrase to an inclusive (start, end) tuple.

    Supports: today, yesterday, tomorrow; this/last week/month/year;
    ytd/mtd/wtd; bare month names ("january", "jan") with or without a
    year; "last N days/weeks/months/years"; bare 4-digit years; single
    ISO dates; ISO ranges joined by "to", "..", or " - ".

    Args:
        phrase: Natural-language description of a date range.
        today: Reference date (defaults to date.today()). Inject in tests.

    Returns:
        (start_date, end_date), both inclusive.

    Raises:
        ValueError: If the phrase can't be parsed.
    """
    if today is None:
        today = date.today()
    text = phrase.strip().lower()
    if not text:
        raise ValueError("empty date phrase")

    if text == "today":
        return today, today
    if text == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if text == "tomorrow":
        d = today + timedelta(days=1)
        return d, d

    if text == "this week":
        return _week_bounds(today)
    if text == "last week":
        return _week_bounds(today - timedelta(days=7))
    if text == "this month":
        return _month_bounds(today.year, today.month)
    if text == "last month":
        prev = today.replace(day=1) - timedelta(days=1)
        return _month_bounds(prev.year, prev.month)
    if text == "this year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if text == "last year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)

    if text in ("ytd", "year to date", "year-to-date"):
        return date(today.year, 1, 1), today
    if text in ("mtd", "month to date", "month-to-date"):
        return today.replace(day=1), today
    if text in ("wtd", "week to date", "week-to-date"):
        start, _ = _week_bounds(today)
        return start, today

    m = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})\s*(?:to|\.\.|-)\s*(\d{4}-\d{2}-\d{2})", text
    )
    if m:
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        d = date.fromisoformat(text)
        return d, d

    m = re.fullmatch(r"(?:in\s+)?(\d{4})", text)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1), date(y, 12, 31)

    m = re.fullmatch(
        r"(?:last|past)\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)",
        text,
    )
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        end = today
        if unit in ("day", "days"):
            start = today - timedelta(days=n - 1)
        elif unit in ("week", "weeks"):
            start = today - timedelta(days=7 * n - 1)
        elif unit in ("month", "months"):
            start = _subtract_months(today, n) + timedelta(days=1)
        else:
            start = today.replace(year=today.year - n) + timedelta(days=1)
        return start, end

    m = re.fullmatch(r"(?:in\s+)?([a-z]+)(?:\s+(\d{4}))?", text)
    if m and m.group(1) in _MONTHS:
        month = _MONTHS[m.group(1)]
        if m.group(2):
            year = int(m.group(2))
        else:
            year = today.year if month <= today.month else today.year - 1
        return _month_bounds(year, month)

    raise ValueError(f"could not parse date phrase: {phrase!r}")
