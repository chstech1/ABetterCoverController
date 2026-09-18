"""Exercise the actual HA flow manager and entity platforms."""

import asyncio
import shutil
from pathlib import Path

import pytest
from homeassistant import config_entries, loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry, frame

from custom_components.better_cover.config_flow import STEPS
from custom_components.better_cover.const import DEFAULTS, DOMAIN
from custom_components.better_cover.select import (
    DATA_SOURCE_SELECT_COORDINATOR,
    SOURCE_SELECT_DEBOUNCE_SECONDS,
    SourceSelect,
)


@pytest.fixture
async def hass(tmp_path):
    shutil.copytree(Path(__file__).parents[1] / "custom_components", tmp_path / "custom_components")
    instance = HomeAssistant(str(tmp_path))
    loader.async_setup(instance)
    frame.async_setup(instance)
    instance.config_entries = config_entries.ConfigEntries(instance, {})
    await instance.config_entries.async_initialize()
    if hasattr(device_registry, "async_setup"):
        device_registry.async_setup(instance)
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


async def settle_source_selects(hass):
    """Wait for the deliberately trailing source-option debounce."""
    await hass.async_block_till_done()
    await asyncio.sleep(SOURCE_SELECT_DEBOUNCE_SECONDS * 1.5)
    await hass.async_block_till_done()


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
    assert len(states) == 8
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


async def test_internal_group_controller_is_not_a_group_platform(hass, caplog):
    """The internal group controller must not be discovered as HA's group platform."""
    from homeassistant.setup import async_setup_component

    await add_shade(hass)
    integration = await loader.async_get_integration(hass, DOMAIN)
    assert integration.platforms_exists(("group",)) == []
    assert await async_setup_component(hass, "group", {})
    await hass.async_block_till_done()
    assert "async_describe_on_off_states" not in caplog.text


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
    assert len(settings) == 33  # 16 numbers, 3 times, 2 switches, 12 selects
    c = hass.data[DOMAIN][entry.entry_id]
    hass.states.async_set("binary_sensor.occupied", "off")
    await settle_source_selects(hass)
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
    await settle_source_selects(hass)
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


async def test_source_select_registry_updates_are_shared_debounced_and_bounded(
    hass, monkeypatch
):
    """A registry burst refreshes 56 selects once and writes only changed options."""
    await add_shade(hass, name="Shade 0")
    for index in range(1, 7):
        entity_id = f"cover.real_{index}"
        hass.states.async_set(
            entity_id, "open", {"supported_features": 255, "current_position": 100}
        )
        await add_shade(hass, entity_id, f"Shade {index}")
    await settle_source_selects(hass)

    coordinator = hass.data[DATA_SOURCE_SELECT_COORDINATOR]
    assert len(coordinator.selects) == 56

    # Ordinary state transitions never affect the option set and are filtered
    # before they can schedule a refresh.
    hass.states.async_set("binary_sensor.steady", "off")
    await settle_source_selects(hass)
    writes = []
    snapshots = 0
    original_write = SourceSelect.async_write_ha_state
    original_snapshot = coordinator._available_entities

    def record_write(entity):
        writes.append((entity.entity_id, entity.key))
        original_write(entity)

    def record_snapshot():
        nonlocal snapshots
        snapshots += 1
        return original_snapshot()

    monkeypatch.setattr(SourceSelect, "async_write_ha_state", record_write)
    monkeypatch.setattr(coordinator, "_available_entities", record_snapshot)
    hass.states.async_set("binary_sensor.steady", "on")
    hass.states.async_set("light.unrelated", "on")
    await settle_source_selects(hass)
    assert snapshots == 0
    assert writes == []

    # Twenty back-to-back registry creations collapse to one snapshot. Only
    # the three sensor-capable dropdowns per controller get one state write.
    registry = entity_registry.async_get(hass)
    for index in range(20):
        registry.async_get_or_create(
            "sensor", "test", f"burst_{index}", suggested_object_id=f"burst_{index}"
        )
    await settle_source_selects(hass)
    assert snapshots == 1
    changed_entities = {entity_id for entity_id, _key in writes}
    assert len(changed_entities) == 21
    # HA may immediately write each changed select once more after synchronizing
    # its new options into that select's own entity-registry capabilities.
    assert len(writes) <= 42
    assert {key for _entity_id, key in writes} == {
        "light_entity",
        "temperature_entity",
        "thermostat_entity",
    }

    # The select state writes above must not recursively schedule another scan,
    # and irrelevant registry metadata must not schedule one either.
    await settle_source_selects(hass)
    registry.async_update_entity("sensor.burst_0", name="Renamed")
    await settle_source_selects(hass)
    assert snapshots == 1
    assert len(writes) <= 42


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
    await settle_source_selects(hass)
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


async def test_sleep_helper_selection_and_reload(hass):
    from unittest.mock import AsyncMock

    entry = await add_shade(hass)
    hass.states.async_set("input_boolean.sleep", "off")
    await settle_source_selects(hass)
    entity_id = "select.better_cover_forced_close_entity"
    assert "input_boolean.sleep" in hass.states.get(entity_id).attributes["options"]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "input_boolean.sleep"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options["forced_close_entity"] == "input_boolean.sleep"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    c.send = AsyncMock()
    hass.states.async_set("input_boolean.sleep", "on")
    await hass.async_block_till_done()
    c.send.assert_awaited_once_with(0, force=False)
    assert not c.enabled and c.reason == "Forced close active"
    hass.states.async_set("input_boolean.sleep", "off")
    await hass.async_block_till_done()
    assert not c.forced_closed and c.reason == "Automatic control off"


async def test_manual_indicator_button_and_positioning_mode(hass):
    from unittest.mock import AsyncMock

    entry = await add_shade(hass)
    c = hass.data[DOMAIN][entry.entry_id]
    assert hass.states.get("binary_sensor.better_cover_manual_mode").state == "off"
    await c.pause()
    c.publish()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.better_cover_manual_mode").state == "on"
    c.recalculate = AsyncMock()
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.better_cover_recalculate_and_move"}, blocking=True
    )
    c.recalculate.assert_awaited_once()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.better_cover_positioning_mode", "option": "Schedule only"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert c.config["positioning_mode"] == "schedule_only"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("select.better_cover_positioning_mode").state == "Schedule only"
    assert hass.states.get("binary_sensor.better_cover_manual_mode").state == "on"


async def test_desired_position_updates_and_restores_manual(hass):
    entry = await add_shade(hass)
    c = hass.data[DOMAIN][entry.entry_id]
    entity_id = "sensor.better_cover_desired_position"
    c.target = 75
    c.publish()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "75%"
    assert hass.states.get(entity_id).attributes["current_percent_open"] == 100
    assert not hass.states.get(entity_id).attributes["automatic_control_enabled"]
    await c.pause()
    c.publish()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "Manual"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "Manual"
    c = hass.data[DOMAIN][entry.entry_id]
    c.paused_at = None
    c.target = None
    c.publish()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"
