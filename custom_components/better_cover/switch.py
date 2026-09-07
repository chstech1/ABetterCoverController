"""Automatic control toggle."""

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import BetterEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AutoSwitch(hass.data[DOMAIN][entry.entry_id])])


class AutoSwitch(BetterEntity, SwitchEntity):
    def __init__(self, controller):
        super().__init__(controller, "automatic", "Automatic control")

    @property
    def is_on(self):
        return self.controller.enabled

    async def async_turn_on(self, **kwargs):
        await self.controller.set_enabled(True)

    async def async_turn_off(self, **kwargs):
        await self.controller.set_enabled(False)
