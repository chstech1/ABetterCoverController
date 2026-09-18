"""Visible explanation and target for troubleshooting without logs."""

from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .entity import BetterEntity
from .group_controller import GroupController


async def async_setup_entry(hass, entry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StatusSensor(c), DesiredPositionSensor(c)])


class StatusSensor(BetterEntity, SensorEntity):
    def __init__(self, controller):
        super().__init__(controller, "status", "Status")

    @property
    def native_value(self):
        return self.controller.reason

    @property
    def extra_state_attributes(self):
        c = self.controller
        schedule = getattr(c, "schedule", None)
        return {
            "daytime_begins_today": schedule.day_start.isoformat()
            if schedule and schedule.day_start
            else None,
            "nighttime_privacy_begins_today": schedule.night_start.isoformat()
            if schedule and schedule.night_start
            else None,
            "schedule_is_daytime": schedule.is_day if schedule else None,
            "forced_close_active": getattr(c, "forced_closed", False),
            "forced_close_entity": c.config.get("forced_close_entity"),
            "target_percent_open": c.target,
            "current_percent_open": c.position,
            "manual_paused_since": c.paused_at.isoformat() if c.paused_at else None,
            "room_empty_since": c.empty_since.isoformat() if c.empty_since else None,
            "room_is_dark": c.dark,
            "group_members": c.config.get("members"),
            "window_open": c.window_open,
            "source_cover": c.config.get("cover_entity"),
        }


class DesiredPositionSensor(BetterEntity, SensorEntity):
    """Human-readable calculated opening, or an explicit manual pause."""

    _attr_icon = "mdi:blinds-horizontal"

    def __init__(self, controller):
        super().__init__(controller, "desired_position", "Desired position")

    @property
    def targets(self):
        c = self.controller
        if isinstance(c, GroupController):
            loaded = {member.entry.entry_id: member.target for member in c.members}
            return {key: loaded.get(key) for key in c.config["members"]}
        return {c.entry.entry_id: c.target}

    @property
    def native_value(self):
        if self.controller.manual_mode:
            return "Manual"
        targets = list(self.targets.values())
        if not targets or any(target is None for target in targets):
            return None
        if len(set(targets)) > 1:
            return "Mixed"
        return f"{targets[0]}%"

    @property
    def extra_state_attributes(self):
        c = self.controller
        targets = list(self.targets.values())
        common = targets[0] if targets and all(t == targets[0] for t in targets) else None
        return {
            "target_percent_open": common,
            "current_percent_open": c.position,
            "automatic_control_enabled": c.enabled,
            "manual_mode": c.manual_mode,
            "forced_close_active": c.forced_closed,
            **({"member_targets": self.targets} if isinstance(c, GroupController) else {}),
        }
