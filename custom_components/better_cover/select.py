"""Source choices and group membership controls on device pages."""

from collections.abc import Mapping

from homeassistant.components.select import SelectEntity
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN, POSITIONING_MODES
from .schedule import SCHEDULE_MODES, SCHEDULE_SETTINGS
from .settings import SOURCES, SettingEntity, update_settings

NONE = "Not configured"
CHOOSE = "Choose a member"
CHANNELS = {"Raise / lower": "position", "Slat tilt": "tilt"}
SOURCE_DOMAINS = frozenset(domain for _, domains in SOURCES.values() for domain in domains)
SOURCE_SELECT_DEBOUNCE_SECONDS = 0.1


class SourceSelectCoordinator:
    """Share source discovery between all source selects."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.selects: set[SourceSelect] = set()
        self._pending_domains: set[str] = set()
        self._cancel_refresh = None
        self._available = self._available_entities()
        self._unsubscribers = (
            hass.bus.async_listen(
                EVENT_STATE_CHANGED,
                self._state_changed,
                event_filter=self._state_change_affects_options,
            ),
            hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED,
                self._registry_changed,
                event_filter=self._registry_change_affects_options,
            ),
        )

    @callback
    def async_add(self, entity: "SourceSelect") -> None:
        """Register one select without adding another global listener."""
        self.selects.add(entity)
        entity._set_options(self._available, er.async_get(self.hass))

    @callback
    def async_remove(self, entity: "SourceSelect") -> None:
        """Unregister one select and tear down the shared listeners when empty."""
        self.selects.discard(entity)
        if self.selects:
            return
        if self._cancel_refresh:
            self._cancel_refresh()
            self._cancel_refresh = None
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        if self.hass.data.get(DATA_SOURCE_SELECT_COORDINATOR) is self:
            self.hass.data.pop(DATA_SOURCE_SELECT_COORDINATOR)

    @callback
    def _state_change_affects_options(self, data) -> bool:
        """Accept only entity additions and removals in selectable domains."""
        entity_id = data.get("entity_id", "")
        old_state = data.get("old_state")
        new_state = data.get("new_state")
        return (
            entity_id.partition(".")[0] in SOURCE_DOMAINS
            and (old_state is None) != (new_state is None)
        )

    @callback
    def _registry_change_affects_options(self, data) -> bool:
        """Accept registry changes that can add, remove, rename, or disable an option."""
        entity_ids = (data.get("entity_id", ""), data.get("old_entity_id", ""))
        if not any(entity_id.partition(".")[0] in SOURCE_DOMAINS for entity_id in entity_ids):
            return False
        if data.get("action") != "update":
            return True
        return "old_entity_id" in data or "disabled_by" in data.get("changes", {})

    @callback
    def _state_changed(self, event) -> None:
        self._schedule_refresh({event.data["entity_id"].partition(".")[0]})

    @callback
    def _registry_changed(self, event) -> None:
        data = event.data
        domains = {
            entity_id.partition(".")[0]
            for entity_id in (data.get("entity_id", ""), data.get("old_entity_id", ""))
            if entity_id.partition(".")[0] in SOURCE_DOMAINS
        }
        self._schedule_refresh(domains)

    @callback
    def _schedule_refresh(self, domains: set[str]) -> None:
        """Coalesce a burst of registry/state events into one option refresh."""
        self._pending_domains.update(domains)
        if self._cancel_refresh:
            self._cancel_refresh()
        self._cancel_refresh = async_call_later(
            self.hass, SOURCE_SELECT_DEBOUNCE_SECONDS, self._refresh
        )

    @callback
    def _refresh(self, _now) -> None:
        """Write only selects whose computed options actually changed."""
        self._cancel_refresh = None
        domains, self._pending_domains = self._pending_domains, set()
        self._available = self._available_entities()
        registry = er.async_get(self.hass)
        for entity in tuple(self.selects):
            if domains.intersection(SOURCES[entity.key][1]) and entity._set_options(
                self._available, registry
            ):
                entity.async_write_ha_state()

    @callback
    def _available_entities(self) -> dict[str, set[str]]:
        """Snapshot selectable state and registry entities once per refresh."""
        available = {domain: set() for domain in SOURCE_DOMAINS}
        for state in self.hass.states.async_all():
            if state.domain in available:
                available[state.domain].add(state.entity_id)
        for entry in er.async_get(self.hass).entities.values():
            if entry.domain in available and not entry.disabled_by:
                available[entry.domain].add(entry.entity_id)
        return available


DATA_SOURCE_SELECT_COORDINATOR: HassKey[SourceSelectCoordinator] = HassKey(
    f"{DOMAIN}_source_select_coordinator"
)


@callback
def _source_select_coordinator(hass: HomeAssistant) -> SourceSelectCoordinator:
    if coordinator := hass.data.get(DATA_SOURCE_SELECT_COORDINATOR):
        return coordinator
    coordinator = SourceSelectCoordinator(hass)
    hass.data[DATA_SOURCE_SELECT_COORDINATOR] = coordinator
    return coordinator


async def async_setup_entry(hass, entry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    if entry.data.get("kind") == "group":
        async_add_entities([MemberSelect(c, False), MemberSelect(c, True)])
    else:
        async_add_entities(
            [SourceSelect(c, key, spec[0]) for key, spec in SOURCES.items()]
            + [ChannelSelect(c, "control_type", "Control channel")]
            + [PositioningSelect(c, "positioning_mode", "Positioning mode")]
            + [ScheduleSelect(c, key, name) for key, name in SCHEDULE_SETTINGS.items()]
        )


class SourceSelect(SettingEntity, SelectEntity):
    _attr_options: list[str]

    def __init__(self, controller, key, name):
        super().__init__(controller, key, name)
        self._attr_options = []

    @property
    def current_option(self):
        return self.saved.get(self.key, NONE)

    @callback
    def _set_options(
        self, available: Mapping[str, set[str]], registry: er.EntityRegistry
    ) -> bool:
        """Cache options and report whether the entity state needs a write."""
        domains = SOURCES[self.key][1]
        ids = set().union(*(available[domain] for domain in domains))
        if self.key == "cover_entity":
            ids = {
                entity_id
                for entity_id in ids
                if not (
                    registry.async_get(entity_id)
                    and registry.async_get(entity_id).platform == DOMAIN
                )
            }
        current = self.saved.get(self.key)
        if current:
            ids.add(current)
        options = ([NONE] if self.key != "cover_entity" else []) + sorted(ids)
        if options == self._attr_options:
            return False
        self._attr_options = options
        return True

    async def async_select_option(self, option):
        await self.write(None if option == NONE else option)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        coordinator = _source_select_coordinator(self.hass)
        coordinator.async_add(self)
        self.async_on_remove(lambda: coordinator.async_remove(self))


class ChannelSelect(SettingEntity, SelectEntity):
    _attr_options = list(CHANNELS)

    @property
    def current_option(self):
        return next(label for label, value in CHANNELS.items() if value == self.saved[self.key])

    async def async_select_option(self, option):
        await self.write(CHANNELS[option])


class MemberSelect(SettingEntity, SelectEntity):
    def __init__(self, controller, remove):
        super().__init__(
            controller,
            "remove_member" if remove else "add_member",
            "Remove group member" if remove else "Add group member",
        )
        self.remove = remove

    @property
    def choices(self):
        members = self.saved["members"]
        entries = self.hass.config_entries.async_entries(DOMAIN)
        choices = {}
        for entry in entries:
            if entry.data.get("kind") == "group":
                continue
            if (entry.entry_id in members) == self.remove:
                label = (
                    f"{(entry.options or entry.data).get('name', entry.title)} [{entry.entry_id}]"
                )
                choices[label] = entry.entry_id
        if self.remove:
            known = set(choices.values())
            for member in members:
                if member not in known:
                    choices[f"Missing controller [{member}]"] = member
        return choices

    @property
    def options(self):
        return [CHOOSE, *sorted(self.choices)]

    @property
    def current_option(self):
        return CHOOSE

    async def async_select_option(self, option):
        if option == CHOOSE:
            return
        member = self.choices[option]
        members = list(self.saved["members"])
        if self.remove:
            members.remove(member)
        else:
            members.append(member)
        await update_settings(self.controller, {"members": members})
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_changed", self.async_write_ha_state)
        )


class ScheduleSelect(SettingEntity, SelectEntity):
    _attr_options = list(SCHEDULE_MODES)

    @property
    def current_option(self):
        return next(
            label for label, value in SCHEDULE_MODES.items() if value == self.saved[self.key]
        )

    async def async_select_option(self, option):
        await self.write(SCHEDULE_MODES[option])


class PositioningSelect(SettingEntity, SelectEntity):
    _attr_options = list(POSITIONING_MODES)

    @property
    def current_option(self):
        return next(
            label for label, value in POSITIONING_MODES.items() if value == self.saved[self.key]
        )

    async def async_select_option(self, option):
        await self.write(POSITIONING_MODES[option])
