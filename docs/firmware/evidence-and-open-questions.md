# Evidence, reproducibility and remaining questions

[Research index](README.md)

Research date: **21 October 2026**. Target: one owned Fraimic Large running
**0.2.29 / f1555ee5**. The [identity manifest](firmware-identity.json) pins the
analyzed bytes. These notes do not generalize to the Standard frame or a later
build without comparison.

## Evidence ledger

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| Owner-scoped local status/boot logs | Reported firmware, panel, running app slot and hardware diagnostics | Full flash map, eFuses or actual presence of every probed chip |
| Stock application download | Exact app image, descriptor, six segments and integrity fields | Full backup of bootloader, NVS, partition table or calibration |
| Owner-scoped API interception | Frame accepted a test chain for its normal hostname; ordinary poll completed with HTTP 200 | Arbitrary self-signed trust, disabled hostname verification or custom app boot |
| ESP image parsing/checks | File identity, segment bounds, checksum and appended hash | Boot authorization or a tested recovery path |
| Ghidra function/reference analysis | Data flow, endpoint consumers, settings and state-machine candidates | Perfect types/control flow or execution of every branch |
| GNU Xtensa disassembly with ESP32-S3 configuration | Critical instructions, literal values and comparisons | Physical timing or runtime race outcomes |
| 42 route registration records | Exact method/path/handler associations in this app | Every route available or authorized in every runtime state |
| Public vendor OpenAPI snapshot | Server-advertised fields/endpoints at retrieval time | Fields actually consumed by the frame or owner authorization |
| Unauthenticated gallery request, 401 | Gallery is not openly readable in that request | Successful owner-account import or device-key authorization |
| Host-side low-battery asset decoding | Recovered RLE format consumes all input and yields correct output size/palette | A newly generated asset renders correctly on the panel |
| Integration source inspection | Existing functions to reuse in HA | Implemented emulator, voice backend or new metadata model |

Temporary DNS/DNAT and interception were removed after the owner-scoped test.
No custom app was flashed. Later static passes did not record audio, purchase
generation, change device settings or make additional device/network changes.

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
| “One URL patch makes it offline” | Public TCP connectivity gate, SNTP, web/auth selectors and setup screens remain |
| “All system images are cached” | Wake-up is local; create-account/get-started fetch from the backend in their active branch |
| “Auto-update off prevents an offered update” | The recovered queue/install path does not consult that switch |
| “A small settings object changes only those fields” | It resets omitted booleans to defaults |
| “An idle poll leaves the schedule alone” | Missing/null/invalid/past next-image time clears the saved deadline |
| “Voice timeout submits the recording” | Timeout stops and fails; explicit completion is required |
| “WAV preparation makes a separate copy” | Header is written into the shared audio/image allocation |
| “A finalize job ID can be polled later” | Stock flow requires a ready image URL in a synchronous HTTP 200 |
| “A successful upload means the panel/cache is updated” | It can mean rendering started even if cache saving failed |
| “GET diagnostics are passive” | The `/test` landing page activates factory-test mode |
| “No appended signature means any app boots” | Bootloader/eFuse/security and recovery remain unverified |
| “TLS hostname checking is disabled” | The examined config sets global CA use, not the adjacent skip-CN byte |

## Next investigations, in priority order

| Question | Useful evidence / next experiment |
| --- | --- |
| Can a minimal local protocol adapter satisfy stock parsing? | Host-side HTTP fixtures for poll, presign, upload, finalize and system images; then one owner-directed device round trip |
| How can a custom image be recovered? | Partition map, actual security state, verified recovery entry and controlled rollback behavior |
| What does account-authenticated gallery import return? | One authorized paginated read with secrets/URLs kept private; verify transcript/style/upload identity |
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
