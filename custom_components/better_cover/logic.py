"""Pure positioning rules. All positions express percent OPEN."""

from dataclasses import dataclass
from datetime import time
from math import asin, atan, cos, degrees, isfinite, radians, tan


@dataclass(frozen=True)
class Decision:
    position: int | None
    reason: str


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


def device_position(position, inverted):
    return round(100 - position if inverted else position)


def daytime(now: time, start: str, end: str):
    start, end = time.fromisoformat(start), time.fromisoformat(end)
    now = now.replace(tzinfo=None)
    return start <= now < end if start < end else now >= start or now < end


def limits(config, window_open):
    # The open-window range replaces the regular range, rather than intersecting it.
    return (
        (config["window_min"], config["window_max"])
        if window_open
        else (config["min_position"], config["max_position"])
    )


def clamp(position, config, window_open):
    low, high = limits(config, window_open)
    return round(max(low, min(high, position)))


def decide(
    config,
    now,
    elevation,
    azimuth,
    window_open=False,
    dark=False,
    temperature=None,
    indoor_target=None,
    is_day=None,
):
    if is_day is None:
        is_day = daytime(now, config["day_start"], config["night_start"])
    if not is_day:
        return Decision(clamp(config["night_position"], config, window_open), "Night schedule")
    if dark:
        return Decision(clamp(config["day_position"], config, window_open), "Room is dark")
    elevation, azimuth = number(elevation), number(azimuth)
    if elevation is None or azimuth is None:
        return Decision(None, "Waiting for sun data")
    delta = (azimuth - config["azimuth"] + 180) % 360 - 180
    if elevation <= 0 or abs(delta) >= 90:
        target, reason = config["day_position"], "No direct sun"
    elif (
        number(temperature) is not None
        and number(indoor_target) is not None
        and number(temperature) > number(indoor_target) + config["temperature_deadband"]
    ):
        target, reason = config["hot_position"], "Warmer outside · shading"
    elif (
        number(temperature) is not None
        and number(indoor_target) is not None
        and number(temperature) < number(indoor_target) - config["temperature_deadband"]
    ):
        target, reason = config["day_position"], "Cooler outside · admitting sun"
    elif config.get("control_type") == "tilt":
        profile = atan(tan(radians(min(elevation, 89.9))) / cos(radians(delta)))
        ratio = min(1, config["slat_spacing"] / config["slat_width"] * cos(profile))
        closing_angle = max(0, degrees(asin(ratio) - profile))
        target, reason = 100 * (1 - closing_angle / 90), "Sun tracking · slat tilt"
    else:
        # Height of uncovered glass allowing sunlight to penetrate no further
        # than sun_depth inward from the window plane. Vertical roller shades only.
        height = config["sun_depth"] * tan(radians(min(elevation, 89.9))) / cos(radians(delta))
        target = 100 * height / config["window_height"]
        reason = "Sun tracking"
    return Decision(clamp(target, config, window_open), reason)


def validate(config, require_temperature_pair=True):
    if (
        config["min_position"] > config["max_position"]
        or config["window_min"] > config["window_max"]
    ):
        return "invalid_limits"
    day_mode = config.get("day_start_mode", "fixed")
    night_mode = config.get("night_start_mode", "fixed")
    if day_mode == night_mode and (
        day_mode != "fixed"
        or time.fromisoformat(config["day_start"]) == time.fromisoformat(config["night_start"])
    ):
        return "same_times"
    if config.get("slat_spacing", 1) > config.get("slat_width", 1):
        return "invalid_slats"
    if require_temperature_pair and bool(config.get("temperature_entity")) != bool(
        config.get("thermostat_entity")
    ):
        return "temperature_pair"
    if config.get("dark_lux", 0) >= config.get("bright_lux", 1):
        return "invalid_light_thresholds"
    return None
