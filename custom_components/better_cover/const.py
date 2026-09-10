"""Constants for Better Cover."""

DOMAIN = "better_cover"
POSITIONING_MODES = {"Sun tracking": "sun_tracking", "Schedule only": "schedule_only"}
DEFAULTS = {
    "name": "Better Cover",
    "control_type": "position",
    "positioning_mode": "sun_tracking",
    "invert_position": False,
    "azimuth": 180,
    "window_height": 1.5,
    "sun_depth": 0.5,
    "day_start_mode": "fixed",
    "night_start_mode": "fixed",
    "day_start": "08:00:00",
    "night_start": "21:00:00",
    "day_position": 100,
    "night_position": 0,
    "min_position": 0,
    "max_position": 100,
    "window_min": 50,
    "window_max": 100,
    "min_change": 5,
    "interval_minutes": 5,
    "reset_time": "08:00:00",
    "empty_hours": 2,
    "dark_lux": 100,
    "bright_lux": 200,
    "temperature_deadband": 2,
    "slat_width": 25,
    "slat_spacing": 20,
    "hot_position": 0,
    "window_overrides_manual": True,
}
