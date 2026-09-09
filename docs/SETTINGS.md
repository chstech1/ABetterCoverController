# Better Cover: every device setting explained

This guide describes **v0.2.0**, using the exact labels on the Home Assistant device page. The defaults below are the integration's defaults, not a record of anyone's home configuration. Examples are illustrative.

Open **Settings → Devices & services → Devices → your Better Cover device**. Daily actions are under **Controls**, the reason for its behavior is under **Sensors**, and editable settings are under **Configuration**. Click an entity if you need its full control or attributes. Settings can also be added to a dashboard.

Contents:

- [Start here](#start-here)
- [Which rule wins?](#which-rule-wins)
- [Daily controls and Status](#daily-controls-and-status)
- [Configuration settings, A–Z](#configuration-settings)
- [Slat-only settings](#slat-only-settings)
- [Group settings](#group-settings)
- [Worked examples](#worked-examples)
- [Troubleshooting](#troubleshooting)

## Start here

**Every percentage means OPEN:** 0% = fully closed, 100% = fully open. Minimum and maximum refer to the amount of opening, not the physical height of the blind's top edge. For a tilt controller, they refer to slat opening.

**A position is a request; limits constrain the result.** A nighttime request of 0% with a minimum opening of 30% produces a target of 30%. It cannot fully close until the applicable minimum permits 0%.

**Edits save as soon as Home Assistant submits the value** (for a number, finish editing and press Enter or leave the field). There is no second Save settings button on the device page. Read the displayed value back to confirm it was accepted. An invalid edit displays an error and leaves the previous value in place. Changes can affect an enabled controller immediately; turn Automatic control off while making several related changes if you want to review them first.

For a first window:

1. Set **Hardware cover**, **Control channel**, and the correct **Device reports zero as open** setting.
2. Set normal **Minimum opening** / **Maximum opening**. Decide whether full nighttime closure must be allowed.
3. Select **Window contact sensor** and choose the window-open range if you have a contact.
4. Set **Window direction**, **Window height**, and **Sunlight reach into room** (or the slat dimensions for tilt).
5. Set day/night times and openings. Set **Morning reset** independently.
6. Add brightness, temperature, and occupancy sources only for the features you want. A threshold alone does not enable a feature without its source.
7. Inspect **Status** and its target, then turn on **Automatic control**.

Routine setting changes preserve a manual pause. Changing the occupancy sensor starts a fresh vacancy timer. Changing the hardware cover or control channel reloads the controller and preserves its saved pause; a reload starts vacancy timing fresh. You do not need to restart HA after routine edits.

## Which rule wins?

First, the controller decides whether it may move:

| Condition | Result |
|---|---|
| Automatic control is OFF | No automatic positioning, including automatic window-limit enforcement. Manual controls still work and are clamped. |
| Hardware cover or its position is unavailable | Wait for a valid position. |
| Manual pause is active | Hold the manual choice. Window-open limits can still correct an out-of-range position if their override switch is ON. |
| Automatic control is ON and no manual pause applies | Use the first matching row below. |

| Priority | Condition | Requested position |
|---|---|---|
| 1 | Outside the daytime schedule | **Nighttime privacy opening** |
| 2 | Room brightness has entered the dark state | **Daytime opening**, even if it is hot outside |
| 3 | Sun is below the horizon, or is 90° or more away from the outward window direction | **Daytime opening** |
| 4 | Direct sun; outside temperature is strictly above thermostat target + temperature difference | **Hot-weather opening** |
| 5 | Direct sun; outside temperature is strictly below thermostat target − temperature difference | **Daytime opening** |
| 6 | Direct sun, with neither temperature condition applying | Calculated sun-tracking position |

The requested position is then restricted to the **normal range**, or to the **window-open range** when the contact is open. The window-open range **replaces** the normal range; it does not intersect it. These ranges apply at night too.

A daytime calculation with missing sun data normally waits instead of using rows 3–6. The dark-room rule can still apply without sun data, and window clearance can still be corrected. Night scheduling does not need sun data.

Movement thresholds can delay or suppress a command even when Status shows a new target. Inputs trigger reevaluation, and a timer reevaluates every 30 seconds. Nighttime and morning reset are not guaranteed to command movement at the exact second shown on the clock.

## Daily controls and Status

### Automatic control

**Initial default: OFF.** ON enables automatic decisions. OFF leaves the blind where it is and prevents further automatic commands; it does not close, open, or issue a stop command to an already-moving motor. Manual cover commands remain usable while OFF.

Turning this switch ON also clears a manual pause and reevaluates the target. Its enabled state survives HA restarts. Morning reset, vacancy, and leaving home clear pauses but **do not turn an explicitly disabled controller on**.

### Cover / Slats

Use these controls for manual open, close, percentage, and supported stop actions. **Cover** controls raising/lowering; **Slats** controls tilt. Open requests 100%; close requests 0%; both obey the currently applicable limits. A manual action starts a pause so ordinary sun and schedule control will not immediately undo your choice.

The original hardware entity bypasses Better Cover's clamping. Direct HA commands targeting that original entity are detected as manual actions. Physical remote movement is inferred from reported position changes. There is a two-minute settling window after Better Cover commands a motor; physical changes during that window may not be recognized if the motor omits command context. Use the Better Cover entity when explicit manual-override behavior matters.

Stop is offered only for a supported channel. A window-limit correction may subsequently move the blind again if automatic control and the window-pause override are both on.

### Resume automatic control

Press to clear the manual pause **and enable Automatic control**, then recalculate. Resume bypasses the ordinary time-between-moves wait, but a target within **Minimum movement** of the current position may still produce no move. Duplicate commands for a target already being approached can also be suppressed.

### Status

This is an explanation, not a switch. Open it to inspect its attributes:

| Attribute | Meaning |
|---|---|
| `target_percent_open` | Current calculated, limit-adjusted target. It may be visible even while OFF or paused; it is not proof that a command was sent. |
| `current_percent_open` | Hardware position translated to Better Cover's percent-open convention. |
| `manual_paused_since` | When the last manual pause began; empty means no pause. |
| `room_empty_since` | When the controller began observing continuous vacancy. The pause-resume timer uses the later of this and the manual action. |
| `room_is_dark` | Whether the brightness thresholds currently classify the room as dark. |
| `window_open` | Whether the window-open range is in use, including a configured but unavailable contact. |
| `source_cover` | Original hardware cover controlled by this controller. |
| `group_members` | Controller identifiers for a group. |

Typical messages include **Automatic control off**, **Manual pause**, **Night schedule**, **Room is dark**, **No direct sun**, **Warmer outside · shading**, **Cooler outside · admitting sun**, **Sun tracking**, and **Sun tracking · slat tilt**. A **window-open limits** suffix means that range is active. **Waiting for sun data**, **Waiting for cover position**, or **Cover command failed; will retry** explains a missing input or unsuccessful command.

<a id="configuration-settings"></a>

## Configuration settings, A–Z

### Anyone-home sensor

**Default: Not configured.** Choose a `binary_sensor` whose **on** state means at least one person is home and **off** means nobody is home. It can display “Home/Away” in the UI, but its underlying binary states must have that meaning.

An OFF transition **after a manual action** clears that controller's manual pause. It does not itself request an open/closed position; normal time/light/temperature/sun rules take over. If the house was already empty when you moved the blind, that existing empty state does not immediately cancel the new pause. Unknown/unavailable is not treated as away.

`person` entities and `zone.home` cannot be selected directly here. Use an anyone-home binary-sensor helper if needed. This source is independent of **Room occupancy sensor**.

### Bright-again threshold

**Default: 200 lx. Range: 0–100,000 lx, steps of 1.** After the room has become dark, a brightness reading **at or above** this value ends the dark-room override and allows the other daytime rules to apply.

It must be greater than **Dark-room threshold**. With dark = 100 and bright-again = 200, a reading of 150 keeps whichever dark/bright state was already active. This gap helps prevent repeated changes near a single cutoff. Requires **Room brightness sensor**.

### Control channel

**Default: Raise / lower. Choices: Raise / lower, Slat tilt.** Choose the physical action that this controller should automate. The selected hardware entity must support percentage positioning for that channel.

If a blind supports both and you want both controlled, create one controller for lift and a second for tilt. Each has its own limits and settings. Selecting tilt changes which geometry fields are created. Tilt assumes a 90° range from vertical/closed at 0% to horizontal/open at 100%, after any inversion. It does not automatically calibrate motors with a 180° range.

### Dark-room threshold

**Default: 100 lx. Range: 0–100,000 lx, steps of 1.** A reading **at or below** this value sets the room to dark. During daytime, the controller requests **Daytime opening** to admit light. This takes priority over hot-weather shading and sun geometry, but not nighttime privacy or travel limits.

Requires **Room brightness sensor**. Raise this threshold if you want the dark-room override to start at a brighter reading; lower it to require a darker room. Keep it below **Bright-again threshold**. Indoor lights and the blind's own movement can affect a room lux sensor: this measures room brightness, not cloud cover directly.

### Daytime begins

**Default: 08:00.** The local HA time at which daytime rules become eligible. Daytime continues until **Nighttime privacy begins**, excluding that ending instant. Schedules may cross midnight, but their two start times cannot be identical.

This is not necessarily an “open fully” time: manual pause, darkness, temperature, sun, and limits still decide the result. It is separate from **Morning reset**. A pause can remain active when daytime begins if the reset is later.

### Daytime opening

**Default: 100%. Range: 0–100%, steps of 1.** The opening requested during daytime when the room is dark, the sun is not directly in front of the window, or outside is cooler than the thermostat target by more than the configured temperature difference.

It is **not the maximum sun-tracking position**. For example, Daytime opening = 70% does not prevent sun geometry from requesting 90%; use **Maximum opening** to cap all normal automatic positions. Night uses its separate privacy opening.

### Device reports zero as open

**Default: OFF.** Enable only when the original **Home Assistant hardware cover** reports 0% for physically open and 100% for physically closed. ON translates both reported positions and outgoing commands using `hardware percentage = 100 − percent open`.

All other Better Cover settings still mean percent open. For example, with inversion ON, a requested 30% opening sends 70 to the hardware. With inversion OFF it sends 30. Do not invert merely because the manufacturer's phone app uses reversed percentages; inspect the original HA entity. Some hardware integrations already normalize them.

### Hardware cover

**Required; no universal default.** Choose the original SmartWings, IKEA, or other `cover` entity that operates this blind. The dropdown uses HA entity IDs.

Do not choose a Better Cover virtual cover. Those are excluded to prevent controllers commanding each other in a loop. A hardware cover/channel combination may have only one Better Cover controller. Use a Better Cover group for shared control. Changing this source reloads the controller.

### Hot-weather opening

**Default: 0%. Range: 0–100%, steps of 1.** Requests this opening when direct sun reaches the window and outside temperature exceeds the thermostat target by **more than** the configured temperature difference.

Requires **Outside temperature sensor** and **Thermostat target source**. Nighttime and the dark-room override take priority. The applicable travel limits still apply. This is a fixed target, not an extra reduction from the calculated sun position: a setting of 60% requests 60%, even if sun tracking would have requested 30%.

### Maximum opening

**Default: 100%. Range: 0–100%, steps of 1.** The greatest permitted percent open when the normal range applies. For example, 80% prevents normal daytime or manual-open requests through Better Cover from exceeding 80%.

Must be at least **Minimum opening**. When the window-open range is active, its maximum replaces this one. A maximum is a cap, not a target the controller always tries to reach.

### Minimum movement

**Default: 5%. Range: 1–100%, steps of 1.** The minimum difference, in **percentage points**, between current position and target before an ordinary automatic command is worthwhile.

From a current 40%, target 44% is skipped with a 5% threshold; target 45% is eligible. It is not “5% of the current position.” Larger values reduce small movements. Correcting a position outside its allowed range uses a 1-point threshold instead. Manual percentage commands do not use this ordinary threshold.

### Minimum opening

**Default: 0%. Range: 0–100%, steps of 1.** The smallest permitted percent open when the normal range applies. For example, 30% stops normal automatic requests and Better Cover manual-close requests from going below 30% open.

**This also limits nighttime closure.** Nighttime privacy opening = 0% with Minimum opening = 30% produces 30%, not full closure. To allow full closure under normal conditions, this minimum must be 0%. When the window-open range is active, **Window-open minimum opening** replaces it.

### Minimum time between moves

**Default: 5 min. Range: 1–60 min, steps of 1.** Minimum elapsed time since the last successful Better Cover position command before an ordinary automatic move. It reduces motor activity as inputs change.

A separate, fixed two-minute motor-settling window also applies to ordinary automation, so selecting one minute does not guarantee one-minute movement. Manual commands and limit corrections bypass the ordinary interval; Resume/turning automation ON bypasses it too. Duplicate commands to the same target within the settling window can still be skipped. Nighttime schedule changes also use movement filtering.

### Morning reset

**Default: 08:00.** Clears a manual pause once this daily HA-local time has passed. The normal decision rules then determine the position. It does not itself request an opening or turn an OFF controller ON.

It does not have to match **Daytime begins**. If reset is 07:00 and daytime begins at 08:00, a resumed controller can use the nighttime position until 08:00. A missed reset is caught up after a restart. Changing this time can immediately clear an existing pause if the newly applicable reset is later than the manual action and has already passed.

### Nighttime privacy begins

**Default: 21:00.** Starts the nighttime rule, which lasts until **Daytime begins**. Night requests **Nighttime privacy opening** regardless of brightness and temperature.

Limits still apply. An active manual pause still holds your manual choice until a resume event; this setting does not force the controller out of manual pause. Automatic control must be ON. Timing and minimum-movement filters still apply to ordinary night commands.

### Nighttime privacy opening

**Default: 0%. Range: 0–100%, steps of 1.** Opening requested outside the daytime schedule. Zero requests full closure; 20 requests a 20% opening.

Both normal and window-open limits can prevent the requested closure. Check **Minimum opening** and **Window-open minimum opening** when a blind stays partly open at night. Brightness and temperature cannot override the night request, but a manual pause can prevent it from being commanded.

### Outside temperature sensor

**Default: Not configured.** Choose a numeric temperature `sensor` with a valid temperature unit such as °F or °C. This is an outdoor measurement, not the desired indoor temperature and not a weather entity.

Used with **Thermostat target source**. Temperatures are converted to HA's configured temperature unit before comparison. If either source is missing, unavailable, nonnumeric, or has an unsupported temperature unit, temperature rules are skipped and sun tracking can still run. Setting the two dropdowns one at a time is supported.

### Resume after room vacancy

**Default: 2 h. Range: 0.25–24 h, steps of 0.25 h.** How long the selected room occupancy sensor must continuously indicate empty before a manual pause can end. Requires **Room occupancy sensor**.

Timing begins at the later of the manual action and the start of observed vacancy. If a room has already been empty for three hours and you move the blind now, a two-hour setting requires two more hours. Occupied/unknown/unavailable resets the vacancy timer. HA restart, controller reload, or changing the occupancy source starts vacancy timing fresh. This is a resume trigger, not a rule that immediately closes blinds in empty rooms.

### Room brightness sensor

**Default: Not configured.** Choose a sensor whose numeric state is room illumination in **lux (lx)**. The controller reads the number as lux; it does not convert percentages or other light units.

Enables **Dark-room threshold** and **Bright-again threshold**. If omitted or unavailable, the dark-room override is inactive. New startup with a reading between the thresholds starts without a dark override; a later reading at/below the dark threshold enables it. After a sensor failure, a middle-of-the-gap reading likewise does not restore a previous dark state automatically.

### Room occupancy sensor

**Default: Not configured.** Choose a `binary_sensor` whose **on** means occupied and **off** means empty. It may display Detected/Clear or Occupied/Unoccupied; verify those underlying meanings.

Used only for the vacancy-based manual-resume trigger. A presence sensor can represent still occupants better than a motion sensor; with motion alone, “off” can mean no recent motion rather than an empty room. It does not choose a separate occupied/unoccupied blind position. **Anyone-home sensor** provides a separate house-wide resume trigger.

### Sunlight reach into room

**Lift only. Default: 0.5 m. Range: 0.01–20 m, steps of 0.01 m.** The horizontal distance sunlight is allowed to penetrate inward from the window plane in the simplified shade calculation. Use the same meter unit as **Window height**.

A smaller distance generally lowers the shade more to block low sunlight. A larger distance generally permits more opening. It does not represent the shade's travel distance. It is used only when the sun-tracking rule wins, not for fixed day/night/hot-weather targets.

Example: a 1.5 m covered height, 45° sun elevation, and sun directly in front of the window produce approximately 33% opening with a 0.5 m reach, or 67% with a 1 m reach, before limits. This simple geometry does not model furniture, trees, buildings, overhangs, or independent top-down shade movement.

### Temperature difference before reacting

**Default: 2 in HA's temperature unit. Range: 0–20, steps of 0.5.** The amount outside temperature must differ from the thermostat target before a hot/cool rule applies. The unit displayed beside this setting is the one used for the difference.

With an indoor target of 70°F and difference of 2°F:

| Outside reading | Eligible daytime behavior with direct sun and no dark-room override |
|---|---|
| Greater than 72°F | Hot-weather opening |
| Exactly 68°F through exactly 72°F | Sun tracking |
| Less than 68°F | Daytime opening |

The comparisons are strict: 72°F is not above 72°F. This is a comparison band around the target, not a remembered heating/cooling mode or a thermostat control. Better Cover never changes your thermostat's setting.

### Thermostat target source

**Default: Not configured.** Select your climate entity or a numeric sensor representing the **desired indoor temperature**. A climate entity supplies its target `temperature`, not its `current_temperature` room reading. A selected sensor supplies its own state as the desired target.

For a climate entity, the code uses `target_temp_high` only if the `temperature` attribute is absent. If `temperature` exists but is null/nonnumeric, the comparison is skipped; choose a target-temperature sensor if that is how your thermostat reports dual setpoints. Sensor units are converted; a sensor without a unit is assumed already in HA's temperature unit. This source and **Outside temperature sensor** must both yield valid values for temperature behavior.

### Window contact sensor

**Default: Not configured.** Choose the window's `binary_sensor`: **on = open**, **off = closed**. Open selects the window-open range; closed selects the normal range. A configured contact that is missing, unknown, or unavailable also selects the window-open range.

With no contact selected, window-open limits never activate. This is a contact input only: Better Cover moves the **blind/shade**, not the actual window or a window-opening motor. For two shades on one window, choose the same contact for each controller and set each shade's clearance limits separately.

### Window direction

**Default: 180°. Range: 0–359°, steps of 1.** The compass bearing you face when looking **out through the window**, perpendicular to the glass. North = 0°, east = 90°, south = 180°, west = 270°. This is a fixed orientation, not the sun's current direction.

The sun is treated as in front of the window when its elevation is above zero and its direction differs by less than 90° from this bearing. A 255° window faces mostly west, slightly south. Wrong orientation shifts the sun-tracking period to the wrong part of the day. HA supplies sun elevation and azimuth using its configured location; no separate sun dropdown is needed.

### Window height

**Lift only. Default: 1.5 m. Range: 0.01–20 m, steps of 0.01 m.** The height of the window area covered by the raising/lowering shade, in meters. Do not enter inches or centimeters directly: 150 cm is 1.5 m.

This converts an allowable uncovered height into percent open. For the same sun and reach, a taller window yields a smaller opening percentage. It assumes a shade lowering from the top and a reasonably linear percentage-to-opening relationship. Use your measured height rather than treating it as a general sensitivity adjustment.

### Window limits override manual pause

**Default: ON.** When a window-open range is active, Automatic control is ON, and the current opening is outside that range, the controller corrects it even during a manual pause.

It moves only to the nearest allowed boundary for this pause correction. For an opening of 20% and window range 60–100%, it requests 60%, not the full sun target. The manual pause remains active. OFF prevents this automatic correction during a pause; it does **not** disable window limits for new manual commands sent through Better Cover. Automatic control OFF disables all automatic window corrections regardless of this switch.

### Window-open maximum opening

**Default: 100%. Range: 0–100%, steps of 1.** The greatest permitted opening while the window-open range is active. It replaces **Maximum opening** and must be at least **Window-open minimum opening**.

For example, a normal maximum of 80% and window-open maximum of 100% allow more opening while the contact is open. This range also applies at night. It has no effect without a configured window contact.

### Window-open minimum opening

**Default: 50%. Range: 0–100%, steps of 1.** The smallest permitted opening while the window-open range is active. It replaces **Minimum opening**.

Use the opening needed for that shade to clear the open window; determine that from your actual hardware. For example, 60% prevents Better Cover requests below 60% while the window-open range applies. Setting this and the window-open maximum to the same percentage fixes all permitted requests at that opening. These are software command limits, not a physical motor interlock; original-hardware commands bypass them.

## Slat-only settings

These replace Window height and Sunlight reach into room for a Slat tilt controller. Lift-only hardware cannot use tilt just because a dropdown exists.

### Slat width

**Default: 25 mm. Range: 1–200 mm, steps of 0.5 mm.** Width across one slat from its front edge to back edge, not the full width of the window. Used with vertical slat spacing to calculate the most horizontal angle that still blocks a direct sun ray.

For otherwise identical geometry, wider slats can block a ray with less closing. Enter the physical measurement rather than adjusting it to compensate for an incorrectly calibrated motor range.

### Slat spacing

**Default: 20 mm. Range: 1–200 mm, steps of 0.5 mm.** Vertical pitch between corresponding points/centers of adjacent slats, not just the visible gap between their edges. Must not exceed Slat width in this model.

Increasing the pitch generally requires more closing to block the same ray. The calculation assumes a linear mapping between 0% vertical/closed and 100% horizontal/open. Reversing that range is supported by inversion; a full 180° tilt range with horizontal in the middle requires a calibrated template cover instead.

## Group settings

A group has shared daily controls and membership configuration. It does not replace its members' geometry, sensors, schedules, inversion, or limits.

### Add group member

Select an existing Better Cover blind controller to add it immediately. The dropdown returns to **Choose a member**. A member can be a lift or tilt controller; other Better Cover groups are not selectable. Add the individual blind first if it does not appear.

Adding membership does not move the blind or force its Automatic control state to match other members. Subsequent group commands include it.

### Remove group member

Select a member to remove it immediately. This removes membership only; it does not delete the member device or its settings. A group must retain at least one member. The dropdown returns to **Choose a member** after the action.

### How the group's daily controls behave

- **Cover:** an open/close/percentage request goes to every member through that member's limits and starts a manual pause on each. Different members can therefore finish at different positions.
- **Automatic control:** ON enables and resumes all members; OFF disables automatic control on all members. The group switch reads ON only if every loaded member is enabled, so OFF may mean a mixture of enabled/disabled members.
- **Resume automatic control:** clears all members' pauses and enables each member.
- **Status:** summarizes unavailable members, manual pauses, or automatic-control state. Inspect individual members for their detailed targets and reasons.

The group's cover percentage averages normalized member openings. In a mixed group this averages lift opening for some members and slat opening for others; it is not a measurement of one physical window. Automatic mode lets each member calculate independently. Group Status does not calculate its own sun target; its target/source attributes can be empty even while members are working.

## Worked examples

### Allow full nighttime privacy

Use normal Minimum opening = 0%, Maximum opening = 100%, Nighttime privacy opening = 0%, and your desired night start time. With automation ON and no manual pause, night requests full closure. If the window is open and its minimum is 60%, the night target becomes 60% until the normal range returns.

### Keep an open window clear

Choose the contact. Set window-open minimum = 60%, maximum = 100%, and enable Window limits override manual pause. With automation ON, opening the window while the blind is at 20% causes a correction to at least 60%. If it is already within 60–100% during a manual pause, the controller holds it there.

### Open a dark room but shade a hot afternoon

Choose a lux sensor, dark threshold = 100 lx, bright-again = 200 lx, Daytime opening = 100%, a valid outside sensor and thermostat target, temperature difference = 2°F, and Hot-weather opening = 0%.

At 50 lx in daytime, the dark-room rule requests 100%, even if outside is 90°F. After brightness reaches 200 lx, direct sun plus 90°F outside versus a 70°F target requests the hot-weather position. If outside is 50°F instead, direct sun requests the daytime position. At night the privacy opening takes priority. Limits apply to every result.

### Resume after manual adjustment

With automation ON, manually move the Better Cover entity. It enters Manual pause. It resumes on the first applicable event: everyone leaves after that move, the room remains empty for the configured duration after that move, Morning reset passes, or you press Resume. Nighttime by itself is not a resume event.

## Troubleshooting

| What you see | What to check |
|---|---|
| No automatic movement | Automatic control must be ON; inspect Status, current position, and pause attributes. |
| A target is shown but the blind does not move | A target is calculated even when OFF or paused. Also check minimum movement, interval, two-minute settling, and hardware availability. |
| Never fully closes at night | Check the active minimum opening and whether a manual pause is still active. |
| Temperature seems ignored | Both sources must be numeric/valid; compare against the desired target, not the room reading. Dark-room, no-direct-sun, and nighttime rules take priority. |
| Brightness thresholds do nothing | Choose a numeric lux sensor. Middle-of-the-gap readings keep the existing state, not necessarily “dark.” |
| Window limits do nothing | Select the correct contact. New automatic corrections need automation ON; corrections during a pause also need the override switch ON. |
| Window-open limits apply while the window is closed | Check whether the configured contact is missing/unavailable or has reversed on/off meaning. |
| Move direction or displayed percentage is reversed | Inspect the original HA cover and verify Device reports zero as open. |
| Changing a minimum/maximum produces an error | Change the opposite boundary first so minimum never exceeds maximum. The same relationship applies to slat dimensions and lux thresholds. |
| Room still occupied when automation resumes | Verify the room sensor represents occupancy, not merely a short motion-clear timeout. Also check whether the house-away or morning-reset trigger fired. |
| Some group members do not match | Limits, inversion, and automatic rules are per member. Check each member's Status. |

Implementation references: [settings and validation](../custom_components/better_cover/settings.py), [defaults](../custom_components/better_cover/const.py), [decision rules](../custom_components/better_cover/logic.py), [movement and resume behavior](../custom_components/better_cover/controller.py), [group behavior](../custom_components/better_cover/group.py). These links are for verifying behavior; normal setup uses the device controls described above.
