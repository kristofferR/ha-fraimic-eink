# Temporary overlays that stay up to date

`fraimic.show_temporary_overlay` adds a temporary set of overlays to the current
artwork. Its timer starts once. During that window, entity-backed widgets and
stored templates are read again every `refresh_interval` seconds. The default
is 60 seconds; choose 60–3600, or 0 to disable periodic updates.

Completing a morning-routine item can therefore change the progress gauge
and next-step text while the artwork stays the same. The interval is a minimum
between refresh attempts, not a guarantee of physical delivery. HA's source
polling and the panel redraw add latency. Identical rendered pixels are not sent
again. Several changes between checks become one update with the latest data.

Start a window once, for example from your existing morning/presence automation.
Replace the example entity ID with the routine sensor in your installation:

```yaml
action: fraimic.show_temporary_overlay
data:
  duration: 5400
  refresh_interval: 60
  overlays:
    - id: morning-progress
      type: gauge
      x: 0
      y: 5
      w: 3
      h: 3
      options:
        entity: sensor.morning_routine
        name: Morgenrutinen
        min: 0
        max: 100
        unit: "%"
        color: green
    - id: morning-next-step
      type: text
      x: 3
      y: 5
      w: 6
      h: 3
      options:
        template: >-
          {% raw %}
          {% if has_value('sensor.morning_routine') %}
          {{ state_attr('sensor.morning_routine', 'completed_steps') }} /
          {{ state_attr('sensor.morning_routine', 'total_steps') }} fullført.
          {{ state_attr('sensor.morning_routine', 'next_step') or 'Ferdig' }}
          {% endif %}
          {% endraw %}
```

The outer `{% raw %}` block prevents the calling HA automation from evaluating
that template once at activation. Fraimic receives the inner template and reads
current values on each refresh. `options.literal` is also supported for text,
but literal content stays unchanged until replaced. For a ready-made strip layout,
see [Morning briefing strip](#morning-briefing-strip-layout-a).

Add `preview_only: true` to render a preview without activating a timer or sending
an image. A clean source must already have been shown through this integration;
the integration refuses to guess at an externally selected picture.

## Updating an active window

Use `fraimic.update_temporary_overlay` when an HA automation prepares new literal
content, or wants to request a refresh. Its optional `overlays` field replaces
the entire temporary set. Omit it to reread the existing widget definitions:

```yaml
action: fraimic.update_temporary_overlay
data: {}
```

For several configured frames, supply `config_entry_id`. Updates are coalesced
at the configured interval (at least 60 seconds for explicit updates), and never
extend `expires_at`. An update after expiry is ignored with `active: false`.
Calling `show_temporary_overlay` again intentionally starts a new window, so do
not call it for each routine checkbox change.

`fraimic.clear_temporary_overlay` ends the window early. Normal expiry and clear
recompose the retained artwork with any permanent overlays still in effect.
The exact clean frame pixels, expiry, and refresh preference survive an HA
restart. A manual picture change becomes the new clean base; overlay refreshes
do not advance the playback queue.

## Delivery and power

- Each changed image is a full e-ink redraw. The explicit overlay interval takes
  precedence over generic automatic-send cooldowns, like a playback interval.
  Local updates still respect low-battery protection and send coalescing.
  Restoring artwork after an accepted temporary display expires or is cleared
  is allowed below the 25% battery threshold: cleanup completes that display
  rather than leaving stale information on the wall. This permits one final
  redraw, not continued live updates. An unreachable frame still needs to wake.
- The frame must be awake/reachable for prompt LAN updates. Refreshing an overlay
  does not enable keep-awake or change the device's power settings.
- Cloud/Hybrid delivery can be delayed until a cloud wake. Changes are held
  while a cloud delivery is pending, so repeated updates do not restart its wake
  timer forever. Identical cloud submissions are skipped without claiming that
  a redraw has been physically confirmed.
- A temporary composite is not submitted to cloud when its earliest wake would
  be after expiry. Expiry stops live updates and attempts to restore the artwork;
  an offline frame can retain the old image until reachable.
- Permanent overlays still follow their own visibility rules. This periodic
  refresh option belongs to the active temporary window.

The source integration or template owns content selection and freshness. Fraimic
owns composition, change detection, expiry and transport. A source becoming
unavailable is different
from an empty task list: upstream selection and templates should omit stale
content, not turn it into zero progress.

Ref #70.

## Morning briefing strip (layout A)

The `briefing` overlay reads a structured snapshot from an ordinary HA entity.
It draws a white bottom strip with a greeting/date, weather, and available
agenda/routine/tasks/focus columns. Missing columns collapse. A routine uses
completed/total counts for its green ring; skipped steps remain separate.
Optional progress entries draw coloured bars. No sleep section or running clock
is included. Labels support `nb` and `en`; the producer supplies localized titles.

```yaml
action: fraimic.show_temporary_overlay
data:
  config_entry_id: YOUR_FRAME_ENTRY_ID
  duration: 5400
  refresh_interval: 60
  overlays:
    - id: morning
      type: briefing
      options:
        entity: sensor.fraimic_morning_content
        attribute: brief
```

Keep the default full-frame overlay geometry: the renderer itself positions the
strip at the bottom. Artwork remains visible above it. Preview with
`preview_only: true` before sending.

The attribute must be a dictionary with `generated_at` and `valid_until` (ISO
8601 with timezone), `greeting`, and `date_label`. `locale` defaults to `en`.
Optional fields:

| Field | Content |
| --- | --- |
| `agenda` | Up to 3 `{title, time, all_day, icon}` entries. No invented times. |
| `routine` | `{label, completed, total, skipped, next_step, icon}`. Total must be positive; completed + skipped cannot exceed total. |
| `tasks` | Up to 12 `{title, icon, priority, deadline}` entries. |
| `focus` | `{title, label, detail, icon, color}`. An explicitly chosen priority. |
| `progress` | Up to 3 `{label, value, max, unit, icon, color}` entries. |
| `weather` | `{temperature, unit, icon}`. Unit is °C or °F. |

Icons use `mdi:name`. Accents are `blue`, `green`, `yellow`, or `red`. Text is
bounded to 240 characters and visually truncated where needed. Snapshots may
be valid for at most five minutes. Malformed, expired, unavailable, and entirely
empty snapshots produce clean artwork rather than an error panel.

Use a Home Assistant automation or package to combine your sensor data, add
optional weather, and start the temporary window. Check source availability,
age and effective date before including content. Fraimic reads the prepared
snapshot; it does not fetch external task APIs or rank personal content.

**Delivery:** a brief whose validity would end before the predicted cloud wake
is deferred. Use reachable LAN delivery for minute-scale changes; neither this
overlay nor its refresh mechanism enables keep-awake. Clearing stale pixels on
a sleeping/offline frame still requires a later successful delivery.

### Ordered shared briefs

A briefing entity may supply `blocks` instead of the older fixed `agenda`, `routine`,
`tasks` and `focus` fields. Blocks remain in provider order. The first four occupy
main columns; up to two more occupy the compact footer. Optional `progress` bars
occupy a separate footer row if both are supplied. No content is re-ranked.

Each block has `type: agenda | tasks | routine | focus`. Agenda/tasks blocks have
`label`, optional `color` and one to three agenda `items` or up to twelve task `items`, using the existing agenda/task
row schema. Routine/focus blocks use the corresponding existing fields plus `type`.
The shared snapshot still requires `generated_at`, `valid_until`, `greeting`,
and `date_label`; `locale` defaults to `en`. Weather can be added by HA without changing those times.
Use one format per snapshot; when `blocks` is present it owns the main content.

Expose this payload in an entity attribute, such as `brief`, and reference that
entity and attribute in the overlay options. The source integration or template
selects the content and supplies its validity timestamps. Fraimic does not need
credentials for the upstream service, select tasks, or infer user priorities.

The existing temporary-window controller re-reads this entity, skips identical
pixels, refuses expired data, and restores the retained artwork at the original
end time. No timer, queue, transport or artwork ownership rules change.

### Choosing a briefing layout

Set `options.layout` on a `briefing` overlay to `overview` (Veileder and day
summary), `side_panel` (artwork alongside Veileder), or `strip` (the existing
bottom strip, still the default). All three read the same snapshot. An optional
`guidance` object supplies `title` (up to 240 characters), `body` (up to 2400),
and `action` (optional, up to 240). The producer supplies existing advice; Fraimic
does not generate it. Missing guidance leaves the other available content visible.

Update the layout through `update_temporary_overlay` to change an active window
without extending its expiry. The companion morning package provides a persistent
Home Assistant layout selector for this.

A red low-battery icon is drawn over every composition at the absolute
bottom-left of the viewed panel when the reported battery is below 30%. It is
omitted at 30% and above, and when the battery is unknown. It remains on restored
artwork after temporary content expires. It has no text or background plate and
reserves no layout space: only the corner icon pixels change. Normal delivery
rules still apply.

Task blocks support up to 12 rows. Longer todo lists use a compact column layout in all three briefing styles, keeping guidance and the leading focus card above the list. Ordered snapshots support up to eight blocks.

Long lists retain agenda times, supporting focus details and the graphical progress footer. The tasks expand into their own columns rather than consuming the other briefing sections.

Dense briefings retain the colored icon tiles and blue strip rule from the original design. Count progress uses discrete segments; minute-based progress keeps a continuous meter. The strip places Veileder and Neste side by side to leave more of the artwork visible.

Rich briefings use measured text blocks and fixed type sizes rather than shrinking supporting sections. Short lists arrange supporting cards alongside the task column; longer lists use two task columns. Agenda times and progress values have dedicated aligned positions.

Optional `weekly_focus` (`text`, `done`) appears beneath the greeting. Task rows accept `priority` and a display-ready `deadline` label. `updated_time` (`HH:mm`) shows the source snapshot's local time at the bottom-right, using small supporting text without reserving layout space. Consumers should derive it from `generated_at` in the source account timezone, never the polling time.

Rich layouts show at most twelve task rows. When supporting cards exceed the available height, the lowest-ranked cards become a `+N more` notice so the progress footer stays on the canvas. Fractional progress uses a continuous meter; routine blocks supplied by other providers retain their completion and skipped counts.
