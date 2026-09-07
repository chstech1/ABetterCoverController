"""Device configuration entities share the integration's persisted options."""

from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .const import DEFAULTS, DOMAIN
from .entity import BetterEntity
from .logic import validate

# key: label, minimum, maximum, step, unit
NUMBERS = {
    "min_position": ("Minimum opening", 0, 100, 1, "%"),
    "max_position": ("Maximum opening", 0, 100, 1, "%"),
    "window_min": ("Window-open minimum opening", 0, 100, 1, "%"),
    "window_max": ("Window-open maximum opening", 0, 100, 1, "%"),
    "day_position": ("Daytime opening", 0, 100, 1, "%"),
    "night_position": ("Nighttime privacy opening", 0, 100, 1, "%"),
    "hot_position": ("Hot-weather opening", 0, 100, 1, "%"),
    "azimuth": ("Window direction", 0, 359, 1, "°"),
    "window_height": ("Window height", 0.01, 20, 0.01, "m"),
    "sun_depth": ("Sunlight reach into room", 0.01, 20, 0.01, "m"),
    "slat_width": ("Slat width", 1, 200, 0.5, "mm"),
    "slat_spacing": ("Slat spacing", 1, 200, 0.5, "mm"),
    "dark_lux": ("Dark-room threshold", 0, 100000, 1, "lx"),
    "bright_lux": ("Bright-again threshold", 0, 100000, 1, "lx"),
    "temperature_deadband": ("Temperature difference before reacting", 0, 20, 0.5, None),
    "empty_hours": ("Resume after room vacancy", 0.25, 24, 0.25, "h"),
    "min_change": ("Minimum movement", 1, 100, 1, "%"),
    "interval_minutes": ("Minimum time between moves", 1, 60, 1, "min"),
}
TIMES = {
    "day_start": "Daytime begins",
    "night_start": "Nighttime privacy begins",
    "reset_time": "Morning reset",
}
SWITCHES = {
    "invert_position": "Device reports zero as open",
    "window_overrides_manual": "Window limits override manual pause",
}
SOURCES = {
    "cover_entity": ("Hardware cover", ["cover"]),
    "window_entity": ("Window contact sensor", ["binary_sensor"]),
    "light_entity": ("Room brightness sensor", ["sensor"]),
    "temperature_entity": ("Outside temperature sensor", ["sensor"]),
    "thermostat_entity": ("Thermostat target source", ["climate", "sensor"]),
    "home_entity": ("Anyone-home sensor", ["binary_sensor"]),
    "occupancy_entity": ("Room occupancy sensor", ["binary_sensor"]),
}
ERRORS = {
    "invalid_limits": "Minimum opening must not exceed maximum opening. Change the other limit first.",
    "same_times": "Daytime and nighttime must begin at different times.",
    "invalid_slats": "Slat spacing must not exceed slat width.",
    "invalid_light_thresholds": "Bright-again threshold must exceed the dark-room threshold.",
}


async def update_settings(controller, changes):
    """Merge against the latest saved options, avoiding lost rapid/concurrent edits."""
    hass, entry = controller.hass, controller.entry
    values = {**DEFAULTS, **(entry.options or entry.data)}
    for key, value in changes.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = value
    if values.get("kind") == "group":
        members = values["members"]
        eligible = {
            e.entry_id
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.data.get("kind") != "group"
        }
        if not members or not set(members).issubset(eligible):
            raise ServiceValidationError("A group needs at least one existing blind controller.")
    else:
        error = validate(values, require_temperature_pair=False)
        # Source dropdowns are edited one at a time. Until both temperature
        # sources exist, the runtime simply uses sun tracking.
        if error:
            raise ServiceValidationError(ERRORS[error])
        if "cover_entity" in changes or "control_type" in changes:
            source = hass.states.get(values["cover_entity"])
            registered = er.async_get(hass).async_get(values["cover_entity"])
            feature = (
                CoverEntityFeature.SET_TILT_POSITION
                if values["control_type"] == "tilt"
                else CoverEntityFeature.SET_POSITION
            )
            if registered and registered.platform == DOMAIN:
                raise ServiceValidationError(
                    "Choose the original hardware cover, not a Better Cover entity."
                )
            if not source or not int(source.attributes.get("supported_features", 0)) & feature:
                raise ServiceValidationError(
                    "The cover does not support percentage control for this channel."
                )
            for other in hass.config_entries.async_entries(DOMAIN):
                data = other.options or other.data
                if (
                    other.entry_id != entry.entry_id
                    and data.get("cover_entity") == values["cover_entity"]
                    and data.get("control_type", "position") == values["control_type"]
                ):
                    raise ServiceValidationError(
                        "That cover and channel already have a controller."
                    )
    # No await before this mutation: each edit reads the preceding edit's result.
    hass.config_entries.async_update_entry(entry, options=values)


class SettingEntity(BetterEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller, key, name):
        super().__init__(controller, f"setting_{key}", name)
        self.key = key

    @property
    def saved(self):
        return {**DEFAULTS, **(self.controller.entry.options or self.controller.entry.data)}

    async def write(self, value):
        await update_settings(self.controller, {self.key: value})
