# Fraimic 2.5

## Awake windows

- Let a Hybrid frame sleep between the times you actually look at it. `fraimic.set_awake_window` keeps the frame awake from a start time to an end time, and it sleeps otherwise.
- Home Assistant wakes the frame through the Fraimic cloud shortly before the window starts, so it is awake and responsive on time.
- Set **Standby from** to have the sleeping frame check in every 5 minutes before the window, without redrawing, so a window you start early reaches it within one check.
- Turn on **Repeat daily** to plan the same window for the next day when the current one ends, for example every morning.
- `fraimic.clear_awake_window` ends or cancels the window. The frame then sleeps and still wakes once a day to pick up new plans.
- Planned wakes use their own empty album, so waking the frame never redraws the picture.

## Fixes

- Read Fraimic account times as UTC. Album deadlines came out hours early on hosts outside UTC.
- Show the favorite heart in the player for artwork sent through the cloud, including library pictures, scenes, and overlay refreshes.

## Updating

Update through HACS, restart Home Assistant, then reload the browser or companion-app page.

**Full changelog:** [v2.4.0…v2.5.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v2.4.0...v2.5.0)
