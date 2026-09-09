"""Exercise the actual HA flow manager and entity platforms."""

import shutil
from pathlib import Path

import pytest
from homeassistant import config_entries, loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry, frame

from custom_components.better_cover.config_flow import STEPS
from custom_components.better_cover.const import DEFAULTS, DOMAIN


@pytest.fixture
async def hass(tmp_path):
    shutil.copytree(Path(__file__).parents[1] / "custom_components", tmp_path / "custom_components")
    instance = HomeAssistant(str(tmp_path))
    loader.async_setup(instance)
    frame.async_setup(instance)
    instance.config_entries = config_entries.ConfigEntries(instance, {})
    await instance.config_entries.async_initialize()
    await device_registry.async_load(instance)
    await entity_registry.async_load(instance)
    instance.states.async_set(
        "cover.real",
        "open",
        {"supported_features": 255, "current_position": 100, "current_tilt_position": 100},
    )
    yield instance
    await instance.async_block_till_done()
    await instance.async_stop()


async def add_shade(hass, source="cover.real", name="Better Cover"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "shade"}
    )
    values = {**DEFAULTS, "cover_entity": source, "name": name}
    for step in ("shade", "sun"):
        keys = STEPS[step]
        assert result["step_id"] == step
        # Submit through HA's schema defaults and selector validation.
        payload = result["data_schema"](
            {k: values[k] for k in keys if k in values and k in result["data_schema"].schema}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], payload)
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "finish"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    return result["result"]


async def test_full_setup_group_options_and_unload(hass):
    entry = await add_shade(hass)
    assert entry.state is config_entries.ConfigEntryState.LOADED
    states = [
        s
        for s in hass.states.async_all()
        if s.entity_id.startswith(
            (
                "switch.better_cover",
                "sensor.better_cover",
                "button.better_cover",
                "cover.better_cover",
            )
        )
    ]
    assert len(states) == 6
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "group"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Living room", "members": [entry.entry_id]}
    )
    await hass.async_block_till_done()
    group = result["result"]
    assert group.state is config_entries.ConfigEntryState.LOADED
    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["step_id"] == "settings"
    hass.config_entries.options.async_abort(options["flow_id"])
    assert await hass.config_entries.async_unload(group.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_save_and_reload(hass):
    entry = await add_shade(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "window_entity": "binary_sensor.original"}
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "limits"}
    )
    payload = result["data_schema"]({"min_position": 20, "window_entity": "binary_sensor.window"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], payload)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "finish"}
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert entry.options["min_position"] == 20
    assert hass.data[DOMAIN][entry.entry_id].config["min_position"] == 20
    assert entry.state is config_entries.ConfigEntryState.LOADED
    # Clearing an optional sensor must actually remove it.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "limits"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], result["data_schema"]({"min_position": 20})
    )
    await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "finish"})
    await hass.async_block_till_done()
    assert "window_entity" not in entry.options
    assert "window_entity" not in hass.data[DOMAIN][entry.entry_id].config


async def test_duplicate_and_recursive_source_rejected(hass):
    await add_shade(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "shade"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], result["data_schema"]({"cover_entity": "cover.real"})
    )
    assert result["errors"]["base"] == "already_configured"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], result["data_schema"]({"cover_entity": "cover.better_cover_cover"})
    )
    assert result["errors"]["base"] == "use_original_cover"


async def test_saved_pause_survives_reload(hass):
    entry = await add_shade(hass)
    c = hass.data[DOMAIN][entry.entry_id]
    await c.pause()
    paused = c.paused_at
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].paused_at == paused


async def test_device_configuration_entities(hass):
    from datetime import timedelta

    from homeassistant.const import EntityCategory
    from homeassistant.util import dt as dt_util

    entry = await add_shade(hass)
    registry = entity_registry.async_get(hass)
    owned = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id]
    assert len({e.device_id for e in owned}) == 1
    settings = [e for e in owned if e.entity_category == EntityCategory.CONFIG]
    assert len(settings) == 31  # 16 numbers, 3 times, 2 switches, 10 selects
    c = hass.data[DOMAIN][entry.entry_id]
    hass.states.async_set("binary_sensor.occupied", "off")
    await hass.async_block_till_done()
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.better_cover_room_occupancy_sensor",
            "option": "binary_sensor.occupied",
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    await c.pause()
    paused = c.paused_at
    c.empty_since = dt_util.utcnow() - timedelta(minutes=10)
    empty_since = c.empty_since
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.better_cover_minimum_opening", "value": 25},
        blocking=True,
    )
    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": "time.better_cover_nighttime_privacy_begins", "time": "20:30:00"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.better_cover_window_limits_override_manual_pause"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id] is c
    assert c.config["min_position"] == 25
    assert c.config["night_start"] == "20:30:00"
    assert not c.config["window_overrides_manual"]
    assert c.paused_at == paused
    assert c.empty_since == empty_since
    assert hass.states.get("number.better_cover_minimum_opening").state == "25.0"
    # Changes persist across a real unload/setup.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].config["min_position"] == 25
    assert hass.data[DOMAIN][entry.entry_id].paused_at == paused


async def test_device_source_selection_and_clear(hass):
    entry = await add_shade(hass)
    c = hass.data[DOMAIN][entry.entry_id]
    hass.states.async_set("binary_sensor.new_window", "off")
    await hass.async_block_till_done()
    selector_id = "select.better_cover_window_contact_sensor"
    assert "binary_sensor.new_window" in hass.states.get(selector_id).attributes["options"]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": selector_id, "option": "binary_sensor.new_window"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert c.config["window_entity"] == "binary_sensor.new_window"
    hass.states.async_set("binary_sensor.new_window", "on")
    await hass.async_block_till_done()
    assert c.window_open
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": selector_id, "option": "Not configured"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert "window_entity" not in c.config
    assert not c.window_open


async def test_device_rejects_invalid_limits(hass):
    from homeassistant.exceptions import ServiceValidationError

    entry = await add_shade(hass)
    c = hass.data[DOMAIN][entry.entry_id]
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.better_cover_minimum_opening", "value": 50},
        blocking=True,
    )
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError, match="Minimum opening"):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.better_cover_maximum_opening", "value": 20},
            blocking=True,
        )
    assert c.config["max_position"] == 100


async def test_device_temperature_sources_set_one_at_a_time(hass):
    entry = await add_shade(hass)
    hass.states.async_set("sensor.outside", "90", {"unit_of_measurement": "°F"})
    hass.states.async_set("climate.home", "cool", {"temperature": 21})
    await hass.async_block_till_done()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.better_cover_outside_temperature_sensor", "option": "sensor.outside"},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.better_cover_thermostat_target_source", "option": "climate.home"},
        blocking=True,
    )
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    assert c.config["temperature_entity"] == "sensor.outside"
    assert c.config["thermostat_entity"] == "climate.home"


async def test_group_device_member_controls(hass):
    from homeassistant.exceptions import ServiceValidationError

    entry = await add_shade(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "group"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Room", "members": [entry.entry_id]}
    )
    await hass.async_block_till_done()
    remove = hass.states.get("select.room_remove_group_member")
    assert len(remove.attributes["options"]) == 2
    with pytest.raises(ServiceValidationError, match="at least one"):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": remove.entity_id, "option": remove.attributes["options"][1]},
            blocking=True,
        )


async def test_group_device_add_and_remove(hass):
    entry = await add_shade(hass)
    hass.states.async_set(
        "cover.second", "open", {"supported_features": 255, "current_position": 100}
    )
    second = await add_shade(hass, "cover.second", "Blackout")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "group"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Room", "members": [entry.entry_id]}
    )
    await hass.async_block_till_done()
    group = hass.data[DOMAIN][result["result"].entry_id]
    option = hass.states.get("select.room_add_group_member").attributes["options"][1]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.room_add_group_member", "option": option},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert group.config["members"] == [entry.entry_id, second.entry_id]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.room_remove_group_member", "option": option},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert group.config["members"] == [entry.entry_id]


async def test_device_solar_schedule_persists(hass):
    entry = await add_shade(hass)
    for entity, option in (
        ("select.better_cover_daytime_begins_at", "Sunrise"),
        ("select.better_cover_nighttime_privacy_begins_at", "Dusk"),
    ):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": entity, "option": option}, blocking=True
        )
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    assert c.config["day_start_mode"] == "sunrise"
    assert c.config["night_start_mode"] == "dusk"
    assert c.config["day_start"] == "08:00:00"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("select.better_cover_daytime_begins_at").state == "Sunrise"
    assert hass.states.get("time.better_cover_daytime_begins").attributes["active"] is False


async def test_copy_latest_settings_independent(hass):
    source = await add_shade(hass)
    saved = {
        **source.data,
        "min_position": 30,
        "azimuth": 255,
        "occupancy_entity": "binary_sensor.old_room",
        "day_start_mode": "dawn",
        "night_start_mode": "dusk",
        "window_entity": "binary_sensor.contact",
    }
    hass.config_entries.async_update_entry(source, options=saved)
    await hass.async_block_till_done()
    await hass.data[DOMAIN][source.entry_id].pause()
    hass.states.async_set(
        "cover.new_room", "open", {"supported_features": 255, "current_position": 100}
    )
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"next_step_id": "copy"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"source_entry": source.entry_id}
    )
    assert flow["step_id"] == "copy_target"
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Family Room",
            "cover_entity": "cover.new_room",
            "occupancy_entity": "binary_sensor.new_room",
        },
    )
    assert flow["step_id"] == "settings"
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"next_step_id": "finish"}
    )
    await hass.async_block_till_done()
    new = flow["result"]
    expected = {
        **saved,
        "name": "Family Room",
        "cover_entity": "cover.new_room",
        "occupancy_entity": "binary_sensor.new_room",
    }
    assert dict(new.data) == expected
    c = hass.data[DOMAIN][new.entry_id]
    assert not c.enabled and c.paused_at is None
    assert new.entry_id != source.entry_id
    hass.config_entries.async_update_entry(new, options={**new.data, "min_position": 10})
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][source.entry_id].config["min_position"] == 30


async def test_copy_rejects_duplicate_and_can_clear_occupancy(hass):
    source = await add_shade(hass)
    hass.config_entries.async_update_entry(
        source, options={**source.data, "occupancy_entity": "binary_sensor.old"}
    )
    await hass.async_block_till_done()
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"next_step_id": "copy"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"source_entry": source.entry_id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": "Copy", "cover_entity": "cover.real"}
    )
    assert flow["errors"]["base"] == "already_configured"
    hass.states.async_set(
        "cover.other", "open", {"supported_features": 255, "current_position": 100}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": "Copy", "cover_entity": "cover.other"}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"next_step_id": "finish"}
    )
    await hass.async_block_till_done()
    assert "occupancy_entity" not in flow["result"].data
