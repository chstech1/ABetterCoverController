"""Normalized manual cover controls, honoring configured limits."""

from homeassistant.components.cover import CoverEntity, CoverEntityFeature

from .const import DOMAIN
from .entity import BetterEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BetterCover(hass.data[DOMAIN][entry.entry_id])])


class BetterCover(BetterEntity, CoverEntity):
    def __init__(self, controller):
        super().__init__(controller, "cover", "Slats" if controller.tilt else "Cover")
        if controller.tilt:
            self._attr_supported_features = (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )
            stop = CoverEntityFeature.STOP_TILT
        else:
            self._attr_supported_features = (
                CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION
            )
            stop = CoverEntityFeature.STOP
        if (
            controller.source
            and int(controller.source.attributes.get("supported_features", 0)) & stop
        ):
            self._attr_supported_features |= stop

    @property
    def available(self):
        return self.controller.available

    @property
    def current_cover_position(self):
        return self.controller.position if not self.controller.tilt else None

    @property
    def current_cover_tilt_position(self):
        return self.controller.position if self.controller.tilt else None

    @property
    def is_closed(self):
        return self.controller.position == 0 if self.controller.position is not None else None

    async def async_open_cover(self, **kwargs):
        await self.controller.manual(100)

    async def async_close_cover(self, **kwargs):
        await self.controller.manual(0)

    async def async_set_cover_position(self, **kwargs):
        await self.controller.manual(kwargs["position"])

    async def async_stop_cover(self, **kwargs):
        await self.controller.stop()

    async def async_open_cover_tilt(self, **kwargs):
        await self.controller.manual(100)

    async def async_close_cover_tilt(self, **kwargs):
        await self.controller.manual(0)

    async def async_set_cover_tilt_position(self, **kwargs):
        await self.controller.manual(kwargs["tilt_position"])

    async def async_stop_cover_tilt(self, **kwargs):
        await self.controller.stop()
