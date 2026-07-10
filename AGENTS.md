# AGENTS.md — Fraimic E-Ink Canvas (Home Assistant integration)

Home Assistant custom integration (domain `fraimic`, `local_polling`) for the Fraimic E-Ink Canvas — a Spectra 6 (6-colour) e-ink art frame. All code lives in `custom_components/fraimic/`.

## Architecture at a glance

| File | Role |
|------|------|
| `__init__.py` | Entry setup/unload. Builds `FraimicClient` + coordinator, stores `FraimicRuntimeData` on `entry.runtime_data`, forwards platforms `[BINARY_SENSOR, BUTTON, IMAGE, MEDIA_PLAYER, SENSOR]`, registers services. Uses non-fatal `async_refresh()` (not first_refresh) so a sleeping frame doesn't abort setup. |
| `api.py` | `FraimicClient` async aiohttp REST client + error classes. The whole frame API surface. |
| `image_convert.py` | The entire image pipeline (decode → orient → fit → preprocess → OKLab dither → `.bin` pack → PNG preview). Pure/CPU-bound, no HA deps, unit-testable. |
| `services.py` | `fraimic.upload_image` service + `async_render_and_upload()` shared render+upload orchestration. |
| `coordinator.py` | Coordinator (polls `/api/info`), `FraimicRuntimeData` (coordinator, client, `preview_image`, `last_preview`), `normalize_info()` (flat/nested firmware JSON → one shape). |
| `entity.py` | `FraimicEntity` base (device_info, model naming from resolution). |
| `config_flow.py` | Config flow (host/zeroconf, resolution detect/pick) + options flow (per-frame settings). |
| `media_player.py` | Display images via media browser / `play_media`; camera snapshot refresh loop. |
| `image.py` | Write-only `image` entity showing the last-uploaded preview PNG. |
| `sensor.py` / `binary_sensor.py` / `button.py` | Description-driven diagnostic entities + Refresh/Sleep/Restart buttons. |
| `diagnostics.py` | Redacted config-entry diagnostics. |
| `const.py` | All constants: resolutions, palette, dither modes, preprocessing defaults, config/service keys. |
| `tests/test_image_convert.py` | Standalone pipeline tests (no HA import). |

## Frame REST API (`api.py`) — verified on firmware 0.2.21 + 0.2.28

Base `http://{host}`, **unauthenticated**, local HTTP.

- `GET /api/info` — device snapshot (polled). `GET /api/battery` — liveness.
- `POST /api/restart` / `/api/sleep` (blocked while charging) / `/api/refresh`.
- `POST /api/image` — raw `application/octet-stream` `.bin` body; used on firmware >= 0.2.28.
- `POST /upload` — multipart `image` field; fallback for older/unknown firmware.

Hardware quirks the code accounts for:

- **Upload path is firmware-gated** (`client.prefer_api_image`, set by the
  coordinator): fw >= 0.2.28 uses `POST /api/image` octet-stream (structured
  errors: `invalid_image_size`, `unsupported_content_type`); older/unknown fw
  uses `POST /upload` multipart, filename `image.bin`. 90s timeout either way.
  A successful upload renders by itself (~20-30s); no follow-up `/api/refresh`.
- `/api/image` requires `Content-Type: application/octet-stream` exactly —
  multipart or other types get a 501 `unsupported_content_type`, and a large
  rejected body briefly wedges the HTTP server (firmware 0.2.21 wedged hard,
  which is why older firmware stays on `/upload`).
- `upload_image(recover=True)` restarts + retries once on connection-level
  failure (firmware upload-handler wedge).
- Frame is battery-powered; deep sleep = unreachable → entities go unavailable.
- `display.last_refresh` tracks only the *scheduled* cycle, not uploads.
- Resolution is stored per config entry (`CONF_WIDTH/HEIGHT` in `entry.data`).

## Image pipeline (`image_convert.py`)

Entry point:

```python
convert_image(
    raw, *, width, height, fit, rotate, mode, saturation,
    contrast, sharpen, tone, preview, preview_rotate,
) -> (bin, preview_png, resolved_mode)
```

Convenience: `image_to_bin(...)`.

Highest-level reuse: `services.async_render_and_upload(hass, entry, raw, overrides)` —
hand it encoded image bytes; it resolves per-frame options, runs conversion in an
executor, uploads, and updates the preview.

Pipeline:

1. Decode (HEIC/AVIF via pillow-heif)
2. EXIF transpose
3. Flatten alpha on white
4. Rotate
5. `_auto_mode` classify (before fit)
6. `_fit_image`
7. `_preprocess` (autocontrast → tone LUT → contrast → saturation → unsharp)
8. `_render_indices` (sRGB → linear → OKLab, `_gamut_soft_clamp`, dither)
9. `_pack_nibbles`
10. PNG preview

Dither modes (`const.DITHER_MODES`): `auto` (picks FS for photos, Bayer for flat
graphics), `floyd_steinberg`, `atkinson`, `bayer`, `none`.

### `.bin` format (reverse-engineered, NOT row-major)

Raw headerless 4bpp, `width*height/2` bytes. Bottom half of panel first, then top
half; each half column-major, columns left→right scanned **bottom-up**, two
vertically-adjacent pixels per byte (high nibble first). Palette position →
E Ink nibble via `SPECTRA6_PANEL_INDEX = (0x0, 0x1, 0x2, 0x3, 0x5, 0x6)` (0x4 unused).

**height must be divisible by 4.** Buffer capped at `MAX_BIN_SIZE` (4 MB).

Palette is only 6 colours (`SPECTRA6_RGB`): black, white, yellow `#f0e050`,
red `#a02020`, blue `#5080b8`, green `#608050` — *calibrated muted* values,
not primaries.

## Config / options

- Config flow: host (default `fraimic.local`) or zeroconf; resolution auto-detect
  (`FRAME_MODELS`: standard 1600×1200, large 2560×1440) else user picks;
  resolution saved to `entry.data`.
- Options (per frame):
  - `scan_interval` (min 30s)
  - `rotation` (base mount 0/90/180/270)
  - `camera_refresh_interval` (0 or ≥60s)
  - Image defaults: `mode`, `fit`, `saturation`, `contrast`, `sharpen`, `tone`
- Param resolution order: **call override > per-frame option > global default**.
- Options change reloads the entry.

## Scheduling

No playlists. Only recurring push is the media_player camera loop
(`async_track_time_interval` → `_async_camera_tick`; interval =
`CONF_CAMERA_INTERVAL`, 0 = once, STOP cancels). Use this as the template for
any periodic-render feature.

## Testing

`tests/test_image_convert.py` covers only the pure pipeline (loads `const` +
`image_convert` directly, no HA).

Run:

```bash
uv run --with pillow --with numpy --with pytest pytest
```

No tests yet for api/services/config_flow/entities. CI: `.github/workflows/validate.yml`.

## Conventions / gotchas

- Requirements (`manifest.json`): `numpy`, `pillow-heif>=0.16.0`. All numpy/Pillow
  work must run in an executor (it's CPU-bound and blocks the event loop otherwise).
- `normalize_info()` tolerates both flat and nested `/api/info` schemas — read
  frame data through it, never raw.
- Entity availability: frame sleep → `UpdateFailed` → clean unavailable
  (don't spam errors).
- Preview PNGs are rotated by `-base_rotation` so the dashboard matches the wall.
