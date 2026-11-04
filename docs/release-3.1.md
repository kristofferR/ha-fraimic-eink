# Fraimic 3.1

## AI art

- **Create** in the top bar turns a description into a picture shaped for the selected frame, saves it in **Creations** with its prompt, model and cost, and can show it right away.
- Set it up once for every frame under **⋮ > AI art**: OpenRouter (with a key check and live per-picture prices), a local server (the OpenAI images API or the Stable Diffusion WebUI API, detected automatically), or any Home Assistant AI Task entity that can make images.
- Styles are editable prompt templates. An optional rewrite step turns short or non-English requests into a detailed prompt, and **Create** lets you edit the final prompt before sending it.
- The new `fraimic.create_art` action does the same from automations.
- Voice-button settings move from the frame options into the AI art dialog, so changing them no longer reloads the frame. Existing settings carry over.

## Local backend (experimental)

- A new **Backend** delivery mode lets a frame on stock firmware run without the Fraimic cloud. A separately deployed companion speaks the frame's own protocol, while Home Assistant renders pictures, schedules wakes and answers recorded voice requests. Setup needs frame-specific TLS and routing; see the [runbook](local-backend.md).
- **⋮ > Local backend** shows the companion's health, the last poll and battery, the next wake, the picture waiting for the frame, and the last day of voice requests.
- The player keeps the picture handed to the companion, for example "Waiting for next wake at 14:05" and then "Served 14:06 · display unconfirmed". Actions that need the frame on the LAN are hidden in this mode.
- Frame options check the companion token and generate one when none is saved. New **Local backend status** and **Next wake** sensors show where delivery stands.

## Auto mode

- Auto mode no longer crops pictures far beyond the frame. A cover fit may trim at most 20% of a picture's width or height. Online sources draw another picture instead, and library and folder sources prefer pictures in the frame's orientation.
- The same limit applies to **New artwork** and Wallhaven packs.
- **Surprise me** now draws from every available source instead of only the museums.

## Other changes

- Voice creations have their own **Creations** folder below **Uploads**, so they're no longer listed twice under **My library**.
- DigitaltMuseum is removed: its API now issues keys only to partner organisations. Frames that used it for **New artwork** fall back to **Surprise me**.
- The repair about the frame keeping time in another time zone is gone. Home Assistant already converts the frame's timestamps.
- Fraimic now has a category in the Home Assistant Marketplace.

## Updating

Update through HACS or the Home Assistant Marketplace, restart Home Assistant, then reload the browser or companion-app page.

**Full changelog:** [v3.0.0…v3.1.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v3.0.0...v3.1.0)
