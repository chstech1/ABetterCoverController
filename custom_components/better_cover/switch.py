"""Automatic control toggle."""

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import BetterEntity
from .settings import SWITCHES, SettingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    entities = [AutoSwitch(c)]
    if entry.data.get("kind") != "group":
        entities += [SettingSwitch(c, key, name) for key, name in SWITCHES.items()]
    async_add_entities(entities)


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


class SettingSwitch(SettingEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.saved[self.key]

    async def async_turn_on(self, **kwargs):
        await self.write(True)

    async def async_turn_off(self, **kwargs):
        await self.write(False)
