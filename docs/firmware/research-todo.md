# Firmware research checklist

[Research index](README.md)

This is the persistent backlog for the explicit unknowns, unverified inferences,
untested behaviors and deferred experiments in the firmware documentation.
Audited on 21 October 2026 against Large 0.2.29 / f1555ee5. Repeated questions
are consolidated under one ID; proposed features are feasibility checks, not
claims that the feature already exists or instructions to implement everything.

Start with local cloud, voice and HA reuse. Recovery findings are prerequisites
for experiments that depend on custom firmware. Battery repair remains deferred
behind the owner's backend priorities.
The owner has explicitly chosen to keep the enclosure closed and focus on backend
emulation. Physical inspection and custom-firmware/recovery experiments remain
deferred; do not repeatedly request board access while pursuing protocol checks.

Check an item only when its linked evidence answers the question. Record firmware
hash, method, result and limitations in the relevant topic page. A confirmed lack
of support is a valid result; a static finding does not close a live-validation
item. Keep private captures and credentials outside the repository.

Method labels: **Static** means binary/source inspection; **Read** means installed
configuration/capability inspection; **Host** means fixtures or a test harness;
**Device** means a controlled physical-frame experiment;
**Account** needs an authenticated owner session; **Hardware** needs physical
identification/access; **Design** means assessing an unimplemented extension.
Device writes, reset, flashing and hardware access are separate experiments,
not actions performed by adding this checklist.

## Latest pass: 21 October 2026

[Validation record](validation-2026-10-21.md) and [live backend pass](backend-emulation.md):
**C09, A01 and H07 completed; 64 items
remain open.** Several open items have substantial new evidence. Completion is
per question, not a count of tool calls or decompiled functions.

| IDs | Progress | Next evidence needed |
| --- | --- | --- |
| C01/C11 | Setup minimum-parser fields, saved-key behavior and sign-in/verification split traced; automatic redirect request/body handling mapped | Independent enrollment, controlled redirect/framing cases and remaining boot dependencies |
| C02/S03 | Five idle polls preserved deadline/switches; I64 deadline and zero cache sentinel traced, including possible old-deadline reload after failed clear | Partial/invalid snapshots, reboot persistence and induced NVS failures |
| C03 | Local panel/TLS controls completed; static downloader length/framing, same-URL retries and short-asset behavior mapped | Device response faults, other TLS consumers and Standard negative controls |
| C05/C06/C07 | Large local 200/empty acknowledgment and successful finalize; Standard vendor 204 upload and finalize without status completed with owner-confirmed generation | Response faults, capture limits, slow/timeout behavior and cancellation |
| C07/C08/D05 | Task creation results are ignored; WAV cleanup does not join/release; cancellation windows, unused finalize status and candidate next-job stale flag traced; five fixture TLS checks passed | Deferred physical cancellation, response/body-read gaps, worker lifetime and two-job validation |
| C09 | Fifteen host checks and one physical recording-to-fixed-image protocol/driver flow completed, including cache save and return to ready | Complete for bounded transport scope; same-card optical refresh was not witnessed, and STT/generation were not invoked |
| C10 | Captured Standard audio job/panel linked to gallery transcript/original; expired URL refreshed to identical PNG bytes; gallery ID differs from object-key UUID | Long-term retention, changing pagination and final vendor prompt availability |
| C12 | Proxy traced; account/device-key reads and actual frame GET against local HTTPS succeeded | Explicit create/update/delete and assignment tests |
| A01 | Installed STT/Assist/AI Task inventory and WAV helper fixture completed | Provider choice/setup belongs to implementation; no image-capable entity currently configured |
| A02/A03 | Five real-library host checks passed; duplicate insertion demonstrated | Persisted import mapping; pull scheduling/locks and no-double-delivery integration |
| R11 | Current/legacy call sites, manifest and forced-version/counter references traced; mode switch's one-poll `0.0.0` override is normally restored before HTTP, but NVS persistence can fail | Host fault fixtures and remaining indirect-reference audit |
| S01/S02 | Large startup retries SNTP five times and can invoke AP failover before the public monitor; callback/RTC flag distinction and allocation-failure path traced; Standard public-probe failure separately observed | Local NTP, cold boot/RTC retention, overlapping synchronization, outage timing and fully offline operation |
| D03/D06/D07 | Normal completion observed; short assets can reach stale-tail rendering or cache save after worker rejection; 1.347 MB free PSRAM cannot hold another full panel buffer | Memory lifetime/fragmentation, induced transfer/size faults and per-image acknowledgment |
| N02/N03 | Application scalar/blob types and sizes mapped; SDK Wi-Fi/PHY namespaces, mode order and unchecked backup/restore operations traced | Remaining SDK/indirect keys, other-build schema, interrupted switching and migration faults |
| N04/N05/N06 | Wake-image version decisions and 8 KiB validation allocation mapped; validation failure can trigger replacement/unlink; version stamp commit is unchecked | Filesystem/allocation faults, custom-artwork persistence and controlled recovery |
| S05/S06 | POSIX parser/default US rules traced; nine parser and eight calendar host cases passed, reproducing stale-DST one-hour target shifts; powered wake/test-timeout observations retained | Physical timezone/DST, stored-schedule recalculation, remaining setter audit and ordinary sleep/wake transitions |
| H05 | `/dev` authentication, action acknowledgments, Wi-Fi form/scan/AP controls and 41 LED records traced; refresh guard uses LED protection and portal reachability does not update the voice gate | Remaining handler schemas, all LED meanings/timing, boot-state and controlled side-effect validation |
| H07 | Separate build-log timestamp has −0400; descriptor still has no zone provenance | Retain descriptor null; do not transfer another timestamp's zone |
| E01/E03 | Missing task entries recovered; restart boundaries/nonreturning flow corrected; consequential time/cancellation branches cross-checked; observed account schema recorded | Remaining incomplete flow and full schema-version comparison |
| E02 | Standard app hash validated; 42 routes and 26 function pairs compared; identical LED records/timezone options and matching calendar/DST/parser branches added to live setup/voice findings | Remaining handler/LED arbitration differences, same-version comparison and other releases |

After the earlier unreachable read, the owner woke the frame on USB. Status/logs,
local-backend polling, microphone transport, an approved test-card display and
the combined voice-to-fixed-image flow were then exercised. The backend
record separates host results, physical observations and incomplete handoffs.
The separate Standard handoff adds owner-directed setup, a complete vendor voice
generation, public-probe failure and cleanup evidence; it does not change the
Large image identity or establish independent local provisioning.
Recovery/security/partition questions still need additional evidence; the stock
app cannot answer them alone. B01–B03 remain deferred.
The owner deferred the physical cancellation experiment. Continue static work;
the prepared fixture is stopped and does not need another recording now.
Batch research and documentation into larger checkpoints. Keep the current
follow-up local; do not push each incremental finding.

## Local cloud and voice

Sources: [cloud protocol](cloud-protocol.md), [voice](voice.md),
[image downloads](image-downloads.md), [local API](local-api.md).

- [ ] **C01 · Static/Host:** Audit every consumer of the API, web and auth selectors,
  redirects and server-supplied URLs. Establish the full hostname/dependency set
  an already-paired local backend must replace.
- [ ] **C02 · Host/Device:** Validate poll parser behavior for settings snapshots,
  missing/invalid fields, schedule clearing and persistence failures. Trace which
  `user_settings` members are actually applied locally rather than merely copied.
- [ ] **C03 · Host/Device:** Verify owner-hosted HTTPS JSON and panel assets, including
  explicit lengths, redirects, response limits and download errors. Test hostname
  and trust behavior with controlled positive/negative certificates; do not infer
  arbitrary self-signed acceptance from the earlier test-chain result.
- [ ] **C04 · Host/Device:** Supply local `create_account` and `get_started` assets;
  verify IP-query handling, format, fetch failures and actual setup-screen behavior.
  Establish what an offline fallback would need.
- [ ] **C05 · Host/Device:** Test multipart voice upload against a plain local HTTP
  service, including empty `{}` fields, required fields, upload tickets, status
  codes, size limits and malformed presign responses. Confirm no S3 service is needed.
  Positive path now reaches the local sink with `{}` fields. Check the discovered
  zero-length upload-acknowledgment requirement separately from positive-length JSON.
- [ ] **C06 · Device:** Verify actual WAV format, duration/size limits, initial tap
  suppression, completion taps, cancellation and deadline behavior with a short
  owner-directed recording. Check the near-60-second boundary separately.
- [ ] **C07 · Host/Device:** Exercise finalize with slow responses, timeout, non-200
  statuses, missing URL, status variants, chunked/missing length, truncated/oversized
  JSON and network retry. Establish end-to-end timeout behavior through the proxy.
- [ ] **C08 · Host/Device:** Trace cancellation through recording, upload, finalize,
  download and rendering. Determine what the backend observes on disconnect and
  what work continues; verify retry/idempotency and stale-result behavior.
- [x] **C09 · Host/Device:** Complete one local end-to-end voice round trip using
  fixture audio and a known panel image first, then one physical tap-to-image flow.
  Separate transport validation from paid generation and provider variability.
  [Host and device evidence](backend-emulation.md#combined-voiceimage-device-result-c09)
  confirms the stock protocol/driver path; identical pixels prevented an
  independently witnessed second refresh. This does not close D06/D07's failure
  and acknowledgment questions.
- [ ] **C10 · Account:** Read a gallery page/item with an owner session; establish
  token versus device-key permissions, actual `upload_type`/metadata/transcript/style
  values, pagination, stable IDs and original availability after URL expiry.
- [ ] **C11 · Static/Host/Device:** Map complete enrollment, verification, web redirects,
  auth dependencies and identity persistence. Determine how independent local
  enrollment could work without unintentionally forwarding account passwords.
- [ ] **C12 · Static/Account/Device:** Verify album proxy headers and authorization,
  create/delete/update payloads and device assignment support. Establish which
  vendor album semantics can map to HA playlists; registration alone is insufficient.

## Home Assistant reuse and proposed capabilities

Sources: [HA roadmap](home-assistant-roadmap.md), [voice integration](voice.md#local-speech-and-ha-integration).

- [x] **A01 · Read/Host:** Inspect the installed HA version and configured STT,
  Assist and AI Task entities. Verify `ai_task.generate_image` availability,
  input/output formats, editing/reference-image support and local-inference options.
- [ ] **A02 · Host/Account:** Validate idempotent gallery import into the library,
  including original retention, transcript/style metadata, pagination, duplicate
  imports and URL expiry. Reuse C10's authenticated evidence.
- [ ] **A03 · Static/Host:** Verify render-without-send reuse, model/orientation/cache
  keys, and integration with existing Cloud/Hybrid, wake-only albums and upload
  locks. Demonstrate that pull delivery does not also cause a local push/redraw.
- [ ] **A04 · Design/Host:** Validate durable voice-job identity, ownership, retries,
  reload recovery, audio retention/deletion, original storage and edit lineage.
  Prove duplicate finalize requests do not create duplicate work or library items.
- [ ] **A05 · Design/Host:** Compare HA-hosted protocol views with a companion service
  using actual TLS/deployment constraints. Check device-scoped authentication,
  upload/download tickets, bounds and log redaction while preserving admin auth.
- [ ] **A06 · Design/Host/Device:** Evaluate recording/busy/cancel/render-result events,
  async jobs that sleep while processing, no-redraw command success, streaming STT
  and automatic end-of-speech. Identify required firmware/protocol changes and
  backward compatibility for each; a feature decision does not require building it.
- [ ] **A07 · Design/Host:** Check that proposed voice creations, image edits,
  dashboard commands, playlist controls and multi-frame scenes can reuse existing
  library/scheduler behavior. Resolve provider capability, ambiguous-current-image
  and UI/interaction choices before implementation.

## Recovery and OTA prerequisites

Sources: [OTA and recovery](ota-and-recovery.md),
[image identity](firmware-identity.json), [hardware layout](hardware-and-layout.md).

- [ ] **R01 · Static/Device:** Recover the complete partition table: bootloader,
  partition metadata, both application slots, OTA data, NVS, image filesystem,
  calibration and other data partitions. Reconcile the observed app1 offset.
- [ ] **R02 · Static/Device:** Establish the actual bootloader configuration and
  boot-selection/validation behavior; distinguish app SDK defaults from this unit.
- [ ] **R03 · Device:** Read and interpret actual secure-boot/eFuse state and image
  authorization requirements. Do not change eFuses to determine their state.
- [ ] **R04 · Device:** Establish flash-encryption state separately from encrypted
  NVS, and determine what form of backup/restore is possible without exposing keys.
- [ ] **R05 · Static/Device:** Determine anti-rollback/security-version policy,
  accepted downgrade conditions and implications for returning to stock.
- [ ] **R06 · Static/Device:** Establish a complete backup/restore strategy including
  provisioning, calibration and original images. Verify backup coverage/integrity
  and restoration prerequisites; the downloaded app alone is insufficient.
- [ ] **R07 · Hardware/Device:** Identify and verify a recovery entry despite the
  absent USB serial interface: actual test points, boot straps/interfaces or a
  supported recovery route, rather than generic ESP32-S3 assumptions.
- [ ] **R08 · Static/Host/Device:** Prepare and review the smallest backend-URL/trust
  candidate, regenerate integrity fields, then determine custom-image boot
  acceptance only after a recovery path is established.
- [ ] **R09 · Host/Device:** Verify pending-validation checks, confirmation timing,
  actual rollback and stock restoration. Include an unreachable configured backend
  and failed changed functionality, not only PSRAM/I2C health.
- [ ] **R10 · Host/Device:** Validate update offers against the disabled auto-update
  preference, repeated/same-version offers, truncation, the three-failure cooldown,
  missing clock, result-report loss and compiled-version/artifact identity mismatch.
- [ ] **R11 · Static/Host:** Trace forced-version bookkeeping and every active OTA
  entry point, including factory controls; establish which newer paths still use
  the older manifest/hash, force-version and statistics mechanisms.
- [ ] **R12 · Host/Device:** Verify direct-download validation, completeness, text
  error rejection, partition-capacity checks and the safety predicate under busy,
  Wi-Fi, time and uptime conditions. Reproduce fault cases in a harness before
  attempting controlled device updates; battery scale is tracked in B02.

## Offline boot, sleep and scheduling

Source: [boot and scheduling](boot-and-scheduling.md).

- [ ] **S01 · Static/Host/Device:** Trace the connectivity manager beyond its cached
  getter. Test backend-up/WAN-down, backend-down/Wi-Fi-up and recovery/failover;
  determine how to replace the public TCP gate without breaking AP recovery.
- [ ] **S02 · Static/Device:** Verify local time-source configuration, DNS/service
  dependencies, unsynchronized cold boot and RTC-preserving sleep. Establish
  offline TLS/time/scheduling behavior, including drift and clock corrections.
  Follow up the separate synchronized/completed/in-progress flags, NTP-triggered
  AP failover and semaphore-allocation/overlapping-wait behavior now mapped in
  [the time-service trace](boot-and-scheduling.md#time-service).
- [ ] **S03 · Host/Device:** Exercise future, absent, invalid, past and failed-poll
  deadlines across reboot. Check persistence and the distinction between clearing
  the schedule and a network failure.
- [ ] **S04 · Host/Device:** Validate the strict 30-second margin, equal deadline
  handling, maintenance/album collisions, long transfer/redraw, overdue five-minute
  retry, missing-album fallback and invalid-time fallback.
- [ ] **S05 · Static/Host/Device:** Validate maintenance calendar calculations,
  default first target, timezone/DST changes and stored schedule limits. Determine
  whether any usable public setter exists for the internal schedule parameters.
  [Timezone and calendar fixtures](boot-and-scheduling.md#timezone-format-and-default-rules)
  now establish the POSIX-only parser and reproduce stale-DST target shifts on
  the host; physical transitions and stored-schedule recalculation remain open.
- [ ] **S06 · Device:** Map actual wake sources and transitions for normal, button,
  charger, maintenance, album, first-setup/storage and factory-test modes. Verify
  HTTP reachability and timeout behavior in each, without treating test-mode sleep
  as evidence of normal idle sleep.
- [ ] **S07 · Host/Device:** Validate a local pull playlist with wake-only scheduling,
  backend outages, changed plans and HA restart; quantify wake latency and battery
  cost. Check offline cached playlists only after N01/N07 establish feasibility.

## Rendering and concurrency

Source: [rendering and concurrency](rendering-and-concurrency.md).

- [ ] **D01 · Static/Host:** Finish the ownership/lifetime map for recording, audio
  transmission, raw/multipart HTTP, cloud downloads, system images, cache I/O and
  rendering, including indirect references and task/mutex boundaries.
- [ ] **D02 · Host/Device:** Reproduce the shared-buffer interference with controlled
  overlapping operations. Record which bytes/operation are affected and when;
  static missing guards alone do not demonstrate a particular runtime failure.
- [ ] **D03 · Static/Host:** Verify SPI/DMA consumption and completion semantics to
  establish when the source bytes can be released. Evaluate exclusive ownership
  versus a real snapshot against measured free memory and fragmentation.
- [ ] **D04 · Host/Device:** Exercise WAIT/DROP, simultaneous producers, stuck worker,
  task-allocation failure and early render failure. Check busy flags, semaphore
  behavior, recording-state query failures and timeout cleanup.
- [ ] **D05 · Host/Device:** Validate voice versus scheduled-content races and every
  cancellation stage, including recording before presign. Check how far HA locks
  and backend holds help and which cases require firmware ownership/events.
- [ ] **D06 · Static/Host/Device:** Trace and inject controller/SPI, BUSY, PMIC and I2C
  failures. Establish watchdog behavior for the power-good wait, recovery and safe
  shutdown; distinguish logged failures from propagated results.
- [ ] **D07 · Host/Device:** Correlate accepted/cached/worker-ended/driver-completed/
  power-safe states with the physical panel. Verify a content-ID result design
  reports errors accurately and does not mistake semaphore release for success.
- [ ] **D08 · Device:** Confirm maintenance-only `last_refresh` behavior across local
  upload, voice, system images, maintenance, errors and reboot. Verify history-ring
  persistence and absence of per-image identity in the exposed field.

## Storage, identity and system artwork

Source: [storage and configuration](storage-and-configuration.md).

- [ ] **N01 · Static/Device:** Establish actual `imagedata` partition size, free space,
  allocation overhead, wear-leveling behavior and practical endurance/write budget.
- [ ] **N02 · Static/Host:** Complete the NVS schema, including value types, defaults,
  namespaces and references omitted from the current table. Map compatibility and
  migration across versions without publishing identity/password values.
- [ ] **N03 · Host/Device:** Verify production/development identity and Wi-Fi isolation,
  legacy-key migration, reset semantics, timezone sharing and interrupted/failed
  saves. Determine exactly what is preserved and what requires reenrollment.
- [ ] **N04 · Host/Device:** Validate mount retries and format-on-failure decisions
  with missing legacy key, NVS read error and filesystem corruption in a disposable
  fixture. Establish which state/artwork survives recovery on the actual layout.
- [ ] **N05 · Host/Device:** Verify partial writes, flush/fsync errors, truncated
  last-image loads and save-failure-with-render behavior. Assess an atomic cache
  replacement/hash design against actual FAT support and available space.
- [ ] **N06 · Static/Host/Device:** Verify custom wake-up artwork feasibility and
  persistence across version changes, missing/truncated/same-size corrupt files,
  resets and cache recovery. Establish the true validation/palette contract.
- [ ] **N07 · Design/Host:** Determine feasible offline playlist capacity, eviction,
  canonical restoration and content deduplication using measured storage. Account
  for system artwork, temporary files and wear before promising multiple images.
- [ ] **N08 · Host/Device:** Test generated low-battery/status RLE artwork, invalid
  palette values and malformed runs; verify actual rendering and preservation of
  last artwork/sys_img state. The existing host decode closes only format recovery.

## Hardware and remaining local interfaces

Sources: [hardware](hardware-and-layout.md), [local API](local-api.md),
[frame API reference](../frame-api/routes.md).

- [ ] **H01 · Hardware:** Identify the microphone's physical part number and verify
  the recovered PDM wiring/configuration against the actual board.
- [ ] **H02 · Static/Hardware:** Identify which accelerometer is fitted, separate
  probe candidates from detected hardware, and verify orientation behavior.
- [ ] **H03 · Static/Hardware:** Determine whether speech/audio output hardware
  exists and is usable; microphone input does not establish speaker capability.
- [ ] **H04 · Static/Host/Hardware:** Determine supported partial-refresh/custom
  waveform modes and their panel/power constraints; do not transfer capabilities
  from another display model without evidence.
- [ ] **H05 · Static/Device:** Map request/response schemas, authentication, boot-state
  availability and side effects for all 42 registrations. Cover action/log/dev/test
  controls and undiscovered setters; validate read-only branches first and track
  mutating/destructive branches as explicit separate experiments. Albums are C12.
  `/dev` authentication is now recovered statically on both builds; its actions
  remain unsubmitted and its storage-failure behavior is not device-validated.
  [Local action ordering](local-api.md#restart-sleep-and-refresh-acknowledgments)
  and the [LED protection latch](led-and-workflow-state.md) are now mapped;
  physical LED timing, remaining state meanings, contended guards and Wi-Fi
  form boundary behavior are untested. Standard table bytes now match; its full
  LED arbitration comparison remains in E02. Wi-Fi scan/escape, AP-switch fault,
  separate reachability and stats-erasure behaviors still need controlled checks.
- [ ] **H06 · Static/Hardware:** Establish current/voltage calibration, fitted battery
  arrangement and hardware measurement accuracy separately from software labels.
- [x] **H07 · Static:** Resolve descriptor build timezone if supporting provenance
  exists; otherwise retain the explicit null/unknown rather than inventing one.

## Deferred battery investigation

Sources: [battery observation](evidence-and-open-questions.md#battery-observation),
[OTA voltage scale](ota-and-recovery.md#apparent-battery-scale-mismatch).

- [ ] **B01 · Static/Device:** Determine the root cause of false cable-connected
  state, including the −50 mA branch, actual plugged/unplugged readings, current
  sign/calibration and resulting sleep decisions. Preserve the owner's deferral
  of the battery fix while investigating backend functionality.
- [ ] **B02 · Host/Device:** Validate the apparent OTA one-cell/two-cell voltage-scale
  mismatch and effective charge protection using controlled inputs/bench conditions,
  without using low-charge flashing as the first validation method.
- [ ] **B03 · Device:** Measure long-term sleep/idle, voice, Wi-Fi recovery, display
  maintenance and local-pull energy use, including cable/LED/keep-awake effects.
  Compare behavior before and after any eventual firmware changes.

## Evidence quality and compatibility

Source: [research method](evidence-and-open-questions.md).

- [ ] **E01 · Static:** Revisit incomplete Ghidra control flow, inferred types,
  function boundaries and indirect references for claims used by implementation.
  Validate consequential instructions with the matching Xtensa configuration.
- [ ] **E02 · Static/Device:** Compare each relevant finding with other firmware
  builds and the Standard model before generalizing. Track hash/version, actual
  hardware, route differences, image packing and timing independently.
- [ ] **E03 · Static/Account:** Reconcile the older repository OpenAPI snapshot,
  the October capture and observed client behavior. Distinguish advertised schema,
  client consumption, account authorization and actually exercised responses.

## Coverage of the existing documentation

This table records the audit scope, not completion of its checks.

| Source | Checklist coverage |
| --- | --- |
| [Index/current boundary](README.md) | C01–C12, R01–R09, E01–E03 |
| [Hardware and layout](hardware-and-layout.md) | R01–R07, D01–D03, H01–H07, E02 |
| [Cloud protocol](cloud-protocol.md) | C01–C05, C10–C12, R08, S01–S04 |
| [Voice](voice.md) | C05–C09, A01/A04/A06, D01–D05 |
| [Image downloads](image-downloads.md) | C03/C04/C07/C08, D03/D05–D07, N05 |
| [Boot and scheduling](boot-and-scheduling.md) | S01–S07, C04/C11, R10/R12 |
| [Storage and configuration](storage-and-configuration.md) | N01–N08, R04/R06, H06 |
| [OTA and recovery](ota-and-recovery.md) | R01–R12, B02 |
| [Local API](local-api.md) | C12, H05, D01/D02/D04/D07, A05/A06 |
| [LED and workflow state](led-and-workflow-state.md) / [records](led-states.json) | H05, A06, D01/D02/D07, E01/E02 |
| [Rendering and concurrency](rendering-and-concurrency.md) | D01–D08, N05, B03 |
| [HA roadmap](home-assistant-roadmap.md) | A01–A07, C01–C12, S07, D05/D07 |
| [21 October validation](validation-2026-10-21.md) | A01–A03, C01/C02/C06/C10–C12, R11, S01, D03/D06, N02, H05/H07, E01/E03 |
| [Live backend emulation](backend-emulation.md) | C02/C03/C05–C07/C09/C12, D03/D06/D07, S05/S06, H05/H07, E01 |
| [Standard comparison and model schemas](standard-model-comparison.md) | C01/C03–C07/C10/C11, S01, D07, H03/H05, B03, E02/E03 |
| [Evidence and open questions](evidence-and-open-questions.md) | All groups, especially B01–B03 and E01–E03 |
| [Route metadata](route-registrations.json) / [address map](address-map.json) | H05, E01/E02, B01 |
| Existing [local](../frame-api/routes.md) and [cloud](../fraimic-cloud-api/routes.md) API references | C12, H05, E02/E03 |

Explicit fields in [firmware-identity.json](firmware-identity.json):

| Unresolved field | Task |
| --- | --- |
| `full_partition_table` | R01 |
| `bootloader_configuration` | R02 |
| `secure_boot_efuses` | R03 |
| `flash_encryption_state` | R04 |
| `anti_rollback_state` | R05 |
| `physical_recovery_entry` | R07 |
| `custom_image_boot_acceptance`, `verified_custom_boot: false` | R08/R09 |
| `imagedata_capacity` | N01 |
| `descriptor_build_timezone: null` | H07 |

Add newly discovered unknowns here with a stable ID and a link to their evidence.
Do not remove an uncertainty from a topic page simply because it has a checkbox.
