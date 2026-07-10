# Fraimic Frame — local REST API reference

The frame runs an **unauthenticated** HTTP server on the local network at
`http://{host}` (default host `fraimic.local`, or the frame's LAN IP). This is
the API the Home Assistant integration talks to via `custom_components/fraimic/api.py`.

Verified on **firmware 0.2.21 and 0.2.28** (physical frame). Firmware is
battery-powered: in deep sleep the frame is completely unreachable until
tapped awake.

Reverse-engineered / hardware-verified — Fraimic's own "REST API Guide"
(fw 0.2.16) is the nominal contract, but the quirks below reflect real devices.

## Endpoints

| Method | Path | Summary |
|--------|------|---------|
| GET  | `/api/info`    | Full device snapshot (polled by the coordinator). |
| GET  | `/api/battery` | Lightweight battery/liveness probe. |
| POST | `/api/restart` | Reboot the frame. |
| POST | `/api/sleep`   | Enter deep sleep. **Blocked while charging.** |
| POST | `/api/refresh` | Trigger a full E-Ink refresh cycle. |
| POST | `/api/image`   | Upload + render an image (raw octet-stream). Works on fw >= 0.2.28. |
| POST | `/upload`      | Upload + render an image (multipart). Works on every firmware seen. |
| GET  | `/info`        | HTML admin page: panel size + battery health (scraped daily). |
| GET  | `/api/albums`  | Cloud albums, proxied to origin.fraimic.com (needs frame internet). |
| PUT  | `/api/albums/{id}` | Edit one album via the same cloud proxy. |
| GET  | `/test`        | HTML web page with a **factory reset** button (see below). |

### `GET /api/info`
Full device snapshot. Schema varies by firmware (flat vs. nested); the
integration reads it through `normalize_info()` in `coordinator.py`, never raw.

### `GET /api/battery`
Minimal battery status. Used as a cheap liveness/"is it awake yet" probe
(e.g. `_wait_reachable()` polls this after a restart).

### `POST /api/restart`
Reboots the frame. Also used to clear a wedged upload handler (see `/upload`).

### `POST /api/sleep`
Puts the frame into deep sleep → unreachable on the network. Returns
`{"error": "charging_cable_connected"}` and refuses while a charging cable is
connected.

### `POST /api/refresh`
Forces a full E-Ink refresh cycle. Not needed after `/upload` (that renders on
its own); firing one mid-render just gets the connection reset by the busy ESP32.

### `POST /upload` — image upload
`multipart/form-data`, field name `image`, filename `image.bin`,
`application/octet-stream`. Body is a raw headerless Spectra-6 4bpp buffer
(`width*height/2` bytes, capped at 4 MB / `MAX_BIN_SIZE`). Uses a 90 s timeout.

- A successful upload **renders by itself (~20–30 s)** — no follow-up
  `/api/refresh` required.
- **Upload-handler wedge:** after an aborted/interrupted upload the firmware's
  upload handler wedges — `/upload` connections get reset while the rest of the
  API still answers. A restart clears it, so `upload_image(recover=True)`
  restarts + waits + retries once on a connection-level failure.

### `POST /api/image` — image upload (firmware >= 0.2.28)
Raw `.bin` body (same buffer as `/upload`) with
`Content-Type: application/octet-stream` — **exactly** that type; anything else
(including multipart) gets `501 {"error":"unsupported_content_type"}`.

Verified on fw 0.2.28 (build 4654a1d8), physical 13.3" frame:

- Valid body → `200 {"status":"rendering","bytes_received":N}` in ~10 s, then
  renders by itself like `/upload`.
- Undersized body → `400 {"error":"invalid_image_size"}` (instant).
- Wrong/missing `Content-Type` → `501 {"error":"unsupported_content_type"}`.
  With a **large** body the firmware rejects without draining the request and
  the HTTP server goes unreachable for ~6 s afterwards.
- On **fw 0.2.21** this endpoint returned 501 and hung the device 45+ s even
  for octet-stream bodies — that's why the integration gates it on a verified
  firmware version (`firmware_supports_api_image()` in `api.py`, >= 0.2.28)
  and falls back to multipart `/upload` otherwise.

### `GET /info` — HTML admin page
Carries data absent from every JSON endpoint: **physical panel size**
(`13.3" E-Ink` / `31.5" E-Ink`) and **battery health** (charge cycles,
state-of-health %, current draw in mA, temperature in °C). Parsed by
`info_page.parse_info_page()` (defensive, every field optional); the
coordinator scrapes it on the first successful poll, then daily.

### `GET/PUT /api/albums` — cloud album proxy
The frame forwards these to origin.fraimic.com authenticated by its own
device_key, so they only work when the frame has real internet — a LAN-only
frame answers `502 {"error":"server_unreachable","detail":"ESP_ERR_HTTP_CONNECT"}`
(verified on fw 0.2.28). Quirks:

- The cloud PUT does **not** merge the `schedule` object — omitted fields are
  nulled, so always read-modify-write the full schedule shape.
- Album create/delete/device-assignment are not exposed through the proxy —
  app.fraimic.com only.
- Album payloads contain presigned S3 image URLs (~1 h bearer credentials);
  don't persist or expose them.

### `GET /test` — factory reset (web page)
An **HTML page served by the frame** — open `http://{host}/test` in a browser,
not an API call. It exposes a **factory reset** control that wipes the frame's
settings/pairing.

⚠️ **Destructive.** Deliberately **not wired into the integration**; documented
here so it isn't triggered by accident.

## Notes

- All requests are plain `http://` (no TLS, no auth) — LAN only.
- `POST` action endpoints return small JSON bodies; errors carry an `error`
  field (surfaced as `FraimicApiError`).
- Deep sleep manifests as connection errors (`FraimicConnectionError`), which
  the integration treats as "unavailable", not an error to spam.

---

See also [`../fraimic-cloud-api/routes.md`](../fraimic-cloud-api/routes.md) for
the separate `origin.fraimic.com` **cloud** API (accounts, albums, OTA).
