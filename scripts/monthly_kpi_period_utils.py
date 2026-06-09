#!/usr/bin/env python3
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def month_end(month_start: date) -> date:
    return date(month_start.year, month_start.month, calendar.monthrange(month_start.year, month_start.month)[1])


def month_bounds(month_start_value: date | None = None) -> tuple[date, date]:
    if month_start_value is None:
        today = datetime.now(MOSCOW_TZ).date()
        month_start_value = today.replace(day=1)
    if month_start_value.day != 1:
        raise ValueError("month_start must be the first day of the month")
    return month_start_value, month_end(month_start_value)


def start_end_datetimes(period_start: date, period_end: date, tz: ZoneInfo = MOSCOW_TZ) -> tuple[datetime, datetime]:
    return (
        datetime.combine(period_start, time.min, tzinfo=tz),
        datetime.combine(period_end, time(23, 59, 59), tzinfo=tz),
    )


def sales_show_lookup_bounds(period_start: date, period_end: date, forward_days: int) -> tuple[datetime, datetime]:
    return (
        datetime.combine(period_start, time.min, tzinfo=MOSCOW_TZ),
        datetime.combine(period_end + timedelta(days=forward_days), time(23, 59, 59), tzinfo=MOSCOW_TZ),
    )
