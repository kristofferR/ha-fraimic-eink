# Fraimic 2.0

Fraimic 2.0 adds a redesigned Home Assistant panel for browsing artwork,
managing playlists, and controlling what each frame displays. Optional cloud
delivery lets frames sleep between scheduled images.

## Highlights

- Browse Reframed and Wallhaven alongside the existing artwork sources, save
  favorites, and install art packs into your library.
- Create named playlists and assign them to frames. Each frame keeps its own
  playback order; rearranging the queue does not edit the saved playlist.
- Configure picture fit, tone, crop, and frame-specific overlays in the panel.
- Choose local uploads or Fraimic account delivery. Cloud delivery uses a private
  album per frame and applies new artwork at the frame's next scheduled wake.
- Use the corrected Large Canvas 1440×2560 native layout and optional official
  converter compatibility mode.
- Diagnostics now redact structured MAC/BSSID fields as well as cloud identifiers.

## Upgrading from 1.x

These steps cover published 1.x releases, including 1.4.1, and development
installations reporting 1.5.0. Migrations already applied by a development build
are not repeated.

Back up Home Assistant, including the Fraimic library and `.storage` data, before
upgrading. Update the integration in HACS and restart Home Assistant, then reload
the browser or companion-app page to load the new panel.

Existing frames keep their delivery setting; cloud delivery requires opting in
and signing in with a Fraimic account. Existing entries without a power mode
migrate to **Responsive**, preserving their previous polling behaviour. New
entries default to **Minimum**.

Legacy frame slides migrate once into a named playlist for that frame, preserving
the saved playback order. Saved library artwork and Fraimic scenes remain stored.
Large-frame dimensions and rotation are migrated to the native panel layout;
check the displayed orientation after upgrading.

### Breaking change: Home Assistant scene entities removed

The integration no longer creates `scene.*` entities or the virtual **Fraimic
Scenes** device. Update automations, scripts, dashboards, and voice shortcuts that
target those entities. Saved Fraimic scenes can still be sent by name:

```yaml
action: fraimic.send_scene
data:
  name: Morning wall
```

This replaces calls to `scene.turn_on` targeting a Fraimic scene entity; it does
not affect scenes belonging to other integrations.

## Delivery behaviour

Cloud acceptance means **queued**, not confirmed on the physical display. The
panel retains the last confirmed local artwork while playback order advances
separately. Allow the scheduled wake interval before expecting a cloud image.

In local mode, a sleeping frame can defer delivery until it wakes. Minimum power
mode limits automatic probing; **Try queued send** can deliver after you wake it.
See the [README](../README.md#battery-saving-modes) for power budgets and controls.

## Release validation

Before publishing the tag, verify the release candidate on Home Assistant:

- Upgrade a backed-up 1.x installation (1.4.1 release or 1.5.0 development build)
  and confirm frame settings, library,
  migrated playlists, and updated scene automations.
- Restart Home Assistant and confirm playlist assignment, order, paused state,
  and pending delivery persist.
- Confirm a local image reaches the panel with correct orientation, and a cloud
  image reaches it at the next timer wake without a duplicate redraw.
- Check gallery, picture preview, playlist, and queue controls on iOS/Safari.

These live checks are separate from the automated test suite and earlier hardware
verification. Record their results before treating this candidate as release-ready.
