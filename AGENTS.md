# AGENTS.md

Guidance for AI agents working in this repository.

## Project

Three Home Assistant **automation blueprints**. There is no application code, no build
step, and no test framework — the deliverable is the YAML files plus their README. The two
lighting blueprints share one sun-elevation–based brightness engine; the notifier is
standalone.

- `motion_light_multisensor.yaml` — multi-sensor motion lighting.
- `switch_light_scenes.yaml` — button/switch-driven lighting (Shelly + Hue/Z2M) with
  scene cycling.
- `washing_machine_done_notifier.yaml` — repeating, acknowledgeable "appliance done"
  notification driven by a power sensor (no sun engine).

## Repository structure

```
.
├── AGENTS.md
├── README.md
├── motion_light_multisensor.yaml      # Blueprint 1 – motion-driven
├── switch_light_scenes.yaml           # Blueprint 2 – button/switch-driven
└── washing_machine_done_notifier.yaml # Blueprint 3 – appliance-done notifier
```

Do not add `hacs.json` or a `custom_components/` tree unless the task is explicitly
to wrap this blueprint in a custom integration. HACS has **no blueprint category**,
so a bare blueprint repo is installed via Home Assistant's native blueprint import,
not HACS.

## Branch & PR workflow (AI changes)

AI-generated changes are **never committed directly to `master`**. Every change lands
through a pull request, mirroring the existing history (PRs #1, #2, …).

1. **Branch off `master`.** Create a dedicated feature branch with a descriptive
   kebab-case name (e.g. `scene-transition-time`, `hue-virtual-multipress`). Keep one
   self-contained change per branch — do not pile unrelated edits onto an open branch.
2. **Validate before committing** (see "Validating a change" below) — there is no CI, so
   the structure / template / behaviour checks are the only safety net.
3. **Commit** in the repo's style: an imperative subject line (`Add …`, `Fix …`), a body
   explaining *why* with bullets for the notable points, and a
   `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.
4. **Keep scratch files out of commits.** `TODO.md` and similar local notes stay
   untracked — do not add them to a PR.
5. **Push and open a PR against `master`.** Merging is done via the GitHub PR (the history
   uses merge commits), not by pushing to `master` directly.

## Validating a change

There is no CI. Before committing an edit to the blueprint:

1. **Structure check.** Standard YAML linters choke on Home Assistant's custom
   `!input` tag. Validate structure with a loader that ignores unknown `!` tags (run for
   each blueprint you touched):
   ```bash
   python3 -c "import yaml; \
   yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); \
   yaml.load(open('motion_light_multisensor.yaml'), Loader=yaml.SafeLoader); \
   print('ok')"
   ```
2. **Template check.** Paste the `target_brightness` (and `tick_targets`) Jinja into
   Home Assistant → Developer Tools → Template and confirm it renders a number / a
   list of entity_ids before trusting it.
3. **Behavior check.** Create an automation from the blueprint and exercise: single
   sensor on/off, multiple sensors (off only when ALL clear), re-entry during the
   off window, and a manual brightness change followed by a tick.

## Critical invariants — do NOT break these

These encode bugs that were deliberately engineered away. "Simplifying" any of them
reintroduces a real failure.

### Shared (both blueprints)

- **Sun-based brightness** (`target_brightness` template) is duplicated verbatim in both
  YAML files. Keep them in sync — change one, change the other. **Morning vs evening** is
  decided by `sun.sun`'s `rising` attribute; both the minimum brightness and the
  low-elevation threshold are split on it. The **auto-scaled high threshold** uses
  `90 - |latitude - declination|` from `zone.home` latitude and day-of-year; when it is
  enabled, low thresholds must stay at/below 0° or the elevation span collapses in winter
  and brightness pins to min.
- **Sun-based color temperature** (`target_color_temp` template) is likewise duplicated
  verbatim in both files — keep it in sync with `target_brightness`. It deliberately reuses
  the *same* elevation→`factor` math (warm at low sun, cool at high sun:
  `warm_k + (cool_k - warm_k) * factor`) so color and brightness track one curve. It is
  injected — only when the opt-in `dynamic_color` is on — into exactly the `light.turn_on`
  calls that set `brightness_pct` (motion / single-press turn-on and the timed tick), by
  templating the whole `data:` block and `combine`-ing in `color_temp_kelvin`. **Never** add
  color to `scene.turn_on` (scenes own their color) or to the Hue `brightness_step_pct`
  up/down keys (manual adjustments).

### `switch_light_scenes.yaml`

- **Triggers are keyed by `id`, not by order.** The `choose:` branches dispatch on
  `trigger.id` (`toggle`, `light_on`, `light_off`, `scene_next`, `scene_next2`,
  `bright_up`, `bright_down`). Keep ids and branches aligned.
- **Shelly single push is a toggle; Hue ON/OFF are dedicated.** `single_push` checks
  whether any light is on and turns all off (else on). Hue `on_press` always turns on,
  `off_press` always turns off — do not collapse them into a toggle.
- **Every off-path resets the scene `input_select` to its first option**
  (`input_select.select_first`): the Shelly toggle's off branch and the Hue `off_press`
  branch. Turning *on* must NOT reset it.
- **Scene cycling advances first, then activates.** Double = one `select_next`; triple =
  two `select_next`; both then `scene.turn_on` with `{{ states(scene_select) }}` (the
  input_select's options are scene entity_ids).
- **Up/down use `brightness_step_pct`** (`+step` / `-step`), not absolute brightness, so
  HA clamps and applies the delta.
- **`mode: parallel` (with `max`)** — NOT `queued` and NOT `restart`. The Hue virtual
  multi-press counts overlapping runs (see below): `queued` serialises them so the second
  press can't start until the first run's delay ends (double/triple never detected), and
  `restart` would cancel an in-flight Shelly scene activation. Parallel keeps "rapid
  presses are never dropped" while letting the counting runs overlap.
- **Virtual multi-press is Hue-ON-only and opt-in.** The Hue ON key has no native
  multi-press, so it is counted in software using an optional `input_text` helper
  (`helper_last_controller_event`) storing `{"a","n","t"}` and a max-delay input
  (`helper_double_press_delay`). The `on_count` variable is self-contained (parses the
  helper itself, referencing only `!input`s per the evaluation-order rule) and increments
  the prior ON streak only when the previous event was `on_press` within the delay window,
  capped at 3. **Triple acts immediately** at count 3;
  **single/double act after the delay**, gated by a post-delay re-check that the helper's
  `t` still equals the `this_ts` this run wrote (a later press overwrites it → the stale
  run aborts — this is what makes parallel mode correct without `restart`). When enabled,
  **every Hue key stamps the helper first** (off/up/down too) so a following press
  invalidates a pending ON single/double. When the helper is empty (`dp_enabled` false)
  the ON key turns on instantly and no key touches the helper. The Shelly keeps its
  **native** single/double/triple and never touches the helper.
- **Device inputs are optional** (`shelly_device` / `hue_device` default to empty) so a
  user with one hardware family isn't forced to select the other. The `shelly_button`
  subtype varies by model (`button1` vs `button`) and is a configurable input.

### `motion_light_multisensor.yaml`

- **`mode: restart` is mandatory.** It is what makes a returning-motion event cancel
  a pending turn-off.
- **The off-delay lives in the `all_clear` template trigger's `for:`, never as an
  in-action `delay` step.** With `mode: restart`, the periodic `tick` trigger would
  restart the automation and silently drop an in-action delay, leaving lights on.
  For the same reason, turn-off uses `transition: 1` (a bulb-side fade), not a delay.
- **"All clear" = template over all sensors**, not a multi-entity state trigger with
  `for` (that fires when *any one* sensor clears, not all). Keep
  `expand(...) | selectattr('state','eq','on') | list | count == 0`.
- **The `tick` branch must only touch lights that are already on** (via `tick_targets`)
  — it must never turn an off light back on.
- **The `motion` branch turns on all off lights and respects manual override on
  already-on lights** (via `motion_targets`). When the optional `input_number` helper
  is configured, already-on lights that have been manually adjusted beyond
  `override_tolerance` are left untouched on motion re-triggers.
- **Manual-override protection** compares a light's current brightness to the last
  automatic value stored in the optional `input_number` helper, within
  `override_tolerance`. The tolerance exists because `brightness_pct` ↔ 0–255
  `brightness` round-trips can be off by ~1; do not set the default to 0.

(See **Shared** above for the sun-based brightness invariants.)

### `washing_machine_done_notifier.yaml`

- **Cycle detection is two-stage and gated by the `input_boolean` helper.** The `running`
  trigger (power above the running threshold) turns the helper ON; the `done` trigger
  (power below the idle threshold, after `done_debounce`) only notifies *if the helper is
  ON*, then turns it OFF. Without this gate an idle dip or a HA restart fires a false
  "done". Never drop the helper or the `state: on` condition on the `done` branch.
- **`mode: restart` is deliberate.** A new `running` event mid-alert restarts the run,
  cancelling the in-progress notify loop and re-arming the helper. Do not change to
  `queued`/`single`.
- **The notify loop uses `repeat.until`, not `while`.** `until` runs the body once before
  testing, so `wait` is always defined when `{{ wait.trigger is not none }}` is evaluated.
  A `while` referencing `wait` would dereference it before the first `wait_for_trigger`.
  On timeout (`wait.trigger is none`) it re-sends; on Acknowledge it stops and clears the
  card.
- **Acknowledge only works from the Companion app.** The stop signal is the
  `mobile_app_notification_action` event matching `action_id` (`ACK_<TAG>`); only the HA
  Companion app emits it. `notify_service` (the phone) must be a `mobile_app_*` service.
  `extra_targets` are delivery-only mirrors (laptop / persistent / WhatsApp) and must not
  be relied on to acknowledge.
- **The `tag` ties re-sends together and derives the action id.** Re-sends reuse the tag so
  a new card replaces the old one; the post-loop `clear_notification` uses the same tag.
  Give each appliance a distinct tag if the blueprint is reused.
- **No sun engine.** This blueprint shares none of the `target_brightness` /
  `target_color_temp` code; keep it that way.

## Home Assistant templating rules to respect

- `!input` cannot be used inside a Jinja template. Capture it in `variables:` first
  (and in `trigger_variables:` for templates used inside triggers).
- Inside the `variables:` block, templated variables should reference only literal
  `!input` variables, not other templated variables (evaluation-order safety).
  `tick_targets` follows this; keep it that way.

## Conventions

- All blueprints are `blueprint.domain: automation`; one automation per YAML file.
- Distribution: native blueprint import via the `my.home-assistant.io` badges in the
  README. Keep each file path stable — HA keys imported blueprints by `source_url`, so
  renaming a file or the repo creates a duplicate instead of an update. The repo was
  renamed from `ha-motion-light-multisensor` to `ha-smart-lighting-blueprints`, then to
  `ha-automation-blueprints`. Imports from either previous URL need a one-time
  re-import and existing automations must be pointed at the new copy before removing
  the old one. Avoid further renames.
- Versioning: GitHub **release tags** only (`vMAJOR.MINOR.PATCH`). There is no version
  field inside the YAML. Cut a release for each user-facing change.
- Keep `README.md` input descriptions in sync with each blueprint's `input:` block.
