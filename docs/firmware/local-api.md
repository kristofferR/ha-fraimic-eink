# Local HTTP API and diagnostics

[Research index](README.md)

The app contains **42 method/path registrations**, including onboarding, portal,
diagnostics and the integration-facing API. This is a static registration
inventory for Large 0.2.29, not a claim that every handler was exercised or is
available in every boot state. The [existing frame reference](../frame-api/routes.md)
records observed behavior across several releases.

## Complete registration inventory

`*` below is the registered wildcard, not a literal album identifier. Each row's
handler and registration-record file offset are in
[route-registrations.json](route-registrations.json). Descriptions summarize the
recovered role; they are not complete request schemas.

| Method | Path | Role / effect |
| --- | --- | --- |
| GET | `/complete` | Onboarding completion |
| GET | `/create-account` | Account creation page |
| POST | `/create-account` | Account creation / configuration writes |
| GET | `/sign-in` | Sign-in page |
| POST | `/sign-in` | Authentication / configuration writes |
| GET | `/api/verification-status` | Account verification check |
| GET | `/` | Portal entry page |
| GET | `/scan.json` | Wi-Fi scan results |
| POST | `/connect` | Wi-Fi connection configuration |
| GET | `/hotspot-detect.html` | Captive-portal handling |
| GET | `/generate_204` | Captive-portal handling |
| GET | `/connecttest.txt` | Captive-portal handling |
| GET | `/connect` | Connection page |
| GET | `/wifi` | Portal redirection |
| GET | `/upload` | Upload page |
| POST | `/upload` | Multipart image upload and render |
| GET | `/action` | Portal actions; not a generic read endpoint |
| GET | `/portal` | Portal page |
| GET | `/info` | Detailed HTML device information |
| GET | `/wifi-stats` | Wi-Fi diagnostics |
| POST | `/clear-stats` | Clear diagnostic history |
| POST | `/switch-ap` | Change Wi-Fi/AP selection |
| GET | `/check-internet` | Connectivity diagnostic |
| GET | `/logs` | Password-gated log UI |
| POST | `/logs` | Log access/form handling |
| POST | `/logs/action` | Log controls |
| GET | `/get-started` | Setup page |
| GET | `/test` | Factory-test page or selected diagnostic; see side effects |
| POST | `/test` | Factory-test actions, including reset/update controls |
| GET | `/dev` | Developer-mode page |
| POST | `/dev` | Password-gated vendor environment switching |
| GET | `/battery/status` | Battery status |
| GET | `/api/info` | JSON device snapshot |
| GET | `/api/battery` | Lightweight JSON battery probe |
| POST | `/api/restart` | Restart |
| POST | `/api/sleep` | Request deep sleep |
| POST | `/api/refresh` | Request display refresh |
| POST | `/api/image` | Raw image upload and render |
| GET | `/api/albums` | List albums through cloud proxy |
| POST | `/api/albums` | Create album through cloud proxy |
| PUT | `/api/albums/*` | Update album through cloud proxy |
| DELETE | `/api/albums/*` | Delete album through cloud proxy |

The integration-facing `/api/*` controls use plain HTTP without authentication
in the observed stock interface. Password-gated diagnostics do not make the
entire local server authenticated. Restrict access to the intended LAN; an
emulator should keep its owner/admin interface authenticated and use separate,
device-scoped credentials for frame traffic.

## Diagnostics have side effects

Opening `/test` **without an action** enters factory-test mode at `0x4201ed28`,
starts a roughly ten-minute timeout and changes normal background behavior. It
is unsuitable as a passive liveness check. The page contains controls that can
reset pairing/settings; the POST handler is `0x4201ba9c`.

`GET /test?action=battery` follows a separate read branch and returns voltage,
percentage, charging and available gauge diagnostics. Other GET branches include
touch, microphone statistics and accelerometer diagnostics; some initialize
hardware or alter diagnostic counters. Do not crawl all actions to discover them.
The factory OTA control uses the older update path and registration checks.

`/dev` selects the vendor development environment, not a root shell or configurable
URL. See [identity and mode switching](storage-and-configuration.md).

Logs and `/info` are valuable for build, partition and hardware evidence but may
contain identifying information. Sanitize captures before sharing. The absence
of a local key in a masked JSON field does not mean that the complete credential
is safe to publish elsewhere.

## Image delivery

The preferred verified raw upload on this build is:

```http
POST /api/image
Content-Type: application/octet-stream
Content-Length: 2304000

<exact packed Large-panel bytes>
```

`0x420307f8` receives the body into the shared PSRAM image buffer and calls
`0x4201727c`. The wrapper attempts to save `last_image.bin`, logs any save failure,
and starts rendering. The handler can respond:

```json
{ "status": "rendering", "bytes_received": 2304000 }
```

This confirms the request reached the render-start path, **not** durable storage
or completed physical display. The upper body limit is 2,304,000 bytes. The
downstream size comparison has a ±1,024-byte tolerance, but the earlier cap
rejects the upper half; clients should always produce the exact expected size.
Do not add an extra refresh after a successful image upload.

The older `/upload` endpoint accepts multipart field `image`, filename `image.bin`.
That is different from the cloud voice multipart field `file`, filename
`recording.wav`. Existing [`api.py`](../../custom_components/fraimic/api.py)
already handles version selection and recovery from interrupted local uploads;
reuse it rather than replacing the integration's transport blindly.

The [shared buffer](hardware-and-layout.md#one-psram-buffer-serves-audio-and-images)
and [cache behavior](storage-and-configuration.md#last-artwork) matter when adding
concurrent voice or cloud delivery.

The render WAIT policy runs **after** reception and cache replacement; it does
not prevent an upload from overwriting another user's buffer. Also,
`display.last_refresh` is maintenance history rather than a per-image completion
acknowledgment. See the [rendering trace](rendering-and-concurrency.md).

## Album proxy correction

Static registrations and handlers in this image include create and delete,
in addition to the previously tested GET/PUT pair. For example, `0x42030790`
reads the create body and calls proxy `0x42030064` with `/api/v1/albums` and POST.
These mutations were not live-tested during this investigation.

The common proxy uses the central API base and provisioned device key. Its
availability depends on connectivity and backend authorization; registration
does not prove the backend accepts every operation or payload. The backend
contract and proxy header handling need their own verification before enabling
additional controls. This is not an on-device album store.

## Changes worth exposing in a firmware fork

These are proposals, not additional stock routes:

- Owner-configurable backend URL, trust and local time source, with readable status.
- Recording/rendering/buffer-owner state for scheduler arbitration.
- Content/job identity and separate accepted, cached, rendering and rendered events.
- Read-only partition/security/capability information with credentials excluded.
- A documented recovery/configuration path independent of the selected cloud host.
