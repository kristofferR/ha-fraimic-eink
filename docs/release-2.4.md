# Fraimic 2.4

## Auto mode

- Keep the art changing after the queue runs out. **Then** in the queue sheet chooses Stop, Repeat queue, or Auto mode, replacing the repeat toggle.
- Auto mode keeps three prepared picks below an **Auto** divider. Anything you queue plays first. Remove a pick to get another, drag it above the divider to keep it, or choose **New picks** to replace all three.
- Draw from Surprise me, any online source, your library, Favorites, albums, art packs, or saved playlists. Any gallery folder or search can be added with **Add to auto mode**, and 1×, 2×, or 3× weights set how often each source is picked.
- Change the picture on the queue interval, an interval of its own, or set times on chosen weekdays, optionally inside daily active hours. Cloud delivery always follows the queue interval because the frame wakes on it.
- Avoid repeats for 7, 30, or 90 days, or until every picture in a source has been shown. Small sources fall back to the least recently shown picture instead of stalling, and failing sources pause for 15 minutes.
- Set orientation, caption, tone, fit, and overlays for auto mode's pictures. Playlist sources keep each slide's own look.
- Automate everything with the `fraimic.set_auto_mode` action and the **End of queue** select entity.

## Fixes

- Restore The Met searches and source checks after The Met retired its v1 search API.

## Updating

Update through HACS, restart Home Assistant, then reload the browser or companion-app page. Existing playback is preserved: a queue that repeated before keeps repeating, and auto mode stays off until you choose it.

**Full changelog:** [v2.3.0…v2.4.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v2.3.0...v2.4.0)
