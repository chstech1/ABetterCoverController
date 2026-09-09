from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import Context, Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.better_cover.const import DOMAIN
from custom_components.better_cover.controller import Controller
from custom_components.better_cover.group import GroupController


@pytest.fixture
async def controller(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    entry = SimpleNamespace(
        entry_id="test",
        data={"cover_entity": "cover.test", "day_start": "00:00:00", "night_start": "23:59:59"},
        options={},
    )
    c = Controller(hass, entry)
    c.save = AsyncMock()
    hass.states.async_set(
        "cover.test", "open", {"current_position": 100, "supported_features": 255}
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 45, "azimuth": 180})
    c.calls = []

    async def move(call):
        c.calls.append(call)

    hass.services.async_register("cover", "set_cover_position", move)
    hass.services.async_register("cover", "set_cover_tilt_position", move)
    yield c
    await hass.async_block_till_done()
    await hass.async_stop()


async def test_off_then_enabled(controller):
    c = controller
    await c.evaluate()
    assert not c.calls
    await c.set_enabled(True)
    assert c.calls[-1].data["position"] == 33
    await c.evaluate()
    assert len(c.calls) == 1


async def test_manual_clamps_and_pauses(controller):
    c = controller
    c.config.update(window_entity="binary_sensor.window", window_min=60)
    c.hass.states.async_set("binary_sensor.window", "on")
    await c.manual(0)
    assert c.calls[-1].data["position"] == 60
    assert c.paused_at


async def test_window_overrides_pause(controller):
    c = controller
    c.enabled = True
    c.config.update(window_entity="binary_sensor.window", window_min=60)
    c.hass.states.async_set("cover.test", "closed", {"current_position": 0})
    c.hass.states.async_set("binary_sensor.window", "on")
    await c.pause()
    await c.evaluate()
    assert c.calls[-1].data["position"] == 60
    await c.evaluate()
    assert len(c.calls) == 1


async def test_vacancy_resumes(controller):
    c = controller
    c.enabled = True
    c.config["occupancy_entity"] = "binary_sensor.room"
    c.hass.states.async_set("binary_sensor.room", "off")
    now = dt_util.utcnow()
    await c.pause()
    c.paused_at = now - timedelta(hours=3)
    c.empty_since = now - timedelta(hours=3)
    await c.update_inputs(now)
    assert c.paused_at is None


async def test_unknown_occupancy_resets_timer(controller):
    c = controller
    c.config["occupancy_entity"] = "binary_sensor.room"
    c.hass.states.async_set("binary_sensor.room", "unavailable")
    c.empty_since = dt_util.utcnow() - timedelta(hours=3)
    await c.pause()
    await c.update_inputs(dt_util.utcnow())
    assert c.empty_since is None
    assert c.paused_at


async def test_leaving_home_resumes(controller):
    c = controller
    c.config["home_entity"] = "binary_sensor.home"
    await c.pause()
    c.hass.states.async_set("binary_sensor.home", "off")
    await c.update_inputs(dt_util.utcnow())
    assert c.paused_at is None


async def test_tilt_command_and_inversion(controller):
    c = controller
    c.config.update(control_type="tilt", invert_position=True)
    c.hass.states.async_set("cover.test", "open", {"current_tilt_position": 20})
    assert c.position == 80
    await c.manual(70)
    assert c.calls[-1].service == "set_cover_tilt_position"
    assert c.calls[-1].data["tilt_position"] == 30


async def test_temperature_conversion(controller):
    c = controller
    c.config.update(temperature_entity="sensor.outside", thermostat_entity="climate.house")
    c.hass.states.async_set("sensor.outside", "90", {"unit_of_measurement": "°F"})
    c.hass.states.async_set("climate.house", "cool", {"temperature": 21})
    outside, target = c.temperatures()
    assert outside == pytest.approx(32.22222)
    assert target == 21


async def test_own_service_not_manual(controller):
    c = controller
    context = c.new_context()
    data = {
        "domain": "cover",
        "service": "set_cover_position",
        "service_data": {"entity_id": "cover.test"},
    }
    await c.service_called(Event("call_service", data, context=context))
    assert c.paused_at is None
    await c.service_called(Event("call_service", data, context=Context()))
    assert c.paused_at


async def test_service_failure_retries(controller):
    c = controller

    async def fail(call):
        raise HomeAssistantError("Device offline")

    c.hass.services.async_register("cover", "set_cover_position", fail)
    await c.set_enabled(True)
    assert c.expected is None
    assert "failed" in c.reason


async def test_group_preserves_member_limits(controller):
    c = controller
    other = Controller(
        c.hass,
        SimpleNamespace(
            entry_id="other",
            data={"cover_entity": "cover.other", "min_position": 40, "invert_position": True},
            options={},
        ),
    )
    other.save = AsyncMock()
    c.hass.states.async_set("cover.other", "open", {"current_position": 0})
    c.hass.data[DOMAIN] = {"test": c, "other": other}
    group = GroupController(
        c.hass,
        SimpleNamespace(
            entry_id="group", data={"name": "Group", "members": ["test", "other"]}, options={}
        ),
    )
    await group.manual(0)
    assert c.calls[-2].data["position"] == 0
    assert c.calls[-1].data["position"] == 60
    assert c.paused_at and other.paused_at


async def test_morning_reset_does_not_turn_on_disabled_control(controller):
    c = controller
    now = dt_util.utcnow()
    c.paused_at = now - timedelta(days=2)
    await c.update_inputs(now)
    assert c.paused_at is None
    assert not c.enabled


async def test_manual_action_while_already_away_stays_paused(controller):
    c = controller
    c.config["home_entity"] = "binary_sensor.home"
    c.hass.states.async_set("binary_sensor.home", "off")
    await c.pause()
    await c.update_inputs(dt_util.utcnow())
    assert c.paused_at


async def test_dark_hysteresis(controller):
    c = controller
    c.config["light_entity"] = "sensor.lux"
    for lux, dark in [(50, True), (150, True), (250, False), (150, False)]:
        c.hass.states.async_set("sensor.lux", str(lux))
        await c.update_inputs(dt_util.utcnow())
        assert c.dark is dark


async def test_missing_window_uses_window_limits(controller):
    c = controller
    c.config.update(window_entity="binary_sensor.missing", window_min=75)
    await c.manual(0)
    assert c.calls[-1].data["position"] == 75


async def test_group_continues_after_one_member_fails(controller):
    c = controller
    second = Controller(
        c.hass,
        SimpleNamespace(entry_id="second", data={"cover_entity": "cover.second"}, options={}),
    )
    second.save = AsyncMock()
    c.manual = AsyncMock(side_effect=HomeAssistantError("failed"))
    second.manual = AsyncMock()
    c.hass.data[DOMAIN] = {"test": c, "second": second}
    group = GroupController(
        c.hass, SimpleNamespace(entry_id="group", data={"members": ["test", "second"]}, options={})
    )
    with pytest.raises(HomeAssistantError):
        await group.manual(50)
    second.manual.assert_awaited_once_with(50)


async def test_forced_close_preserves_window_limits_despite_off_pause_and_missing_sun(controller):
    c = controller
    c.config.update(
        forced_close_entity="input_boolean.sleep",
        min_position=70,
        window_entity="binary_sensor.window",
        window_min=90,
    )
    c.hass.states.async_set("input_boolean.sleep", "on")
    c.hass.states.async_set("binary_sensor.window", "on")
    c.hass.states.async_set("sun.sun", "unavailable")
    await c.pause()
    paused = c.paused_at
    await c.evaluate()
    assert c.calls[-1].data["position"] == 90
    assert c.reason == "Forced close active · window-open limits" and c.target == 90
    assert c.paused_at == paused and not c.enabled


async def test_forced_close_has_no_timeout(controller):
    c = controller
    c.config["forced_close_entity"] = "input_boolean.sleep"
    c.hass.states.async_set("input_boolean.sleep", "on")
    c.paused_at = dt_util.utcnow() - timedelta(days=5)
    c.empty_since = dt_util.utcnow() - timedelta(days=5)
    paused = c.paused_at
    await c.evaluate()
    assert c.forced_closed and c.paused_at == paused
    await c.set_enabled(True)
    assert c.forced_closed and c.target == 0


async def test_forced_close_blocks_manual_and_stop(controller):
    from homeassistant.exceptions import ServiceValidationError

    c = controller
    c.config["forced_close_entity"] = "input_boolean.sleep"
    c.hass.states.async_set("input_boolean.sleep", "on")
    with pytest.raises(ServiceValidationError, match="Forced close"):
        await c.manual(100)
    with pytest.raises(ServiceValidationError, match="Forced close"):
        await c.stop()
    assert c.paused_at is None


async def test_forced_close_release_restores_disabled_state(controller):
    c = controller
    c.config["forced_close_entity"] = "input_boolean.sleep"
    c.hass.states.async_set("input_boolean.sleep", "on")
    await c.evaluate()
    c.hass.states.async_set("cover.test", "closed", {"current_position": 0})
    c.hass.states.async_set("input_boolean.sleep", "off")
    await c.evaluate()
    assert c.reason == "Automatic control off" and not c.enabled
    assert len(c.calls) == 1


async def test_forced_close_inverted_tilt(controller):
    c = controller
    c.config.update(
        control_type="tilt", invert_position=True, forced_close_entity="binary_sensor.sleep"
    )
    c.hass.states.async_set("cover.test", "open", {"current_tilt_position": 0})
    c.hass.states.async_set("binary_sensor.sleep", "on")
    await c.evaluate()
    assert c.calls[-1].service == "set_cover_tilt_position"
    assert c.calls[-1].data["tilt_position"] == 100


async def test_external_open_recloses_during_settling(controller):
    c = controller
    c.config["forced_close_entity"] = "input_boolean.sleep"
    c.hass.states.async_set("input_boolean.sleep", "on")
    await c.evaluate()
    data = {"domain": "cover", "service": "open_cover", "service_data": {"entity_id": "cover.test"}}
    await c.service_called(Event("call_service", data, context=Context()))
    assert len(c.calls) == 2 and c.calls[-1].data["position"] == 0
    assert c.paused_at is None


async def test_physical_reopen_recloses(controller):
    c = controller
    c.config["forced_close_entity"] = "input_boolean.sleep"
    c.hass.states.async_set("input_boolean.sleep", "on")
    await c.evaluate()
    c.hass.states.async_set("cover.test", "closed", {"current_position": 0})
    old = c.source
    c.hass.states.async_set("cover.test", "opening", {"current_position": 20})
    await c.changed(
        Event("state_changed", {"entity_id": "cover.test", "old_state": old, "new_state": c.source})
    )
    assert len(c.calls) == 2 and c.calls[-1].data["position"] == 0


@pytest.mark.parametrize("state", ["off", "unknown", "unavailable"])
async def test_forced_close_only_on_activates(controller, state):
    c = controller
    c.config["forced_close_entity"] = "input_boolean.sleep"
    c.hass.states.async_set("input_boolean.sleep", state)
    await c.evaluate()
    assert not c.forced_closed and not c.calls


async def test_forced_close_follows_window_open_and_closed(controller):
    c = controller
    c.config.update(
        forced_close_entity="input_boolean.sleep",
        window_entity="binary_sensor.window",
        window_min=60,
        min_position=30,
    )
    c.hass.states.async_set("input_boolean.sleep", "on")
    c.hass.states.async_set("binary_sensor.window", "off")
    await c.evaluate()
    assert c.calls[-1].data["position"] == 0
    c.hass.states.async_set("cover.test", "closed", {"current_position": 0})
    c.hass.states.async_set("binary_sensor.window", "on")
    await c.evaluate()
    assert c.calls[-1].data["position"] == 60
    c.hass.states.async_set("cover.test", "open", {"current_position": 60})
    c.hass.states.async_set("binary_sensor.window", "off")
    await c.evaluate()
    assert c.calls[-1].data["position"] == 0


async def test_forced_close_unavailable_contact_and_inversion(controller):
    c = controller
    c.config.update(
        forced_close_entity="input_boolean.sleep",
        window_entity="binary_sensor.missing",
        window_min=65,
        invert_position=True,
    )
    c.hass.states.async_set("input_boolean.sleep", "on")
    c.hass.states.async_set("cover.test", "closed", {"current_position": 100})
    await c.evaluate()
    assert c.target == 65
    assert c.calls[-1].data["position"] == 35


async def test_forced_close_corrects_external_close_below_window_minimum(controller):
    c = controller
    c.config.update(
        forced_close_entity="input_boolean.sleep",
        window_entity="binary_sensor.window",
        window_min=60,
        window_overrides_manual=False,
    )
    c.hass.states.async_set("input_boolean.sleep", "on")
    c.hass.states.async_set("binary_sensor.window", "on")
    await c.evaluate()
    c.hass.states.async_set("cover.test", "open", {"current_position": 60})
    old = c.source
    c.hass.states.async_set("cover.test", "closing", {"current_position": 30})
    await c.changed(
        Event("state_changed", {"entity_id": "cover.test", "old_state": old, "new_state": c.source})
    )
    assert len(c.calls) == 2
    assert c.calls[-1].data["position"] == 60
