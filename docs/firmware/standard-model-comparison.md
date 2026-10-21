# Standard model comparison and live capture

[Research index](README.md) · [Model metadata and schemas](model-comparison.json)

This page reconciles the 21 October 2026 Standard-frame research handoff with the
Large-frame investigation. The handoff's redacted API trace contains 24 complete
exchanges; its capture report includes device-log results and owner confirmation.
The preserved Standard application hash was checked again when importing this
report. The live tests below were owner-directed vendor-proxy tests on the
Standard frame, not a replay against the Large-frame local emulator.

The earlier static comparison described unfinished setup and untested Standard
TLS acceptance. The later live capture supersedes those two statements:
registration completed and persisted across restart, and the frame accepted the
test chain for its normal API hostname. Neither frame has been flashed.

## Model and application identity

| Property | Standard | Large |
| --- | --- | --- |
| Vendor model | `133` | `315` |
| Live version/build | `0.2.28 / 4654a1d8` | `0.2.29 / f1555ee5` |
| Application bytes | 2,589,216 | 4,123,920 |
| Descriptor version | `v0.2.28` | `v0.2.24-33-gf1555ee` |
| Descriptor build time, zone unspecified | 6 July 2026 17:19:50 | 16 July 2026 10:17:43 |
| Chip / SDK | ESP32-S3 / ESP-IDF 5.4.1 | ESP32-S3 / ESP-IDF 5.4.1 |
| Image flash header | 16 MB, DIO, 80 MHz | 16 MB, DIO, 80 MHz |
| Panel payload | 960,000 bytes | 2,304,000 bytes |
| Controller transfers | 2 × 480,000 bytes | 8 × 288,000 bytes |
| Local method/path pairs | 42 | Same 42 pairs |

Standard SHA-256:
`d31870cca2c6ef7395a80be4466c9c3424867dc42cfa39a34d1c60492f7c5ce7`.
Large SHA-256:
`a75914caba6f5f35936a40e394b1d55eb88de4be4e76aa6d6bdabc061486a64f`.

These are matching vendor application downloads, **not installed-flash dumps or
full backups**. The Standard image passed checksum and appended SHA-256 checks;
no additional Secure Boot v2 signature sector followed its image hash. Bootloader,
partitions, NVS, eFuses, flash encryption and custom-image boot acceptance remain
unproven. Do not infer cross-flash compatibility from a shared chip or SDK.

The Large application is 1,534,704 bytes bigger; its read-only data segment is
1,535,660 bytes bigger, while executable IROM differs by only 816 bytes and
combined IRAM by 32 bytes. This supports a shared software base with substantial
model data/assets, not instruction-by-instruction equivalence. Hardware model
and firmware release differ together, so their effects cannot always be separated.

The preserved metadata maps 19 corresponding functions. The poll paths share 86
referenced strings apart from their model/version literals; selected presign and
finalize paths share 32 and 44 strings respectively. Control-flow inspection
supports a shared cloud contract. Identical routes/strings alone do not prove
all handlers behave identically.

## Keep model renderers and power paths separate

The Standard renderer sends two 480,000-byte blocks. Its resolution command uses
1200 × 800 per controller, consistent with the integration's 1600 × 1200 profile.
Its exact panel part number remains unidentified. Large uses EL315TW1 with a
portrait-native 1440 × 2560 layout and eight padded controller blocks. Packing,
rotation, waveforms, GPIOs and power sequencing belong to the model profile.

The Standard local upload handler rejects lengths above 960,000. A downstream
render-start tolerance of ±1,024 bytes is not a format specification: produce
exactly the model's expected payload. Both local handlers can report `rendering`
before physical completion.

Static power differences also matter: the Standard voltage getter returns the
gauge reading without Large's doubling and has an ADC fallback. Large's examined
path doubles the gauge result and returns zero on gauge failure. Post-update
health accepts 2,000–6,000 mV on Standard and 5,000–9,000 mV on Large; both
pre-update percentage helpers retain the 3,000–4,200 mV calculation and nominal
30% threshold. This supports the documented Large OTA-voltage mismatch, without
establishing its development history or testing a low-battery update.

## Enrollment and setup screens

The trace records these owner-initiated API calls:

| Route | Result |
| --- | --- |
| `GET /api/v1/upload/global/133/create_account?ip=…` | HTTP 200 and `presigned_url` |
| `POST /api/v1/account/setup`, twice | HTTP 200, `success: true`, successful setup message |
| `GET /api/v1/upload/global/133/get_started` | HTTP 200 and `presigned_url` |

Setup sends string fields `email`, `password`, `device_key`, `mac_address` and
`display_type`. Its 764-byte responses contain `success`, `message` and
`device_info`; the latter includes identity, `user_id`, settings, pending
settings, public ID and telemetry. The exact **type-only** response shapes are in
[model-comparison.json](model-comparison.json). Registered/account-created flags
changed false → true and survived restart. Minimum required emulator fields and
complete independent enrollment remain untested.

Both setup-screen URLs pointed to the vendor's S3 bucket. Capturing the URL
response does not establish local caching or offline availability of those
screens.

During setup the UI reported a wrong password, while device logs showed
`mbedtls_ssl_setup` failing with `-0x7F00` before a subsequent sign-in connection.
Espressif identifies that code as SSL allocation failure in its
[Mbed TLS troubleshooting reference](https://docs.espressif.com/projects/esp-techpedia/en/latest/esp-friends/advanced-development/protocol/mbedtls-troubleshooting.html).
Registration had already succeeded; another image connection also hit allocation
failure. This does not independently validate the password or identify the
source of memory pressure. Concurrent downloads, diagnostics and proxy overhead
were not isolated. Inspect the underlying error before interpreting a UI label.

## Public reachability caused a real transfer failure

The existing IoT policy blocked Standard's TCP connection to `8.8.8.8:53`.
The frame treated that as no internet, repeatedly switched APs, and stopped an
otherwise working image download at **556,592 / 960,000 bytes**. An owner-approved
temporary exception for that frame and destination, ordered before the block,
restored internet-available state and stabilized the connection.

This is an observed TCP reachability gate, not an observed Google DNS query.
Changing the API origin alone cannot make the frame fully local. A future fork
needs backend-aware connectivity policy and configurable/local time services.
This Standard observation supports the Large static trace without proving every
Large outage/recovery transition. All temporary exceptions were removed; the
original policy again blocks Standard's probe. No permanent exception was approved.

## Poll and voice observations

Eighteen captured polls were HTTP 200. Idle cadence was about 30 seconds, with
extra checks on taps/restarts. Query fields were `display_type`, `orientation`,
`is_periodic_poll`, `current_version`, `battery_pct`, `wifi_ssid` and `ip`.
Idle results contained false upload, null image/firmware/deadline/account and a
settings object with `style`, `keepAwakeEnabled`, `chargingLedEnabled` and
`voiceRecordingEnabled`. `autoUpdateEnabled` was absent in these responses.
This does not override the static full-snapshot/defaulting behavior or justify
omitting a future deadline in an emulator response.

Voice initially failed before upload because cloud settings disabled recording.
The subsequent generic timeout/no-upload log did not prove a microphone timeout.
The owner enabled voice, the setting was verified and the frame restarted. That
sequence demonstrates a working enabled state, not that restart is always required.

The ensuing vendor-backed workflow completed:

| Stage | Observed result |
| --- | --- |
| Recording | 192,556 WAV bytes: 44-byte header plus 192,512 audio bytes, about six seconds |
| Presign | HTTP 200; 3,553-byte JSON with `success`, `url`, `fields`, `key`, null `upload_id`, `message` |
| Multipart form | Fields included Content-Type, encryption setting, key, access-key ID, session token, policy and signature |
| Direct storage upload | HTTP 204; about 13.1 seconds |
| Finalize | `{device_key,user_id,key,orientation}`; about 26.265 seconds at proxy, about 28 seconds in device measurement |
| Finalize response | HTTP 200; 1,542 bytes with `success`, `message`, null `upload_public_id`, `presigned_url`; **no `status` field** |
| Image download | HTTP 200, all 960,000 bytes; about 90 seconds |
| Display | `Render OK` about 35 seconds later; 0 failures / 3 attempts; owner confirmed the generated image appeared |

The omitted `status` is live evidence for Standard's default-to-completed path.
The direct 204 upload is an additional observed success status; its encrypted
storage response body was not captured by the API proxy. Large's local test
separately established HTTP 200 with an empty acknowledgment and `{}` form fields.
The 3,553-byte vendor presign response fits under the recovered 4,095-byte JSON
read limit, but leaves limited space for added fields.

The slow image transfer bypassed the API proxy. Its bottleneck was not isolated;
do not attribute it to the proxy or generalize it to local delivery. Standard's
`last_refresh` remained null after successful display, independently reinforcing
that maintenance history is not an image acknowledgment.

## Prompt visibility and HA reuse

The API capture did not recover spoken words or the final AI prompt: the recording
went directly to storage over HTTPS, and presign/finalize contained neither.
A subsequent private correlation did identify this exact creation in the
authenticated gallery. The finalize image URL and gallery original share the
same generation directory and non-user UUID, which also matches the audio job's
object key. The gallery record was created at 18:52:44.626 UTC, immediately before
the captured finalize completed at 18:52:44.748 UTC; matching object identity,
not timestamp proximity alone, establishes the link.

That gallery record contains a nonempty transcript and the original 1200 × 1600
PNG. It is the same 4,016,864-byte original used in the verified expired-URL
[refresh test](validation-2026-10-21.md#authenticated-gallery-and-album-reads-c10c12e03).
The API's gallery upload ID is not literally the object-key UUID, so retain an
explicit mapping rather than assuming those identifiers are interchangeable.
No recording was decrypted, and neither transcript text, job identifiers, signed
URLs nor artwork is published here. The final vendor generation prompt remains
unknown; a transcript alone does not establish it.

The owner is interested in prompt visibility. A shared adapter can retain
recording, transcript, interpreted intent, final generation prompt, model/style
and original artwork under one stable job ID, then expose the result in HA's
library and playlists. Keep model-specific packed assets derived from that
canonical original. The local job record is a proposed feature, not recovered
vendor prompt data or an implemented integration.

## Coverage and cleanup

The 24 decoded origin-API exchanges were complete and all HTTP 200: one
create-account asset, two setup requests, one get-started asset, 18 polls,
one presign and one finalize. Direct S3 bodies were not decrypted. AP captures
include DNS/NTP/connection metadata, duplicate interfaces and substantial bulk
traffic omissions; they are not a complete packet record. Diagnostic reads can
keep the device awake, so this is not a battery or ordinary sleep baseline.

The handoff records removal of both NAT redirects, both temporary allow policies
and the generated return policy. The original DNS block was restored to index
10000 with only its pre-existing Large exception; configuration matched baseline
apart from counters. Proxy, sampler, six long AP captures, expiry worker and
task-owned SSH masters were stopped. Owner-enabled voice/keep-awake settings were
preserved. No HA deployment or firmware update occurred. This import made no
additional changes to the Standard frame or its network rules.

Raw flows, logs, recordings, firmware binaries and packet captures remain private.
Only report-derived observations and type-only schemas are published here.
