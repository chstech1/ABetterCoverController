"""Shared entity metadata and state updates."""

from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class BetterEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, controller, key, name):
        self.controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, controller.entry.entry_id)},
            "name": controller.config["name"],
            "manufacturer": "Better Cover",
            "model": "Sun-tracking shade controller",
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.controller.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self.controller.listeners.discard(self.async_write_ha_state))
