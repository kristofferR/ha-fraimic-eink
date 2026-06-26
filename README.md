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
2. Confirm the **resolution**. It is auto-filled when the frame reports it; otherwise the
   default is **1600×1200** (the 13.3" frame). Set the correct pixel size for a smaller frame.

Change the polling interval later via the integration's **Configure** button (default 300 s,
since the frame is battery-powered).

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

## Uploading artwork

The killer feature. Call the `fraimic.upload_image` service with **one** image source:

```yaml
action: fraimic.upload_image
data:
  url: https://example.com/poster.jpg
  fit: cover      # cover (crop) | contain (pad) | stretch
  rotate: 0       # 0 | 90 | 180 | 270
  dither: true    # Floyd-Steinberg to the 6-colour palette — recommended for photos
```

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

| Index | Colour |
|:-----:|--------|
| 0x0 | Black |
| 0x1 | White |
| 0x2 | Green |
| 0x3 | Blue |
| 0x4 | Red |
| 0x5 | Yellow |

The integration applies EXIF orientation + your `rotate`, fits to the frame resolution
(`cover`/`contain`/`stretch`), dithers to the 6-colour palette (Floyd-Steinberg), clamps every
nibble to a valid `0–5` index, packs the buffer, and `POST`s it as multipart to `/upload`.

## Accuracy note

Fraimic's official REST API guide describes the frame as "4-bit **grayscale**, 1200×1600,
upload via `POST /api/image` (octet-stream body)". On real hardware that is wrong on three
counts, confirmed by community reverse engineering
([dsackr/fraimic-controller](https://github.com/dsackr/fraimic-controller)):

- The panel is **Spectra 6 colour**, not grayscale.
- The 13.3" frame is **1600×1200** (landscape), not 1200×1600.
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
