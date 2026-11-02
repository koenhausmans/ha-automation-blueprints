# Airco heating blueprint plan

Status: planning only. No blueprint has been implemented. Open decisions are listed
below; recommendations are not yet confirmed requirements.

## Goal

Use the apartment's Haier airconditioning for scheduled comfort heating, with a
day-by-day weekly schedule and optional presence detection. Nest continues to
control the central heating (CV) independently and maintains the minimum temperature.

## Confirmed requirements

- Use the Haier airco through the installed
  [gvigroux/hon integration](https://github.com/gvigroux/hon).
- Configure heating periods independently for each day of the week.
- Provide configurable morning and evening temperature setpoints.
- Support heating throughout the day on Friday, when working from home.
- Turn off airco heating when nobody is home; do not use an airco setback temperature.
- Leave all Nest setpoints, schedules, and operating modes unchanged.
- Do not require the girlfriend to install the Nest app.
- The home router runs OpenWrt.

Nest and the airco remain independent. The CV may therefore heat alongside the
airco whenever Nest requests heat. This blueprint will not coordinate or prevent
that overlap.

## Proposed blueprint and setup

When implementation starts, add
`blueprints/climate/airco_heating_schedule.yaml` (proposed filename). Do not add a
placeholder blueprint as part of this plan.

Use standard Home Assistant climate actions rather than hOn-specific actions where
possible. Select the airco's `climate.*` entity in the blueprint. The installed entity
ID, integration version, temperature limits, and temperature step still need checking.

### Weekly schedule

Use Home Assistant's built-in Schedule helper, created separately and selected as
a blueprint input. Each active block carries a profile in its additional data:
`morning`, `daytime`, or `evening`. Configure the corresponding temperatures in the
blueprint. A separate daytime setpoint is a proposal, pending confirmation.

This keeps the weekly timetable editable in the Home Assistant UI without dozens
of weekday/time inputs in the blueprint.

Illustrative timetable only; no times have been agreed:

| Days | Morning | Daytime | Evening |
| --- | --- | --- | --- |
| Monday–Thursday | 06:30–08:30 | Off | 17:00–22:30 |
| Friday | 06:30–09:00 | 09:00–17:00 | 17:00–22:30 |
| Saturday–Sunday | Configure independently | Configure independently | Configure independently |

Friday's adjoining blocks keep heating enabled while changing the temperature at
profile boundaries. The automation must observe profile attribute changes, not
just schedule on/off transitions: adjoining blocks can leave the schedule `on`.

Heating enabled means the airco regulates to the target temperature. It does not
mean the compressor must run continuously.

### Presence detection

Proposed app-free approach:

1. Use the OpenWrt integration to create phone device trackers.
2. Associate each phone tracker with its owner's Home Assistant person entity.
3. Treat the apartment as occupied when either selected person is home.
4. Apply a configurable departure grace period to tolerate short Wi-Fi dropouts.
   A suggested starting value is 10–15 minutes, not an agreed default. Account for
   any delay already configured in the tracker so delays do not stack unexpectedly.
5. Offer a manual occupancy override for guests or phones with Wi-Fi disabled.

Neither the Nest app nor another phone app is required for router-based tracking.
Each phone needs a stable MAC address on the home Wi-Fi network. A fixed private
address is suitable; a rotating address can disrupt tracking. Phone-based presence
is imperfect: a phone left at home or disconnected from Wi-Fi can give the wrong
occupancy result. Configure tracking with both occupants' consent.

Home Assistant's OpenWrt (LuCI) integration supports local device tracking. The
alternative ubus integration specifically needs OpenWrt devices providing wireless
access points, not a router-only device. The actual Wi-Fi/access-point topology
still needs confirmation before choosing the setup instructions.

The standard Home Assistant Nest integration does not expose household Home/Away
as a presence entity. Do not infer occupancy from Nest Eco mode: it can also be
selected manually. If another existing integration exposes genuine occupancy, it
could be considered as an alternative optional presence source.

### Proposed operating rules

| Situation | Airco action |
| --- | --- |
| Scheduled block active and someone home | Select heat mode and apply the block's setpoint |
| Everyone away beyond the grace period | Turn off airco heating |
| Someone arrives during an active block | Resume heating at that block's setpoint |
| No scheduled block active | Turn off airco heating |
| Presence detection not configured | Follow the schedule alone |
| Home Assistant restarts | Re-evaluate the current schedule and occupancy |

Let the airco regulate temperature internally. Do not implement a separate loop
that repeatedly switches the compressor on and off.

Proposed manual-control behavior, pending confirmation:

- A manual temperature adjustment lasts until the next schedule block.
- A separate pause control suspends automatic heating. Its effect on an already
  running airco and its resume behavior must be defined before implementation.
- Define whether this heating blueprint should leave manually selected cooling,
  dry, and fan modes alone, especially outside the heating season.

## hOn integration findings

The upstream `master` implementation was inspected during planning; this is not
verification of the installed integration version or the apartment's device.

- It exposes a climate entity with `heat` and `off` modes and target-temperature
  control.
- To start heating, call `climate.set_hvac_mode` with `heat`, then call
  `climate.set_temperature` separately with the desired temperature.
- Do not rely on a combined mode-and-temperature `climate.set_temperature` call:
  the inspected implementation handles only temperature in that method.
- Do not use plain `climate.turn_on` to start heating. It uses a generic start
  command and can resume the previous mode rather than explicitly selecting heat.
- Use `climate.set_hvac_mode` with `off` to stop heating.
- The integration uses the hOn cloud. Commands depend on internet and cloud
  availability, and reported state can lag after commands. Avoid redundant writes
  and rapid retries; define bounded recovery behavior before implementation.
- Nest/CV remains an independent heating fallback, but the blueprint cannot
  guarantee that an airco off command succeeds during a cloud outage.

## Open decisions and information needed

1. Does OpenWrt provide the Wi-Fi, or are there separate access points? Which
   Home Assistant version is installed?
2. What is the airco's `climate.*` entity ID, installed hOn version, supported
   modes, temperature limits, and temperature step? Is there one indoor unit or
   more than one to control?
3. Should Friday daytime have a separate setpoint, or reuse morning/evening?
4. Confirm the proposed manual-adjustment and pause behavior.
5. Define handling for unavailable/unknown presence, invalid schedule profiles,
   and cloud command failures. Unknown presence must not silently count as a
   confirmed departure.
6. Define heating-season enablement and interaction with manually selected
   non-heating modes. The blueprint must not unexpectedly take over summer cooling.

Exact weekly times and temperature values can be entered during setup; they do
not need to be hard-coded in the blueprint.

## Implementation and validation outline

Once the open decisions are resolved:

1. Implement the climate blueprint on a dedicated branch and document its inputs,
   prerequisite helpers, import link, and setup in `README.md`.
2. Validate YAML using a loader that tolerates Home Assistant's `!input` tags.
3. Check templates in Home Assistant Developer Tools.
4. Exercise morning/evening transitions, adjoining Friday blocks, arrivals,
   departures, brief Wi-Fi dropouts, guest override, manual changes, pause/resume,
   restarts, invalid inputs, and cloud outages/recovery.
5. Verify Nest is never targeted and that unrelated airco modes are handled as
   agreed. Verify behavior on the actual Haier entity, not just against upstream
   integration source.
6. Review, commit, and open a PR against `master`. Publish a release for the new
   user-facing blueprint after merge.

## References

- [hOn integration](https://github.com/gvigroux/hon)
- [hOn climate implementation](https://github.com/gvigroux/hon/blob/master/custom_components/hon/climate.py)
- [Home Assistant Schedule helper](https://www.home-assistant.io/integrations/schedule/)
- [Home Assistant Person integration](https://www.home-assistant.io/integrations/person/)
- [OpenWrt (LuCI) integration](https://www.home-assistant.io/integrations/luci/)
- [OpenWrt (ubus) integration](https://www.home-assistant.io/integrations/ubus/)
- [Nest integration](https://www.home-assistant.io/integrations/nest/)
