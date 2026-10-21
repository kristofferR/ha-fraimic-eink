# Cloud protocol and local emulator contract

[Research index](README.md)

The first emulator target is an **already-paired frame**. This page describes the
client contract recovered from the app; examples use reserved domains and
placeholders, not credentials or deployable services.

The [bounded backend experiment](backend-emulation.md) now validates local idle
polls, album reads, physical microphone upload and one owner-confirmed panel image.
It also found an upload-response
length bug; follow the [empty acknowledgment requirement](voice.md#upload-acknowledgment-must-have-an-empty-body).

## Backend selection

`0x42017a4c` chooses between `https://origin.fraimic.com` and
`https://dev-api.fraimic.com`. NVS `app_data/server_mode == 1` selects development.
There is no arbitrary URL setting in this selector.

The production string is 26 bytes long at file offset `0x11590`, virtual address
`0x3c101590`. An equal-or-shorter replacement is a possible in-place patch, with
image integrity fields regenerated. This has not been prepared or boot-tested.
Longer, configurable URLs require additional code/storage, not an oversized string
overwrite. See [OTA and recovery](ota-and-recovery.md).

| Caller | Uses the central API base for |
| --- | --- |
| `0x42023bcc` | Global/system-image metadata |
| `0x42023ed4` | Account/device setup |
| `0x4202475c` | Image, settings and firmware polling |
| `0x420266d8` | Voice presign |
| `0x42027380` | Voice finalization |
| `0x42030064` | Album API proxy |

The web-app (`0x42017a64`) and Supabase authentication (`0x42017a7c`) selectors
are separate. Image, audio-upload and firmware URLs come from server responses.
A replacement API host therefore does not automatically replace every host.

The recovered web-selector consumers are the successful sign-in page
(`0x420192c8`) and portal HTML (`0x4201e81c`). They insert a dashboard link:
production `https://app.fraimic.com`, development
`https://d2fz2sijx5cx76.cloudfront.net`. The auth selector feeds the email-verification
task at `0x42023674`: production `https://sclpedxwezoiwzesfdps.supabase.co`,
development `https://mhabnmforgicbwlyudxa.supabase.co`. The development API URL
also appears as a label in `/dev` HTML; that occurrence is not another client.

For already-paired operation, the main dependencies are API requests, the asset
and upload URLs returned by that API, the public TCP probe and SNTP. Independent
enrollment additionally needs an intentional replacement for the auth flow and
dashboard links. These are recovered consumers, not a packet capture proving
every boot-state dependency has been removed.

## Poll

```http
GET /api/v1/upload/check/<device_key>?display_type=315&orientation=portrait&is_periodic_poll=false&current_version=0.2.29
```

The client additionally sends battery percentage, Wi-Fi SSID and, when available,
LAN IP. Some requests include `include_account=true` and OTA result fields.
All three URL formats in `0x4202475c` hardcode `is_periodic_poll=false`; it cannot
identify scheduled wakes versus user activity on this build.

The key in the URL path is a credential. Redact it in application, reverse-proxy
and observability logs. Do not confuse an account-facing device ID or masked info
value with the full provisioned key.

### Successful response fields

| Field | Client behavior |
| --- | --- |
| `has_new_upload` | Boolean pending-image flag; compatibility fallback `has_new_tasks` |
| `presigned_url` | Image URL copied when pending content is true |
| `user_settings` | Serialized into an output buffer; not proof of local application of every setting |
| `device_settings` | Applies a complete four-switch snapshot when an object |
| `firmware` | Nonempty `version` and `presigned_url` queue an update, subject to the recovered guards |
| `next_image_utc` | Future numeric UTC epoch; compatibility fallback `next_scheduled_image_time` |
| `account.email_verified` | Can reconcile an existing registration's verification state |

Illustrative idle response for a device with no active album schedule:

```json
{
  "has_new_upload": false,
  "presigned_url": null,
  "next_image_utc": null,
  "firmware": null
}
```

When content is ready, return `has_new_upload: true` and its packed panel asset
URL. When scheduling is active, return the intended future deadline on **every**
successful poll, including polls without new content. An absent, nonnumeric,
null or past time clears the saved deadline. See [scheduling](boot-and-scheduling.md).

### Settings snapshot semantics

Omitting the entire `device_settings` object preserves current switches. Including
an object invokes `0x420158cc` with defaults for absent/non-boolean members:

| Cloud key | Default within an incomplete object | `/api/info` key |
| --- | --- | --- |
| `voiceRecordingEnabled` | `true` | `settings.voice_recording` |
| `keepAwakeEnabled` | `false` | `settings.keep_awake` |
| `autoUpdateEnabled` | `false` | `settings.auto_update` |
| `chargingLedEnabled` | `true` | `settings.charging_led` |

`{ "device_settings": {} }` resets all four to those defaults. Read existing
preferences where available and send a complete intended snapshot. Unchanged
snapshots avoid the settings-save path. RAM changes precede NVS persistence;
an NVS failure can leave session state different from the next boot's state.

`autoUpdateEnabled=false` does **not** locally block an otherwise accepted
firmware offer in the recovered path. Withhold `firmware` unless deliberately
offering an update. See [update policy](ota-and-recovery.md#update-policy).

### `user_settings` is copied, with no recovered local application

The poll worker serializes this object into a 2,048-byte output buffer at
`0x3fca8c81`. Getter `0x42025da0` copies it to its caller. The recovered callers
are the button-wait path (`0x4201163c`) and main loop (`0x42012810`); neither was
found parsing or applying members of that copy. Main receives at most 511 bytes
plus NUL, and the button path supplies a small scratch destination.

This does not make backend-owned preferences meaningless. It means a setting
such as style can affect server generation without a local parser. Do not assume
that adding a member to `user_settings` creates a firmware setting. The distinct
`device_settings` branch above does apply its switches. Device fixtures and
remaining indirect-reference checks are still tracked in C02/E01.

## System and setup screens

```http
GET /api/v1/upload/global/315/create_account?ip=<frame_ip>
GET /api/v1/upload/global/315/get_started
```

`0x42023bcc` requires HTTP 200 and JSON containing a string `presigned_url`.
It reads at most 2,047 response bytes and rejects a URL that does not fit the
caller's 1,536-byte buffer. Use compact JSON and a short asset URL.

`0x4202a8b8` maps instruction type 1 to `create_account`, type 2 to `get_started`;
type 0 (`wake_up`) has no server key. The dispatcher `0x4202ad38` downloads the
two server-keyed screens whenever it displays them. There is no local cache
fallback in that branch. The account screen adds the current station IP if known.

**Correction to an early hypothesis:** the presence of `system_images/` does not
mean every setup screen is cached. The wake-up image is locally installed; these
two screens depend on the backend in the recovered path. An emulator supporting
onboarding needs corresponding assets or an explicit firmware fallback.

## Enrollment boundary

`POST /api/v1/account/setup` (`0x42023ed4`) sends JSON fields `email`, `password`,
`device_key`, `mac_address` and `display_type`. Its HTTP 200 parser expects a
boolean `success`, optional `message`, and `device_info.user_id` /
`device_info.device_key`. This is not the complete enrollment flow: authentication,
email verification, local configuration persistence and web redirects are separate.

The local create-account and sign-in POST handlers both use account setup and
save identity through `0x42018af0`. Sign-in marks it verified; create-account
starts `0x4202463c` / `0x42023674` to check verification. That task posts
`email`/`password` to the selected auth host's
`/auth/v1/token?grant_type=password`, using the embedded public anonymous-client
key in `apikey` and Bearer headers. The identity NVS record has no password field.
The task temporarily retains credentials in RAM; this is not a password-free flow.

Verification checks for HTTP 200 and a parsed string `access_token`, then saves
verified state and requests the get-started screen. It makes at most 180 attempts,
with five-second delays and a 15-second HTTP timeout. This is not a fixed
15-minute wall-clock deadline: request time adds to the delays. Poll responses
can separately reconcile `account.email_verified`.

Do not forward account passwords to a replacement server as an accidental
consequence of a URL patch. Define an explicit owner-enrollment flow before
supporting unpaired or reset frames. Preserve existing paired state for the first
local-backend experiment. [Configuration notes](storage-and-configuration.md)
describe production/development identity separation and migration.

## Albums and gallery

The frame's local album routes are cloud proxies, not an on-device playlist
database. Supporting them in an emulator is separate from using HA playlists
to answer the image poll. See [all local routes](local-api.md).

Owner-account reads on 21 October 2026 returned HTTP 200 for both gallery pages
and `/api/v1/gallery/<upload_public_id>`. A device key supplied as a Bearer token
returned 401; an earlier request without authentication also returned 401.

Observed items have `upload_id`, `upload_type`, `created_at`, `metadata`,
`transcript`, `style_name`, `original_url`, `orientation` and `crop_params`.
The account contains both `audio` and `image` uploads. Voice items can carry
transcripts; metadata/style may be null. Crop objects include `x`, `y`, `unit`,
`width`, `height`, `orientation` and `display_type`; do not discard their unit.

Pagination returns `page`, `page_size`, `total_count`, `total_pages`, `has_next`
and `items`; the advertised maximum page size is 50. IDs matched between sampled
list/detail reads. One voice original downloaded successfully as a 1200 × 1600 PNG,
separate from the packed panel asset. Its signed URL had about an hour remaining.
Actual retrieval after expiry and long-term retention remain untested. Re-fetch
the item to obtain a current URL; persist originals and deduplicate by
account/upload identity, not the signed URL. No library import was performed.

Both owner-authenticated `GET /api/v1/albums` and a credential-bearing
`GET /api/v1/albums/<device_key>` without a Bearer header returned 200. In this
account they returned the same album IDs, including empty wake-planning albums.
Do not assume this endpoint filters solely to the requesting frame. Observed
albums include `device_assignments` containing `device_id`, interval schedules,
image counts and images. Create/update/delete remain untested; see the
[recovered proxy contract](local-api.md#album-proxy-contract).

## HTTP and TLS requirements

- Use explicit `Content-Length`, compact JSON and short URLs. The voice JSON
  readers skip body reading when fetched length is non-positive.
- Serve final URLs directly. The recovered image downloader and voice JSON paths
  use `esp_http_client_open` / `fetch_headers`; they do not run the automatic
  redirect loop in `esp_http_client_perform`. A redirect accepted by a desktop
  HTTP client is not evidence the frame follows it. Poll/setup/auth paths using
  `perform` must be assessed separately. This distinction follows the matching
  [IDF client implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c);
  controlled device redirect/error tests remain open.
- Serve panel assets as HTTP 200, `application/octet-stream`, exactly 2,304,000
  bytes for this Large build. A PNG/JPEG is not the raw panel buffer.
- The image downloader logs AWS query-field presence but does not require an
  S3-specific URL. A local HTTPS file on the accepted API hostname, without AWS
  query parameters, was downloaded, cached and physically displayed in the
  [one-shot test](backend-emulation.md#one-shot-panel-delivery-c03c09d06).
- The examined clients attach the ESP-IDF CA bundle. Their config byte `0x71`
  enables global CA use; `0x72` is skip-CN and remains zero. This was checked
  against the binary and the [ESP-IDF v5.4.1 header](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/include/esp_http_client.h).
- DNS redirection alone does not make an unrelated certificate valid for the
  vendor hostname. Use deliberately configured hostname/trust for a durable
  custom backend. The earlier test-chain acceptance does not prove acceptance
  of arbitrary self-signed certificates.
- [Connectivity and NTP](boot-and-scheduling.md#offline-dependencies) still need
  attention for WAN-free operation.

For audio endpoint schemas, limits and status handling, see [voice](voice.md).
