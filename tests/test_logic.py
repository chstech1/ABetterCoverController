from datetime import time

import pytest

from custom_components.better_cover.const import DEFAULTS
from custom_components.better_cover.logic import decide, device_position, validate


def config(**kwargs):
    return {**DEFAULTS, **kwargs}


def test_sun_geometry():
    assert decide(config(), time(12), 45, 180).position == 33
    assert decide(config(), time(12), 10, 180).position < 33
    assert decide(config(), time(12), 75, 180).position == 100


def test_back_of_window_and_night():
    assert decide(config(), time(12), 45, 0).position == 100
    assert (
        decide(config(), time(23), 45, 180, dark=True, temperature=90, indoor_target=70).position
        == 0
    )


def test_limits_and_inversion():
    cfg = config(min_position=20, max_position=80, window_min=90, window_max=100)
    assert decide(cfg, time(23), 45, 180).position == 20
    assert decide(cfg, time(23), 45, 180, window_open=True).position == 90
    assert device_position(90, True) == 10
    assert device_position(90, False) == 90


def test_temperature_and_light():
    assert decide(config(), time(12), 45, 180, temperature=90, indoor_target=70).position == 0
    assert decide(config(), time(12), 45, 180, temperature=50, indoor_target=70).position == 100
    assert (
        decide(config(), time(12), 45, 180, temperature=71, indoor_target=70).reason
        == "Sun tracking"
    )
    assert (
        decide(config(), time(12), 45, 180, dark=True, temperature=90, indoor_target=70).position
        == 100
    )


def test_tilt():
    cfg = config(control_type="tilt")
    low = decide(cfg, time(12), 5, 180).position
    high = decide(cfg, time(12), 60, 180).position
    assert 0 < low < high == 100


@pytest.mark.parametrize("bad", [None, "unavailable", "nan", "inf"])
def test_missing_sun_holds(bad):
    assert decide(config(), time(12), bad, 180).position is None
    assert decide(config(), time(23), bad, 180).position == 0


def test_wrapped_schedule_and_azimuth():
    cfg = config(day_start="21:00:00", night_start="08:00:00", azimuth=350)
    assert decide(cfg, time(23), 45, 10).reason == "Sun tracking"
    assert decide(cfg, time(12), 45, 10).reason == "Night schedule"


def test_validation():
    assert validate(config(min_position=90, max_position=10)) == "invalid_limits"
    assert validate(config(slat_spacing=30)) == "invalid_slats"
    assert validate(config(temperature_entity="sensor.outdoor")) == "temperature_pair"
    assert validate(config(dark_lux=300)) == "invalid_light_thresholds"
