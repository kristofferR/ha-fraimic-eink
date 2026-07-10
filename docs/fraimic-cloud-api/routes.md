# Fraimic Cloud API — route reference

Backend host: `https://origin.fraimic.com` (FastAPI). Captured 2026-07-07 from the public `/openapi.json`.

Auth: Supabase JWT `Authorization: Bearer <access_token>` for account routes; device routes use `device_key`.

## Firmware / OTA mechanism

There is **no dedicated firmware route**. OTA is piggybacked on the device's poll endpoint:

```
GET /api/v1/upload/check/{device_key}?current_version=<ver>&display_type=133&is_periodic_poll=false&orientation=portrait
```

Description (from the spec): *"Also checks for firmware updates if current_version is provided. Called by ESP32 to see if there's new content to display or firmware to update."*

The `CheckUploadResponse` carries a `firmware` object → **`FirmwareInfo { version, presigned_url }`**. The `presigned_url` is a short-lived S3 URL to the `.bin` in the private bucket **`fraimic-prod-firmware`** (sibling of `fraimic-prod-user-files`; both `403` on anonymous access — no public listing/download).

To pull a specific firmware you only need one call:
```
curl "https://origin.fraimic.com/api/v1/upload/check/<DEVICE_KEY>?current_version=0.0.1&display_type=133"
# → .firmware.presigned_url  → curl that URL -o firmware.bin
```
Pass a low `current_version` (e.g. `0.0.1`) to force the latest to be offered.

**Blocker:** `{device_key}` is the device's provisioned secret. It is **masked** (`...<tail>`) on every accessible surface — local `/api/info`, the web app bundle (0 references; app targets frames by `device_id`), and the account API. `device_id` is rejected (`{"detail":"Device not found"}`). The full key is only in the frame's password-gated **Info** logs, on a physical sticker/QR, or from Fraimic support.

---

The account/web API itself exposes **no** firmware route; the OTA path above is the only one.

| Method | Path | Summary |
|--------|------|---------|
| GET | `/` | Health Check |
| POST | `/api/v1/account/device-name` | Update Device Name |
| GET | `/api/v1/account/devices` | Get User Devices |
| POST | `/api/v1/account/settings` | Update Device Settings |
| POST | `/api/v1/account/setup` | Setup Device |
| GET | `/api/v1/albums` | Get Albums |
| POST | `/api/v1/albums` | Create Album |
| DELETE | `/api/v1/albums/{album_id}` | Delete Album |
| PUT | `/api/v1/albums/{album_id}` | Update Album |
| DELETE | `/api/v1/albums/{album_id}/{device_key}` | Delete Album For Device |
| GET | `/api/v1/albums/{device_key}` | Get Albums For Device |
| POST | `/api/v1/billing/stripe/webhook` | Stripe Webhook |
| GET | `/api/v1/discover` | Get Discover Artworks |
| POST | `/api/v1/discover/send-to-canvas` | Send Discover Artwork To Canvas |
| GET | `/api/v1/discover/{source}/{source_object_id}` | Get Discover Artwork |
| GET | `/api/v1/gallery` | Get Gallery |
| GET | `/api/v1/gallery/{upload_public_id}` | Get Gallery Image |
| POST | `/api/v1/upload/audio/finalize` | Finalize Audio |
| POST | `/api/v1/upload/audio/presign` | Presign Audio |
| GET | `/api/v1/upload/check/{device_key}` | Check For Upload |
| GET | `/api/v1/upload/global/{display_type}/{key}` | Get Global Image |
| POST | `/api/v1/upload/image/lock-to-device` | Lock Image To Device |
| POST | `/api/v1/upload/image/presign` | Presign Image |
| PUT | `/api/v1/upload/image/refresh` | Refresh Image |
| DELETE | `/api/v1/upload/images` | Delete Images |
