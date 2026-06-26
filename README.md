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

Via the integration's **Configure** button (per frame) you can set the **polling interval**
(default 300 s, since the frame is battery-powered) and a **base rotation** (0/90/180/270) to
match how that frame is physically mounted — it's applied to every upload, on top of any per-call
`rotate`.

## Entities

| Type | Entities |
|------|----------|
| Sensor | Battery %, Battery voltage, Battery source, Wi-Fi signal, Wi-Fi SSID, Wi-Fi channel, IP address, Firmware, Uptime, Last refresh, Next refresh |
| Binary sensor | Charging, Cable connected, Wi-Fi connected, Registered, Time synced, Voice recording, Keep awake |
| Button | Refresh display, Sleep, Restart |
| Image | Current artwork (colour preview of the last upload) |

Diagnostic / noisy entities (SSID, IP, voltage, uptime, …) are disabled by default — enable
them on the device page if you want them. Sensors whose field the frame doesn't report simply
stay unavailable.

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

The killer feature. Call the `fraimic.upload_image` service with **one** image source:

```yaml
action: fraimic.upload_image
data:
  url: https://example.com/poster.jpg
  fit: cover            # cover (crop) | contain (pad) | stretch
  rotate: 0             # 0 | 90 | 180 | 270
  mode: auto            # auto | floyd_steinberg | atkinson | bayer | none
  saturation: 1.25      # boost for the small Spectra gamut (1.0 = none)
  contrast: 1.1         # 1.0 = none
  sharpen: 80           # unsharp-mask strength 0-100
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
requires and uploads it over the safe `/upload` path, then triggers a refresh.

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

## How image conversion works

Fraimic frames are **E Ink Spectra 6** colour panels. The display buffer is raw, header-less,
uncompressed: every pixel is a 4-bit index into a 6-colour palette, packed two pixels per byte
(high nibble = left pixel, low nibble = right pixel), scanned left-to-right, top-to-bottom. For
the 13.3" frame that's `1600 × 1200 / 2 = 960,000` bytes.

| Index | Colour | Calibrated RGB |
|:-----:|--------|:--------------:|
| 0x0 | Black  | #000000 |
| 0x1 | White  | #ffffff |
| 0x2 | Green  | #608050 |
| 0x3 | Blue   | #5080b8 |
| 0x4 | Red    | #a02020 |
| 0x5 | Yellow | #f0e050 |

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
7. **Pack** nibbles (clamped to 0–5) and `POST` as multipart to `/upload`.

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
`POST /api/image` (octet-stream body)". On real hardware that is wrong on two counts, confirmed
by community reverse engineering
([dsackr/fraimic-controller](https://github.com/dsackr/fraimic-controller)):

- The panel is **Spectra 6 colour**, not grayscale.
- Uploads go to **`POST /upload`** (multipart). The documented `POST /api/image` returns 501
  **and hangs the frame for 45+ seconds** — this integration never uses it.

This integration follows the reverse-engineered behaviour and tolerates both the flat and
nested `/api/info` JSON shapes seen in the wild.

## Troubleshooting

- **Entities "unavailable":** the frame is probably asleep (deep sleep = no network). Tap it.
  Expected, and resolves itself when the frame wakes.
- **`fraimic.local` won't resolve:** use the IP address (find it at `http://fraimic.local/info`
  or in your router's DHCP table).
- **Colours look wrong:** make sure the frame's configured resolution matches the panel, and
  keep `dither: true` for photos. Only Black/White/Green/Blue/Red/Yellow can be shown.

## Credits

- Frame behaviour, the Spectra 6 format, and the `/upload` endpoint were reverse-engineered by
  [**dsackr/fraimic-controller**](https://github.com/dsackr/fraimic-controller) — thank you.
- Not affiliated with Fraimic. Unofficial, community-built. MIT licensed.
