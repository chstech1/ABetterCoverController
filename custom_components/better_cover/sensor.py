"""Visible explanation and target for troubleshooting without logs."""

from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .entity import BetterEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([StatusSensor(hass.data[DOMAIN][entry.entry_id])])


class StatusSensor(BetterEntity, SensorEntity):
    def __init__(self, controller):
        super().__init__(controller, "status", "Status")

    @property
    def native_value(self):
        return self.controller.reason

    @property
    def extra_state_attributes(self):
        c = self.controller
        return {
            "target_percent_open": c.target,
            "current_percent_open": c.position,
            "manual_paused_since": c.paused_at.isoformat() if c.paused_at else None,
            "room_empty_since": c.empty_since.isoformat() if c.empty_since else None,
            "room_is_dark": c.dark,
            "group_members": c.config.get("members"),
            "window_open": c.window_open,
            "source_cover": c.config.get("cover_entity"),
        }
