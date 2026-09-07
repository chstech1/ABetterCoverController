"""Better Cover: a small controller for existing positionable shades."""

from .const import DOMAIN
from .controller import Controller
from .group import GroupController

PLATFORMS = ["cover", "switch", "sensor", "button"]


async def async_setup_entry(hass, entry):
    controller = (
        GroupController(hass, entry)
        if entry.data.get("kind") == "group"
        else Controller(hass, entry)
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller
    await controller.start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False
