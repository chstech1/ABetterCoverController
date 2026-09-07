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


async def add_shade(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "shade"}
    )
    values = {**DEFAULTS, "cover_entity": "cover.real"}
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
    assert len(states) == 4
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
