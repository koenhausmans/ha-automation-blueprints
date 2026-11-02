# Automation Blueprints (Home Assistant)

A set of Home Assistant automation blueprints. The two lighting blueprints share the same
sun-elevation–based brightness engine (sine curve, separate morning/evening minimums,
optional auto-scaling to today's peak sun); the third is a standalone appliance notifier:

1. **Motion Light (multi-sensor)** — motion-activated lights for multiple sensors per
   room, with a cancellable off-delay, periodic brightness refresh while occupied, and
   optional manual-override protection.
2. **Switch Light + Scenes** — the same kind of lights driven by a physical button
   (Shelly) or dimmer (Philips Hue / Zigbee2MQTT): single press toggles, double / triple
   press cycle through scenes, and the Hue up / down keys step brightness.
3. **Appliance done notifier** — watches a power sensor and sends a repeating,
   acknowledgeable notification when a washing machine (or dishwasher / dryer) finishes
   its cycle.

## Repository layout

```
.
├── AGENTS.md                        # guidance for AI agents
├── LICENSE
├── README.md
└── blueprints/
    ├── lighting/
    │   ├── motion_light_multisensor.yaml
    │   └── switch_light_scenes.yaml
    └── appliances/
        └── washing_machine_done_notifier.yaml
```

Blueprints are grouped by purpose, not by trigger: motion and switch control both
belong under lighting. All current blueprints are automations, so there is no separate
`automation/` level. Future airco control will go under `blueprints/climate/` when added.

The repository lives at
[github.com/koenhausmans/ha-automation-blueprints](https://github.com/koenhausmans/ha-automation-blueprints).

---

## Blueprint 1 — Motion Light (multi-sensor)

Turns light(s) ON when ANY selected motion sensor detects motion, and OFF (with a 1s
fade) only once ALL of them have been clear for an optional delay. New motion cancels the
pending off. While occupied, brightness is refreshed on a timer — but only on lights that
are already on, and (with the optional helper) both timer refreshes and motion
re-triggers leave lights you haven't manually changed alone.

### Install (one-click import)

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fkoenhausmans%2Fha-automation-blueprints%2Fmaster%2Fblueprints%2Flighting%2Fmotion_light_multisensor.yaml)

Or manually: **Settings → Automations & Scenes → Blueprints → Import Blueprint**, and
paste this raw URL:

```
https://raw.githubusercontent.com/koenhausmans/ha-automation-blueprints/master/blueprints/lighting/motion_light_multisensor.yaml
```

### Requirements

- A `sun.sun` entity (default in HA).
- For per-room manual-override protection: one `input_number` helper per room.

---

## Blueprint 2 — Switch Light + Scenes

Drives the same lights from a physical button instead of motion. Two hardware families
are supported, and you can use either or both (leave the other device empty):

| Press | Shelly (`single_push` button) | Hue / Zigbee2MQTT dimmer (`action`) |
|---|---|---|
| Single / ON | **Toggle** — off → on at sun-based brightness; on → off | `on_press` → on at sun-based brightness |
| Double | Next scene: advance the input_select, then activate that scene | `on_press` ×2 → next scene *(needs multi-press helper)* |
| Triple | Advance two scenes, then activate the result | `on_press` ×3 → two scenes forward *(needs multi-press helper)* |
| Off | — | `off_press` → off |
| Up / Down | — | `up_press` / `down_press` → step brightness ±step% |

Whenever the lights are turned **off** (Shelly toggle-off or Hue `off_press`), the scene
`input_select` is reset to its **first** option.

- **The Shelly cycles scenes natively** (a single-button Shelly exposes single/double/triple
  push). **The Hue ON key cycles scenes via _virtual_ multi-press** — the dimmer has no
  native double/triple, so presses are counted in software. This is **opt-in**: it only
  activates when you assign the multi-press `input_text` helper below. Leave the helper
  empty and the Hue ON key fires a single press instantly, exactly as before.
- **Multi-press latency:** when the helper is configured, a single and a double ON press
  act only after the configured max-delay window (default 500 ms), since the automation
  must wait to see whether more presses follow. A triple fires immediately on the third
  press. The Shelly is unaffected (its multi-press is native).
- **Brightness stepping is Hue-only** (it has dedicated up/down keys). This mirrors the
  hardware.
- **Sun-tracking refresh while on.** When the lights are on, brightness is re-applied on a
  timer (`brightness_update_interval`, default every 15 min) so it follows the sun through
  the evening. With the optional `input_number` helper assigned, the refresh skips lights
  you've **manually dimmed** (Hue up/down) and lights set by an **active scene**, only
  touching those still at the last automatic value (within `override_tolerance`). Leave the
  helper empty and the refresh repaints every light that is on.
- The scene `input_select`'s options must be scene **entity_ids** (e.g.
  `scene.bedroom_relax`). Cycling selects the next option, then calls `scene.turn_on` on
  that value with the configured `scene_transition` fade (default 1 s; set 0 for an
  instant switch).
- **`shelly_button` subtype gotcha:** the push event's button identifier varies by model.
  Single-channel Shellys are usually `button1`; some report `button`. Set the input to
  match what your device exposes.

### Install (one-click import)

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fkoenhausmans%2Fha-automation-blueprints%2Fmaster%2Fblueprints%2Flighting%2Fswitch_light_scenes.yaml)

Or manually paste this raw URL into the Import Blueprint dialog:

```
https://raw.githubusercontent.com/koenhausmans/ha-automation-blueprints/master/blueprints/lighting/switch_light_scenes.yaml
```

### Requirements

- A `sun.sun` entity (default in HA).
- An `input_select` helper whose options are scene entity_ids (e.g.
  `input_select.bedroom_scene_entities`).
- A Shelly button and/or a Hue (MQTT / Zigbee2MQTT) dimmer device.
- *(Optional, for Hue scene cycling)* an `input_text` helper — **one per automation
  instance** — assigned to the multi-press helper input. It stores the last ON event so
  double/triple presses can be detected. Leave it empty to keep the Hue ON key instant
  (single press only).
- *(Optional, for the sun-tracking refresh's manual-override & scene protection)* an
  `input_number` helper — **one per automation instance** — assigned to the
  last-auto-brightness helper input. It stores the last automatic brightness so the timed
  refresh leaves manually-dimmed and scene-lit lights alone. Leave it empty to refresh
  every light that is on.

---

## Blueprint 3 — Appliance done notifier

Watches a power sensor in front of an appliance (washing machine, dishwasher, dryer) and
notifies you when its cycle finishes. A cycle is detected only when the power first rises
above a **running** threshold and then drops below an **idle** threshold, so an idle dip or
a Home Assistant restart never raises a false alarm. Use a **5-minute mean** power sensor
(a statistics sensor) so brief draw fluctuations mid-cycle don't read as "done" — for a
washing machine the idle mean is typically a couple of watts.

The notification is **sticky** and carries an **Acknowledge** button, and **re-popups every
20 minutes** (configurable) until you tap it. Tapping Acknowledge on the phone stops the
loop and clears the card. If a new cycle starts while an alert is still looping, the loop is
cancelled and re-armed automatically (`mode: restart`).

- **The phone target must be a Home Assistant Companion app service** (e.g.
  `notify.mobile_app_pixel`). Only the Companion app emits the
  `mobile_app_notification_action` event that the Acknowledge button uses to stop the loop.
  To find yours, open **Developer Tools → Actions** and type `notify.mobile_app` — it
  autocompletes one service per phone, named after the device you set when installing the
  Companion app (e.g. `notify.mobile_app_koen_iphone`, `notify.mobile_app_galaxy_s24`).
  Paste that value into the **Phone notify service** input. It must be a `mobile_app_*`
  service — WhatsApp, `persistent_notification`, and laptop services can't acknowledge and
  belong in **Extra targets** below.
- **Extra targets** (one notify service per line) mirror the text but can't acknowledge —
  a laptop Companion service, `notify.persistent_notification`, or a **WhatsApp** bridge.
  WhatsApp-to-self works via a delivery-only bridge such as **CallMeBot** (free) or
  **Twilio** exposed as a `notify` service; it has no Acknowledge button, so keep the phone
  Companion app as the primary target.
- Set the **running threshold** comfortably above the **idle threshold**.

### Install (one-click import)

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fkoenhausmans%2Fha-automation-blueprints%2Fmaster%2Fblueprints%2Fappliances%2Fwashing_machine_done_notifier.yaml)

Or manually paste this raw URL into the Import Blueprint dialog:

```
https://raw.githubusercontent.com/koenhausmans/ha-automation-blueprints/master/blueprints/appliances/washing_machine_done_notifier.yaml
```

### Requirements

- A power sensor for the appliance, ideally a **5-minute mean** statistics sensor.
- One **`input_boolean`** helper (Settings → Devices & Services → Helpers → Toggle),
  assigned to the cycle-in-progress input. It remembers a cycle is running.
- A Home Assistant **Companion app** notify service for the phone (the Acknowledge target).
  Find it under **Developer Tools → Actions** by typing `notify.mobile_app` — pick the
  entry for your phone (e.g. `notify.mobile_app_pixel`).
- *(Optional)* any additional `notify.*` services to mirror the message to.

---

## How the sun-based brightness (elevation) system works

Both blueprints compute a turn-on brightness from the sun's current elevation, so the
lights are dim around dawn/dusk and brighter at midday. The math (see the
`target_brightness` template in either YAML):

1. **Read the sun.** Take `sun.sun`'s `elevation`, and its `rising` attribute to decide
   *morning vs evening*. The minimum brightness and the low-elevation threshold are split
   on this — morning and evening can ramp differently
   (`brightness_min_morning` / `brightness_min_evening`,
   `elevation_low_morning` / `elevation_low_evening`).
2. **Normalize.** `frac` is where the current elevation sits within
   `[elevation_low, elevation_high]`, clamped to `0…1`. Below `elevation_low` → `0`
   (minimum brightness); at/above `elevation_high` → `1` (maximum brightness).
3. **Smooth.** A cosine ease — `factor = (1 − cos(frac · π)) / 2` — turns the linear
   fraction into a soft S-curve so brightness eases in and out rather than ramping
   linearly.
4. **Scale.** `brightness = brightness_min + (brightness_max − brightness_min) · factor`,
   rounded and clamped to `1…100 %`.

**Optional: sun-based color temperature.** Enable `dynamic_color` and the lights' color
temperature follows the *same* `factor` curve as brightness — warm when the sun is low,
cool at peak sun — via `color_temp = warm_k + (cool_k − warm_k) · factor`. It's applied on
the same turn-on and timed-refresh as brightness, so color and brightness track together.
This is **opt-in** (default off) and only affects lights that support color temperature;
scene activations and the Hue up/down brightness keys are left untouched.

**Which setting controls what:**

| Setting | Controls |
|---|---|
| `brightness_min_morning` / `brightness_min_evening` | Brightness floor at/below `elevation_low` |
| `brightness_max` | Brightness ceiling at/above `elevation_high` |
| `elevation_low_morning` / `elevation_low_evening` | Sun angle where the ramp *starts* |
| `elevation_high` | Sun angle where the ramp *reaches max* (fixed mode) |
| `auto_elevation_high` | If on, sets the high angle to today's solar-noon elevation (`90 − \|latitude − declination\|`) so midday is full brightness year-round; `elevation_high` is then ignored |
| `dynamic_brightness` / `fixed_brightness` | Turn the whole sun engine off and use a flat brightness instead |
| `dynamic_color` | If on, color temperature also follows the sun (same curve as brightness); off by default |
| `color_temp_warm` / `color_temp_cool` | Color temperature (K) at low sun / high sun — the warm and cool ends of the curve |

### Tuning `elevation_high`

Worth tuning: **`elevation_high`**. Peak sun is very seasonal — in the Netherlands /
Central Europe solar noon is roughly **60° midsummer** but only **~14° midwinter**. With
the default `elevation_high: 40`, a winter noon only reaches `frac ≈ 0.35`, so the light
stays fairly dim even at midday — which may be exactly what you want (dark days → softer
light), or not. For full midday brightness every day year-round, drop `elevation_high` to
around **15** (or enable **auto-scale**, which tracks it for you). The `elevation_low`
default of `0°` means the ramp tracks actual daylight; set it to **−6** to start
brightening during civil twilight.

---

## Optional: update notifications

To get "new version available" notifications for these blueprints, use the
[Blueprints Updater](https://github.com/luuquangvu/blueprints-updater) integration:

1. **Install it through HACS.** Search for *Blueprints Updater*. If it isn't in the
   default store, add `https://github.com/luuquangvu/blueprints-updater` as a custom
   repository with category **Integration**, then download it and restart Home
   Assistant.
2. **Add the integration:** **Settings → Devices & Services → Add Integration →
   Blueprints Updater**, and pick your update options (auto-update, interval, etc.).

No URL needs to be entered manually: the integration automatically detects any blueprint
that carries a `source_url` in its metadata, which Home Assistant records for you when you
import a blueprint from a raw URL above. Detected updates show up as native `update`
entities.

> **Migration from previous URLs:** Home Assistant keys an imported blueprint by its
> `source_url`. The repository is now `ha-automation-blueprints`, previously
> `ha-smart-lighting-blueprints` and originally `ha-motion-light-multisensor`.
> Blueprints have also moved from the repository root into `blueprints/lighting/`
> and `blueprints/appliances/`. If you imported from either previous repository URL
> or a root-level file in the current repository, importing from the links above is
> treated as a *new* blueprint, not an update. Re-import each
> affected blueprint once, point existing automations at the new copy, then remove
> the old copy.

## Versioning

Version = the GitHub release tag, e.g. `v0.2.0`:

```bash
git tag v0.2.0
git push --tags
```

Then publish it as a Release on GitHub.
