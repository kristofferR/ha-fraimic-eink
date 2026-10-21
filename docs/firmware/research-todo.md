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

## Local cloud and voice

Sources: [cloud protocol](cloud-protocol.md), [voice](voice.md),
[local API](local-api.md).

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
- [ ] **C06 · Device:** Verify actual WAV format, duration/size limits, initial tap
  suppression, completion taps, cancellation and deadline behavior with a short
  owner-directed recording. Check the near-60-second boundary separately.
- [ ] **C07 · Host/Device:** Exercise finalize with slow responses, timeout, non-200
  statuses, missing URL, status variants, chunked/missing length, truncated/oversized
  JSON and network retry. Establish end-to-end timeout behavior through the proxy.
- [ ] **C08 · Host/Device:** Trace cancellation through recording, upload, finalize,
  download and rendering. Determine what the backend observes on disconnect and
  what work continues; verify retry/idempotency and stale-result behavior.
- [ ] **C09 · Host/Device:** Complete one local end-to-end voice round trip using
  fixture audio and a known panel image first, then one physical tap-to-image flow.
  Separate transport validation from paid generation and provider variability.
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

- [ ] **A01 · Read/Host:** Inspect the installed HA version and configured STT,
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
- [ ] **S03 · Host/Device:** Exercise future, absent, invalid, past and failed-poll
  deadlines across reboot. Check persistence and the distinction between clearing
  the schedule and a network failure.
- [ ] **S04 · Host/Device:** Validate the strict 30-second margin, equal deadline
  handling, maintenance/album collisions, long transfer/redraw, overdue five-minute
  retry, missing-album fallback and invalid-time fallback.
- [ ] **S05 · Static/Host/Device:** Validate maintenance calendar calculations,
  default first target, timezone/DST changes and stored schedule limits. Determine
  whether any usable public setter exists for the internal schedule parameters.
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
- [ ] **H06 · Static/Hardware:** Establish current/voltage calibration, fitted battery
  arrangement and hardware measurement accuracy separately from software labels.
- [ ] **H07 · Static:** Resolve descriptor build timezone if supporting provenance
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
| [Boot and scheduling](boot-and-scheduling.md) | S01–S07, C04/C11, R10/R12 |
| [Storage and configuration](storage-and-configuration.md) | N01–N08, R04/R06, H06 |
| [OTA and recovery](ota-and-recovery.md) | R01–R12, B02 |
| [Local API](local-api.md) | C12, H05, D01/D02/D04/D07, A05/A06 |
| [Rendering and concurrency](rendering-and-concurrency.md) | D01–D08, N05, B03 |
| [HA roadmap](home-assistant-roadmap.md) | A01–A07, C01–C12, S07, D05/D07 |
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
