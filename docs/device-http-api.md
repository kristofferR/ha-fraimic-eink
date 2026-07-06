# Fraimic device HTTP surface & behaviour (firmware 0.2.21)

Reverse-engineered on a real 13.3" Fraimic E-Ink Canvas (device name `Fraimic_29476`,
firmware **0.2.21**). This documents the frame's *local* HTTP server and cloud behaviour —
useful context for the integration and for anyone debugging a frame. It is **not** an official
Fraimic spec; later firmware may differ.

## HTTP endpoints

The frame runs an unauthenticated ESP-IDF `httpd` on port 80 (plain HTTP, no TLS).

### JSON API

| Method & path | Purpose | Notes |
|---|---|---|
| `GET /api/info` | Full device snapshot | Nested schema on 0.2.21 (see below). No display size/model field. |
| `GET /api/battery` | Lightweight battery status | `{percent, voltage_mv, charging, cable_connected, source}` |
| `POST /api/refresh` | Full E-Ink refresh cycle | GET → 405 |
| `POST /api/sleep` | Deep sleep | Blocked while charging (`{"error":"charging_cable_connected"}`) |
| `POST /api/restart` | Reboot | Recovers a wedged upload handler |
| `POST /upload` | Upload a raw `.bin` (multipart, field `image`) | The frame **auto-renders** it; see below |
| `POST /api/image` | **Do not use** | Returns 501 and hangs the frame ~45 s |

There is **no settings-write endpoint** (`/api/settings`, `/api/config`, `/api/update`,
`/api/ota`, … all 404) and **no local firmware-update trigger**. Firmware updates are entirely
cloud-driven and gated by the `auto_update` setting (see below).

### Portal (HTML) pages

| Path | Purpose |
|---|---|
| `GET /portal` | Landing page; links to the pages below and to `https://app.fraimic.com` |
| `GET /upload` | Upload form (`multipart/form-data`, field `image`, `.bin`, ~960 KB, 1 MB max) |
| `GET /info` | Human-readable device info |
| `GET /wifi`, `GET /get-started` | Wi-Fi / onboarding |
| `GET /logs` | ESP-IDF log viewer (see below) |
| `GET /dev` | **Developer Mode** (see below) |
| `GET /battery/status` | JSON used by the portal's live battery widget |

## `/api/info` schema (0.2.21, nested)

```jsonc
{
  "firmware_version": "0.2.21",
  "build": "…",
  "wifi":    { "connected", "ssid", "rssi", "channel", "band", "bssid", "ip", "mac" },
  "battery": { "percent", "voltage_mv", "charging", "cable_connected", "source" },
  "device":  { "registered", "account_created", "device_key", "time_synced",
               "local_time", "uptime_s" },
  "settings":{ "voice_recording", "keep_awake", "auto_update", "charging_led" },
  "display": { "last_refresh", "next_refresh", "refresh_interval_days", "refresh_hour" }
}
```

- `display.last_refresh` only tracks the **scheduled** refresh cycle — it does **not** move on
  uploads, and reads a bogus `1970-…` date until the first scheduled cycle.
- No `display.width/height` or model field, so resolution auto-detect can't work on this
  firmware — the config flow falls back to the manual model picker.

## Upload behaviour

- A successful `POST /upload` **renders by itself** (~20–30 s). No follow-up `/api/refresh` is
  needed; firing one mid-render just gets the connection reset by the busy single-threaded ESP32.
- An aborted / timed-out upload can **wedge the upload handler**: subsequent `/upload`
  connections reset after ~10 s while the rest of the API keeps answering. `POST /api/restart`
  clears it. The integration auto-recovers from this (restart + one retry).
- With `curl`, disable `Expect: 100-continue` (`-H "Expect:"`) or the ESP32 stalls the upload
  for ~90 s. `aiohttp` (what the integration uses) doesn't send it, so it's unaffected.

For the `.bin` pixel format, see the README "Accuracy note" — it is a two-half, column-major,
bottom-up layout with E-Ink-standard Spectra 6 nibble codes, **not** the row-major format
community write-ups describe.

## Developer Mode — `GET/POST /dev`

A password-gated page that points the frame at Fraimic's **dev** backend
(`https://dev-api.fraimic.com`) instead of production:

- `POST /dev` with `action` + `password`. The password is verified **in firmware** (no
  client-side hash/hint) and failures are **rate-limited**.
- Switching **back to production** needs **no password** (restarts the device).
- Entering dev mode makes all AI prompts / downloads use the dev environment — **not** something
  you want on a normal production frame.

## Logs — `GET /logs`

ESP-IDF log viewer with per-subsystem tabs (WiFi, Server, System, Recording, Display, Battery,
OTA) and Error/Warning/Info level filters. The standard levels are readable **without** a
password; a password (same firmware-side, rate-limited gate as `/dev`) unlocks the extra verbose
tabs. `POST /logs/action` with `action=clear` clears captured logs.

The log/dev password is **not** recoverable over HTTP — it lives in the firmware. Obtain it from
Fraimic support, or by dumping the ESP32 flash and running `strings`.

## Cloud & network requirements

The frame needs outbound internet. While awake it polls, roughly every 30 s:

- `origin.fraimic.com` — the API (AWS ALB), and
- `fraimic-prod-user-files.s3.amazonaws.com` — artwork/file storage,
- plus NTP to `pool.ntp.org`.

DNS + HTTPS (443) egress must be allowed. If IoT DNS is forced through a local resolver
(e.g. AdGuard/Pi-hole), make sure it isn't blocking `*.fraimic.com` or the S3 bucket.

### `auto_update` and known issues

- **`settings.auto_update: false` stops firmware updates.** There's no local way to change it —
  toggle it in the Fraimic app / `app.fraimic.com` (it syncs to the frame on its next cloud poll).
- **Voice → AI generation can fail with a Wi-Fi drop:** on this firmware the radio can drop the
  instant voice recording starts (`/logs` shows `WiFi lost — reason 2/4/204`, then
  `Recording timeout … no audio upload`). This is an ESP32 mic(I2S)-vs-Wi-Fi coexistence /
  power-brownout symptom, not a network problem — retry on cable power, and it's the kind of bug
  a firmware update is likely to address.
