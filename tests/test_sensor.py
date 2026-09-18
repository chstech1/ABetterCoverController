"""Display targets without confusing averages, actual position, or manual pauses."""

from types import SimpleNamespace

from custom_components.better_cover.const import DOMAIN
from custom_components.better_cover.group import GroupController
from custom_components.better_cover.sensor import DesiredPositionSensor


def member(key, target, manual=False):
    return SimpleNamespace(
        entry=SimpleNamespace(entry_id=key),
        target=target,
        manual_mode=manual,
        position=100,
        enabled=True,
        forced_closed=False,
    )


def test_group_desired_position():
    left, right = member("left", 50), member("right", 50)
    hass = SimpleNamespace(data={DOMAIN: {"left": left, "right": right}})
    entry = SimpleNamespace(
        entry_id="group",
        data={"name": "Bedroom", "kind": "group", "members": ["left", "right"]},
        options={},
    )
    sensor = DesiredPositionSensor(GroupController(hass, entry))
    assert sensor.native_value == "50%"
    right.target = 75
    assert sensor.native_value == "Mixed"
    assert sensor.extra_state_attributes["member_targets"] == {"left": 50, "right": 75}
    assert sensor.extra_state_attributes["target_percent_open"] is None
    right.manual_mode = True
    right.forced_closed = True
    assert sensor.native_value == "Manual"
    assert sensor.extra_state_attributes["forced_close_active"]
    right.manual_mode = False
    right.target = None
    assert sensor.native_value is None
    del hass.data[DOMAIN]["right"]
    assert sensor.native_value is None
