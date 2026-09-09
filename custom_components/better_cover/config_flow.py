"""Small, guided setup and editable options."""

from copy import deepcopy

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import DEFAULTS, DOMAIN
from .logic import validate
from .schedule import SCHEDULE_MODES

STEPS = {
    "shade": ["name", "cover_entity", "control_type", "invert_position"],
    "sun": ["azimuth", "window_height", "sun_depth", "slat_width", "slat_spacing"],
    "schedule": [
        "day_start_mode",
        "day_start",
        "night_start_mode",
        "night_start",
        "day_position",
        "night_position",
    ],
    "limits": ["min_position", "max_position", "window_entity", "window_min", "window_max"],
    "comfort": [
        "light_entity",
        "dark_lux",
        "bright_lux",
        "temperature_entity",
        "thermostat_entity",
        "temperature_deadband",
        "hot_position",
    ],
    "manual": [
        "forced_close_entity",
        "home_entity",
        "occupancy_entity",
        "empty_hours",
        "reset_time",
        "window_overrides_manual",
        "min_change",
        "interval_minutes",
    ],
}


def schema(step, values):
    fields = {}
    for key in STEPS[step]:
        if step == "sun" and (
            (values.get("control_type") == "tilt" and key in ("window_height", "sun_depth"))
            or (values.get("control_type") != "tilt" and key in ("slat_width", "slat_spacing"))
        ):
            continue
        optional = key in (
            "forced_close_entity",
            "window_entity",
            "light_entity",
            "temperature_entity",
            "thermostat_entity",
            "home_entity",
            "occupancy_entity",
        )
        marker = (
            vol.Optional(key)
            if optional
            else vol.Required(key, default=values.get(key, DEFAULTS.get(key)))
        )
        if key.endswith("_entity"):
            domain = {
                "forced_close_entity": ["input_boolean", "binary_sensor", "switch"],
                "cover_entity": "cover",
                "window_entity": "binary_sensor",
                "light_entity": "sensor",
                "temperature_entity": "sensor",
                "thermostat_entity": ["climate", "sensor"],
                "home_entity": "binary_sensor",
                "occupancy_entity": "binary_sensor",
            }[key]
            field = selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))
        elif key in ("day_start_mode", "night_start_mode"):
            field = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": value, "label": label} for label, value in SCHEDULE_MODES.items()
                    ]
                )
            )
        elif key == "control_type":
            field = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": "position", "label": "Raise / lower"},
                        {"value": "tilt", "label": "Slat tilt"},
                    ]
                )
            )
        elif key in ("invert_position", "window_overrides_manual"):
            field = selector.BooleanSelector()
        elif key in ("day_start", "night_start", "reset_time"):
            field = selector.TimeSelector()
        elif key == "name":
            field = selector.TextSelector()
        else:
            low, high, step_size = 0, 100, 1
            if key == "azimuth":
                high = 359
            elif key in ("window_height", "sun_depth"):
                low, high, step_size = 0.01, 20, 0.01
            elif key in ("dark_lux", "bright_lux"):
                high = 100000
            elif key == "temperature_deadband":
                low, high, step_size = 0, 20, 0.5
            elif key in ("slat_width", "slat_spacing"):
                low, high, step_size = 1, 200, 0.5
            elif key == "empty_hours":
                low, high, step_size = 0.25, 24, 0.25
            elif key == "interval_minutes":
                low, high = 1, 60
            elif key == "min_change":
                low = 1
            field = selector.NumberSelector(
                selector.NumberSelectorConfig(min=low, max=high, step=step_size, mode="box")
            )
        fields[marker] = field
    return vol.Schema(fields)


def cover_error(hass, values, own_id=None):
    entity_id = values["cover_entity"]
    registered = er.async_get(hass).async_get(entity_id)
    if registered and registered.platform == DOMAIN:
        return "use_original_cover"
    state = hass.states.get(entity_id)
    feature = (
        CoverEntityFeature.SET_TILT_POSITION
        if values["control_type"] == "tilt"
        else CoverEntityFeature.SET_POSITION
    )
    if state is None or not int(state.attributes.get("supported_features", 0)) & feature:
        return "position_required"
    for entry in hass.config_entries.async_entries(DOMAIN):
        data = entry.options or entry.data
        if (
            entry.entry_id != own_id
            and data.get("cover_entity") == entity_id
            and data.get("control_type", "position") == values["control_type"]
        ):
            return "already_configured"
    return None


class Wizard:
    """Shared setup steps."""

    _values = None

    async def _step(self, step, user_input):
        if self._values is None:
            self._values = dict(DEFAULTS)
            if isinstance(self, config_entries.OptionsFlow):
                self._values.update(self.config_entry.options or self.config_entry.data)
        errors = {}
        if user_input is not None:
            for key in STEPS[step]:
                self._values.pop(key, None)
            self._values.update(user_input)
            self._values = {**DEFAULTS, **self._values}
            if step == "shade":
                own_id = (
                    self.config_entry.entry_id
                    if isinstance(self, config_entries.OptionsFlow)
                    else None
                )
                error = cover_error(self.hass, self._values, own_id)
                if error:
                    errors["base"] = error
            if step in ("sun", "schedule", "limits", "comfort"):
                error = validate(self._values)
                if error:
                    errors["base"] = error
            if not errors:
                if step == "shade":
                    return await self._step("sun", None)
                return await self.async_step_settings()
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(
                schema(step, self._values), self._values
            ),
            errors=errors,
        )

    async def async_step_settings(self, user_input=None):
        if self._values is None:
            self._values = {**DEFAULTS, **(self.config_entry.options or self.config_entry.data)}
        return self.async_show_menu(
            step_id="settings",
            menu_options=["finish", "shade", "schedule", "limits", "comfort", "manual"],
        )

    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(title=self._values["name"], data=self._values)

    async def async_step_shade(self, user_input=None):
        return await self._step("shade", user_input)

    async def async_step_group(self, user_input=None):
        entries = [
            e
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.data.get("kind") != "group"
        ]
        if not entries:
            return self.async_abort(reason="no_members")
        values = (
            self.config_entry.options or self.config_entry.data
            if isinstance(self, config_entries.OptionsFlow)
            else {}
        )
        errors = {}
        if user_input is not None:
            if not user_input.get("members") or not set(user_input["members"]).issubset(
                {e.entry_id for e in entries}
            ):
                errors["base"] = "invalid_members"
            else:
                return self.async_create_entry(
                    title=user_input["name"], data={**user_input, "kind": "group"}
                )
        fields = vol.Schema(
            {
                vol.Required("name", default=values.get("name", "Blind group")): str,
                vol.Required("members", default=values.get("members", [])): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        multiple=True,
                        options=[
                            {
                                "value": e.entry_id,
                                "label": (e.options or e.data).get("name", e.title),
                            }
                            for e in entries
                        ],
                    )
                ),
            }
        )
        return self.async_show_form(step_id="group", data_schema=fields, errors=errors)

    async def async_step_sun(self, user_input=None):
        return await self._step("sun", user_input)

    async def async_step_schedule(self, user_input=None):
        return await self._step("schedule", user_input)

    async def async_step_limits(self, user_input=None):
        return await self._step("limits", user_input)

    async def async_step_comfort(self, user_input=None):
        return await self._step("comfort", user_input)

    async def async_step_manual(self, user_input=None):
        return await self._step("manual", user_input)


class BetterCoverFlow(Wizard, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["shade", "copy", "group"])

    async def async_step_copy(self, user_input=None):
        entries = [
            e
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.data.get("kind") != "group"
        ]
        if not entries:
            return self.async_abort(reason="no_copy_source")
        errors = {}
        if user_input is not None:
            source = next((e for e in entries if e.entry_id == user_input["source_entry"]), None)
            if source is None:
                errors["base"] = "invalid_copy_source"
            else:
                self._values = {**DEFAULTS, **deepcopy(dict(source.options or source.data))}
                self._values.pop("kind", None)
                self._values.pop("members", None)
                self._values["name"] = f"{self._values['name']} copy"
                self._values.pop("cover_entity", None)
                return await self.async_step_copy_target()
        return self.async_show_form(
            step_id="copy",
            data_schema=vol.Schema(
                {
                    vol.Required("source_entry"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": e.entry_id,
                                    "label": f"{(e.options or e.data).get('name', e.title)} ({(e.options or e.data).get('cover_entity')})",
                                }
                                for e in entries
                            ]
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_copy_target(self, user_input=None):
        errors = {}
        if user_input is not None:
            values = {**self._values, **user_input}
            if "occupancy_entity" not in user_input:
                values.pop("occupancy_entity", None)
            error = cover_error(self.hass, values)
            if error:
                errors["base"] = error
            else:
                self._values = values
                return await self.async_step_settings()
        fields = vol.Schema(
            {
                vol.Required("name", default=self._values["name"]): selector.TextSelector(),
                vol.Required("cover_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="cover")
                ),
                vol.Optional("occupancy_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor")
                ),
            }
        )
        return self.async_show_form(
            step_id="copy_target",
            data_schema=self.add_suggested_values_to_schema(fields, self._values),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BetterCoverOptions()


class BetterCoverOptions(Wizard, config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if self.config_entry.data.get("kind") == "group":
            return await self.async_step_group(user_input)
        return await self.async_step_settings(user_input)
