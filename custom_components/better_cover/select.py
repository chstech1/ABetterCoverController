"""Source choices and group membership controls on device pages."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, POSITIONING_MODES
from .schedule import SCHEDULE_MODES, SCHEDULE_SETTINGS
from .settings import SOURCES, SettingEntity, update_settings

NONE = "Not configured"
CHOOSE = "Choose a member"
CHANNELS = {"Raise / lower": "position", "Slat tilt": "tilt"}


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
    @property
    def options(self):
        domains = SOURCES[self.key][1]
        registry = er.async_get(self.hass)
        ids = {s.entity_id for s in self.hass.states.async_all() if s.domain in domains}
        ids.update(
            e.entity_id
            for e in registry.entities.values()
            if e.domain in domains and not e.disabled_by
        )
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
        return ([NONE] if self.key != "cover_entity" else []) + sorted(ids)

    @property
    def current_option(self):
        return self.saved.get(self.key, NONE)

    async def async_select_option(self, option):
        await self.write(None if option == NONE else option)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        @callback
        def changed(event):
            if (
                event.event_type == "entity_registry_updated"
                or event.data.get("old_state") is None
                or event.data.get("new_state") is None
            ):
                self.async_write_ha_state()

        self.async_on_remove(self.hass.bus.async_listen("state_changed", changed))
        self.async_on_remove(self.hass.bus.async_listen("entity_registry_updated", changed))


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
