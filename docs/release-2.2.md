# Fraimic 2.2

## Independent playback queues

- Add playlists to the queue or play them next without replacing existing playback. **Play now** explicitly replaces the queue.
- Edit and delete saved playlists independently. Queued items keep their own copies, order, shuffle, repeat, and interval settings.
- Choose a custom interval per frame. Explicit playback intervals now override power-mode cooldowns and daily redraw limits; low-battery protection remains.
- See why playback is waiting and when it will retry. Clearing the queue leaves the displayed picture intact.

## Playback fixes

- Preserve manually selected artwork while a sleeping frame waits to retry.
- Keep time-windowed items queued until eligible and advance when the displayed item's window closes.
- Handle repeat navigation, shuffle changes, exhausted queues, and unavailable artwork consistently.
- Remove copied queue entries when their library images or art packs are deleted.

## Updating

Update through HACS, restart Home Assistant, then reload the browser or companion-app page. Existing playback migrates automatically, preserving the current picture, upcoming order, interval, and repeating rotation. Saved playlists remain unchanged.

**Full changelog:** [v2.1.0…v2.2.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v2.1.0...v2.2.0)
