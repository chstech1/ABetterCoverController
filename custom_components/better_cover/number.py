"""Editable limits and tuning on each device."""

from homeassistant.components.number import NumberEntity, NumberMode

from .const import DOMAIN
from .settings import NUMBERS, SettingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    controller = hass.data[DOMAIN][entry.entry_id]
    if entry.data.get("kind") == "group":
        return
    keys = [
        key
        for key in NUMBERS
        if not (
            (controller.tilt and key in ("window_height", "sun_depth"))
            or (not controller.tilt and key in ("slat_width", "slat_spacing"))
        )
    ]
    async_add_entities([SettingNumber(controller, key) for key in keys])


class SettingNumber(SettingEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, controller, key):
        name, low, high, step, unit = NUMBERS[key]
        super().__init__(controller, key, name)
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = (
            controller.hass.config.units.temperature_unit if key == "temperature_deadband" else unit
        )

    @property
    def native_value(self):
        return self.saved[self.key]

    async def async_set_native_value(self, value):
        await self.write(value)
