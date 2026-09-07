"""Explicit resume action."""

from homeassistant.components.button import ButtonEntity

from .const import DOMAIN
from .entity import BetterEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ResumeButton(hass.data[DOMAIN][entry.entry_id])])


class ResumeButton(BetterEntity, ButtonEntity):
    def __init__(self, controller):
        super().__init__(controller, "resume", "Resume automatic control")

    async def async_press(self):
        await self.controller.set_enabled(True)
