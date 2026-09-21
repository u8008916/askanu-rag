"""Canberra Event time semantics ported from the isolated WIP."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from askanu_rag.event_time import (
    CANBERRA,
    events_starting_in_window,
    resolve_event_time_window,
    upcoming_events,
)


@dataclass(frozen=True)
class SuppliedEvent:
    key: str
    starts: datetime


def local(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=CANBERRA)


def upcoming(events, now, limit=5):
    return upcoming_events(
        events,
        now=now,
        start_at=lambda event: event.starts,
        stable_key=lambda event: event.key,
        limit=limit,
    )


@pytest.mark.parametrize(
    ("period", "expected_start", "expected_end"),
    [
        ("today", local(2026, 9, 16), local(2026, 9, 17)),
        ("tomorrow", local(2026, 9, 17), local(2026, 9, 18)),
        ("this Friday", local(2026, 9, 18), local(2026, 9, 19)),
        ("next week", local(2026, 9, 21), local(2026, 9, 28)),
    ],
)
def test_canberra_windows(period, expected_start, expected_end):
    window = resolve_event_time_window(period, now=local(2026, 9, 16, 9))
    assert window is not None
    assert (window.start, window.end) == (expected_start, expected_end)


def test_this_friday_after_friday_does_not_become_next_friday():
    assert resolve_event_time_window(
        "this Friday", now=local(2026, 9, 19, 9)
    ) is None


def test_window_is_start_inclusive_and_end_exclusive():
    window = resolve_event_time_window("today", now=local(2026, 9, 16, 9))
    assert window is not None
    at_start = SuppliedEvent("start", window.start)
    at_end = SuppliedEvent("end", window.end)
    assert events_starting_in_window(
        [at_end, at_start],
        window=window,
        start_at=lambda event: event.starts,
        stable_key=lambda event: event.key,
    ) == (at_start,)


def test_upcoming_excludes_past_includes_now_and_sorts_ties_by_stable_key():
    now = local(2026, 9, 16, 9)
    past = SuppliedEvent("past", now - timedelta(seconds=1))
    second = SuppliedEvent("b", now)
    first = SuppliedEvent("a", now)
    assert upcoming([second, past, first], now) == (first, second)


def test_upcoming_uses_known_end_to_keep_an_ongoing_event_current():
    now = local(2026, 9, 16, 9)
    ongoing = SuppliedEvent("ongoing", now - timedelta(hours=1))
    ended = SuppliedEvent("ended", now - timedelta(hours=2))
    ends = {
        "ongoing": now + timedelta(hours=1),
        "ended": now - timedelta(hours=1),
    }
    assert upcoming_events(
        [ended, ongoing],
        now=now,
        start_at=lambda event: event.starts,
        end_at=lambda event: ends[event.key],
        stable_key=lambda event: event.key,
    ) == (ongoing,)


def test_limit_is_applied_after_filtering_and_ordering():
    now = local(2026, 9, 16, 9)
    events = [
        SuppliedEvent("past", now - timedelta(hours=1)),
        SuppliedEvent("third", now + timedelta(hours=3)),
        SuppliedEvent("first", now + timedelta(hours=1)),
        SuppliedEvent("second", now + timedelta(hours=2)),
    ]
    assert [item.key for item in upcoming(events, now, 2)] == ["first", "second"]


def test_dst_offsets_are_not_fixed_and_recompute_across_boundary():
    standard = resolve_event_time_window("today", now=local(2026, 7, 15, 12))
    daylight = resolve_event_time_window("today", now=local(2026, 1, 15, 12))
    crossing = resolve_event_time_window("next week", now=local(2026, 9, 30, 12))
    assert standard is not None and daylight is not None and crossing is not None
    assert standard.start.utcoffset() == timedelta(hours=10)
    assert daylight.start.utcoffset() == timedelta(hours=11)
    assert crossing.start.utcoffset() == timedelta(hours=11)


def test_aware_utc_inputs_are_compared_in_canberra_time():
    now = local(2026, 9, 16, 9)
    event = SuppliedEvent("utc", now.astimezone(timezone.utc))
    assert upcoming([event], now) == (event,)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_upcoming_limit_must_be_a_positive_integer(limit):
    with pytest.raises(ValueError, match="positive integer"):
        upcoming([], local(2026, 9, 16, 9), limit=limit)


def test_naive_now_and_event_start_are_rejected():
    aware = local(2026, 9, 16, 9)
    naive = datetime(2026, 9, 16, 9)
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        upcoming([], naive)
    with pytest.raises(ValueError, match="event start must be timezone-aware"):
        upcoming([SuppliedEvent("naive", naive)], aware)
