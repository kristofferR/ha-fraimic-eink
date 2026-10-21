# Checklist validation, 21 October 2026

[Research index](README.md) · [Checklist](research-todo.md)

This pass combines static analysis of the same Large 0.2.29 image with read-only
owner-account/HA inspection and isolated host fixtures. It did not flash, reset,
change device settings, intercept a new recording, import into the live library
or invoke paid generation. Firmware identity remains the hash in
[firmware-identity.json](firmware-identity.json).

This page covers the initial static/account/host pass. Later USB-powered reads
and owner-directed microphone experiments are recorded separately in
[backend emulation](backend-emulation.md), including a response-length bug found
only after testing the physical upload client.

## HA capability inspection: A01

The installed HA version is 2026.10.2. Complete STT and AI Task entity listings,
the configured Assist pipeline, service schemas and authenticated STT metadata
were inspected. Cloud and Google STT advertise compatible mono 16 kHz/16-bit
formats. No Wyoming/local STT entry was configured. The two configured AI Task
entities have feature mask 3, while image generation requires bit 4.

Result: STT is available as a candidate; no configured image-generation entity
can satisfy `ai_task.generate_image`. Image editing and fully local inference
need provider setup, not an assumption based on a registered service. No STT,
Assist intent, generation or edit operation was executed. The inventory is a
dated deployment observation, not a permanent claim about HA's capabilities.

## Real library/converter experiment: A02/A03

Source checkout: [`a890bf19`](https://github.com/kristofferR/ha-fraimic-eink/commit/a890bf192027503a6789b92de9adb768b61696a7).
The experiment ran on a development host with a temporary directory, a synthetic
PNG and a minimal HA executor/config stub. It used the repository's library
fixture to load the real `FraimicLibrary`, converter, model and filesystem cache.
No frame, vendor account or live HA storage was involved.

Five checks passed:

| Check | Result |
| --- | --- |
| Render under Local delivery option | Original retained byte-for-byte, 2,304,000 panel bytes, no send |
| Same under Cloud delivery option | Same behavior |
| Same under Hybrid delivery option | Same behavior |
| Add the same original twice | Two different IDs and two persisted library entries; deduplication is needed above this method |
| Vary model dimensions, rotation, preview rotation, crop and dither mode | Distinct render cache keys |

Each render case made `async_upload_rendered` fail if invoked. A second render
replaced the converter with a failing sentinel and still returned the cached
result. The Large preview is **720 × 1280**; the initial experiment's full-size
preview assumption was corrected after inspecting the intentional thumbnail
conversion. The final run reported **5 passed in 7.73 seconds**.

The reproduction recipe is: use `tests/test_library_manager.py`'s `library_module`
fixture, supply temporary HA config storage/executor, add a synthetic PNG, call
`async_render_for_entry` with explicit Large parameters, assert the lengths/cache
behavior above, then reload after adding identical originals. Dependencies used
through `uv run --with` were Pillow, NumPy, pytest, voluptuous and resvg_py.

Limitations: parameter resolution was supplied explicitly; real HA config-flow
resolution, cloud clients, scheduler locks, wake-only albums and a new pull adapter
were not exercised. The mode variants show that this render primitive does not
deliver; they do not establish end-to-end delivery-mode integration. A03 remains
open for that integration, and A02 remains open for a real idempotent importer.

## WAV-to-STT fixture: A01/C06

The pure conversion functions from HA 2026.10.2's Google AI
[`helpers.py`](https://raw.githubusercontent.com/home-assistant/core/2026.10.2/homeassistant/components/google_generative_ai_conversation/helpers.py)
were executed with one second of synthetic silence, without importing HA or
calling a provider. Source SHA-256:
`2e561a773b6306533e3ee0aab6555b0e2a7c158682f3e32d5acf5ab17a7da941`.

| Input | Output |
| --- | --- |
| 32,000 raw PCM bytes | 32,044-byte WAV, 16,000 mono samples at 16 kHz |
| That complete WAV passed as PCM | 32,088-byte WAV; original header becomes 22 extra samples |

Assertions checked channel count, sample width, rate, frame count and exact PCM
round trip. This verifies the provider boundary described in [voice](voice.md),
not the physical microphone, tap behavior, maximum duration or recognition quality.
C06 still requires an owner-directed recording.

## Authenticated gallery and album reads: C10/C12/E03

Existing owner credentials were used privately for normal account login. Reads
covered small and maximum-sized gallery pages, an item detail, account device
metadata and albums. Gallery IDs matched list/detail observations; audio and
image upload types were present. One audio item's original downloaded as a PNG.
No image contents, transcript, account/device ID, signed URL or credentials are
included here.

| Read | Result |
| --- | --- |
| Owner Bearer token, gallery list/detail | HTTP 200 |
| Device key as Bearer token, gallery | HTTP 401 |
| Owner Bearer token, account albums | HTTP 200 |
| Device key in album-list path, no Bearer token | HTTP 200; same album IDs in this account |
| Sample signed original | HTTP 200, PNG, 1200 × 1600 |

The observed fields and nullable values are documented in
[cloud protocol](cloud-protocol.md#albums-and-gallery). Original URLs expire;
observed validity was roughly one hour. A successful current download does not
prove retrieval after expiry, indefinite retention, or stable pagination while
new generations arrive. Those cases remain in C10/A02. Album writes remain in C12.

## Static follow-up: C01/C02/C11/C12/R11/S01/D03/N02/H05/H07

The private evidence comprises nine additional Ghidra/reference exports and
matching GNU ESP32-S3 instruction checks, alongside the earlier corpus. New task
entries at `0x42023674` and `0x4202f674` were verified before defining them; the
original 471-function index missed those entries and was not treated as exhaustive.

| Topic | Evidence added |
| --- | --- |
| Selectors and enrollment | Separate dashboard/auth consumers; verification task; identity persistence |
| Poll settings | `user_settings` copy reaches callers with no recovered member application |
| Album proxy | Header/path/body behavior beyond Ghidra's truncated branch |
| OTA | Legacy manifest reads, direct callers, retained forced-version references and counter resets |
| WAN dependency | Monitor intervals, fallback AP/failover behavior and keep-awake effect |
| Rendering | Blocking SPI transactions consume successive chunks of the original shared buffer |
| Local actions | Bare `/action` defaults to reset; test POST upload is a panel image; log reads update activity and expose previous saved logs |
| Build timestamp | Descriptor has no zone provenance; later boot-log timestamp is separately documented in [hardware](hardware-and-layout.md) |

Static completion does not close the corresponding device fault/timing tests.
The separate partition, bootloader/eFuse, recovery, storage-capacity and hardware
questions remain unanswered. Battery work remains deferred by the owner.

## Later awake read: S05/S06/H05/H07

The owner subsequently woke the frame on USB power. Read-only `/api/info`,
`/info`, authenticated `/logs`, `/api/verification-status` and `/api/albums`
were available. Logs were read without clearing them; authentication/read activity
can extend the device's activity timer. Firmware/build remained 0.2.29/f1555ee5.

Observed: encrypted NVS, valid `app1` at `0x4a0000` with 4,718,592-byte capacity,
registered/verified identity, synchronized time, configured `EST5EDT`, CW2217
initialization and existing settings. The log's separate build timestamp includes
`-0400`; the descriptor's timezone remains unknown. The previous saved session's
factory-test timeout must not be mistaken for normal idle-sleep evidence.

This read did not recover the partition table, bootloader/eFuses, whole-flash
encryption, image-filesystem capacity or recovery pads. The enclosure stays closed.
