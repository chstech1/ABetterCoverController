"""Groups coordinate individual controllers without discarding their limits."""

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN


class GroupController:
    tilt = False
    source = None
    paused_at = None
    empty_since = None
    dark = False
    target = None

    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.config = {**entry.data, **entry.options}
        self.listeners = set()

    @property
    def members(self):
        loaded = self.hass.data.get(DOMAIN, {})
        return [
            loaded[key]
            for key in self.config["members"]
            if key in loaded and not isinstance(loaded[key], GroupController)
        ]

    @property
    def available(self):
        return len(self.members) == len(self.config["members"]) and all(
            c.available for c in self.members
        )

    @property
    def enabled(self):
        return bool(self.members) and all(c.enabled for c in self.members)

    @property
    def position(self):
        positions = [c.position for c in self.members if c.position is not None]
        return round(sum(positions) / len(positions)) if positions else None

    @property
    def window_open(self):
        return any(c.window_open for c in self.members)

    @property
    def forced_closed(self):
        return any(c.forced_closed for c in self.members)

    @property
    def reason(self):
        if not self.available:
            return "One or more members unavailable"
        if self.forced_closed:
            return "One or more members forced closed"
        if any(c.paused_at for c in self.members):
            return "One or more members manually paused"
        return "Automatic control on" if self.enabled else "Automatic control off or mixed"

    async def start(self):
        self.entry.async_on_unload(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_changed", self.publish)
        )

    @callback
    def publish(self):
        for listener in tuple(self.listeners):
            listener()

    async def _each(self, method, *args):
        errors = []
        for member in self.members:
            try:
                await getattr(member, method)(*args)
            except HomeAssistantError as err:
                errors.append(str(err))
        self.publish()
        if errors or len(self.members) != len(self.config["members"]):
            raise HomeAssistantError(
                "Some group members could not be controlled. " + "; ".join(errors)
            )

    async def manual(self, position):
        await self._each("manual", position)

    async def set_enabled(self, enabled):
        await self._each("set_enabled", enabled)

    @property
    def manual_mode(self):
        return any(c.manual_mode for c in self.members)

    async def recalculate(self):
        await self._each("recalculate")

    async def stop(self):
        await self._each("stop")
