"""Event-driven controller with persistent manual overrides."""

import asyncio
import logging
from datetime import datetime, time, timedelta

from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import DEFAULTS, DOMAIN
from .logic import Decision, clamp, decide, device_position, limits, number
from .schedule import resolve_schedule

_LOGGER = logging.getLogger(__name__)


class Controller:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.config = {**DEFAULTS, **(entry.options or entry.data)}
        self.enabled = False
        self.paused_at = None
        self.empty_since = None
        self.dark = False
        self.reason = "Automatic control off"
        self.target = None
        self.schedule = None
        self.last_sent = None
        self.expected = None
        self.moving_until = None
        self.context_ids = []
        self.listeners = set()
        self._state_unsub = None
        self.lock = asyncio.Lock()
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    @property
    def source(self):
        return self.hass.states.get(self.config["cover_entity"])

    @property
    def tilt(self):
        return self.config["control_type"] == "tilt"

    @property
    def position_attribute(self):
        return "current_tilt_position" if self.tilt else "current_position"

    @property
    def position(self):
        raw = number(self.source.attributes.get(self.position_attribute)) if self.source else None
        return (
            device_position(raw, self.config["invert_position"])
            if raw is not None and 0 <= raw <= 100
            else None
        )

    @property
    def available(self):
        return (
            self.source is not None
            and self.source.state not in ("unknown", "unavailable")
            and self.position is not None
        )

    def state(self, key):
        entity_id = self.config.get(key)
        return self.hass.states.get(entity_id) if entity_id else None

    @property
    def forced_closed(self):
        state = self.state("forced_close_entity")
        return state is not None and state.state == "on"

    @property
    def forced_close_target(self):
        # Sleep may override ordinary positions, but never window clearance.
        return clamp(0, self.config, True) if self.window_open else 0

    @property
    def window_open(self):
        if not self.config.get("window_entity"):
            return False
        state = self.state("window_entity")
        return state is None or state.state != "off"

    async def start(self):
        saved = await self.store.async_load() or {}
        self.enabled = saved.get("enabled", False)
        paused = saved.get("paused_at")
        self.paused_at = dt_util.parse_datetime(paused) if paused else None
        # Occupancy timer starts fresh after restart: downtime is not evidence of vacancy.
        self.watch_sources()
        self.entry.async_on_unload(lambda: self._state_unsub())
        self.entry.async_on_unload(
            async_track_time_interval(self.hass, self.tick, timedelta(seconds=30))
        )
        self.entry.async_on_unload(self.hass.bus.async_listen("call_service", self.service_called))
        await self.evaluate()

    def watch_sources(self):
        if self._state_unsub:
            self._state_unsub()
        entities = ["sun.sun"] + [v for k, v in self.config.items() if k.endswith("_entity") and v]
        self._state_unsub = async_track_state_change_event(self.hass, entities, self.changed)

    async def update_config(self, values):
        async with self.lock:
            if self.config.get("occupancy_entity") != values.get("occupancy_entity"):
                self.empty_since = None
            if self.config.get("light_entity") != values.get("light_entity"):
                self.dark = False
            if self.config.get("invert_position") != values.get("invert_position"):
                self.expected = None
                self.moving_until = None
            self.config = {**DEFAULTS, **values}
            self.watch_sources()
        await self.evaluate()

    async def save(self):
        await self.store.async_save(
            {
                "enabled": self.enabled,
                "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            }
        )

    @callback
    def publish(self):
        async_dispatcher_send(self.hass, f"{DOMAIN}_changed")
        for listener in tuple(self.listeners):
            listener()

    async def tick(self, now):
        await self.evaluate()

    async def service_called(self, event):
        data = event.data
        actions = (
            (
                "open_cover_tilt",
                "close_cover_tilt",
                "set_cover_tilt_position",
                "stop_cover_tilt",
                "toggle_cover_tilt",
            )
            if self.tilt
            else ("open_cover", "close_cover", "set_cover_position", "stop_cover", "toggle")
        )
        if data.get("domain") != "cover" or data.get("service") not in actions:
            return
        targets = data.get("service_data", {}).get("entity_id", [])
        if isinstance(targets, str):
            targets = [targets]
        if self.config["cover_entity"] in targets and event.context.id not in self.context_ids:
            if self.forced_closed:
                self.expected = None
                self.moving_until = None
            else:
                await self.pause()
            await self.evaluate()

    async def changed(self, event):
        if event.data["entity_id"] == self.config["cover_entity"]:
            old, new = event.data.get("old_state"), event.data.get("new_state")
            if (
                old
                and new
                and old.state not in ("unknown", "unavailable")
                and new.state not in ("unknown", "unavailable")
            ):
                moved = old.attributes.get(self.position_attribute) != new.attributes.get(
                    self.position_attribute
                ) or (
                    not self.tilt and old.state != new.state and new.state in ("opening", "closing")
                )
                own = (
                    new.context.id in self.context_ids or new.context.parent_id in self.context_ids
                )
                settling = self.moving_until and dt_util.utcnow() < self.moving_until
                if moved and not own:
                    if self.forced_closed:
                        old_raw = number(old.attributes.get(self.position_attribute))
                        new_raw = number(new.attributes.get(self.position_attribute))
                        old_open = (
                            device_position(old_raw, self.config["invert_position"])
                            if old_raw is not None
                            else None
                        )
                        new_open = (
                            device_position(new_raw, self.config["invert_position"])
                            if new_raw is not None
                            else None
                        )
                        if (new.state == "opening" and self.forced_close_target == 0) or (
                            old_open is not None
                            and new_open is not None
                            and abs(new_open - self.forced_close_target)
                            > abs(old_open - self.forced_close_target)
                        ):
                            self.expected = None
                            self.moving_until = None
                    elif new.context.user_id or not settling:
                        await self.pause()
        await self.evaluate()

    async def pause(self):
        self.paused_at = dt_util.utcnow()
        await self.save()

    async def set_enabled(self, enabled):
        self.enabled = enabled
        self.paused_at = None
        await self.save()
        await self.evaluate(force=True)

    async def manual(self, position):
        async with self.lock:
            if self.forced_closed:
                raise ServiceValidationError(
                    "Forced close is active. Turn off the configured forced-close entity before using manual controls."
                )
            await self.pause()
            await self.send(clamp(position, self.config, self.window_open))
        await self.evaluate()

    async def stop(self):
        async with self.lock:
            if self.forced_closed:
                raise ServiceValidationError(
                    "Forced close is active. Turn off the configured forced-close entity before using manual controls."
                )
            await self.pause()
            context = self.new_context()
            await self.hass.services.async_call(
                "cover",
                "stop_cover_tilt" if self.tilt else "stop_cover",
                {"entity_id": self.config["cover_entity"]},
                blocking=True,
                context=context,
            )
        await self.evaluate()

    def new_context(self):
        context = Context()
        self.context_ids = (self.context_ids + [context.id])[-20:]
        return context

    async def send(self, target):
        if self.forced_closed:
            target = self.forced_close_target
        if self.expected == target and self.moving_until and dt_util.utcnow() < self.moving_until:
            return
        context = self.new_context()
        now = dt_util.utcnow()
        self.expected = target
        # Motors may omit service context and report intermediate positions.
        self.moving_until = now + timedelta(seconds=120)
        try:
            await self.hass.services.async_call(
                "cover",
                "set_cover_tilt_position" if self.tilt else "set_cover_position",
                {
                    "entity_id": self.config["cover_entity"],
                    ("tilt_position" if self.tilt else "position"): device_position(
                        target, self.config["invert_position"]
                    ),
                },
                blocking=True,
                context=context,
            )
        except HomeAssistantError:
            self.expected = None
            self.moving_until = None
            raise
        self.last_sent = now

    async def update_inputs(self, now):
        occupancy = self.state("occupancy_entity")
        if occupancy and occupancy.state == "off":
            self.empty_since = self.empty_since or now
        else:
            self.empty_since = None
        light = self.state("light_entity")
        lux = number(light.state) if light else None
        if lux is None:
            self.dark = False
        elif lux <= self.config["dark_lux"]:
            self.dark = True
        elif lux >= self.config["bright_lux"]:
            self.dark = False
        if not self.paused_at:
            return
        home = self.state("home_entity")
        # Resume on a vacancy transition after the manual action, not continuously
        # just because the house was already empty when the action was made.
        away = home and home.state == "off" and home.last_changed > self.paused_at
        empty = self.empty_since and now - max(self.empty_since, self.paused_at) >= timedelta(
            hours=self.config["empty_hours"]
        )
        local_now = dt_util.as_local(now)
        reset = datetime.combine(
            local_now.date(), time.fromisoformat(self.config["reset_time"]), local_now.tzinfo
        )
        if local_now < reset:
            reset -= timedelta(days=1)
        morning = dt_util.as_utc(reset) > self.paused_at
        if away or empty or morning:
            self.paused_at = None
            await self.save()

    async def evaluate(self, force=False):
        async with self.lock:
            try:
                await self._evaluate(force)
            except HomeAssistantError as err:
                self.reason = "Cover command failed; will retry"
                _LOGGER.warning("Unable to move %s: %s", self.config["cover_entity"], err)
            self.publish()

    def temperatures(self):
        outside, thermostat = self.state("temperature_entity"), self.state("thermostat_entity")
        if not outside or not thermostat or thermostat.state in ("unknown", "unavailable"):
            return None, None
        unit = self.hass.config.units.temperature_unit
        target = (
            thermostat.state
            if thermostat.domain == "sensor"
            else thermostat.attributes.get(
                "temperature", thermostat.attributes.get("target_temp_high")
            )
        )
        target_unit = thermostat.attributes.get("unit_of_measurement", unit)
        outside_value, target_value = number(outside.state), number(target)
        if outside_value is None or target_value is None:
            return None, None
        try:
            return (
                TemperatureConverter.convert(
                    outside_value, outside.attributes.get("unit_of_measurement"), unit
                ),
                TemperatureConverter.convert(target_value, target_unit, unit),
            )
        except ValueError:
            return None, None

    async def _evaluate(self, force):
        now = dt_util.utcnow()
        if self.forced_closed:
            self.target = self.forced_close_target
            self.reason = "Forced close active" + (
                " · window-open limits" if self.window_open else ""
            )
            if not self.available:
                self.reason += " · waiting for cover position"
            elif self.position != self.target:
                await self.send(self.target)
            return
        await self.update_inputs(now)
        sun = self.hass.states.get("sun.sun")
        outside, indoor_target = self.temperatures()
        self.schedule = resolve_schedule(self.hass, self.config, now)
        decision = (
            decide(
                self.config,
                dt_util.as_local(now).time(),
                sun.attributes.get("elevation")
                if sun and sun.state not in ("unknown", "unavailable")
                else None,
                sun.attributes.get("azimuth") if sun else None,
                window_open=self.window_open,
                dark=self.dark,
                temperature=outside,
                indoor_target=indoor_target,
                is_day=self.schedule.is_day,
            )
            if self.schedule.is_day is not None
            else Decision(None, "Waiting for schedule boundaries")
        )
        self.target = decision.position
        if not self.enabled:
            self.reason = "Automatic control off"
            return
        if not self.available:
            self.reason = "Waiting for cover position"
            return
        low, high = limits(self.config, self.window_open)
        outside_limits = not low <= self.position <= high
        if self.paused_at:
            self.reason = "Manual pause"
            if self.window_open and self.config["window_overrides_manual"] and outside_limits:
                self.reason = "Manual pause · enforcing window-open limits"
                await self.send(clamp(self.position, self.config, True))
            return
        self.reason = decision.reason + (" · window-open limits" if self.window_open else "")
        if decision.position is None:
            # Window clearance still applies when environmental data is absent.
            if self.window_open and outside_limits:
                await self.send(clamp(self.position, self.config, True))
            return
        if abs(decision.position - self.position) < (
            1 if outside_limits else self.config["min_change"]
        ):
            return
        if not force and not outside_limits:
            if self.moving_until and now < self.moving_until:
                return
            if self.last_sent and now - self.last_sent < timedelta(
                minutes=self.config["interval_minutes"]
            ):
                return
        # Avoid resending the same command while a slow shade is still moving.
        if self.expected == decision.position and self.moving_until and now < self.moving_until:
            return
        await self.send(decision.position)
