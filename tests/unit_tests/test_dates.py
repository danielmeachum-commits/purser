"""Unit tests for agent.dates.resolve_range."""

from datetime import date

import pytest

from agent.dates import resolve_range

# Reference date: Tuesday, 2026-06-16. The Monday of that week is 2026-06-15.
TODAY = date(2026, 6, 16)


def r(phrase: str) -> tuple[date, date]:
    return resolve_range(phrase, today=TODAY)


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("today", (date(2026, 6, 16), date(2026, 6, 16))),
        ("yesterday", (date(2026, 6, 15), date(2026, 6, 15))),
        ("tomorrow", (date(2026, 6, 17), date(2026, 6, 17))),
    ],
)
def test_single_day_shortcuts(phrase, expected):
    assert r(phrase) == expected


def test_this_week_runs_monday_to_sunday():
    assert r("this week") == (date(2026, 6, 15), date(2026, 6, 21))


def test_last_week_is_the_prior_full_monday_to_sunday():
    assert r("last week") == (date(2026, 6, 8), date(2026, 6, 14))


def test_this_month():
    assert r("this month") == (date(2026, 6, 1), date(2026, 6, 30))


def test_last_month():
    assert r("last month") == (date(2026, 5, 1), date(2026, 5, 31))


def test_last_month_crosses_year_boundary():
    # January -> December of previous year.
    jan = date(2026, 1, 14)
    assert resolve_range("last month", today=jan) == (date(2025, 12, 1), date(2025, 12, 31))


def test_this_year_and_last_year():
    assert r("this year") == (date(2026, 1, 1), date(2026, 12, 31))
    assert r("last year") == (date(2025, 1, 1), date(2025, 12, 31))


@pytest.mark.parametrize(
    "phrase,expected_start,expected_end",
    [
        ("ytd", date(2026, 1, 1), date(2026, 6, 16)),
        ("year to date", date(2026, 1, 1), date(2026, 6, 16)),
        ("mtd", date(2026, 6, 1), date(2026, 6, 16)),
        ("month-to-date", date(2026, 6, 1), date(2026, 6, 16)),
        ("wtd", date(2026, 6, 15), date(2026, 6, 16)),
    ],
)
def test_to_date_phrases(phrase, expected_start, expected_end):
    assert r(phrase) == (expected_start, expected_end)


def test_bare_month_in_past_uses_current_year():
    # "january" with TODAY in June -> January of the same year.
    assert r("january") == (date(2026, 1, 1), date(2026, 1, 31))
    assert r("jan") == (date(2026, 1, 1), date(2026, 1, 31))


def test_bare_month_in_future_falls_back_to_prior_year():
    # "july" with TODAY in June -> July of the prior year.
    assert r("july") == (date(2025, 7, 1), date(2025, 7, 31))


def test_current_month_resolves_to_current_year():
    assert r("june") == (date(2026, 6, 1), date(2026, 6, 30))


def test_month_with_explicit_year():
    assert r("june 2025") == (date(2025, 6, 1), date(2025, 6, 30))
    assert r("jan 2024") == (date(2024, 1, 1), date(2024, 1, 31))


def test_in_month_prefix():
    assert r("in january") == (date(2026, 1, 1), date(2026, 1, 31))
    assert r("in june 2025") == (date(2025, 6, 1), date(2025, 6, 30))


@pytest.mark.parametrize(
    "phrase,expected_start,expected_end",
    [
        ("last 1 day", date(2026, 6, 16), date(2026, 6, 16)),
        ("last 7 days", date(2026, 6, 10), date(2026, 6, 16)),
        ("last 30 days", date(2026, 5, 18), date(2026, 6, 16)),
        ("last 1 week", date(2026, 6, 10), date(2026, 6, 16)),
        ("last 2 weeks", date(2026, 6, 3), date(2026, 6, 16)),
    ],
)
def test_last_n_days_and_weeks(phrase, expected_start, expected_end):
    assert r(phrase) == (expected_start, expected_end)


def test_last_n_months():
    # _subtract_months(2026-06-16, 3) = 2026-03-16; +1 day -> 2026-03-17.
    assert r("last 3 months") == (date(2026, 3, 17), date(2026, 6, 16))


def test_last_n_years():
    assert r("last 1 year") == (date(2025, 6, 17), date(2026, 6, 16))
    assert r("last 2 years") == (date(2024, 6, 17), date(2026, 6, 16))


def test_past_is_alias_for_last():
    assert r("past 5 days") == r("last 5 days")


@pytest.mark.parametrize(
    "phrase",
    ["2025", "in 2025", "in 2024"],
)
def test_year_only(phrase):
    year = int(phrase.split()[-1])
    assert r(phrase) == (date(year, 1, 1), date(year, 12, 31))


def test_iso_single_date():
    assert r("2026-06-16") == (date(2026, 6, 16), date(2026, 6, 16))


@pytest.mark.parametrize(
    "phrase",
    [
        "2026-06-01 to 2026-06-30",
        "2026-06-01..2026-06-30",
        "2026-06-01 - 2026-06-30",
    ],
)
def test_iso_range(phrase):
    assert r(phrase) == (date(2026, 6, 1), date(2026, 6, 30))


def test_case_and_whitespace_insensitive():
    assert r("  LAST month ") == r("last month")
    assert r("YTD") == r("ytd")


@pytest.mark.parametrize(
    "phrase",
    ["", "   ", "blarg", "next month", "two weeks ago", "last fortnight"],
)
def test_unparseable_phrases_raise(phrase):
    with pytest.raises(ValueError):
        r(phrase)


def test_default_today_used_when_not_injected():
    # Just verify the call works without `today=`; correctness is covered by other tests.
    start, end = resolve_range("today")
    assert start == end == date.today()
