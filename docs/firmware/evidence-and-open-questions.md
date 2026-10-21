# Evidence, reproducibility and remaining questions

[Research index](README.md)

Research dates: **21–22 October 2026**. Target: one owned Fraimic Large running
**0.2.29 / f1555ee5**. The [identity manifest](firmware-identity.json) pins the
analyzed bytes. A separate [Standard comparison and live capture](standard-model-comparison.md)
now covers 0.2.28 / 4654a1d8. Model-specific observations remain scoped to their
identified builds; shared routes and SDK version do not establish full equivalence.

## Evidence ledger

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| Owner-scoped local status/boot logs | Reported firmware, panel, running app slot and hardware diagnostics | Full flash map, eFuses or actual presence of every probed chip |
| Stock application download | Exact app image, descriptor, six segments and integrity fields | Full backup of bootloader, NVS, partition table or calibration |
| Owner-scoped API interception | Frame accepted a test chain for its normal hostname; ordinary poll completed with HTTP 200 | Arbitrary self-signed trust, disabled hostname verification or custom app boot |
| Standalone local HTTPS fixture | Five physical-frame idle polls and an unchanged album GET succeeded without upstream forwarding | Complete offline cloud, image delivery, new enrollment or durable album state |
| Owner-directed local microphone upload | Empty presign fields and ordinary HTTP multipart delivered a valid mono 16 kHz/16-bit WAV | Successful generation, display, all capture limits or all response variants |
| Positive-length upload acknowledgment | HTTP 200 plus a 15-byte body was rejected; GNU trace shows body length treated as an error code | A transport failure or need for S3 storage |
| Fixed-card poll and voice experiments | Poll image visually confirmed; local voice flow completed through download, driver refresh, cache save and ready | STT/generation, distinct pixels in the repeated-card voice test, durable job replay or a reliable render acknowledgment |
| Large negative TLS controls | Poll rejected untrusted and wrong-host certificates; matching-profile correct-name control worked | Every HTTP consumer, revocation/expiry handling or Standard negative cases |
| Standard live vendor-proxy capture | Test-chain acceptance, successful setup surviving restart, HTTP 204 upload and finalize without status; generated image confirmed by owner | Independent local provisioning, recovered prompt text or custom firmware boot |
| Standard blocked reachability probe | AP failover and interrupted download; scoped exception restored operation | A fully offline backend or every Large outage/recovery transition |
| ESP image parsing/checks | File identity, segment bounds, checksum and appended hash | Boot authorization or a tested recovery path |
| Ghidra function/reference analysis | Data flow, endpoint consumers, settings and state-machine candidates | Perfect types/control flow or execution of every branch |
| GNU Xtensa disassembly with ESP32-S3 configuration | Critical instructions, literal values and comparisons | Physical timing or runtime race outcomes |
| Enrollment and HTTP static follow-up | Setup field consumption, saved request key, sign-in verification/timezone behavior, redirect replay and shared JSON accumulator | Independently provisioned local frame, induced NVS faults, live redirect/framing errors or a reproduced concurrency failure |
| Cancellation lifetime and offline-time follow-up | Unchecked worker creation, non-owning WAV cleanup, candidate stale cancellation, recovered background initialization and SNTP-triggered AP failover | Physical cancellation across jobs, induced allocation failures, overlapping time-sync calls or WAN-free cold boot |
| Developer-mode static follow-up | Shared embedded password comparison on both builds; Large form authentication, Wi-Fi backup/restore, restart, setup-asset cleanup and one-poll version override | A submitted mode change, new local-server setting, working staging account or fault-tolerant recovery |
| Startup-artwork static follow-up | Version-dependent adoption/replacement, 8 KiB read-validation allocation, non-atomic rewrite/unlink and unchecked version commit | Installed custom wake artwork, fault injection, palette safety or upgrade persistence |
| Image-download static follow-up | Header/status/length checks, zero-length reads, consecutive-stall handling, same-URL retries, render-size tolerance and cache ordering | Device response-fault tests, observed stale pixels, induced cache corruption or all Standard equivalents |
| NVS schema follow-up | Scalar/blob types, record sizes, permissive length handling, schedule cache sentinel, SDK Wi-Fi and PHY namespaces | Installed NVS contents, complete SDK schema, migration success, storage-fault injection or other-build compatibility |
| Calendar/timezone static and host follow-up | Actual parser's POSIX/default-US branches; nine parser cases and eight calendar cases, including stale-DST one-hour shifts | Execution of firmware time code, physical wake timing, full timezone database support, stored-schedule recalculation or exact toolchain revision |
| Local-control and LED static follow-up | Response/action ordering, pending sleep, recording/LED guard behavior, Wi-Fi form byte limits and all 41 LED records | Submitted control faults, physical LED timings, comprehensive buffer arbitration or all Standard equivalents |
| Standard calendar/table comparison | Byte-identical LED records and timezone select; matching lookup, calendar caller, DST-correction and POSIX-parser branches | All LED arbitration paths, physical DST/wake/LED timing or general firmware equivalence |
| Wi-Fi handler follow-up | Separate portal TCP test, blocking scan, AP-switch/save ordering and unchecked stats erase | Controlled scan/connectivity faults, AP changes or successful persistent history erasure |
| HTTP-server and factory follow-up | Actual server configuration, shared task, per-group registration failures, teardown wait, factory query fallthrough and microphone/control semantics | Physical concurrency, socket/heap faults, factory-mode validation or a streaming-audio endpoint |
| Poll parser static and host follow-up | 25 cases against pinned cJSON/selected caller rules; precedence, permissive parsing and different error-versus-empty-response state effects | Xtensa execution, full library equivalence, HTTP faults on the device, NVS persistence or actual recording interruption |
| Direct OTA static follow-up | Request-header MIME-check mistake, length-bounded read loop, post-write timeout and sequential erase before image-magic validation | A flashed image, observed flash corruption, device security state, successful rollback or a recovery path |
| Album-proxy static and host follow-up | 19 pinned-cJSON cases, permissive body transformation, first-only duplicate replacement, ID truncation/query stripping and response-failure translation | Vendor mutation authorization, transaction success, device transport faults or a deployed HA playlist adapter |
| Diagnostic-storage static follow-up | Fixed detail cookie, visibility classes, 64 KiB whole-history reset, truncation/mutex losses and unchecked single-snapshot persistence | Live bypass/clear behavior, measured log-loss rates, filesystem faults, panic persistence or complete capture |
| Orientation static follow-up | Fixed software sensor target, ineffective alternative detection, two-way absolute-axis comparison/error fallback and post-upload voice sampling | Physical part marking, four-way mounting, actual motion/read faults or sample coherence |
| Standard orientation/album comparison | Matching decoded sensor candidates, relevant orientation/caller branches and album-body transformation structure | Physical sensor equivalence, execution of host fixtures on Xtensa or all proxy/error paths |
| Voice response static and host follow-up | 12 actual-SDK-reader/parser cases with scripted transport; partial-prefix acceptance, read-cap behavior and per-read timeout scope; separate static presign zero-read hazard | Device response faults, real elapsed waits, TLS, full firmware execution, outer task cleanup or watchdog behavior |
| Task-watchdog static follow-up | Actual startup values, idle subscriptions, renderer unsubscribe before long panel work and non-panic timeout branch | An induced hang, guaranteed restart, interrupt-watchdog coverage, hardware fallback or complete recovery |
| Conditioning static follow-up | Full-panel MIN/MID clear sequence, 288 KB temporary allocation, 12/48-hour selection, unconditional MID success and shared timestamp writes | Partial-refresh/custom-waveform support, physical conditioning timing/results, panel requirements or power-fault recovery |
| Account-response ownership follow-up | Stack/global/heap backing stores, conditional verification/poll exclusion, duplicate verification starter, stale-pointer exits and unescaped verification JSON | An observed concurrency/memory fault, independently provisioned frame or explanation of the earlier TLS allocation failure |
| Instruction-task follow-up | Metadata reader contract, copied 8-byte context, heap/creation retries, two-minute Get Started polling hold, shared-buffer writes before arbitration and 90-second global completion wait | A tested timeout/collision, reliable per-image completion, offline enrollment or Standard task equivalence |
| 42 route registration records | Exact method/path/handler associations in this app | Every route available or authorized in every runtime state |
| Public vendor OpenAPI snapshot | Server-advertised fields/endpoints at retrieval time | Fields actually consumed by the frame or owner authorization |
| Owner gallery list/detail and original reads | Token-authenticated schema, nullable fields and an available original; after expiry, refreshed same-item URL returned identical bytes | Implemented import, indefinite retention or stable pagination under concurrent additions |
| Gallery permission comparisons | No-auth and device-key Bearer requests returned 401; owner token returned 200 | Every alternative authentication mechanism |
| Account/device-key album reads | Both listing paths worked; assignment/schedule fields observed | Create/update/delete permissions or payload acceptance |
| Installed HA capability reads | Configured STT/Assist and lack of an image-capable AI Task entity on HA 2026.10.2 | Provider quality, local inference or generation/edit success |
| Five isolated library checks | Original retention, render/cache without send, cache-key distinctions and duplicate insertion | A new pull adapter's scheduling/delivery behavior |
| Actual HA Google helper with synthetic PCM | Complete WAV must be parsed before this raw-PCM boundary | Physical recording format or transcription quality |
| Host-side low-battery asset decoding | Recovered RLE format consumes all input and yields correct output size/palette | A newly generated asset renders correctly on the panel |
| Integration source inspection | Existing functions to reuse in HA | Implemented emulator, voice backend or new metadata model |

Temporary DNS/DNAT and interception were removed after each bounded experiment.
No custom app was flashed. The Large [backend passes](backend-emulation.md) used
frame-only routing, owner-directed recordings and approved fixed-card refreshes,
without transcription, AI generation or device-setting mutation. The separate
Standard capture forwarded vendor responses unchanged; the owner completed
setup, enabled voice/keep-awake and requested a real vendor generation. Those
owner-selected settings were preserved when the capture network rules were removed.
The [follow-up validation record](validation-2026-10-21.md) distinguishes owner
cloud reads and host fixtures from physical-device tests.
The [22 October continuation](validation-2026-10-22.md) adds static and host checks
without physical-device experiments.

## Method and private artifacts

The private working set contains the stock app, a synthetic ELF, disassembly,
471 indexed application functions, selected Ghidra exports, literal/reference
tables, logs and a server schema snapshot. These artifacts are deliberately not
copied wholesale into this repository: captures can contain credentials and
identifiers, and the vendor binary embeds artwork and web resources.

The repository instead includes:

- [Image identity and segment metadata](firmware-identity.json).
- [42 route registrations](route-registrations.json), with file offsets for records.
- [Selected addresses and roles](address-map.json), with analytical names.
- Endpoint shapes, limits, call relationships and important unknowns in the linked pages.

To reproduce static work with a legitimately obtained matching image:

1. Verify its length and SHA-256 against the manifest before applying any address.
2. Parse the ESP image's 24-byte header and six segment headers. Each segment
   header has little-endian 32-bit load address and length, followed by its bytes.
3. Map segments at their declared virtual addresses in an Xtensa analysis project.
   Preserve the untouched app separately; the analysis ELF is not an update image.
4. Recover HTTP registration records and start with the selected caller addresses.
5. Resolve `l32r` literal loads, pointers and direct call references, not just strings.
6. Cross-check consequential comparisons, offsets and branch conditions in a GNU
   Xtensa disassembler configured for ESP32-S3 before drawing conclusions.

Example bounded disassembly, using locally installed toolchain paths:

```sh
XTENSA_GNU_CONFIG="/path/to/lib/xtensa_esp32s3.so" \
  "/path/to/xtensa-esp-elf-objdump" -d \
  --start-address=0x42015de8 --stop-address=0x42015f2c \
  "/path/to/stock-symbolized.elf"
```

Ghidra's generic Xtensa language can miss ESP32-S3 instructions such as `SALT` /
`SALTU`, truncate control flow or infer the wrong aggregate return type. The wake
selector is a concrete example: treating its multi-register structure as a scalar
loses information. GNU decoding without the matching core configuration can also
mislabel these instructions. Linear disassembly starting in padding can become
misaligned; begin at a confirmed function address.

The DROM/IROM mappings in [hardware](hardware-and-layout.md#address-translation)
translate virtual addresses into app-file bytes. Addresses in tables may be code,
data, literals or call sites; use the manifest/map's kind, not appearance alone.

### Reproducing the RLE check

Extract the half-open DROM range `[0x3c372e18, 0x3c3a7b56)` with the DROM mapping.
Expand `(color, count)` byte pairs row by row: 8 controllers × 720 rows × 800 pixels.
Reject zero counts, input exhaustion and a run that crosses a row. Pack adjacent
pixels high nibble first. Require consumption of all 216,382 input bytes and
production of 2,304,000 output bytes; compare the output hash in the manifest.
This check can run entirely on the host without sending anything to the frame.

## Corrections to tempting assumptions

| Assumption | Evidence-backed correction |
| --- | --- |
| “One URL patch makes it offline” | Public TCP gate, SNTP-triggered AP failover, web/auth selectors and setup screens remain |
| “A rejected update leaves both slots intact” | Sequential OTA can erase inactive-slot sectors before rejecting invalid magic; abort frees context without restoring flash |
| “A retained RTC clock is enough for normal scheduling” | Recovered initialization waits for its separate SNTP-set validity flag; absent validity takes fallback scheduling |
| “The frame accepts HA's IANA timezone name” | Its POSIX parser does not resolve `Europe/Oslo`; this input leaves UTC offsets, while empty application configuration selects `EST5EDT` |
| “03:00 maintenance stays at 03:00 across DST” | The caller retains the current DST flag; controlled host cases shifted the target to 04:00 in spring and 02:00 in autumn |
| “All system images are cached” | Wake-up is local; create-account/get-started fetch from the backend in their active branch |
| “Auto-update off prevents an offered update” | The recovered queue/install path does not consult that switch |
| “A small settings object changes only those fields” | It resets omitted booleans to defaults |
| “An idle poll leaves the schedule alone” | Missing/null/invalid/past next-image time clears the saved deadline |
| “Voice timeout submits the recording” | Timeout stops and fails; explicit completion is required |
| “Any 2xx audio-upload response succeeds” | The header-reader result is wrongly treated as an error code; use an empty acknowledgment |
| “WAV preparation makes a separate copy” | Header is written into the shared audio/image allocation |
| “A finalize job ID can be polled later” | Stock flow requires a ready image URL in a synchronous HTTP 200 |
| “Finalize's timeout is a total request deadline” | Its configured timeout is reused per transport read; a separate outer task wait has different cleanup semantics |
| “Parsed voice JSON proves the response arrived completely” | The caller parses one bounded read without comparing it to the declared length; a partial HTTP body can contain an accepted JSON prefix |
| “A successful upload means the panel/cache is updated” | It can mean rendering started even if cache saving failed |
| “Download complete means a complete panel image” | HTTP length can match a short asset; later worker rejection does not reliably stop cache replacement |
| “A retry resumes the image or renews its ticket” | The recovered poll/voice loops reuse the same URL and restart from byte zero |
| “The render copy creates an independent snapshot” | Its display pointer aliases the same audio/image allocation |
| “WAIT protects incoming image bytes” | Raw HTTP receives into shared memory before the render wait |
| “Completion signal or last_refresh acknowledges my image” | The signal also follows errors; last_refresh is maintenance history |
| “The task watchdog bounds a stuck panel refresh” | The renderer unsubscribes before the long panel sequence; idle supervision and the non-panic startup policy do not provide that deadline |
| “`last_sleep_ts` measures only the previous sleep entry” | Conditioning can also advance it before artwork transfer, including after errors that MID logs but suppresses |
| “Refresh's busy guard owns the image buffer” | It reads recording state and an LED protection latch; both getters return false on mutex acquisition failure |
| “GET diagnostics are passive” | `/test` activates factory-test mode; bare `/action` defaults to reset |
| “HA exposes generate_image, so a provider is ready” | The installed entities lack the image-generation feature bit |
| “Adding the same original imports idempotently” | The library creates a second item; an importer needs a stable upstream-ID mapping |
| “WAV metadata means send a complete WAV to every STT provider” | This version's Google provider wraps raw PCM, so forwarding a RIFF header nests it |
| “No appended signature means any app boots” | Bootloader/eFuse/security and recovery remain unverified |
| “TLS hostname checking is disabled” | Static config leaves skip-CN zero; Large's wrong-name live test failed and matching-profile correct-name control succeeded |

## Next investigations, in priority order

The complete, actionable backlog is the [research checklist](research-todo.md).
It covers the unresolved statements throughout all firmware pages and the identity
metadata, including hardware, recovery, live validation and proposed capabilities.
The table below remains a short priority overview.

| Question | Useful evidence / next experiment |
| --- | --- |
| Can a minimal local protocol adapter satisfy stock parsing? | Poll, album and voice-to-fixed-image transport succeeded; test response faults, durable jobs, independent enrollment and offline dependencies |
| How can a custom image be recovered? | Still requires partition/security/recovery evidence; hardware inspection deferred under the closed-enclosure preference |
| Will gallery import remain reliable? | Reads now work; test expired URLs, retention, pagination changes and persisted deduplication |
| Do current album create/delete handlers work end to end? | Verify proxy auth and payload semantics before owner-directed mutations |
| Which paths own the shared buffer concurrently? | Trace local upload, background download, recording and renderer locks; instrument ownership in a test build |
| Can WAN-free cold boot work reliably? | Local backend/time support and explicit cold-boot/outage test, not only RTC-preserving sleep |
| How much image cache can be retained? | Real partition/filesystem capacity, system-image overhead, write policy and endurance |
| Can display completion be observed accurately? | Driver busy/power-down completion traced to a content-ID event; correlate with the physical panel |
| Which boot-time checks actually cause rollback? | Instrumented pending-validation test with a known recoverable image |
| Can offline playlists avoid unnecessary writes/redraws? | Content identity, cache capacity and scheduler tests after recovery is established |

Additional unresolved details include the physical microphone part number,
accelerometer model, alternative panel refresh modes, current calibration,
complete factory-reset/mode-migration semantics, and long-term battery behavior.
Absence of a discovered interface is not proof that no such interface exists.

## Battery observation

The original live investigation saw an unplugged frame report a connected cable,
with roughly 35–40 mA discharge and sleep blocked. Static cable detection at
`0x42029ed0` includes a branch around a −50 mA threshold that merits further work.
This is a symptom and candidate explanation, not a completed root-cause finding.
The owner deferred the battery fix in favor of firmware/backend understanding.

The independent OTA voltage-scale mismatch is documented in
[OTA and recovery](ota-and-recovery.md#apparent-battery-scale-mismatch). Neither
finding was verified by changing firmware or attempting an update at low charge.

## External references

The app binary is the primary evidence for version-specific behavior. External
references explain SDK types and integration protocols:

- [ESP-IDF v5.4.1 HTTP client configuration](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/include/esp_http_client.h)
  and [implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c).
- [ESP-IDF v5.4.1 PDM input configuration](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_driver_i2s/include/driver/i2s_pdm.h).
- [ESP-IDF v5.4.1 OTA API](https://docs.espressif.com/projects/esp-idf/en/v5.4.1/esp32s3/api-reference/system/ota.html).
- [HA Assist pipeline protocol](https://contributors.home-assistant.io/core/internals/assist-pipelines/)
  and [STT entity formats](https://contributors.home-assistant.io/core/entities/stt/).
- [Vendor OpenAPI](https://origin.fraimic.com/openapi.json), retrieved 21 October 2026;
  the older [repository snapshot](../fraimic-cloud-api/openapi.json) has a different
  capture date and should not be assumed identical.

When updating this directory, record the new firmware/schema identity and retain
the distinction between an advertised server feature, a recovered client branch
and a successful physical-device experiment.
