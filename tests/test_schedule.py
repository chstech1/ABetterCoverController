"""Solar boundaries use today's date, actual local time, and exact transitions."""

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.better_cover.const import DEFAULTS
from custom_components.better_cover.logic import decide, validate
from custom_components.better_cover.schedule import resolve_schedule


@pytest.fixture
def events(monkeypatch):
    zone = ZoneInfo("America/New_York")
    monkeypatch.setattr(dt_util, "DEFAULT_TIME_ZONE", zone)
    calls = []

    def event(hass, mode, date):
        calls.append((mode, date))
        hour = {"dawn": 5, "sunrise": 6, "sunset": 18, "dusk": 19}[mode]
        return datetime.combine(date, time(hour), zone).astimezone(UTC)

    monkeypatch.setattr("custom_components.better_cover.schedule.get_astral_event_date", event)
    return zone, calls


@pytest.mark.parametrize(
    "start,end", [("dawn", "dusk"), ("sunrise", "sunset"), ("sunset", "sunrise"), ("dusk", "dawn")]
)
def test_solar_transitions(events, start, end):
    zone, _ = events
    cfg = {**DEFAULTS, "day_start_mode": start, "night_start_mode": end}
    noon = datetime(2026, 9, 9, 12, tzinfo=zone)
    resolved = resolve_schedule(None, cfg, noon)
    assert resolved.is_day == (start in ("dawn", "sunrise"))
    assert resolve_schedule(None, cfg, resolved.day_start).is_day is True
    assert resolve_schedule(None, cfg, resolved.night_start).is_day is False
    assert resolve_schedule(None, cfg, resolved.day_start - timedelta(seconds=1)).is_day is False
    assert resolve_schedule(None, cfg, resolved.night_start - timedelta(seconds=1)).is_day is True


def test_local_date_and_midnight(events):
    zone, calls = events
    cfg = {**DEFAULTS, "day_start_mode": "sunrise", "night_start_mode": "dusk"}
    # 01:00 UTC is still the previous local evening, after that day's dusk.
    now = datetime(2026, 9, 10, 1, tzinfo=UTC)
    result = resolve_schedule(None, cfg, now)
    assert result.day_start.astimezone(zone).date().isoformat() == "2026-09-09"
    assert not result.is_day
    assert all(date.isoformat() in ("2026-09-08", "2026-09-09") for _, date in calls)


def test_mixed_and_fixed_times_retained(events):
    zone, _ = events
    cfg = {**DEFAULTS, "day_start_mode": "dawn", "night_start": "22:00:00"}
    assert resolve_schedule(None, cfg, datetime(2026, 9, 9, 6, tzinfo=zone)).is_day
    assert resolve_schedule(None, cfg, datetime(2026, 9, 9, 21, tzinfo=zone)).is_day
    assert not resolve_schedule(None, cfg, datetime(2026, 9, 9, 22, tzinfo=zone)).is_day
    cfg["day_start_mode"] = "fixed"
    assert not resolve_schedule(None, cfg, datetime(2026, 9, 9, 6, tzinfo=zone)).is_day


def test_dst_uses_each_dates_offset(events):
    zone, _ = events
    cfg = {**DEFAULTS, "day_start_mode": "sunrise", "night_start_mode": "sunset"}
    before = resolve_schedule(None, cfg, datetime(2026, 3, 7, 12, tzinfo=zone))
    after = resolve_schedule(None, cfg, datetime(2026, 3, 8, 12, tzinfo=zone))
    assert before.day_start.hour == 11
    assert after.day_start.hour == 10
    assert before.is_day and after.is_day


def test_missing_polar_event(monkeypatch):
    monkeypatch.setattr(
        "custom_components.better_cover.schedule.get_astral_event_date", lambda *args: None
    )
    result = resolve_schedule(None, {**DEFAULTS, "day_start_mode": "sunrise"}, datetime.now(UTC))
    assert result.is_day is None


def test_same_event_rejected_but_unused_clock_fields_allowed():
    assert (
        validate({**DEFAULTS, "day_start_mode": "dusk", "night_start_mode": "dusk"}) == "same_times"
    )
    assert validate({**DEFAULTS, "day_start_mode": "sunrise", "day_start": "21:00:00"}) is None


def test_resolved_schedule_wins_over_saved_clock():
    result = decide(DEFAULTS, time(23), 45, 180, is_day=True)
    assert result.reason == "Sun tracking"
    result = decide(
        DEFAULTS, time(12), 45, 180, dark=True, temperature=90, indoor_target=70, is_day=False
    )
    assert result.reason == "Night schedule"


def test_real_astral_calculation(monkeypatch):
    zone = ZoneInfo("America/New_York")
    monkeypatch.setattr(dt_util, "DEFAULT_TIME_ZONE", zone)
    hass = SimpleNamespace(
        config=SimpleNamespace(
            latitude=40.7, longitude=-74.0, time_zone="America/New_York", elevation=0
        ),
        data={},
    )
    now = datetime(2026, 9, 9, 12, tzinfo=zone)
    twilight = resolve_schedule(
        hass, {**DEFAULTS, "day_start_mode": "dawn", "night_start_mode": "dusk"}, now
    )
    daylight = resolve_schedule(
        hass, {**DEFAULTS, "day_start_mode": "sunrise", "night_start_mode": "sunset"}, now
    )
    assert (
        twilight.day_start < daylight.day_start < now < daylight.night_start < twilight.night_start
    )
    assert twilight.is_day and daylight.is_day
