"""Resolve fixed or solar daily boundaries using HA's location and time zone."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

SCHEDULE_MODES = {
    "Fixed time": "fixed",
    "Dawn": "dawn",
    "Sunrise": "sunrise",
    "Sunset": "sunset",
    "Dusk": "dusk",
}
SCHEDULE_SETTINGS = {
    "day_start_mode": "Daytime begins at",
    "night_start_mode": "Nighttime privacy begins at",
}


@dataclass(frozen=True)
class Schedule:
    is_day: bool | None
    day_start: datetime | None
    night_start: datetime | None


def resolve_schedule(hass, config, now):
    local_now = dt_util.as_local(now)
    today = local_now.date()

    def boundary(key, date):
        mode = config.get(f"{key}_mode", "fixed")
        if mode == "fixed":
            return dt_util.as_utc(
                datetime.combine(date, time.fromisoformat(config[key]), local_now.tzinfo)
            )
        return get_astral_event_date(hass, mode, date)

    start, end = boundary("day_start", today), boundary("night_start", today)
    # At polar locations an event may not occur. Do not silently substitute a
    # different time; hold normal automation until the schedule is resolvable.
    if start is None or end is None or start == end:
        return Schedule(None, start, end)
    transitions = [(start, True), (end, False)]
    yesterday = today - timedelta(days=1)
    for key, is_day in (("day_start", True), ("night_start", False)):
        event = boundary(key, yesterday)
        if event is not None:
            transitions.append((event, is_day))
    passed = [(event, state) for event, state in transitions if event <= now]
    active = max(passed, key=lambda item: item[0])[1] if passed else None
    return Schedule(active, start, end)
