# Better Cover

A small Home Assistant custom integration for existing SmartWings, IKEA, and other covers that support percentage positioning. It controls shades and slats using sun direction, time of day, room brightness, and outside temperature. Every blind has its own settings; groups provide shared controls.

No YAML automation is needed. Initial setup is two screens. Extra settings live in a menu so you can configure only what you use.

## Install with HACS

1. Open **HACS → ⋮ → Custom repositories**.
2. Enter **https://github.com/chstech1/ABetterCoverController** and select type **Integration**.
3. Add the repository, find **Better Cover** in HACS, and download it.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration → Better Cover**.
6. Add your first blind, then enable its **Automatic control** switch when ready.

[Open this repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=chstech1&repository=ABetterCoverController&category=integration)

Future tagged releases appear as updates in HACS. This is a custom repository, not a listing in the default HACS catalog.

## Manual install

1. Download `better-cover-0.1.1.zip` from [Releases](https://github.com/chstech1/ABetterCoverController/releases), or build it locally and extract it.
2. Copy the included `custom_components/better_cover` folder into your Home Assistant configuration folder, producing `/config/custom_components/better_cover/manifest.json`.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Better Cover**.
5. Select **Add a blind or shade**, choose the original hardware cover, and select **Raise / lower** or **Slat tilt**.
6. Enter the direction the window faces and its measurements. Select **Save settings**, or customize limits and sensors first.
7. Check the new **Status** sensor's target. Turn on **Automatic control** when ready.

The new controller starts with automatic movement OFF. After you turn it on, its enabled state and manual pause survive restarts. Disable any existing Adaptive Cover or other automatic positioning for the same cover to avoid conflicting commands.

Tested with Home Assistant **2026.2.3 / Python 3.13**. Hardware behavior still needs verification on your installation.

## Change settings after setup

Open **Settings → Devices & services → Integrations → Better Cover**. Find the blind or group you want to edit and select **Configure** (the gear icon). Choose a settings section, submit the changes, then select **Save settings** from the menu.

The cover, automatic-control switch, resume button, and status sensor are daily controls. They do not replace the integration's configuration screen.

If you installed v0.1.0, update to v0.1.1 or later in HACS and restart Home Assistant. The initial release mistakenly classified Better Cover as a helper. The update moves it to Integrations while preserving your existing entries and settings; do not delete and recreate them.

## Daily controls

Each controller creates four entities:

| Control | What it does |
|---|---|
| Cover / Slats | Open, close, or set a percentage manually; honors limits and pauses automation |
| Automatic control | ON enables automation; OFF stops automatic commands until you turn it on |
| Resume automatic control | Clears the manual pause and turns automation on immediately |
| Status | Shows the current reason and attributes including target, current opening, pause, and window state |

Use the new Cover / Slats entity in dashboards and automations. The original hardware cover remains available, but direct hardware commands bypass this integration's clamping. Direct entity-targeted HA cover commands are detected as manual actions, and physical moves are detected from position reports when possible.

## Percentages and limits

All settings mean **percent open**: 0 is fully closed, 100 is fully open. Enable **This device reports 0% as fully open** only if the original Home Assistant entity actually reports the opposite. Do not invert simply because the manufacturer's app uses a different convention.

Each controller has a normal minimum/maximum and a separate window-open minimum/maximum. The window-open range **replaces** the normal range. For example, normal 0–80 and window-open 60–100 lets the shade close to 0 normally but keeps it at least 60% open when the contact is on.

A missing or unavailable configured contact uses the window-open range. By default this range is enforced during manual pauses, moving only as far as needed to enter the allowed range. Turning **Automatic control OFF** disables automatic enforcement too. This is software positioning, not a motor interlock: commands issued directly to hardware can still move outside these limits before the controller detects the move.

For tilt controllers these are slat-opening limits, not shade-height limits. If a blind has both lift and tilt, add it twice with different control channels and configure its lift controller for physical window clearance.

## The positioning rules

When automatic control is on and not manually paused:

1. **Night schedule:** use the privacy position, regardless of temperature or brightness.
2. **Dark room:** use the daytime opening to admit light.
3. **No direct sun on this window:** use the daytime position.
4. **Warmer outside than the thermostat target:** use the hot-weather shade position.
5. **Cooler outside than the thermostat target:** use the daytime opening to admit sunlight.
6. **Otherwise:** track the sun.

The applicable normal/window-open range clamps the result. By default, night is 21:00–08:00, daytime opening is 100%, night opening is 0%, and moves smaller than 5% or more frequent than five minutes are skipped. A window limit can bypass these movement thresholds. Schedules may cross midnight and use Home Assistant's time zone.

Temperature compares an outside sensor with a climate entity's target temperature, or a sensor containing your desired indoor temperature. For dual-setpoint thermostats it uses the upper target if a single target is absent. Fahrenheit and Celsius are converted to Home Assistant's units; the configurable deadband uses those units. Temperature rules apply when direct sun hits the window. Night privacy wins over these rules. A manual pause still holds your manual choice overnight until a resume event.

Brightness uses lux, with separate dark and bright-again thresholds (defaults 100 and 200). This reduces switching near a cutoff, but indoor lights and the blinds themselves affect indoor lux. Tune thresholds and sensor placement for each room. Missing brightness disables the dark-room override; missing temperature falls back to sun tracking. Missing sun data holds the current position during the day, except that dark-room opening and window clearance can still apply. Night scheduling does not need sun data.

## Manual control resumes when…

A manual move pauses normal automatic positioning. Any of these clears the pause:

- Your anyone-home binary sensor changes to **off** after the manual move.
- The room occupancy sensor stays **off** for two hours (configurable). The timer counts from the later of vacancy or the manual move.
- The configurable morning reset time passes (default 08:00).
- You press **Resume automatic control** or turn Automatic control on.

Sensors are optional and chosen separately for every controller. Unknown occupancy resets the vacancy timer; restarts start that timer fresh because vacancy during downtime cannot be confirmed. Manual overrides themselves are saved. The morning reset catches up if HA was offline when it passed. None of these triggers turns an explicitly disabled controller back on.

For home presence, choose a binary sensor where **on means someone is home**. If you use people or `zone.home`, create a Template binary-sensor helper with state `{{ states('zone.home') | int(0) > 0 }}` and an availability template `{{ is_number(states('zone.home')) }}`. A room sensor must mean **on = occupied**.

Some motors omit command context and send intermediate position reports. The controller allows a two-minute movement window to avoid treating its own movement as manual. Physical remote movement during this window may not be detected; using the new Cover / Slats control gives explicit override behavior. Commands targeted indirectly through HA device/area groups rely on reported movement for detection.

## Groups

Add another Better Cover integration and choose **Group existing blinds**. Choose a name and members. A group may mix different windows, brands, direction conventions, and lift/tilt controllers.

- Group open, close, or percentage commands act on every member through that member's limits and start manual pauses.
- Group Automatic control toggles every member; group Resume clears every member's pause.
- In automatic mode each member continues tracking its own window and sensors. Automatic mode does not force all positions to be identical.
- The group slider is the average normalized opening. Members may reach different positions because of their limits. In mixed lift/tilt groups it expresses each member's controlled channel.
- The group is unavailable if a member is missing/unavailable. If a member command fails, the other members are still attempted and HA reports the partial failure.

For a SmartWings shade plus an IKEA blackout blind on one window, configure each separately using the same window contact, then add both to a group. Their limits, night positions, and inversion can differ.

## Sun measurements

Window direction is outward-facing: north 0°, east 90°, south 180°, west 270°. The HA Sun integration supplies sun position from your configured location.

For a shade lowering from the top, enter the covered window height and how far sunlight may reach into the room, in meters. The uncovered height is calculated as `depth × tan(sun elevation) / cos(sun azimuth − window direction)`. Low direct sun lowers the shade more; high sun allows more opening. Top-down/bottom-up shades and projecting awnings require different geometry and are not supported by this calculation.

For slats, enter width and vertical spacing in millimeters. The tilt calculation chooses the most horizontal slat angle that blocks a direct ray, using the sun's profile angle. It assumes 0% means vertical/closed and 100% means horizontal/open, with a linear 90° tilt range. Inversion handles a reversed range, but full 180° motors with the horizontal position in the middle need a separate calibrated template cover. Do not select tilt for a device that only raises/lowers.

Sun geometry assumes an unobstructed window. It does not model trees, overhangs, or neighboring buildings.

## Development

```sh
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/ruff check custom_components tests
python3 scripts/package.py
```

Tests cover geometry, privacy priority, temperature conversion, manual reset events, window limits, inversion, tilt commands, grouping, persisted pauses, and HA's actual config/options/setup/unload flows. No hardware is operated by the tests.

Inspired by [Adaptive Cover](https://github.com/basbruss/adaptive-cover). This implementation is written independently. HA's [cover entity contract](https://developers.home-assistant.io/docs/core/entity/cover/) defines its normalized percentages; its [options flow API](https://developers.home-assistant.io/docs/core/integration/options_flow/) is used for editable settings.
