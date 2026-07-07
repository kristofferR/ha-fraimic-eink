# Fraimic E-Ink Canvas — Home Assistant integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A proper, UI-configured Home Assistant integration for the **Fraimic E-Ink Canvas** colour art frame.

The frame ships with a local REST API, but Fraimic's official "guide" is just copy-paste
`rest:` sensors and `shell_command:` curl calls in `configuration.yaml` — no device, no UI
setup, brittle when the frame sleeps, and you have to hand-convert every image to a raw binary
file *outside* Home Assistant before you can show it.

Worse, that official guide is **factually wrong** about the frame (see
[Accuracy note](#accuracy-note) below). This integration is built against how the frames
*actually* behave.

- 🔌 **UI setup** — add it from *Settings → Devices & Services*, no YAML. Auto-discovered via mDNS.
- 🔋 **Rich entities** — battery, voltage, Wi-Fi signal/SSID/channel/IP, firmware, uptime,
  last/next refresh, charging, cable, connectivity, and more — all on one device with correct
  device classes. Works with **both** the nested and flat `/api/info` schemas.
- 🎛️ **Buttons** — refresh display, sleep, restart.
- 🎨 **`fraimic.upload_image` service** — point it at a **file, URL, or camera/image entity**
  and it does resize / rotate / **Spectra 6 colour dithering** / nibble-packing and uploads it
  via the safe `/upload` endpoint. No manual conversion, no `tools/` scripts.
- 🪞 **Live preview** — an `image` entity shows a colour preview of the artwork on the frame.
- 😴 **Sleep-aware** — when the frame is in deep sleep (and unreachable), entities go
  *unavailable* cleanly instead of spamming errors.
- 📐 **Per-frame resolution** — set each frame's pixel size (the 13.3" frame is 1600×1200;
  smaller frames differ), so colour conversion always produces the exact buffer the frame wants.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/kristofferR/ha-fraimic-eink` as an **Integration**.
3. Install **Fraimic E-Ink Canvas**, then restart Home Assistant.

### Manual

Copy `custom_components/fraimic/` into your Home Assistant `config/custom_components/` directory
and restart.

## Setup

Make sure the frame is **awake** (tap it — it is unreachable in deep sleep), then:

*Settings → Devices & Services → Add Integration → Fraimic E-Ink Canvas*

1. Enter the host (`fraimic.local`, or the frame's IP if mDNS doesn't resolve — common with
   Docker/VLAN setups). With multiple frames, use IP addresses to tell them apart.
2. **Resolution is auto-detected** when the frame reports its size or model. If it can't be
   determined, you pick the model — **Standard Canvas** (13.3", 1600×1200) or **Large Canvas**
   (31.5", 2560×1440) — or choose *Custom* and enter the pixels. Add each frame separately; they
   can be different models.

**Multiple frames:** add each one separately — they appear as independent devices with their
own resolution, entities, and options. Use IP addresses (not `fraimic.local`) to tell them apart
when you have more than one. The `fraimic.upload_image` service takes a **Frame** picker
(`config_entry_id`) to target a specific one.

Every image setting is **configurable per frame** via the integration's **Configure** button —
not just YAML/service-call. Each frame stores its own defaults for **dither mode, fit, saturation,
contrast, sharpen**, plus **polling interval** (default 300 s) and **base rotation** (0/90/180/270,
to match how that frame is mounted). The `upload_image` service overrides a value only when you
pass it explicitly; otherwise the frame's configured default is used.

## Entities

| Type | Entities |
|------|----------|
| Sensor | Battery %, Battery voltage, Battery source, Wi-Fi signal, Wi-Fi SSID, Wi-Fi channel, IP address, Firmware, Uptime, Last refresh, Next refresh |
| Binary sensor | Charging, Cable connected, Wi-Fi connected, Registered, Time synced, Voice recording, Keep awake |
| Button | Refresh display, Sleep, Restart |
| Image | Current artwork (colour preview of the last upload), Screen preview (last rendered [dashboard screen](#dashboard-screens)) |
| Media player | Display images via the media browser / `play_media` |

Diagnostic / noisy entities (SSID, IP, voltage, uptime, …) are disabled by default — enable
them on the device page if you want them. Sensors whose field the frame doesn't report simply
stay unavailable.

**Sources & formats:** anything Pillow reads (JPEG, PNG, WebP, GIF, BMP, TIFF, …) plus
**HEIC/HEIF** (iPhone photos) and **AVIF**. Non-image media (videos, streams) is rejected with
an error that says what it actually was.

**Cameras:** playing a camera on the frame (media browser or
`play_media` with `media-source://camera/camera.x` / plain `camera.x`) takes a **still
snapshot** — a live stream is meaningless on a ~30 s E-Ink panel. By default it keeps
re-snapshotting every 30 minutes while the player is *Playing* (a slow live view); tune or
disable this with the **Camera refresh interval** option per frame (min 60 s, `0` = show once).
Press **Stop** on the media player to end the loop — the last image stays on the frame.

## Dashboard

Each frame is its own device, so the auto-generated device page already gives you everything.
For a nicer view, this card shows the **Current artwork** preview (it renders at the frame's real
aspect ratio and **mounted orientation** — portrait or landscape — automatically, because the
preview is rotated to match the frame's base rotation), plus battery and one-tap controls:

```yaml
type: vertical-stack
cards:
  - type: picture-entity
    entity: image.fraimic_e_ink_canvas_current_artwork
    show_state: false
    show_name: false
  - type: glance
    entities:
      - entity: sensor.fraimic_e_ink_canvas_battery
      - entity: binary_sensor.fraimic_e_ink_canvas_charging
      - entity: sensor.fraimic_e_ink_canvas_wi_fi_signal
  - type: horizontal-stack
    cards:
      - type: button
        name: Refresh
        icon: mdi:monitor-shimmer
        tap_action:
          action: perform-action
          perform_action: button.press
          target: { entity_id: button.fraimic_e_ink_canvas_refresh_display }
      - type: button
        name: Sleep
        icon: mdi:sleep
        tap_action:
          action: perform-action
          perform_action: button.press
          target: { entity_id: button.fraimic_e_ink_canvas_sleep }
      - type: button
        name: Restart
        icon: mdi:restart
        tap_action:
          action: perform-action
          perform_action: button.press
          target: { entity_id: button.fraimic_e_ink_canvas_restart }
```

**Multiple frames:** entity IDs are suffixed per device (e.g.
`image.fraimic_e_ink_canvas_2_current_artwork`) — duplicate the stack per frame using each
frame's IDs (check *Settings → Devices* for the exact names). The Large frame's preview comes out
landscape (16:9) and the Standard's portrait (3:4) — or whatever orientation you set, so each card
matches the real frame.

## Uploading artwork

### The easy way — media player + media browser

Each frame is also a **`media_player`**, so the simplest way to display an image is the native HA
media browser: open the frame's media-player card, **Browse media**, pick any image from your
media sources (e.g. *Local Media* in `/config/media`), and it's sent to the frame — converted with
that frame's configured settings. No paths, no service YAML.

It also works with the standard service, which is handy for automations:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.fraimic_e_ink_canvas
data:
  media_content_type: image
  media_content_id: media-source://media_source/local/art/sunset.jpg
```

The media player also shows the current artwork as its cover image.

### Full control — the upload service

For per-call overrides (fit, rotate, dither mode, saturation…), call the `fraimic.upload_image`
service with **one** image source:

```yaml
action: fraimic.upload_image
data:
  url: https://example.com/poster.jpg
  fit: cover            # cover (crop) | contain (pad) | stretch
  rotate: 0             # 0 | 90 | 180 | 270
  mode: auto            # auto | floyd_steinberg | atkinson | bayer | none
  saturation: 1.15      # kept modest (real Spectra 6 owners push contrast, not saturation)
  contrast: 1.4         # pushed hard — the panel has no backlight
  sharpen: 80           # unsharp-mask strength 0-100
  tone: 25              # filmic S-curve: midtone contrast + shadow/highlight rolloff
```

All processing options are optional with sensible defaults — the simple call is just
`data: { url: ... }`.

Other sources:

```yaml
# A local file (must be in an allowlisted dir, e.g. /config/www/...)
action: fraimic.upload_image
data:
  path: /config/www/art/sunset.jpg

# A camera or image entity (e.g. a generated dashboard, weather snapshot, etc.)
action: fraimic.upload_image
data:
  image_entity_id: camera.front_door
```

If more than one frame is configured, add `config_entry_id:` (a **Frame** picker is shown in the
UI service editor). The integration produces the exact buffer the targeted frame's resolution
requires and uploads it over the safe `/upload` path — the frame renders it by itself
(~20–30 s, verified on real hardware; no extra refresh call needed).

### Example automation — rotate art each morning

```yaml
automation:
  - alias: Fraimic daily art
    triggers:
      - trigger: time
        at: "08:00:00"
    actions:
      - action: fraimic.upload_image
        data:
          path: >-
            /config/www/fraimic/{{ ["mon","tue","wed","thu","fri","sat","sun"][now().weekday()] }}.jpg
```

**Low battery alert** — just a `numeric_state` trigger on `sensor.fraimic_e_ink_canvas_battery`;
no template sensor needed.

## Dashboard screens

The frame can render **Home Assistant data natively** — sensors, entity lists, templated text —
as a designed e-ink dashboard, TRMNL-style: widgets composed into layout slots, built as crisp
vector graphics on the server (no headless browser, works on any HA install) using only the
panel's six real colours, so the result is pixel-perfect with zero dithering noise.

![Sample dashboard screen](docs/sample-screen.png)

The screen above is exactly what this call produces:

```yaml
action: fraimic.render_screen
data:
  screen:
    name: Home
    layout: quadrant          # full | half_horizontal | half_vertical | quadrant
    widgets:
      - type: clock
        slot: top_left
      - type: stat
        slot: top_right
        entity: sensor.outdoor_temperature
        icon: mdi:thermometer
        trend: true           # ▲/▼ + change vs 1 h ago (needs recorder)
      - type: entities
        slot: bottom_left
        entities:
          - sensor.living_room_temperature
          - sensor.living_room_humidity
          - light.kitchen
          - lock.front_door
      - type: template
        slot: bottom_right
        template: >-
          Energy today: {{ states('sensor.energy_today') }} kWh
```

Layouts define the slots: `full` (`main`), `half_horizontal` (`top`/`bottom`), `half_vertical`
(`left`/`right`), `quadrant` (`top_left`/`top_right`/`bottom_left`/`bottom_right`) — one widget
per slot. Empty slots stay blank.

### Widgets

![Widget showcase](docs/sample-widgets.png)

| Type | What it shows | Key options |
|------|---------------|-------------|
| `clock` | Big HH:MM | `format` (strftime, no seconds) |
| `date` | Weekday + date | `format` (default `%A, %-d %B`) |
| `stat` | One big value + label + icon + optional trend arrow | `entity` (required), `name`, `icon`, `unit`, `precision`, `trend`, `trend_hours`, `color` |
| `entities` | Rows of name → state (with icons) | `entities` (list of ids or `{entity, name, icon}`), `max_rows` |
| `template` | Free-form Jinja-templated text | `template` (required), `align` (`left`/`center`), `size` (`s`/`m`/`l`) |
| `weather_current` | Condition icon + temperature + condition text | `entity` (weather, required), `name` |
| `weather_forecast` | Hourly/daily forecast strip (icon, high/low) | `entity` (required), `mode` (`hourly`/`daily`), `count` (1–8) |
| `calendar` | Agenda grouped by day (Today/Tomorrow/…) with accent bars | `entities` (calendar ids, required), `days` (1–14), `max_events` |
| `todo` | Checklist with checkboxes (strikethrough when done) | `entity` (todo, required), `max_items`, `show_completed` |
| `chart` | History line/area/bar chart from recorder data | `entities` (≤3, required), `hours` (1–168), `style`, `min`, `max`, `name` |
| `gauge` | 270° arc gauge with big value | `entity` (required), `min`, `max`, `unit`, `color`, `thresholds` (`[{from, color}]`) |
| `progress` | Labelled progress bar | `entity` (required), `min`, `max`, `name`, `color` |
| `image` | A photo / camera frame inside a slot (dithered) | `url` or `entity` (camera/image), `fit` (`cover`/`contain`) |

### Picture screens — full-bleed image / screenshot URL

`kind: picture` skips the widget renderer entirely and shows one image full-screen through the
normal photo pipeline (dithered + enhanced). Point it at any URL that returns an image — e.g. the
[puppet add-on](https://github.com/balloob/home-assistant-addons/tree/main/puppet), which
screenshots real Lovelace dashboards — or a camera/image entity:

```yaml
action: fraimic.render_screen
data:
  screen:
    kind: picture
    url: http://homeassistant.local:10000/lovelace/eink?viewport=1600x1200&kiosk
```

Screen-level options: `name` (shown in the header), `background` / `accent` / per-stat `color`
(one of `black`, `white`, `yellow`, `red`, `blue`, `green` — the panel's real palette),
`padding`, and `show_header: false` to drop the title bar. Icons are any
[Material Design Icon](https://pictogrammers.com/library/mdi/) (`mdi:...`), same names as
everywhere in HA.

### Managing screens in the UI

Screens can also be created **without any YAML**: on the frame's device page (Settings →
Devices & Services → Fraimic), choose **Add dashboard screen**. A short wizard asks for the
basics (name, layout, colours, rotation interval, optional time-of-day window) and then walks
through each slot with a widget picker and that widget's options — entity pickers, icon picker,
template editor, the lot. Screens are stored on the frame's config entry and can be edited or
deleted there later.

Show a stored screen by its name (or id) instead of an inline definition:

```yaml
action: fraimic.render_screen
data:
  screen_id: Gangen
```

(Gauge `thresholds` are the one option not exposed in the wizard — use the inline YAML form for
those.)

### Designing without burning refreshes

Every upload is a full ~30 s e-ink refresh and costs battery. Add `preview_only: true` to the
service call and the screen renders **only to the `Screen preview` image entity** — exactly what
the panel would show, including the 6-colour quantisation — so you can iterate on a design from
Developer Tools with zero uploads, then drop the flag when it's right.

Called from an automation (time pattern, state trigger, …), `render_screen` keeps the frame's
dashboard current — the same trigger patterns as the artwork examples above.

### The playlist — rotate screens automatically

When a frame has stored screens, it grows four playlist entities: a **Playlist** switch, a
**Screen** select, and **Next/Previous screen** buttons. Turn the switch on and the frame
rotates through its screens by itself:

- Each screen shows for its own **rotation interval** (min 5 minutes) and only inside its
  optional **time-of-day window / weekdays** (TRMNL-style scheduling: calendar+weather in the
  morning, photos in the evening…).
- Before every upload the freshly rendered panel content is **hashed and compared with what's
  already on the glass — unchanged screens are skipped entirely.** Data still refreshes every
  cycle; the ~30 s refresh flash and its battery cost only happen when something actually
  changed. (The clock widget renders minutes, so a clock-bearing screen changes every cycle by
  design.)
- **Sleep-aware:** while the frame is unreachable (deep sleep) cycles are skipped quietly, and
  the moment it answers a poll again the current screen is re-rendered fresh and pushed.
- **Manual uploads play nice:** `upload_image`, `render_screen`, or the media browser hold the
  playlist for one interval (your image gets its screen time), then rotation resumes. Starting
  a camera loop on the media player turns the playlist off explicitly.
- Selecting a screen in the **Screen** select (or pressing Next/Previous) shows it immediately
  and rotation continues from there. Playlist state survives restarts.

## Online artwork

The frame can fetch art **by itself** — no keys, no accounts:

```yaml
action: fraimic.show_online_image
data:
  provider: shuffle     # random masterpiece from a random museum
  caption: true         # small attribution strip: "The Bedroom — Vincent van Gogh, Art Institute of Chicago"
```

**Zero-config sources:** `met` (The Met), `aic` (Art Institute of Chicago), `cleveland`
(Cleveland Museum of Art) — public-domain masterpieces from each museum's open-access API,
aggressively curated for the panel (highlights only, paintings preferred, resolution and
aspect-ratio checked against your frame's mounted orientation). Plus `wikimedia` (Commons
picture of the day), `bing` (Bing's daily image — unofficial endpoint, personal use),
`apod` (NASA Astronomy Picture of the Day), and `picsum` (random stock photos).
`shuffle` picks a random museum.

**In the playlist:** a `kind: picture` screen with a `provider` shows a *fresh* artwork every
rotation — a set-and-forget art frame:

```yaml
# As a stored screen (Add dashboard screen → layout: Picture), or inline:
action: fraimic.render_screen
data:
  screen:
    name: Daily art
    kind: picture
    provider: shuffle
    caption: true
    interval: 3600
```

If an online source is down, the playlist keeps the current image and retries later — a flaky
API never blanks your wall. Attribution for whatever is showing is returned in the service
response (`title`, `artist`, `attribution`).

## How image conversion works

Fraimic frames are **E Ink Spectra 6** colour panels. The display buffer is raw, header-less,
uncompressed 4bpp — `1600 × 1200 / 2 = 960,000` bytes for the 13.3" frame — but the layout is
**not** a row-major scan (see [Accuracy note](#accuracy-note)): the buffer holds the bottom half
of the panel first, then the top half, each half column-major with columns scanned bottom-up and
two vertically-adjacent pixels per byte. Pixel values are the E Ink standard Spectra 6 codes
(`0x4` is unused — the panel renders it as white):

| Nibble | Colour | Calibrated RGB |
|:------:|--------|:--------------:|
| 0x0 | Black  | #000000 |
| 0x1 | White  | #ffffff |
| 0x2 | Yellow | #f0e050 |
| 0x3 | Red    | #a02020 |
| 0x5 | Blue   | #5080b8 |
| 0x6 | Green  | #608050 |

Getting good results from a tiny-gamut, low-contrast 6-colour panel is as much about
pre-processing as the dither, so the integration runs a full pipeline (all in an executor):

1. **Orient + fit** — EXIF transpose, your `rotate`, then resize (`cover`/`contain`/`stretch`).
2. **Tone** — autocontrast (black/white point) + a contrast boost.
3. **Saturation** — a boost, because the Spectra gamut is small (the single biggest perceptual
   win after the palette fix).
4. **Sharpen** — a mild unsharp mask (dithering softens detail).
5. **Match against a *calibrated* palette** (the muted RGB above, **not** pure primaries — pure
   primaries are what a Spectra 6 panel can't make, and matching against them looks harsh) in
   **OKLab**, with **neutral preservation** so near-grey pixels dither between black/white instead
   of speckling with red/yellow.
6. **Dither** with the selected `mode`:
   - **`auto`** (default) — looks at the image and chooses for you: **Floyd-Steinberg** for photos,
     **Bayer** for flat graphics/UI (lots of solid colour). The mode it picked is shown on the
     `Current artwork` image entity as the `dither_mode` attribute (and logged).
   - `floyd_steinberg` — best general error diffusion for photos.
   - `atkinson` — localised, preserves highlights; nice for portraits.
   - `bayer` — fast ordered dithering, best for flat graphics/dashboards/UI.
   - `none` — nearest colour, no dithering.
   Error-diffusion modes use serpentine scanning in linear light.
7. **Pack** into the frame's native half-panel/column layout and `POST` as multipart to
   `/upload`. Error-diffusion targets are clamped to the panel's reachable gamut, so
   out-of-gamut colours degrade gracefully instead of smearing accumulated error across the
   image (yellow blobs trailing saturated patches — seen on real hardware before the clamp).

**Which mode?** Just leave it on `auto` — it picks per image. Override only if you want a specific
look (e.g. force `bayer` for a poster-style image, or `atkinson` for a portrait).

The calibrated palette comes from community reverse engineering of real Spectra 6 panels
([Toon-nooT's converter](https://github.com/Toon-nooT/PhotoPainter-E-Ink-Spectra-6-image-converter),
the [Pimoroni Inky community](https://forums.pimoroni.com/t/what-rgb-colors-are-you-using-for-the-colors-on-the-impression-spectra-6/27942)).

**Speed:** `none`/`bayer` are vectorised (well under a second at 1600×1200); the error-diffusion
modes are inherently sequential and take a few seconds (longer on a Pi Zero) — still far less than
the panel's own 20–30 s refresh, and they run in the background.

## Accuracy note

Fraimic's official REST API guide describes the frame as "4-bit **grayscale**, upload via
`POST /api/image` (octet-stream body)". On real hardware that is wrong on two counts:

- The panel is **Spectra 6 colour**, not grayscale.
- Uploads go to **`POST /upload`** (multipart). The documented `POST /api/image` returns 501
  **and hangs the frame for 45+ seconds** — this integration never uses it.

The `.bin` buffer layout was **reverse-engineered on a real 13.3" frame (firmware 0.2.21)**
with physical test patterns, and it differs from every community write-up we found — including
[dsackr/fraimic-controller](https://github.com/dsackr/fraimic-controller)'s row-major, 0–5
sequential-palette description, which renders scrambled on 0.2.21:

- The buffer holds the **bottom half of the panel first**, then the top half.
- Each half is **column-major**: panel columns left→right, each column scanned **bottom-up**,
  two vertically-adjacent pixels per byte (high nibble first).
- Pixel values are the **E Ink standard Spectra 6 codes** (`0x2` yellow, `0x3` red, `0x5` blue,
  `0x6` green, `0x4` unused) — matching E Ink's EL133UF1 reference driver, not the sequential
  0–5 palette used by community converters.

Other verified-on-hardware behaviour this integration accounts for:

- A successful `/upload` **renders by itself** (~20–30 s). No follow-up `/api/refresh` is
  needed; firing one mid-render just gets the connection reset by the busy ESP32.
- `display.last_refresh` in `/api/info` only tracks the *scheduled* refresh cycle — it does
  **not** update on uploads (and reads as a bogus 1970 date until the first scheduled cycle).
- On firmware 0.2.21, `/api/info` reports no display size or model field, so resolution
  auto-detect has nothing to work with — the config flow asks you to pick the model instead.

This integration follows the verified behaviour and tolerates both the flat and nested
`/api/info` JSON shapes seen in the wild. The frame's full local HTTP surface (portal pages,
Developer Mode, logs, cloud endpoints, and the `auto_update` / voice-recording quirks) is
documented in [`docs/device-http-api.md`](docs/device-http-api.md).

## Troubleshooting

- **Entities "unavailable":** the frame is probably asleep (deep sleep = no network). Tap it.
  Expected, and resolves itself when the frame wakes.
- **`fraimic.local` won't resolve:** use the IP address (find it at `http://fraimic.local/info`
  or in your router's DHCP table).
- **Colours look wrong:** make sure the frame's configured resolution matches the panel, and
  keep `dither: true` for photos. Only Black/White/Yellow/Red/Blue/Green can be shown — there is
  no cyan or magenta ink, so those hues are approximated with dithered mixes.
- **Uploads suddenly failing (connection reset ~10 s in) while sensors still work:** the frame's
  upload handler is wedged — this happens after an aborted or timed-out upload. Press the
  integration's **Restart** button (or `POST /api/restart`); uploads work again after the reboot.

## Credits

- The `/upload` endpoint and the `POST /api/image` hang were first documented by
  [**dsackr/fraimic-controller**](https://github.com/dsackr/fraimic-controller) — thank you.
  The actual buffer layout and palette codes on firmware 0.2.21 were reverse-engineered for
  this integration on real hardware (see [Accuracy note](#accuracy-note)).
- Not affiliated with Fraimic. Unofficial, community-built. MIT licensed.
