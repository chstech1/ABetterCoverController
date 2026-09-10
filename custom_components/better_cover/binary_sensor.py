"""Manual pause indicator for individual controllers and groups."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN
from .entity import BetterEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ManualModeSensor(hass.data[DOMAIN][entry.entry_id])])


class ManualModeSensor(BetterEntity, BinarySensorEntity):
    _attr_icon = "mdi:hand-back-right"

    def __init__(self, controller):
        super().__init__(controller, "manual_mode", "Manual mode")

    @property
    def is_on(self):
        return self.controller.manual_mode
