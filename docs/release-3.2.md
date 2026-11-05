# Fraimic 3.2.1

## Online art

- Bing image of the day works on Standard frames with the Cover fit again. Since 3.1, its wide pictures needed more cropping than the 20% limit allows, so every pick failed with "produced no usable image". A source that offers nothing in the frame's shape now returns its closest-shaped picture instead. Auto mode still skips pictures that need more than a 20% crop.

**Full changelog:** [v3.2.0…v3.2.1](https://github.com/kristofferR/ha-fraimic-eink/compare/v3.2.0...v3.2.1)

# Fraimic 3.2

## Auto mode and queue timing

- Cloud and Hybrid frames no longer change pictures every few minutes before an awake window. A picture sent through your Fraimic account now starts the queue interval, just like one sent over your local network. Previously the 5-minute standby checks before a planned wake could shorten the time between pictures to about 10 minutes, which also drained the battery.

## Updating

Update through HACS or the Home Assistant Marketplace, restart Home Assistant, then reload the browser or companion-app page.

**Full changelog:** [v3.1.0…v3.2.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v3.1.0...v3.2.0)
