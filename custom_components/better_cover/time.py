"""Editable daily schedules on each device."""

from datetime import time

from homeassistant.components.time import TimeEntity

from .const import DOMAIN
from .settings import TIMES, SettingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("kind") != "group":
        async_add_entities(
            [
                SettingTime(hass.data[DOMAIN][entry.entry_id], key, name)
                for key, name in TIMES.items()
            ]
        )


class SettingTime(SettingEntity, TimeEntity):
    @property
    def native_value(self):
        return time.fromisoformat(self.saved[self.key])

    async def async_set_value(self, value):
        await self.write(value.isoformat())
