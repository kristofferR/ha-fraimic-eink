# Temporary overlays that stay up to date

`fraimic.show_temporary_overlay` adds a temporary set of overlays to the current
artwork. Its timer starts once. During that window, entity-backed widgets and
stored templates are read again every `refresh_interval` seconds. The default
is 60 seconds; choose 60–3600, or 0 to disable periodic updates.

Completing a KrisHQ morning-routine item can therefore change the progress gauge
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
        entity: sensor.krishq_morning
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
          {% if has_value('sensor.krishq_morning') %}
          {{ state_attr('sensor.krishq_morning', 'completed_steps') }} /
          {{ state_attr('sensor.krishq_morning', 'total_steps') }} fullført.
          {{ state_attr('sensor.krishq_morning', 'next_step') or 'Ferdig' }}
          {% endif %}
          {% endraw %}
```

The outer `{% raw %}` block prevents the calling HA automation from evaluating
that template once at activation. Fraimic receives the inner template and reads
current values on each refresh. `options.literal` is also supported for text,
but literal content stays unchanged until replaced. This is a service example,
not the final KrisHQ morning-brief layout.

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
  Local delivery still respects low-battery protection and send coalescing.
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

KrisHQ owns content selection and freshness. Fraimic owns composition, change
detection, expiry and transport. A source becoming unavailable is different
from an empty task list: upstream selection and templates should omit stale
content, not turn it into zero progress.

Ref #70.
