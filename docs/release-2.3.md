# Fraimic 2.3

## Temporary overlays and briefings

- Show information over the current artwork for a fixed window with `fraimic.show_temporary_overlay`. Update it with `fraimic.update_temporary_overlay`, or end the window with `fraimic.clear_temporary_overlay`.
- Refresh entity-backed content without extending the window or advancing playback. Identical pixels skip the redraw; expiry restores artwork with its permanent overlays.
- Render optional agendas, tasks, routine progress, weather, and guidance from any Home Assistant entity providing the documented briefing format. Choose a bottom strip, overview, or side panel, with English or Norwegian labels.
- Keep expired briefing content out of delayed deliveries and preserve overlay state across restarts. Saved permanent-overlay edits take effect on the next picture change, or immediately with **Apply now**.

## Discovery, availability, and previews

- Discover unconfigured frames on Home Assistant's local network even when zeroconf or DHCP discovery misses them. A shared **Network scan** option can disable the periodic sweep.
- Keep last-known entity values available while battery-powered frames sleep, with a 72-hour contact window and a **Last seen** sensor.
- Preview `fraimic.upload_image` conversions without sending them to the frame using `preview_only: true`.
- Improve upload completion, queued delivery, and briefing layouts. The mount-rotation fix from 2.2.1 remains included.

## Updating

Update through HACS, restart Home Assistant, then reload the browser or companion-app page. Existing frame settings and playback queues are preserved. Briefings are optional: supply your own entity and content; no separate companion package or upstream account is required.

**Full changelog:** [v2.2.1…v2.3.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v2.2.1...v2.3.0)
