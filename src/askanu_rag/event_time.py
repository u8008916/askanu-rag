"""Persistence-independent Canberra Event time and ordering semantics."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal, TypeVar
from zoneinfo import ZoneInfo

CANBERRA = ZoneInfo("Australia/Canberra")
EventTimePeriod = Literal["today", "tomorrow", "this Friday", "next week"]
T = TypeVar("T")


@dataclass(frozen=True)
class DateTimeWindow:
    """A Canberra-local, start-inclusive and end-exclusive time window."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = as_canberra(self.start, name="window start")
        end = as_canberra(self.end, name="window end")
        if end <= start:
            raise ValueError("window end must be after its start")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def contains(self, value: datetime) -> bool:
        return self.start <= as_canberra(value, name="event start") < self.end


def resolve_event_time_window(
    period: EventTimePeriod, *, now: datetime
) -> DateTimeWindow | None:
    """Resolve a supported phrase against an explicit Canberra-local now."""

    local_date = as_canberra(now, name="now").date()
    if period == "today":
        start_date, end_date = local_date, local_date + timedelta(days=1)
    elif period == "tomorrow":
        start_date = local_date + timedelta(days=1)
        end_date = local_date + timedelta(days=2)
    elif period == "this Friday":
        friday = 4
        if local_date.weekday() > friday:
            return None
        start_date = local_date + timedelta(days=friday - local_date.weekday())
        end_date = start_date + timedelta(days=1)
    elif period == "next week":
        monday = local_date - timedelta(days=local_date.weekday())
        start_date, end_date = monday + timedelta(days=7), monday + timedelta(days=14)
    else:
        raise ValueError(f"Unsupported event time period: {period!r}")
    return DateTimeWindow(_start_of_day(start_date), _start_of_day(end_date))


def events_starting_in_window(
    events: Iterable[T],
    *,
    window: DateTimeWindow,
    start_at: Callable[[T], datetime],
    stable_key: Callable[[T], str],
) -> tuple[T, ...]:
    return _sorted_events(
        events,
        start_at=start_at,
        stable_key=stable_key,
        include=lambda start: window.start <= start < window.end,
    )


def upcoming_events(
    events: Iterable[T],
    *,
    now: datetime,
    start_at: Callable[[T], datetime],
    stable_key: Callable[[T], str],
    limit: int = 5,
) -> tuple[T, ...]:
    """Exclude past starts, sort by start/key, then apply a positive limit."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    local_now = as_canberra(now, name="now")
    return _sorted_events(
        events,
        start_at=start_at,
        stable_key=stable_key,
        include=lambda start: start >= local_now,
    )[:limit]


def as_canberra(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(CANBERRA)


def _sorted_events(
    events: Iterable[T],
    *,
    start_at: Callable[[T], datetime],
    stable_key: Callable[[T], str],
    include: Callable[[datetime], bool],
) -> tuple[T, ...]:
    ranked: list[tuple[datetime, str, T]] = []
    for event in events:
        start = as_canberra(start_at(event), name="event start")
        key = stable_key(event)
        if not isinstance(key, str) or not key.strip():
            raise ValueError("stable event key must be a non-blank string")
        if include(start):
            ranked.append((start, key, event))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in ranked)


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=CANBERRA)
